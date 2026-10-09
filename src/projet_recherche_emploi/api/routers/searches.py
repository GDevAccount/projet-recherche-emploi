import logging
import queue
import threading
from collections.abc import Iterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from projet_recherche_emploi.api.security import Services, UserId
from projet_recherche_emploi.schemas import PageEvaluationRead, SearchProgress, SearchRunRead, SearchSummary

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
    return StreamingResponse(_to_server_sent_events(_run_detached(events)), media_type="text/event-stream")


@router.get("/searches")
def list_searches(user_id: UserId, services: Services) -> list[SearchRunRead]:
    """Derniers lancements de l'utilisateur, avec leur bilan : compteurs, durées par étape, appels et jetons."""
    return services.search.list_runs(user_id)


@router.get("/searches/{run_id}/evaluations")
def list_evaluations(run_id: int, user_id: UserId, services: Services) -> list[PageEvaluationRead]:
    """Pages évaluées pendant un lancement, retenues ou non : faits lus, verdict, jetons et durée de l'appel."""
    return services.search.list_evaluations(user_id, run_id)


def _run_detached(events: Iterator[SearchEvent]) -> Iterator[SearchEvent | Exception]:
    # La recherche tourne dans son propre fil : si le navigateur ferme la connexion, elle va quand même
    # au bout, et les pages déjà payées chez Tavily et OpenAI sont enregistrées.
    done = object()
    results: queue.Queue = queue.Queue()

    def work() -> None:
        try:
            for event in events:
                results.put(event)
        except Exception as error:
            logger.exception("La recherche a échoué")
            results.put(error)
        finally:
            results.put(done)

    threading.Thread(target=work, daemon=True).start()
    while (item := results.get()) is not done:
        yield item


def _to_server_sent_events(events: Iterator[SearchEvent | Exception]) -> Iterator[str]:
    for event in events:
        if isinstance(event, Exception):
            # Le détail est dans les logs : il peut contenir une réponse brute de Tavily ou d'OpenAI
            yield _server_sent_event("error", '{"detail": "La recherche a échoué."}')
        else:
            name = "result" if isinstance(event, SearchSummary) else "progress"
            yield _server_sent_event(name, event.model_dump_json())


def _server_sent_event(name: str, data: str) -> str:
    return f"event: {name}\ndata: {data}\n\n"
