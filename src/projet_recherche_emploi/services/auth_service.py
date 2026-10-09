import base64
import binascii
import hashlib
import hmac
import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from projet_recherche_emploi.config import DEFAULT_USER_ID, LOCAL_TIMEZONE, SESSION_DAYS, Settings
from projet_recherche_emploi.data.database import Database
from projet_recherche_emploi.data.repositories.activity_repository import ActivityRepository
from projet_recherche_emploi.data.repositories.user_repository import UserRepository
from projet_recherche_emploi.errors import ConfigurationError

# Valeur de ALLOWED_EMAILS qui ouvre l'application à tout compte Google
EVERYONE = "*"

SESSION_SECONDS = SESSION_DAYS * 24 * 3600
# La dernière activité d'un compte est datée au jour près : assez pour un délai compté en mois
ACTIVITY_PRECISION = timedelta(days=1)

LoginMode = Literal["google", "password"]


@dataclass(frozen=True)
class SessionIdentity:
    # Adresse Google vérifiée à l'ouverture de la session, ou None pour une session ouverte par mot de passe
    email: str | None
    # Nom et photo du profil Google, pour l'affichage seulement : ils ne sont enregistrés nulle part ailleurs
    name: str | None = None
    picture: str | None = None


class AuthService:
    def __init__(self, settings: Settings, database: Database, clock: Callable[[], float] = time.time):
        self.settings = settings
        self.database = database
        self.clock = clock

    @property
    def password_required(self) -> bool:
        return bool(self.settings.app_password)

    @property
    def login_mode(self) -> LoginMode | None:
        """Dit quelle preuve d'identité l'instance attend, ou None si elle n'est pas protégée."""
        # La connexion Google l'emporte : une fois activée, le mot de passe n'ouvre plus rien
        if self.settings.google_client_id:
            return "google"
        return "password" if self.password_required else None

    def check_configuration(self) -> None:
        """Refuse une instance dont la connexion est à moitié réglée, avant qu'elle ne serve une requête."""
        missing = []
        if self.settings.google_client_id and not _normalize(self.settings.owner_email):
            # Sans propriétaire, personne ne pourrait retrouver les données de l'utilisateur par défaut
            missing.append("OWNER_EMAIL")
        if self.login_mode is not None and not self.settings.auth_cookie_secret:
            # Sans lui, aucune session ne s'ouvre : la connexion serait refusée à tout le monde
            missing.append("AUTH_COOKIE_SECRET")
        if missing:
            raise ConfigurationError(f"Connexion incomplète, variable(s) manquante(s) : {', '.join(missing)}")

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
        # Un administrateur est invité d'office : il a un compte d'invité, avec son quota
        if EVERYONE not in allowed_emails and email not in allowed_emails | self._admin_emails():
            return None
        now = datetime.fromtimestamp(self.clock(), UTC)
        with self.database.session() as session:
            users = UserRepository(session)
            user_id = users.get_or_create_user_id(email)
            # Sans cela, un compte qui sert encore serait supprimé comme inactif
            users.record_activity(user_id, now, now - ACTIVITY_PRECISION)
            # Chaque jour où il vient, noté une fois : c'est ce qui dit qu'un invité revient
            days = ActivityRepository(session, user_id)
            day = now.astimezone(ZoneInfo(LOCAL_TIMEZONE)).date().isoformat()
            if not days.has_day(day):
                days.record_day(day)
            return user_id

    def create_session_token(self, email: str | None, name: str | None = None, picture: str | None = None) -> str:
        """Renvoie le jeton de session d'une identité déjà vérifiée : une adresse Google, ou None pour le mot de passe.

        Le jeton porte l'adresse, pas l'utilisateur : chaque requête repasse par resolve_user_id, donc
        retirer une adresse de ALLOWED_EMAILS ferme ses sessions.
        """
        key = self._session_key()
        if key is None:
            raise ConfigurationError("AUTH_COOKIE_SECRET n'est pas défini : l'API ne peut pas ouvrir de session.")
        expires_at = int(self.clock()) + SESSION_SECONDS
        payload = json.dumps({"email": email, "name": name, "picture": picture, "exp": expires_at})
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
        # Absents d'une session ouverte avant qu'ils y soient portés
        return SessionIdentity(email, payload.get("name"), payload.get("picture"))

    def _session_key(self) -> bytes | None:
        secret = self.settings.auth_cookie_secret
        if not secret:
            return None
        # Clé dérivée du secret, propre aux sessions. Le mot de passe en fait partie : le changer ferme
        # les sessions ouvertes avec l'ancien. Changer le préfixe fermerait toutes les sessions.
        message = b"session-api-v1:" + self.settings.app_password.encode()
        return hmac.new(secret.encode(), message, hashlib.sha256).digest()

    def is_admin(self, user_id: int, email: str | None) -> bool:
        """Dit si cet appelant, déjà identifié, est un administrateur : le propriétaire, ou une adresse d'ADMIN_EMAILS.

        Relu à chaque requête, comme l'autorisation : retirer une adresse d'ADMIN_EMAILS lui retire ce droit.
        """
        return user_id == DEFAULT_USER_ID or (bool(email) and _normalize(email) in self._admin_emails())

    def _allowed_emails(self) -> set[str]:
        return _split_emails(self.settings.allowed_emails)

    def _admin_emails(self) -> set[str]:
        return _split_emails(self.settings.admin_emails)


def _sign(key: bytes, body: bytes) -> str:
    return base64.urlsafe_b64encode(hmac.new(key, body, hashlib.sha256).digest()).decode()


def _split_emails(emails: str) -> set[str]:
    return {_normalize(email) for email in emails.split(",") if email.strip()}


def _normalize(email: str | None) -> str:
    return (email or "").strip().lower()
