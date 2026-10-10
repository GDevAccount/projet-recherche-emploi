import json
from collections.abc import Iterator

from fastapi import APIRouter, Request, status
from fastapi.responses import StreamingResponse

from jobgrep.api.security import Services, UserId
from jobgrep.api.streaming import run_detached, server_sent_event
from jobgrep.container import Container
from jobgrep.errors import AppError
from jobgrep.schemas import (
    AssistantConversation,
    AssistantFeedbackUpdate,
    AssistantProgress,
    AssistantQuestion,
    AssistantReply,
)

router = APIRouter(tags=["assistant"])

STREAM_PATH = "/assistant/questions/stream"
FAILURE_MESSAGE = "L'assistant ne répond pas pour l'instant. Réessayez dans un moment."


@router.get("/assistant")
def get_conversation(user_id: UserId, services: Services) -> AssistantConversation:
    """Conversation en cours de l'appelant avec l'assistant, et le nombre de questions qu'il peut encore poser."""
    return services.assistant.get_conversation(user_id)


@router.post("/assistant/questions")
def ask(user_id: UserId, question: AssistantQuestion, services: Services) -> AssistantReply:
    """Pose une question sur l'application. La réponse ne vient que des textes du site, qu'elle cite.

    Une question hors sujet reçoit un refus, et compte comme une autre. Refusée (429) une fois le quota du
    jour atteint, ou le budget du jour de l'instance.
    """
    return services.assistant.ask(user_id, question.question, new_conversation=question.new_conversation)


@router.post(
    STREAM_PATH,
    response_class=StreamingResponse,
    responses={200: {"content": {"text/event-stream": {}}}},
)
def ask_and_follow(
    user_id: UserId, question: AssistantQuestion, services: Services, request: Request
) -> StreamingResponse:
    """Pose une question et suit la réponse à mesure qu'elle s'écrit (Server-Sent Events).

    Événements « progress » (AssistantProgress) pendant la réponse, puis un seul « result » (AssistantReply),
    ou « error » si l'assistant ne répond pas. Un refus (quota, budget, question vide) est une réponse
    d'erreur ordinaire, sans flux.
    """
    events = services.assistant.stream_answer(user_id, question.question, new_conversation=question.new_conversation)
    route = request.url.path
    return StreamingResponse(
        _to_server_sent_events(run_detached(events), services, user_id, route), media_type="text/event-stream"
    )


@router.put("/assistant/messages/{message_id}/feedback", status_code=status.HTTP_204_NO_CONTENT)
def set_feedback(message_id: int, update: AssistantFeedbackUpdate, user_id: UserId, services: Services) -> None:
    """Note une réponse de l'assistant, utile (« up ») ou non (« down »), ou retire la note (null)."""
    services.assistant.set_feedback(user_id, message_id, update.feedback)


def _to_server_sent_events(
    events: Iterator[AssistantProgress | AssistantReply | Exception], services: Container, user_id: int, route: str
) -> Iterator[str]:
    for event in events:
        if isinstance(event, Exception):
            # La réponse est déjà partie : l'erreur ne passe plus par le serveur, qui l'aurait enregistrée
            services.health.record_error(
                user_id, "POST", route, status.HTTP_503_SERVICE_UNAVAILABLE, type(event).__name__
            )
            # Le message d'une erreur prévue est écrit pour l'utilisateur ; celui d'une autre ne sort pas
            detail = str(event) if isinstance(event, AppError) else FAILURE_MESSAGE
            yield server_sent_event("error", json.dumps({"detail": detail}))
        else:
            name = "result" if isinstance(event, AssistantReply) else "progress"
            yield server_sent_event(name, event.model_dump_json())
