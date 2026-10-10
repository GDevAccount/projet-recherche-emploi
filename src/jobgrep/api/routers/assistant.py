from fastapi import APIRouter

from jobgrep.api.security import Services, UserId
from jobgrep.schemas import AssistantConversation, AssistantQuestion, AssistantReply

router = APIRouter(tags=["assistant"])


@router.get("/assistant")
def get_conversation(user_id: UserId, services: Services) -> AssistantConversation:
    """Derniers échanges de l'appelant avec l'assistant, et le nombre de questions qu'il peut encore poser."""
    return services.assistant.get_conversation(user_id)


@router.post("/assistant/questions")
def ask(user_id: UserId, question: AssistantQuestion, services: Services) -> AssistantReply:
    """Pose une question sur l'application. La réponse ne vient que des textes du site, qu'elle cite.

    Une question hors sujet reçoit un refus, et compte comme une autre. Refusée (429) une fois le quota du
    jour atteint, ou le budget du jour de l'instance.
    """
    return services.assistant.ask(user_id, question.question)
