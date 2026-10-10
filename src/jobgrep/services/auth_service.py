import base64
import binascii
import hashlib
import hmac
import json
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from jobgrep.config import (
    DEFAULT_USER_ID,
    LOCAL_TIMEZONE,
    MAX_TRIALS_PER_IP_PER_DAY,
    SESSION_DAYS,
    TRIAL_START_DAYS,
    Settings,
)
from jobgrep.data.database import Database
from jobgrep.data.repositories.activity_repository import ActivityRepository
from jobgrep.data.repositories.user_repository import UserRepository
from jobgrep.errors import ConfigurationError, NotFoundError, QuotaExceededError
from jobgrep.schemas import TrialStatus

# Valeur de ALLOWED_EMAILS qui ouvre l'application à tout compte Google
EVERYONE = "*"

SESSION_SECONDS = SESSION_DAYS * 24 * 3600
# La dernière activité d'un compte est datée au jour près : assez pour un délai compté en mois
ACTIVITY_PRECISION = timedelta(days=1)

LoginMode = Literal["google", "password"]

# Longueur, en octets, de la clé tirée au hasard d'un compte d'essai
TRIAL_KEY_BYTES = 32
TRIALS_EXHAUSTED_MESSAGE = "Les essais sans compte sont épuisés pour aujourd'hui : revenez demain, ou connectez-vous."


@dataclass(frozen=True)
class SessionIdentity:
    # Adresse Google vérifiée à l'ouverture de la session, ou None pour une session ouverte par mot de passe
    email: str | None
    # Nom et photo du profil Google, pour l'affichage seulement : ils ne sont enregistrés nulle part ailleurs
    name: str | None = None
    picture: str | None = None
    # Clé du compte d'essai, pour une session ouverte sans connexion
    trial_key: str | None = None


class AuthService:
    def __init__(
        self,
        settings: Settings,
        database: Database,
        clock: Callable[[], float] = time.time,
        budget_reached: Callable[[], bool] | None = None,
    ):
        self.settings = settings
        self.database = database
        self.clock = clock
        # Dit si le budget du jour de l'instance est atteint : aucun essai ne s'ouvre alors
        self._budget_reached = budget_reached or (lambda: False)

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
            user_id = UserRepository(session).get_or_create_user_id(email)
            self._record_visit(session, user_id, now)
            return user_id

    def _record_visit(self, session, user_id: int, now: datetime) -> None:
        # Sans cela, un compte qui sert encore serait supprimé comme inactif
        UserRepository(session).record_activity(user_id, now, now - ACTIVITY_PRECISION)
        # Chaque jour où il vient, noté une fois : c'est ce qui dit qu'un utilisateur revient
        days = ActivityRepository(session, user_id)
        day = now.astimezone(ZoneInfo(LOCAL_TIMEZONE)).date().isoformat()
        if not days.has_day(day):
            days.record_day(day)

    def _start_of_local_day(self) -> datetime:
        local = datetime.fromtimestamp(self.clock(), ZoneInfo(LOCAL_TIMEZONE))
        return local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)

    def _hash_ip(self, ip_address: str | None) -> str:
        # Avec un secret de l'instance : sans lui, essayer toutes les adresses suffirait à retrouver celle-ci
        key = hmac.new(self.settings.auth_cookie_secret.encode(), b"trial-ip-v1", hashlib.sha256).digest()
        return hmac.new(key, (ip_address or "").encode(), hashlib.sha256).hexdigest()

    @property
    def trial_enabled(self) -> bool:
        """Dit si l'instance ouvre des comptes d'essai, sans connexion."""
        return self.login_mode is not None and self.settings.max_trials_per_day > 0

    def trial_status(self) -> TrialStatus | None:
        """Dit si un essai sans compte peut s'ouvrir maintenant, ou None si l'instance n'en propose pas.

        « exhausted » : plus d'essai aujourd'hui, pour personne. L'écran de connexion le dit avant que le
        visiteur ne dépose son CV pour rien. Le plafond d'une adresse IP, lui, ne se lit qu'à l'ouverture.
        """
        if not self.trial_enabled:
            return None
        if self._budget_reached():
            return "exhausted"
        with self.database.session() as session:
            started = UserRepository(session).count_trial_starts(self._start_of_local_day())
        return "exhausted" if started >= self.settings.max_trials_per_day else "available"

    def start_trial(self, ip_address: str | None) -> str:
        """Ouvre un compte d'essai et renvoie sa clé, à porter dans le jeton de session.

        Refusé quand le budget du jour est atteint, quand l'instance a ouvert assez d'essais aujourd'hui, ou
        quand cette adresse IP en a ouvert assez : effacer son cookie ne redonne pas un essai.
        """
        if not self.trial_enabled:
            raise NotFoundError("Cette instance ne propose pas d'essai sans compte.")
        if self._budget_reached():
            raise QuotaExceededError(TRIALS_EXHAUSTED_MESSAGE)
        now = datetime.fromtimestamp(self.clock(), UTC)
        today = self._start_of_local_day()
        ip_hash = self._hash_ip(ip_address)
        with self.database.session() as session:
            users = UserRepository(session)
            # En premier, exprès : la transaction commence par une écriture, et attend donc son tour. Une
            # lecture suivie d'une écriture serait refusée d'emblée par SQLite si une recherche écrit entre-temps
            users.forget_trial_starts(now - timedelta(days=TRIAL_START_DAYS))
            if users.count_trial_starts(today) >= self.settings.max_trials_per_day:
                raise QuotaExceededError(TRIALS_EXHAUSTED_MESSAGE)
            if users.count_trial_starts(today, ip_hash) >= MAX_TRIALS_PER_IP_PER_DAY:
                raise QuotaExceededError(
                    "Trop d'essais ont été ouverts depuis votre connexion aujourd'hui : "
                    "revenez demain, ou connectez-vous."
                )
            users.record_trial_start(ip_hash, now)
            trial_key = secrets.token_urlsafe(TRIAL_KEY_BYTES)
            users.create_trial_user(trial_key)
        return trial_key

    def resolve_trial_user_id(self, trial_key: str) -> int | None:
        """Renvoie le compte d'essai de cette clé, ou None s'il a été supprimé."""
        now = datetime.fromtimestamp(self.clock(), UTC)
        with self.database.session() as session:
            user_id = UserRepository(session).get_trial_user_id(trial_key)
        if user_id is None:
            return None
        # Dans une autre transaction que la lecture, qui commence ainsi par une écriture et attend son tour :
        # à la suite d'une lecture, SQLite la refuserait d'emblée pendant qu'une recherche écrit
        with self.database.session() as session:
            self._record_visit(session, user_id, now)
        return user_id

    def create_session_token(
        self,
        email: str | None,
        name: str | None = None,
        picture: str | None = None,
        trial_key: str | None = None,
    ) -> str:
        """Renvoie le jeton de session d'une identité déjà vérifiée : une adresse Google, la clé d'un compte
        d'essai, ou ni l'une ni l'autre pour le mot de passe.

        Le jeton porte l'adresse, pas l'utilisateur : chaque requête repasse par resolve_user_id, donc
        retirer une adresse de ALLOWED_EMAILS ferme ses sessions. Celui d'un essai porte sa clé, relue de
        même : un compte d'essai supprimé ferme sa session.
        """
        key = self._session_key()
        if key is None:
            raise ConfigurationError("AUTH_COOKIE_SECRET n'est pas défini : l'API ne peut pas ouvrir de session.")
        expires_at = int(self.clock()) + SESSION_SECONDS
        payload = {"email": email, "name": name, "picture": picture, "exp": expires_at}
        if trial_key is not None:
            payload["trial"] = trial_key
        body = base64.urlsafe_b64encode(json.dumps(payload).encode())
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
        trial_key = payload.get("trial")
        if trial_key is not None:
            # Fermer les essais (MAX_TRIALS_PER_DAY à 0) ferme aussi les sessions d'essai déjà ouvertes
            valid = isinstance(trial_key, str) and self.trial_enabled
            return SessionIdentity(None, trial_key=trial_key) if valid else None
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
