"""Identification de l'appelant de l'API.

Une preuve d'identité se présente dans l'en-tête « Authorization: Bearer … ». Avec la connexion Google,
c'est un jeton d'identité Google et l'adresse qu'il porte désigne l'utilisateur ; sans elle, c'est
APP_PASSWORD, qui désigne le propriétaire. Sans aucun des deux, l'API refuse tout : elle ne s'ouvre
jamais par défaut.

Un navigateur ne présente cette preuve qu'une fois, à « POST /api/session », qui l'échange contre un cookie
de session : le jeton Google expire au bout d'une heure, et le cookie n'est pas lisible par le JavaScript de la page.
"""

from dataclasses import dataclass
from typing import Annotated, Protocol
from urllib.parse import urlsplit

from fastapi import Depends, HTTPException, Request, Response, status
from fastapi.security import APIKeyCookie, HTTPAuthorizationCredentials, HTTPBearer
from google.auth.exceptions import GoogleAuthError
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

from jobgrep.config import DEFAULT_USER_ID
from jobgrep.container import Container
from jobgrep.services.auth_service import SESSION_SECONDS

SESSION_COOKIE = "session"
SESSION_COOKIE_PATH = "/api"
LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}
# Méthodes qui ne modifient rien : une requête forgée par un autre site n'y gagne rien
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
# Au sortir d'une mise en veille, l'horloge de la machine retarde de quelques secondes : sans cette marge,
# un jeton Google tout juste émis serait refusé comme « émis dans le futur »
CLOCK_SKEW_SECONDS = 10

BearerCredentials = Annotated[HTTPAuthorizationCredentials | None, Depends(HTTPBearer(auto_error=False))]
SessionToken = Annotated[str | None, Depends(APIKeyCookie(name=SESSION_COOKIE, auto_error=False))]


@dataclass(frozen=True)
class Identity:
    email: str | None
    email_verified: bool | None
    name: str | None = None
    picture: str | None = None


class IdentityVerifier(Protocol):
    def verify(self, token: str) -> Identity | None:
        """Renvoie l'identité portée par ce jeton, ou None s'il est invalide ou expiré."""
        ...


class GoogleIdentityVerifier:
    def __init__(self, client_id: str):
        self.client_id = client_id

    def verify(self, token: str) -> Identity | None:
        try:
            # Vérifie la signature de Google, l'expiration, et que le jeton a été émis pour cette application
            claims = id_token.verify_oauth2_token(
                token, google_requests.Request(), self.client_id, clock_skew_in_seconds=CLOCK_SKEW_SECONDS
            )
        except (ValueError, GoogleAuthError):
            return None
        return Identity(claims.get("email"), claims.get("email_verified"), claims.get("name"), claims.get("picture"))


@dataclass(frozen=True)
class Caller:
    user_id: int
    # Adresse Google vérifiée, ou None si l'appelant a donné le mot de passe de l'instance
    email: str | None
    # Nom et photo du profil Google, pour l'affichage seulement
    name: str | None = None
    picture: str | None = None
    # Compte d'essai, ouvert sans connexion et reconnu par son seul cookie
    is_trial: bool = False


def get_container(request: Request) -> Container:
    return request.app.state.container


def get_caller_from_credentials(
    request: Request,
    container: Annotated[Container, Depends(get_container)],
    credentials: BearerCredentials,
) -> Caller:
    """Renvoie l'appelant prouvé par l'en-tête Authorization. Seule preuve acceptée pour ouvrir une session."""
    _require_protection(container)
    if credentials is None:
        raise _unauthorized()
    return _caller_from_credentials(request, container, credentials.credentials)


def get_current_caller(
    request: Request,
    container: Annotated[Container, Depends(get_container)],
    credentials: BearerCredentials,
    session_token: SessionToken,
) -> Caller:
    """Renvoie l'appelant de la requête, prouvé par l'en-tête Authorization ou par le cookie de session."""
    caller = _identify(request, container, credentials, session_token)
    # Pour le suivi des erreurs : il dit quel compte a rencontré celle que cette requête va peut-être rendre
    request.state.user_id = caller.user_id
    # Après l'identification : elle vient de dater l'activité de l'appelant, qui n'est donc pas supprimé
    container.account.delete_inactive_accounts_if_due()
    return caller


def _identify(
    request: Request,
    container: Container,
    credentials: HTTPAuthorizationCredentials | None,
    session_token: str | None,
) -> Caller:
    _require_protection(container)
    if credentials is not None:
        return _caller_from_credentials(request, container, credentials.credentials)
    if session_token is None:
        raise _unauthorized()

    session = container.auth.read_session_token(session_token)
    if session is None:
        raise _unauthorized()
    _check_origin(request, container)
    if session.trial_key is not None:
        user_id = container.auth.resolve_trial_user_id(session.trial_key)
        # Supprimé par son utilisateur, ou après TRIAL_ACCOUNT_DAYS
        if user_id is None:
            raise _unauthorized()
        return Caller(user_id, None, is_trial=True)
    if session.email is None:
        return Caller(DEFAULT_USER_ID, None)
    # L'adresse a été vérifiée par Google à l'ouverture de la session ; l'autorisation, elle, est relue ici
    user_id = container.auth.resolve_user_id(session.email, True)
    if user_id is None:
        raise _forbidden()
    return Caller(user_id, session.email, session.name, session.picture)


def open_trial(
    request: Request,
    container: Annotated[Container, Depends(get_container)],
    session_token: SessionToken,
) -> tuple[Caller, str | None]:
    """Renvoie le compte d'essai du visiteur et, s'il vient d'être ouvert, sa clé à poser dans un cookie.

    Seule ouverture de session sans preuve d'identité : c'est AuthService.start_trial qui la plafonne. Un
    visiteur qui a déjà son essai le retrouve, sans que son cookie soit prolongé.
    """
    _check_origin(request, container)
    session = container.auth.read_session_token(session_token) if session_token else None
    if session is not None and session.trial_key is not None:
        user_id = container.auth.resolve_trial_user_id(session.trial_key)
        if user_id is not None:
            return Caller(user_id, None, is_trial=True), None
    trial_key = container.auth.start_trial(_client_ip(request))
    user_id = container.auth.resolve_trial_user_id(trial_key)
    request.state.user_id = user_id
    return Caller(user_id, None, is_trial=True), trial_key


def _client_ip(request: Request) -> str | None:
    # Fly.io écrit lui-même cet en-tête, que le visiteur ne peut donc pas choisir, contrairement à
    # X-Forwarded-For. Hors de Fly.io, il n'existe pas : c'est l'adresse de la connexion qui sert
    return request.headers.get("fly-client-ip") or (request.client.host if request.client else None)


def get_current_user_id(caller: Annotated[Caller, Depends(get_current_caller)]) -> int:
    """Renvoie l'utilisateur de la requête. Toute route qui lit ou modifie des données en dépend."""
    return caller.user_id


def get_admin_id(
    caller: Annotated[Caller, Depends(get_current_caller)],
    container: Annotated[Container, Depends(get_container)],
) -> int:
    """Renvoie l'utilisateur de la requête s'il est administrateur, et refuse tout autre appelant.

    Les routes de suivi en dépendent : coûts, durées et journal des évaluations ne regardent que ceux qui
    exploitent l'instance. Le front peut masquer l'écran, c'est ici que l'accès se décide.
    """
    if not container.auth.is_admin(caller.user_id, caller.email):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Réservé aux administrateurs de l'instance.")
    return caller.user_id


def set_session_cookie(request: Request, response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=SESSION_SECONDS,
        path=SESSION_COOKIE_PATH,
        httponly=True,
        secure=_is_secure(request),
        samesite="strict",
    )


def clear_session_cookie(request: Request, response: Response) -> None:
    response.delete_cookie(
        SESSION_COOKIE, path=SESSION_COOKIE_PATH, httponly=True, secure=_is_secure(request), samesite="strict"
    )


def _require_protection(container: Container) -> None:
    if container.auth.login_mode is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "L'API n'est pas protégée : définir la connexion Google ou APP_PASSWORD.",
        )


def _caller_from_credentials(request: Request, container: Container, token: str) -> Caller:
    if container.auth.login_mode == "google":
        identity = request.app.state.identity_verifier.verify(token)
        if identity is None:
            raise _unauthorized()
        user_id = container.auth.resolve_user_id(identity.email, identity.email_verified)
        if user_id is None:
            raise _forbidden()
        return Caller(user_id, identity.email, identity.name, identity.picture)

    if not container.auth.password_matches(token):
        raise _unauthorized()
    return Caller(DEFAULT_USER_ID, None)


def _check_origin(request: Request, container: Container) -> None:
    """Refuse une requête qui modifie des données si elle vient d'un autre site que le front.

    Le navigateur joint le cookie de lui-même : sans ce contrôle, une page d'un autre site pourrait agir
    au nom de l'utilisateur. SameSite=Strict l'empêche déjà, ceci couvre un navigateur qui l'ignorerait.
    L'en-tête Authorization n'est pas concerné : un autre site ne peut pas le remplir.
    """
    origin = request.headers.get("origin")
    if request.method in SAFE_METHODS or origin is None:
        return
    same_host = urlsplit(origin).netloc == request.headers.get("host")
    if not same_host and origin not in container.settings.cors_origin_list:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Cette origine n'est pas autorisée à appeler l'API.")


def _is_secure(request: Request) -> bool:
    # Le cookie ne circule qu'en HTTPS, sauf sur la machine du développeur. On ne se fie pas au schéma
    # de la requête : derrière le proxy d'un hébergeur, l'application la reçoit en HTTP.
    return request.url.hostname not in LOOPBACK_HOSTS


def _unauthorized() -> HTTPException:
    return HTTPException(
        status.HTTP_401_UNAUTHORIZED, "Authentification requise.", headers={"WWW-Authenticate": "Bearer"}
    )


def _forbidden() -> HTTPException:
    return HTTPException(status.HTTP_403_FORBIDDEN, "Cette adresse n'est pas autorisée à utiliser l'application.")


Services = Annotated[Container, Depends(get_container)]
UserId = Annotated[int, Depends(get_current_user_id)]
AdminId = Annotated[int, Depends(get_admin_id)]
CurrentCaller = Annotated[Caller, Depends(get_current_caller)]
CredentialsCaller = Annotated[Caller, Depends(get_caller_from_credentials)]
TrialOpening = Annotated[tuple[Caller, str | None], Depends(open_trial)]
