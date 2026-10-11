from dataclasses import replace

from fastapi import APIRouter, Request, Response, status

from jobgrep.api.security import (
    Caller,
    CredentialsCaller,
    CurrentCaller,
    Services,
    SessionToken,
    TrialOpening,
    UserId,
    check_origin,
    clear_session_cookie,
    set_session_cookie,
)
from jobgrep.config import CONTRACT_TYPES, DEFAULT_USER_ID, MAX_SEARCHES_PER_DAY, MAX_SKILLS_PER_QUERY
from jobgrep.container import Container
from jobgrep.schemas import (
    DELETE_REASONS,
    Account,
    AppConfig,
    ClientErrorReport,
    DeleteReasonOption,
)

router = APIRouter(tags=["compte"])


@router.get("/config")
def get_config(services: Services) -> AppConfig:
    """Ce que le front lit avant la connexion : comment se connecter, et les choix de ses formulaires."""
    return AppConfig(
        login_mode=services.auth.login_mode,
        google_client_id=services.settings.google_client_id or None,
        trial=services.auth.trial_status(),
        contract_types=CONTRACT_TYPES,
        max_skills_per_query=MAX_SKILLS_PER_QUERY,
        delete_reasons=[DeleteReasonOption(code=code, label=label) for code, label in DELETE_REASONS.items()],
    )


@router.get("/me")
def get_account(caller: CurrentCaller, services: Services) -> Account:
    return _account(caller, services)


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(caller: CurrentCaller, services: Services, request: Request, response: Response) -> None:
    """Efface le compte de l'appelant et tout ce qu'il contient, puis ferme sa session."""
    services.account.delete_account(caller.user_id)
    clear_session_cookie(request, response)


@router.post("/session")
def open_session(
    caller: CredentialsCaller,
    services: Services,
    request: Request,
    response: Response,
    session_token: SessionToken,
) -> Account:
    """Échange un jeton d'identité Google (ou le mot de passe de l'instance) contre un cookie de session.

    Qui se connecte avec Google après avoir essayé sans compte garde ce qu'il y a fait, si son compte est neuf.
    """
    caller = _adopt_trial(caller, session_token, services)
    token = services.auth.create_session_token(caller.email, caller.name, caller.picture)
    set_session_cookie(request, response, token)
    return _account(caller, services)


@router.post("/session/trial")
def open_trial_session(opening: TrialOpening, services: Services, request: Request, response: Response) -> Account:
    """Ouvre un compte d'essai, sans connexion : une seule recherche, et un cookie pour seule identité.

    Publique, donc plafonnée : par jour pour l'instance, et par adresse IP. Refusée (429) au-delà, et
    absente (404) si l'instance ne propose pas d'essai.
    """
    caller, trial_key = opening
    if trial_key is not None:
        set_session_cookie(request, response, services.auth.create_session_token(None, trial_key=trial_key))
    return _account(caller, services)


@router.delete("/session", status_code=status.HTTP_204_NO_CONTENT)
def close_session(request: Request, response: Response) -> None:
    # Sans contrôle d'identité : on doit pouvoir se déconnecter même avec une session expirée
    clear_session_cookie(request, response)


def _adopt_trial(caller: Caller, session_token: str | None, services: Container) -> Caller:
    """Renvoie l'appelant sous le compte qui est désormais le sien : son essai, s'il en avait un à reprendre."""
    session = services.auth.read_session_token(session_token) if session_token else None
    # Sans adresse, c'est le mot de passe de l'instance, donc le propriétaire : il n'a rien à reprendre
    if session is None or session.trial_key is None or caller.email is None:
        return caller
    trial_user_id = services.auth.resolve_trial_user_id(session.trial_key)
    if trial_user_id is None:
        return caller
    return replace(caller, user_id=services.account.adopt_trial(trial_user_id, caller.user_id, caller.email))


def _account(caller: Caller, services: Container) -> Account:
    user_id = caller.user_id
    return Account(
        user_id=user_id,
        is_owner=user_id == DEFAULT_USER_ID,
        is_trial=caller.is_trial,
        is_admin=services.auth.is_admin(user_id, caller.email),
        email=caller.email,
        name=caller.name,
        picture=caller.picture,
        can_search=services.search.can_search(user_id),
        has_searched=services.search.has_searched(user_id),
        search_running=services.search.is_running(user_id),
        remaining_searches=services.search.remaining_searches(user_id),
        max_searches_per_day=MAX_SEARCHES_PER_DAY,
    )


@router.post("/client-errors", status_code=status.HTTP_204_NO_CONTENT)
def report_client_error(user_id: UserId, report: ClientErrorReport, services: Services) -> None:
    """Signale une erreur survenue dans le navigateur : son type, l'écran et l'emplacement dans le code.

    Le front l'appelle de lui-même. Jamais le message de l'erreur ; au-delà d'un nombre par jour, elle est ignorée.
    """
    services.health.record_client_error(user_id, report)


@router.post("/client-errors/visitor", status_code=status.HTTP_204_NO_CONTENT)
def report_visitor_error(report: ClientErrorReport, services: Services, request: Request) -> None:
    """Signale une erreur survenue dans le navigateur d'un visiteur sans session.

    Publique : les écrans s'ouvrent sans compte, et une erreur avant le dépôt du CV ne se verrait pas. Les
    mêmes motifs que pour un compte n'y laissent passer ni message ni contenu, et tous les visiteurs
    partagent un plafond par jour.
    """
    check_origin(request, services)
    services.health.record_client_error(None, report)
