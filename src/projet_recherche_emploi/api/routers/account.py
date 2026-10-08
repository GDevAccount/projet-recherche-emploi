from fastapi import APIRouter

from projet_recherche_emploi.api.security import Services, UserId
from projet_recherche_emploi.config import DEFAULT_USER_ID, MAX_SEARCHES_PER_DAY
from projet_recherche_emploi.schemas import Account

router = APIRouter(tags=["compte"])


@router.get("/me")
def get_account(user_id: UserId, services: Services) -> Account:
    return Account(
        user_id=user_id,
        is_owner=user_id == DEFAULT_USER_ID,
        remaining_searches=services.search.remaining_searches(user_id),
        max_searches_per_day=MAX_SEARCHES_PER_DAY,
    )
