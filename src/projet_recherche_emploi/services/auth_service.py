import hmac

from projet_recherche_emploi.config import DEFAULT_USER_ID, Settings
from projet_recherche_emploi.data.database import Database
from projet_recherche_emploi.data.user_repository import UserRepository
from projet_recherche_emploi.errors import ConfigurationError

# Valeur de ALLOWED_EMAILS qui ouvre l'application à tout compte Google
EVERYONE = "*"


class AuthService:
    def __init__(self, settings: Settings, database: Database):
        self.settings = settings
        self.database = database

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

    def _allowed_emails(self) -> set[str]:
        emails = self.settings.allowed_emails.split(",")
        return {_normalize(email) for email in emails if email.strip()}


def _normalize(email: str | None) -> str:
    return (email or "").strip().lower()
