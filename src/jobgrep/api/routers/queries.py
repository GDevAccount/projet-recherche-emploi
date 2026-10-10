from fastapi import APIRouter, status
from pydantic import BaseModel

from jobgrep.api.security import Services, UserId
from jobgrep.schemas import SearchQueryRead

router = APIRouter(tags=["postes recherchés"])


class SearchQueryCreate(BaseModel):
    contract_type: str
    query: str
    # Ville ou région ; vide pour toute la France
    location: str = ""
    # Télétravail complet : le lieu est alors ignoré
    remote: bool = False


@router.get("/queries")
def list_queries(user_id: UserId, services: Services) -> list[SearchQueryRead]:
    return services.queries.list_queries(user_id)


@router.post("/queries", status_code=status.HTTP_201_CREATED)
def add_query(creation: SearchQueryCreate, user_id: UserId, services: Services) -> SearchQueryRead:
    return services.queries.add_query(
        user_id, creation.contract_type, creation.query, creation.location, creation.remote
    )


@router.delete("/queries/{query_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_query(query_id: int, user_id: UserId, services: Services) -> None:
    services.queries.delete_query(user_id, query_id)
