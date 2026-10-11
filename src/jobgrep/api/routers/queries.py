from typing import Annotated

from fastapi import APIRouter, Query, status
from pydantic import BaseModel

from jobgrep.api.security import Services, UserId
from jobgrep.config import MAX_SKILL_CHARS
from jobgrep.schemas import SearchQueryRead

router = APIRouter(tags=["postes recherchés"])


class SearchQueryCreate(BaseModel):
    contract_type: str
    # Le métier visé
    query: str
    # Compétences qui précisent la recherche
    skills: list[str] = []
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
        user_id, creation.contract_type, creation.query, creation.location, creation.remote, creation.skills
    )


@router.get("/skills")
def suggest_skills(
    q: Annotated[str, Query(max_length=MAX_SKILL_CHARS)], user_id: UserId, services: Services
) -> list[str]:
    return services.queries.suggest_skills(user_id, q)


@router.delete("/queries/{query_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_query(query_id: int, user_id: UserId, services: Services) -> None:
    services.queries.delete_query(user_id, query_id)
