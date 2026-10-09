import threading
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from typing import Protocol
from zoneinfo import ZoneInfo

from projet_recherche_emploi.config import DEFAULT_USER_ID, LOCAL_TIMEZONE, MAX_SEARCHES_PER_DAY
from projet_recherche_emploi.data.database import Database
from projet_recherche_emploi.data.repositories.cv_text_repository import CvTextRepository
from projet_recherche_emploi.data.repositories.page_evaluation_repository import PageEvaluationRepository
from projet_recherche_emploi.data.repositories.query_repository import QueryRepository
from projet_recherche_emploi.data.repositories.search_run_repository import SearchRunRepository
from projet_recherche_emploi.errors import ConflictError, InvalidInputError, NotFoundError, QuotaExceededError
from projet_recherche_emploi.schemas import PageEvaluationRead, SearchProgress, SearchRunRead, SearchSummary

# Nombre de lancements renvoyés par list_runs
RUN_HISTORY_SIZE = 100
# Mesures que les nœuds du graph laissent dans son état (« metrics »), recopiées telles quelles dans le lancement
RUN_METRICS = (
    "model",
    "prompt_version",
    "search_ms",
    "dedupe_ms",
    "evaluate_ms",
    "save_ms",
    "search_calls",
    "input_tokens",
    "output_tokens",
)
# Listes de l'état du graph dont la longueur donne un compteur du lancement
RUN_COUNTS = {
    "found_count": "jobs",
    "new_count": "new_jobs",
    "kept_count": "filtered_jobs",
    "rejected_count": "rejected_jobs",
}


class SearchGraph(Protocol):
    def stream(self, state: dict, *, stream_mode: list[str]) -> Iterator[tuple[str, dict]]: ...


def start_of_local_day() -> datetime:
    """Renvoie minuit du jour en cours à Paris."""
    return datetime.now(ZoneInfo(LOCAL_TIMEZONE)).replace(hour=0, minute=0, second=0, microsecond=0)


class RunningSearch:
    """Déroulement d'une recherche, qui libère sa place dès qu'il s'arrête : fin, échec ou abandon avant lecture."""

    def __init__(self, events: Iterator[SearchProgress | SearchSummary], release: Callable[[], None]):
        self._events = events
        self._release = release

    def __iter__(self) -> "RunningSearch":
        return self

    def __next__(self) -> SearchProgress | SearchSummary:
        try:
            return next(self._events)
        except BaseException:
            # Fin normale (StopIteration) comprise
            self._release()
            raise

    def __del__(self) -> None:
        # Un déroulement jamais lu ne doit pas bloquer les recherches suivantes de l'utilisateur
        self._release()


class SearchService:
    def __init__(self, database: Database, get_graph: Callable[[], SearchGraph]):
        self.database = database
        # Le graph n'est construit qu'à la première recherche
        self._get_graph = get_graph
        # Utilisateurs dont une recherche tourne. En mémoire : un redémarrage interrompt les recherches, et vide ceci
        self._running: set[int] = set()
        self._running_lock = threading.Lock()

    def is_running(self, user_id: int) -> bool:
        """Dit si une recherche de l'utilisateur est en cours."""
        with self._running_lock:
            return user_id in self._running

    def remaining_searches(self, user_id: int) -> int | None:
        """Renvoie le nombre de recherches encore permises aujourd'hui, ou None si l'utilisateur n'est pas limité."""
        # Le propriétaire paie les clés API : le quota ne protège que des recherches des invités
        if user_id == DEFAULT_USER_ID:
            return None
        with self.database.session() as session:
            used = SearchRunRepository(session, user_id).count_runs_since(start_of_local_day())
        return max(0, MAX_SEARCHES_PER_DAY - used)

    def can_search(self, user_id: int) -> bool:
        """Dit si l'utilisateur a ce qu'il faut pour lancer une recherche : un CV et au moins un poste recherché."""
        with self.database.session() as session:
            has_queries = bool(QueryRepository(session, user_id).list_queries())
            has_cv = CvTextRepository(session, user_id).get_updated_at() is not None
        return has_queries and has_cv

    def stream_search(self, user_id: int) -> Iterator[SearchProgress | SearchSummary]:
        """Lance la recherche de l'utilisateur et renvoie son déroulement : l'avancement, puis le bilan.

        Le refus (rien à chercher, recherche déjà en cours, quota atteint) est levé ici, avant le premier élément.
        """
        if not self.can_search(user_id):
            raise InvalidInputError("Il faut un CV et au moins une recherche enregistrée pour lancer une recherche.")

        # Une seule recherche à la fois par utilisateur : la seconde paierait les mêmes pages, et compterait au quota
        with self._running_lock:
            if user_id in self._running:
                raise ConflictError("Une recherche est déjà en cours : attendez qu'elle se termine.")
            self._running.add(user_id)

        try:
            # Le lancement est compté avant la recherche : même en échec, elle a pu consommer des crédits
            limit = None if user_id == DEFAULT_USER_ID else MAX_SEARCHES_PER_DAY
            with self.database.session() as session:
                run_id = SearchRunRepository(session, user_id).record_run(start_of_local_day(), limit)
            if run_id is None:
                raise QuotaExceededError("Quota de recherches atteint pour aujourd'hui.")
        except BaseException:
            self._release(user_id)
            raise

        return RunningSearch(self._stream(user_id, run_id), lambda: self._release(user_id))

    def _release(self, user_id: int) -> None:
        with self._running_lock:
            self._running.discard(user_id)

    def run_search(
        self, user_id: int, on_progress: Callable[[SearchProgress], None] | None = None
    ) -> SearchSummary:
        """Lance la recherche de l'utilisateur, signale son avancement à on_progress et renvoie son bilan."""
        summary = None
        for event in self.stream_search(user_id):
            if isinstance(event, SearchSummary):
                summary = event
            elif on_progress:
                on_progress(event)
        return summary

    def list_runs(self, user_id: int) -> list[SearchRunRead]:
        """Renvoie les derniers lancements de l'utilisateur avec leur bilan, le plus récent en premier."""
        with self.database.session() as session:
            rows = SearchRunRepository(session, user_id).list_runs(RUN_HISTORY_SIZE)
            runs = [SearchRunRead.model_validate(row) for row in rows]
        # Seul le dernier lancement peut encore tourner : un autre resté « en cours » a été coupé par un redémarrage
        running_id = runs[0].id if runs and self.is_running(user_id) else None
        for run in runs:
            if run.status == "running" and run.id != running_id:
                run.status = "interrupted"
        return runs

    def list_evaluations(self, user_id: int, run_id: int) -> list[PageEvaluationRead]:
        """Renvoie les pages évaluées pendant ce lancement, retenues ou non."""
        with self.database.session() as session:
            if SearchRunRepository(session, user_id).get_run(run_id) is None:
                raise NotFoundError("Cette recherche n'existe pas.")
            rows = PageEvaluationRepository(session, user_id).list_for_run(run_id)
            return [PageEvaluationRead.model_validate(row) for row in rows]

    def _stream(self, user_id: int, run_id: int) -> Iterator[SearchProgress | SearchSummary]:
        state = {}
        try:
            # Le mode « custom » remonte l'avancement écrit par les nœuds, « values » l'état du graph
            events = self._get_graph().stream(
                {"user_id": user_id, "run_id": run_id}, stream_mode=["custom", "values"]
            )
            for mode, chunk in events:
                if mode == "values":
                    state = chunk
                else:
                    yield SearchProgress(**chunk)
        except Exception as error:
            # Le type seul : le message peut contenir une réponse brute de Tavily ou d'OpenAI
            self._close_run(user_id, run_id, state, "failed", type(error).__name__)
            raise
        self._close_run(user_id, run_id, state, "done")
        yield SearchSummary(
            found=len(state.get("jobs", [])),
            new=len(state.get("new_jobs", [])),
            kept=len(state.get("filtered_jobs", [])),
            rejected=len(state.get("rejected_jobs", [])),
            inserted=state.get("inserted_count", 0),
        )

    def _close_run(self, user_id: int, run_id: int, state: dict, status: str, error: str | None = None) -> None:
        """Écrit le bilan du lancement à partir du dernier état connu du graph : une étape non franchie reste vide."""
        metrics = state.get("metrics", {})
        values = {
            "status": status,
            "error": error,
            "finished_at": datetime.now(UTC),
            "inserted_count": state.get("inserted_count"),
            **{column: len(state[key]) if key in state else None for column, key in RUN_COUNTS.items()},
            **{name: metrics.get(name) for name in RUN_METRICS},
        }
        with self.database.session() as session:
            SearchRunRepository(session, user_id).finish_run(run_id, values)
