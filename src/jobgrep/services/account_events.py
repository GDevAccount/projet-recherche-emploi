from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from jobgrep.config import DEFAULT_USER_ID, LOCAL_TIMEZONE
from jobgrep.data.repositories.account_event_repository import AccountEventRepository

# Moments du parcours gardés après le départ d'un compte
TRIAL_OPENED = "trial_opened"
ACCOUNT_CREATED = "account_created"
CV_DEPOSITED = "cv_deposited"
SEARCH_LAUNCHED = "search_launched"
TRIAL_ADOPTED = "trial_adopted"
ACCOUNT_DELETED = "account_deleted"

# Causes du départ d'un compte, et ce qu'en lit un administrateur
DELETION_REASONS = {
    "requested": "À la demande de l'utilisateur",
    "inactive": "Compte resté inactif",
    "trial_expired": "Essai arrivé à son terme",
    "trial_replaced": "Essai abandonné à la connexion",
    "merged": "Compte neuf remplacé par son essai",
}


def record_event(
    session,
    user_id: int,
    kind: str,
    detail: str | None = None,
    plan: str | None = None,
    now: datetime | None = None,
) -> None:
    """Note un moment du parcours de ce compte, sans le compte : le jour de Paris, le genre et la formule.

    Sans formule donnée, c'est celle du compte à cet instant. Le propriétaire n'y est pas : ce parcours dit
    si l'application sert à d'autres que lui.
    """
    if user_id == DEFAULT_USER_ID:
        return
    day = (now or datetime.now(UTC)).astimezone(ZoneInfo(LOCAL_TIMEZONE)).date().isoformat()
    events = AccountEventRepository(session)
    if plan is None:
        events.record_for(user_id, day, kind, detail)
    else:
        events.record(day, kind, plan, detail)
