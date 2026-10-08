import threading
from collections.abc import Callable, Iterator
from datetime import datetime
from typing import Protocol
from zoneinfo import ZoneInfo

from projet_recherche_emploi.config import DEFAULT_USER_ID, LOCAL_TIMEZONE, MAX_SEARCHES_PER_DAY
from projet_recherche_emploi.data.cv_storage import CvStorage
from projet_recherche_emploi.data.database import Database
from projet_recherche_emploi.data.query_repository import QueryRepository
from projet_recherche_emploi.data.search_run_repository import SearchRunRepository
from projet_recherche_emploi.errors import InvalidInputError, QuotaExceededError
from projet_recherche_emploi.schemas import SearchProgress, SearchSummary


class SearchGraph(Protocol):
    def stream(self, state: dict, *, stream_mode: list[str]) -> Iterator[tuple[str, dict]]: ...


def start_of_local_day() -> datetime:
    """Renvoie minuit du jour en cours à Paris."""
    return datetime.now(ZoneInfo(LOCAL_TIMEZONE)).replace(hour=0, minute=0, second=0, microsecond=0)


class SearchService:
    def __init__(self, database: Database, cv_storage: CvStorage, get_graph: Callable[[], SearchGraph]):
        self.database = database
        self.cv_storage = cv_storage
        # Le graph n'est construit qu'à la première recherche
        self._get_graph = get_graph
        # Utilisateurs dont une recherche tourne dans ce processus
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
        return has_queries and self.cv_storage.updated_at(user_id) is not None

    def stream_search(self, user_id: int) -> Iterator[SearchProgress | SearchSummary]:
        """Lance la recherche de l'utilisateur et renvoie son déroulement : l'avancement, puis le bilan.

        Le refus (rien à chercher, quota atteint) est levé ici, avant le premier élément.
        """
        if not self.can_search(user_id):
            raise InvalidInputError("Il faut un CV et au moins une recherche enregistrée pour lancer une recherche.")

        # Le lancement est compté avant la recherche : même en échec, elle a pu consommer des crédits
        limit = None if user_id == DEFAULT_USER_ID else MAX_SEARCHES_PER_DAY
        with self.database.session() as session:
            if not SearchRunRepository(session, user_id).record_run(start_of_local_day(), limit):
                raise QuotaExceededError("Quota de recherches atteint pour aujourd'hui.")

        return self._stream(user_id)

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

    def _stream(self, user_id: int) -> Iterator[SearchProgress | SearchSummary]:
        state = {}
        with self._running_lock:
            self._running.add(user_id)
        try:
            # Le mode « custom » remonte l'avancement écrit par les nœuds, « values » l'état du graph
            for mode, chunk in self._get_graph().stream({"user_id": user_id}, stream_mode=["custom", "values"]):
                if mode == "values":
                    state = chunk
                else:
                    yield SearchProgress(**chunk)
        finally:
            with self._running_lock:
                self._running.discard(user_id)
        yield SearchSummary(
            found=len(state.get("jobs", [])),
            new=len(state.get("new_jobs", [])),
            kept=len(state.get("filtered_jobs", [])),
            rejected=len(state.get("rejected_jobs", [])),
            inserted=state.get("inserted_count", 0),
        )
