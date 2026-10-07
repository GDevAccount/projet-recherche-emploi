import os
from pathlib import Path

from projet_recherche_emploi.config import DEFAULT_USER_ID
from projet_recherche_emploi.user_repository import UserRepository


def resolve_user_id(db_path: str | Path, email: str | None, email_verified: bool | None) -> int | None:
    """Renvoie l'utilisateur lié à cette adresse Google, ou None si elle n'est pas invitée."""
    owner_email = _normalize(os.environ.get("OWNER_EMAIL"))
    if not owner_email:
        # Sans propriétaire, personne ne pourrait retrouver les données de l'utilisateur par défaut
        raise ValueError("La connexion Google est activée, mais OWNER_EMAIL n'est pas défini.")

    email = _normalize(email)
    # Une adresse non vérifiée par Google peut avoir été déclarée par n'importe qui
    if not email or email_verified is not True:
        return None

    if email == owner_email:
        return DEFAULT_USER_ID
    if email not in _allowed_emails():
        return None
    return UserRepository(db_path).get_or_create_user_id(email)


def _allowed_emails() -> set[str]:
    emails = os.environ.get("ALLOWED_EMAILS", "").split(",")
    return {_normalize(email) for email in emails if email.strip()}


def _normalize(email: str | None) -> str:
    return (email or "").strip().lower()
