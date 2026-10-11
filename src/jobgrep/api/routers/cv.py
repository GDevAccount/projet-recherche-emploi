import json
from collections.abc import Iterator
from typing import Annotated

from fastapi import APIRouter, Form, Request, UploadFile, status
from fastapi.responses import StreamingResponse

from jobgrep.api.security import CurrentCaller, Services, UserId
from jobgrep.api.streaming import run_detached, server_sent_event
from jobgrep.container import Container
from jobgrep.errors import AppError, InvalidInputError
from jobgrep.schemas import CvDeposit, CvProgress, CvStatus
from jobgrep.services.cv_service import MAX_CV_BYTES

router = APIRouter(tags=["CV"])

FAILURE_MESSAGE = "Le CV n'a pas pu être enregistré. Réessayez dans un moment."
# Remplacer les postes recherchés par ceux tirés du CV : sans effet pour qui n'en a aucun, ils sont alors créés
ReplaceQueries = Annotated[bool, Form()]


@router.get("/cv")
def get_cv_status(user_id: UserId, services: Services) -> CvStatus:
    return services.cv.get_status(user_id)


@router.put("/cv")
def save_cv(
    file: UploadFile, caller: CurrentCaller, services: Services, replace_queries: ReplaceQueries = False
) -> CvDeposit:
    """Dépose un CV (PDF), et en tire les postes recherchés de qui n'en a pas, ou demande à les remplacer."""
    # Un octet de plus que la limite suffit au service pour refuser, sans lire un fichier énorme en entier
    return services.cv.save_cv(caller.user_id, file.file.read(MAX_CV_BYTES + 1), _names(caller), replace_queries)


@router.post(
    "/cv/stream",
    response_class=StreamingResponse,
    responses={200: {"content": {"text/event-stream": {}}}},
)
def save_cv_and_follow(
    file: UploadFile,
    caller: CurrentCaller,
    services: Services,
    request: Request,
    replace_queries: ReplaceQueries = False,
) -> StreamingResponse:
    """Dépose un CV et suit son traitement étape par étape (Server-Sent Events).

    Événements « progress » (CvProgress) à chaque étape, puis un seul « result » (CvDeposit), ou « error » si
    le fichier n'est pas un PDF lisible. Un fichier trop gros est une réponse d'erreur ordinaire, sans flux.
    """
    data = file.file.read(MAX_CV_BYTES + 1)
    events = services.cv.stream_deposit(caller.user_id, data, _names(caller), replace_queries)
    route = request.url.path
    return StreamingResponse(
        _to_server_sent_events(run_detached(events), services, caller.user_id, route),
        media_type="text/event-stream",
    )


def _names(caller) -> list[str]:
    # Le nom du compte Google ne se reconnaît pas à sa forme : il est donné pour être retiré du texte du CV
    return [caller.name] if caller.name else []


def _to_server_sent_events(
    events: Iterator[CvProgress | CvDeposit | Exception], services: Container, user_id: int, route: str
) -> Iterator[str]:
    for event in events:
        if isinstance(event, Exception):
            # La réponse est déjà partie : l'erreur ne passe plus par le serveur, qui l'aurait enregistrée.
            # Un fichier refusé n'est pas une panne
            refused = isinstance(event, InvalidInputError)
            code = status.HTTP_422_UNPROCESSABLE_CONTENT if refused else status.HTTP_500_INTERNAL_SERVER_ERROR
            services.health.record_error(user_id, "POST", route, code, type(event).__name__)
            # Le message d'une erreur prévue est écrit pour l'utilisateur ; celui d'une autre ne sort pas
            detail = str(event) if isinstance(event, AppError) else FAILURE_MESSAGE
            yield server_sent_event("error", json.dumps({"detail": detail}))
        else:
            name = "result" if isinstance(event, CvDeposit) else "progress"
            yield server_sent_event(name, event.model_dump_json())
