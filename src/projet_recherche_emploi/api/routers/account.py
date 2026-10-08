from fastapi import APIRouter, Request, Response, status

from projet_recherche_emploi.api.security import (
    CredentialsCaller,
    Services,
    UserId,
    clear_session_cookie,
    set_session_cookie,
)
from projet_recherche_emploi.config import CONTRACT_TYPES, DEFAULT_USER_ID, MAX_SEARCHES_PER_DAY
from projet_recherche_emploi.container import Container
from projet_recherche_emploi.schemas import Account, AppConfig

router = APIRouter(tags=["compte"])


@router.get("/config")
def get_config(services: Services) -> AppConfig:
    """Ce que le front lit avant la connexion : comment se connecter, et les choix de ses formulaires."""
    return AppConfig(
        login_mode=services.auth.login_mode,
        google_client_id=services.settings.google_client_id or None,
        contract_types=CONTRACT_TYPES,
    )


@router.get("/me")
def get_account(user_id: UserId, services: Services) -> Account:
    return _account(user_id, services)


@router.post("/session")
def open_session(caller: CredentialsCaller, services: Services, request: Request, response: Response) -> Account:
    """Échange un jeton d'identité Google (ou le mot de passe de l'instance) contre un cookie de session."""
    set_session_cookie(request, response, services.auth.create_session_token(caller.email))
    return _account(caller.user_id, services)


@router.delete("/session", status_code=status.HTTP_204_NO_CONTENT)
def close_session(request: Request, response: Response) -> None:
    # Sans contrôle d'identité : on doit pouvoir se déconnecter même avec une session expirée
    clear_session_cookie(request, response)


def _account(user_id: int, services: Container) -> Account:
    return Account(
        user_id=user_id,
        is_owner=user_id == DEFAULT_USER_ID,
        can_search=services.search.can_search(user_id),
        remaining_searches=services.search.remaining_searches(user_id),
        max_searches_per_day=MAX_SEARCHES_PER_DAY,
    )
