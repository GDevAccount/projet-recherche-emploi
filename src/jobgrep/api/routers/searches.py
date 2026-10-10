import logging
from collections.abc import Iterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from jobgrep.api.security import AdminId, Services, UserId
from jobgrep.api.streaming import run_detached, server_sent_event
from jobgrep.schemas import (
    PageEvaluationRead,
    SearchProgress,
    SearchRunRead,
    SearchStats,
    SearchSummary,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["recherche"])

SearchEvent = SearchProgress | SearchSummary


@router.post(
    "/searches",
    response_class=StreamingResponse,
    responses={200: {"content": {"text/event-stream": {}}}},
)
def start_search(user_id: UserId, services: Services) -> StreamingResponse:
    """Lance une recherche et la suit en direct (Server-Sent Events).

    Événements « progress » (SearchProgress) pendant la recherche, puis un seul « result » (SearchSummary),
    ou « error » si elle échoue. Un refus (quota, CV manquant) est une réponse d'erreur ordinaire, sans flux.
    """
    events = services.search.stream_search(user_id)
    return StreamingResponse(_to_server_sent_events(run_detached(events)), media_type="text/event-stream")


@router.get("/searches")
def list_searches(user_id: AdminId, services: Services) -> list[SearchRunRead]:
    """Derniers lancements de l'appelant, avec leur bilan : compteurs, durées par étape, appels, jetons, coûts.

    Réservé aux administrateurs (403 pour un invité), comme les deux routes suivantes.
    """
    return services.search.list_runs(user_id)


@router.get("/searches/stats")
def get_search_stats(user_id: AdminId, services: Services) -> SearchStats:
    """Synthèse de toutes les recherches suivies : volumes, coûts, et répartition des pages évaluées."""
    return services.search.get_stats(user_id)


@router.get("/searches/{run_id}/evaluations")
def list_evaluations(run_id: int, user_id: AdminId, services: Services) -> list[PageEvaluationRead]:
    """Pages évaluées pendant un lancement, retenues ou non : faits lus, verdict, jetons et durée de l'appel."""
    return services.search.list_evaluations(user_id, run_id)


def _to_server_sent_events(events: Iterator[SearchEvent | Exception]) -> Iterator[str]:
    for event in events:
        if isinstance(event, Exception):
            logger.error("La recherche a échoué", exc_info=event)
            # Le détail est dans les logs : il peut contenir une réponse brute de Tavily ou d'OpenAI
            yield server_sent_event("error", '{"detail": "La recherche a échoué."}')
        else:
            name = "result" if isinstance(event, SearchSummary) else "progress"
            yield server_sent_event(name, event.model_dump_json())
