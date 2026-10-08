import base64
import binascii
import hashlib
import hmac
import json
import time
from collections.abc import Callable
from dataclasses import dataclass

from projet_recherche_emploi.config import DEFAULT_USER_ID, SESSION_DAYS, Settings
from projet_recherche_emploi.data.database import Database
from projet_recherche_emploi.data.user_repository import UserRepository
from projet_recherche_emploi.errors import ConfigurationError

# Valeur de ALLOWED_EMAILS qui ouvre l'application à tout compte Google
EVERYONE = "*"

SESSION_SECONDS = SESSION_DAYS * 24 * 3600


@dataclass(frozen=True)
class SessionIdentity:
    # Adresse Google vérifiée à l'ouverture de la session, ou None pour une session ouverte par mot de passe
    email: str | None


class AuthService:
    def __init__(self, settings: Settings, database: Database, clock: Callable[[], float] = time.time):
        self.settings = settings
        self.database = database
        self.clock = clock

    @property
    def password_required(self) -> bool:
        return bool(self.settings.app_password)

    def password_matches(self, password: str) -> bool:
        """Dit si ce mot de passe est celui de l'instance (APP_PASSWORD)."""
        expected = self.settings.app_password
        return bool(expected) and hmac.compare_digest(password.encode(), expected.encode())

    def resolve_user_id(self, email: str | None, email_verified: bool | None) -> int | None:
        """Renvoie l'utilisateur lié à cette adresse Google, ou None si elle n'est pas autorisée."""
        owner_email = _normalize(self.settings.owner_email)
        if not owner_email:
            # Sans propriétaire, personne ne pourrait retrouver les données de l'utilisateur par défaut
            raise ConfigurationError("La connexion Google est activée, mais OWNER_EMAIL n'est pas défini.")

        email = _normalize(email)
        # Une adresse non vérifiée par Google peut avoir été déclarée par n'importe qui
        if not email or email_verified is not True:
            return None

        if email == owner_email:
            return DEFAULT_USER_ID
        allowed_emails = self._allowed_emails()
        if EVERYONE not in allowed_emails and email not in allowed_emails:
            return None
        with self.database.session() as session:
            return UserRepository(session).get_or_create_user_id(email)

    def create_session_token(self, email: str | None) -> str:
        """Renvoie le jeton de session d'une identité déjà vérifiée : une adresse Google, ou None pour le mot de passe.

        Le jeton porte l'adresse, pas l'utilisateur : chaque requête repasse par resolve_user_id, donc
        retirer une adresse de ALLOWED_EMAILS ferme ses sessions.
        """
        key = self._session_key()
        if key is None:
            raise ConfigurationError("AUTH_COOKIE_SECRET n'est pas défini : l'API ne peut pas ouvrir de session.")
        payload = json.dumps({"email": email, "exp": int(self.clock()) + SESSION_SECONDS})
        body = base64.urlsafe_b64encode(payload.encode())
        return f"{body.decode()}.{_sign(key, body)}"

    def read_session_token(self, token: str) -> SessionIdentity | None:
        """Renvoie l'identité d'un jeton de session, ou None s'il est falsifié, expiré ou d'un autre mode."""
        key = self._session_key()
        body, _, signature = token.partition(".")
        if key is None or not hmac.compare_digest(_sign(key, body.encode()).encode(), signature.encode()):
            return None
        try:
            payload = json.loads(base64.urlsafe_b64decode(body))
            email, expires_at = payload["email"], payload["exp"]
        except (binascii.Error, ValueError, KeyError, TypeError):
            return None
        if expires_at <= self.clock():
            return None
        # Une session ouverte par mot de passe ne vaut plus rien une fois la connexion Google activée, et inversement
        if (email is None) == bool(self.settings.google_client_id):
            return None
        return SessionIdentity(email)

    def _session_key(self) -> bytes | None:
        secret = self.settings.auth_cookie_secret
        if not secret:
            return None
        # Clé propre aux sessions de l'API, distincte de celle du cookie de Streamlit. Le mot de passe
        # en fait partie : le changer ferme les sessions ouvertes avec l'ancien.
        message = b"session-api-v1:" + self.settings.app_password.encode()
        return hmac.new(secret.encode(), message, hashlib.sha256).digest()

    def _allowed_emails(self) -> set[str]:
        emails = self.settings.allowed_emails.split(",")
        return {_normalize(email) for email in emails if email.strip()}


def _sign(key: bytes, body: bytes) -> str:
    return base64.urlsafe_b64encode(hmac.new(key, body, hashlib.sha256).digest()).decode()


def _normalize(email: str | None) -> str:
    return (email or "").strip().lower()
