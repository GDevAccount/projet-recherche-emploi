"""Identification de l'appelant de l'API, à partir de l'en-tête « Authorization: Bearer … ».

Même règle que l'interface Streamlit : avec la connexion Google, le jeton est un jeton d'identité Google
et l'adresse qu'il porte désigne l'utilisateur ; sans elle, le jeton est APP_PASSWORD et désigne le propriétaire.
Sans aucun des deux, l'API refuse tout : elle ne s'ouvre jamais par défaut.
"""

from dataclasses import dataclass
from typing import Annotated, Protocol

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from google.auth.exceptions import GoogleAuthError
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

from projet_recherche_emploi.config import DEFAULT_USER_ID
from projet_recherche_emploi.container import Container


@dataclass(frozen=True)
class Identity:
    email: str | None
    email_verified: bool | None


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
            claims = id_token.verify_oauth2_token(token, google_requests.Request(), self.client_id)
        except (ValueError, GoogleAuthError):
            return None
        return Identity(claims.get("email"), claims.get("email_verified"))


def get_container(request: Request) -> Container:
    return request.app.state.container


def get_current_user_id(
    request: Request,
    container: Annotated[Container, Depends(get_container)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(HTTPBearer(auto_error=False))],
) -> int:
    """Renvoie l'utilisateur de la requête. Toute route qui lit ou modifie des données en dépend."""
    if container.settings.google_client_id:
        identity = request.app.state.identity_verifier.verify(credentials.credentials) if credentials else None
        if identity is None:
            raise _unauthorized()
        user_id = container.auth.resolve_user_id(identity.email, identity.email_verified)
        if user_id is None:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "Cette adresse n'est pas autorisée à utiliser l'application."
            )
        return user_id

    if container.auth.password_required:
        if credentials is None or not container.auth.password_matches(credentials.credentials):
            raise _unauthorized()
        return DEFAULT_USER_ID

    raise HTTPException(
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "L'API n'est pas protégée : définir la connexion Google ou APP_PASSWORD.",
    )


def _unauthorized() -> HTTPException:
    return HTTPException(
        status.HTTP_401_UNAUTHORIZED, "Authentification requise.", headers={"WWW-Authenticate": "Bearer"}
    )


Services = Annotated[Container, Depends(get_container)]
UserId = Annotated[int, Depends(get_current_user_id)]
