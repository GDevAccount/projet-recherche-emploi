import threading
from collections.abc import Callable, Iterable, Iterator
from datetime import UTC, datetime
from typing import Protocol
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from projet_recherche_emploi.config import DEFAULT_USER_ID, LOCAL_TIMEZONE, MAX_SEARCHES_PER_DAY, OFFER_PAGE_KIND
from projet_recherche_emploi.data.database import Database
from projet_recherche_emploi.data.models import Correction
from projet_recherche_emploi.data.repositories.correction_repository import CorrectionRepository
from projet_recherche_emploi.data.repositories.cv_text_repository import CvTextRepository
from projet_recherche_emploi.data.repositories.page_evaluation_repository import PageEvaluationRepository
from projet_recherche_emploi.data.repositories.query_repository import QueryRepository
from projet_recherche_emploi.data.repositories.search_run_repository import SearchRunRepository
from projet_recherche_emploi.errors import ConflictError, InvalidInputError, NotFoundError, QuotaExceededError
from projet_recherche_emploi.schemas import (
    DELETE_REASON_NOT_GIVEN,
    DELETE_REASONS,
    DELETE_REASONS_WITHOUT_ERROR,
    CorrectionStats,
    EvaluationGroup,
    PageEvaluationRead,
    ReasonCount,
    SearchProgress,
    SearchRunRead,
    SearchStats,
    SearchSummary,
)
from projet_recherche_emploi.services.search_costs import (
    COST_DECIMALS,
    model_cost_usd,
    search_cost_usd,
    sum_costs,
    total_cost_usd,
)

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
    "cache_read_tokens",
    "cache_write_tokens",
    "reasoning_tokens",
)
# Étapes du graph dont les durées, réunies, font celle d'une recherche
STEP_DURATIONS = ("search_ms", "dedupe_ms", "evaluate_ms", "save_ms")
# Libellés des groupes de la synthèse selon le texte lu par le modèle
TEXT_FULL = "Page entière"
TEXT_TRUNCATED = "Page tronquée"
TEXT_EXTRACT = "Extrait seul"
UNKNOWN_LABEL = "Non précisé"
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


def site_of(url: str) -> str:
    """Renvoie le site d'une page : son nom de domaine, sans « www. »."""
    return (urlsplit(url).hostname or UNKNOWN_LABEL).removeprefix("www.")


def text_read(evaluation: PageEvaluationRead) -> str:
    """Dit quel texte le modèle a lu pour cette page."""
    if not evaluation.full_page:
        return TEXT_EXTRACT
    return TEXT_TRUNCATED if evaluation.truncated else TEXT_FULL


def price_run(run: SearchRunRead) -> SearchRunRead:
    """Complète un lancement par sa durée et ses coûts."""
    steps = [getattr(run, step) for step in STEP_DURATIONS]
    run.duration_ms = None if all(step is None for step in steps) else sum(step or 0 for step in steps)
    run.search_cost_usd = search_cost_usd(run.search_calls)
    run.model_cost_usd = model_cost_usd(
        run.model, run.input_tokens, run.output_tokens, run.cache_read_tokens, run.cache_write_tokens
    )
    run.cost_usd = total_cost_usd(run.search_cost_usd, run.model_cost_usd, run.input_tokens is not None)
    return run


def price_evaluation(evaluation: PageEvaluationRead, model: str | None) -> PageEvaluationRead:
    """Complète une page évaluée par le coût de son appel au modèle, qui est celui de son lancement."""
    evaluation.model_cost_usd = model_cost_usd(
        model,
        evaluation.input_tokens,
        evaluation.output_tokens,
        evaluation.cache_read_tokens,
        evaluation.cache_write_tokens,
    )
    return evaluation


def group_evaluations(
    evaluations: Iterable[PageEvaluationRead], label_of: Callable[[PageEvaluationRead], str | None]
) -> list[EvaluationGroup]:
    """Regroupe des pages évaluées selon un trait, le groupe le plus fourni en premier."""
    groups: dict[str, list[PageEvaluationRead]] = {}
    for evaluation in evaluations:
        groups.setdefault(label_of(evaluation) or UNKNOWN_LABEL, []).append(evaluation)
    summaries = [
        EvaluationGroup(
            label=label,
            evaluated=len(pages),
            kept=sum(page.kept for page in pages),
            not_an_offer=sum(not page.kept and page.page_kind != OFFER_PAGE_KIND for page in pages),
            rejected_offers=sum(not page.kept and page.page_kind == OFFER_PAGE_KIND for page in pages),
            input_tokens=sum(page.input_tokens or 0 for page in pages),
            output_tokens=sum(page.output_tokens or 0 for page in pages),
            # Une page sans jetons connus n'a rien coûté qu'on puisse compter : seul un tarif manquant rend None
            model_cost_usd=sum_costs(page.model_cost_usd for page in pages if page.input_tokens is not None),
        )
        for label, pages in groups.items()
    ]
    return sorted(summaries, key=lambda group: (-group.evaluated, group.label))


def rate(part: int, whole: int) -> float | None:
    """Renvoie la part d'un ensemble, ou None s'il est vide."""
    return round(part / whole, 4) if whole else None


def summarize_corrections(
    corrections: list[Correction], evaluations: Iterable[PageEvaluationRead], runs: Iterable[SearchRunRead]
) -> list[CorrectionStats]:
    """Compte les corrections par version du prompt, la plus récente en premier."""
    # Les lancements arrivent du plus récent au plus ancien : l'ordre des versions est celui de leur dernier usage
    versions = {run.id: run.prompt_version for run in runs}
    order = list(dict.fromkeys(versions.values()))
    judged: dict[str | None, list[bool]] = {}
    for evaluation in evaluations:
        judged.setdefault(versions.get(evaluation.search_run_id), []).append(evaluation.kept)
    corrected: dict[str | None, list[Correction]] = {}
    for correction in corrections:
        corrected.setdefault(correction.prompt_version, []).append(correction)

    stats = []
    for version in [*order, *(version for version in corrected if version not in order)]:
        if version not in corrected:
            continue
        verdicts = judged.get(version, [])
        deleted = [correction for correction in corrected[version] if correction.kind == "deleted"]
        wrongly_kept = sum(
            correction.reason is not None and correction.reason not in DELETE_REASONS_WITHOUT_ERROR
            for correction in deleted
        )
        restored = len(corrected[version]) - len(deleted)
        kept = sum(verdicts)
        stats.append(
            CorrectionStats(
                prompt_version=version,
                evaluated=len(verdicts),
                kept=kept,
                rejected=len(verdicts) - kept,
                restored=restored,
                wrongly_kept=wrongly_kept,
                other_deleted=len(deleted) - wrongly_kept,
                restored_rate=rate(restored, len(verdicts) - kept),
                wrongly_kept_rate=rate(wrongly_kept, kept),
            )
        )
    return stats


def count_delete_reasons(corrections: Iterable[Correction]) -> list[ReasonCount]:
    """Compte les suppressions d'offres par motif, le plus fréquent en premier."""
    counts: dict[str, int] = {}
    for correction in corrections:
        if correction.kind == "deleted":
            label = DELETE_REASONS.get(correction.reason, DELETE_REASON_NOT_GIVEN)
            counts[label] = counts.get(label, 0) + 1
    return [ReasonCount(label=label, count=count) for label, count in sorted(counts.items(), key=lambda item: -item[1])]


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
        return self._describe_runs(user_id, runs)

    def _describe_runs(self, user_id: int, runs: list[SearchRunRead]) -> list[SearchRunRead]:
        # Seul le dernier lancement peut encore tourner : un autre resté « en cours » a été coupé par un redémarrage
        running_id = runs[0].id if runs and self.is_running(user_id) else None
        for run in runs:
            if run.status == "running" and run.id != running_id:
                run.status = "interrupted"
            price_run(run)
        return runs

    def list_evaluations(self, user_id: int, run_id: int) -> list[PageEvaluationRead]:
        """Renvoie les pages évaluées pendant ce lancement, retenues ou non."""
        with self.database.session() as session:
            run = SearchRunRepository(session, user_id).get_run(run_id)
            if run is None:
                raise NotFoundError("Cette recherche n'existe pas.")
            rows = PageEvaluationRepository(session, user_id).list_for_run(run_id)
            return [price_evaluation(PageEvaluationRead.model_validate(row), run.model) for row in rows]

    def get_stats(self, user_id: int) -> SearchStats:
        """Renvoie la synthèse de toutes les recherches suivies de l'utilisateur : volumes, coûts, répartitions."""
        with self.database.session() as session:
            run_rows = SearchRunRepository(session, user_id).list_runs()
            runs = [SearchRunRead.model_validate(row) for row in run_rows]
            evaluation_rows = PageEvaluationRepository(session, user_id).list_all()
            evaluations = [PageEvaluationRead.model_validate(row) for row in evaluation_rows]
            corrections = CorrectionRepository(session, user_id).list_all()
            # Lus tant que la session est ouverte : la synthèse n'en garde que des nombres
            correction_stats = summarize_corrections(corrections, evaluations, runs)
            delete_reasons = count_delete_reasons(corrections)
        # Un lancement d'avant le suivi n'a que sa date : il n'entre pas dans la synthèse
        runs = [run for run in self._describe_runs(user_id, runs) if run.status is not None]
        models = {run.id: run.model for run in runs}
        for evaluation in evaluations:
            price_evaluation(evaluation, models.get(evaluation.search_run_id))

        def total(name: str) -> int:
            return sum(getattr(run, name) or 0 for run in runs)

        done = [run for run in runs if run.status == "done"]
        durations = [run.duration_ms or 0 for run in done]
        model_cost = sum_costs(run.model_cost_usd for run in runs if run.input_tokens is not None)
        search_cost = round(sum(run.search_cost_usd or 0 for run in runs), COST_DECIMALS)
        cost = None if model_cost is None else round(search_cost + model_cost, COST_DECIMALS)
        kept = total("kept_count")
        return SearchStats(
            runs=len(runs),
            unfinished_runs=len(runs) - len(done),
            found_count=total("found_count"),
            new_count=total("new_count"),
            kept_count=kept,
            rejected_count=total("rejected_count"),
            search_calls=total("search_calls"),
            input_tokens=total("input_tokens"),
            output_tokens=total("output_tokens"),
            cache_read_tokens=total("cache_read_tokens"),
            reasoning_tokens=total("reasoning_tokens"),
            search_cost_usd=search_cost,
            model_cost_usd=model_cost,
            cost_usd=cost,
            cost_per_kept_usd=round(cost / kept, COST_DECIMALS) if cost is not None and kept else None,
            average_duration_ms=round(sum(durations) / len(durations)) if durations else None,
            by_query=group_evaluations(evaluations, lambda page: page.query),
            by_site=group_evaluations(evaluations, lambda page: site_of(page.url)),
            by_page_kind=group_evaluations(evaluations, lambda page: page.page_kind),
            by_text=group_evaluations(evaluations, text_read),
            corrections=correction_stats,
            delete_reasons=delete_reasons,
        )

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
