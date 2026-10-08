from fastapi import APIRouter, status
from pydantic import BaseModel

from projet_recherche_emploi.api.security import Services, UserId
from projet_recherche_emploi.schemas import JobRead, RejectedJobRead

router = APIRouter(tags=["offres"])


# Une offre est désignée par son URL, qui ne tient pas dans un chemin : elle voyage dans le corps
class AppliedUpdate(BaseModel):
    url: str
    applied: bool


class JobsDeletion(BaseModel):
    urls: list[str]


class DeletionResult(BaseModel):
    deleted: int


@router.get("/jobs")
def list_jobs(user_id: UserId, services: Services) -> list[JobRead]:
    return services.jobs.list_jobs(user_id)


@router.patch("/jobs", status_code=status.HTTP_204_NO_CONTENT)
def set_applied(update: AppliedUpdate, user_id: UserId, services: Services) -> None:
    services.jobs.set_applied(user_id, update.url, update.applied)


@router.post("/jobs/delete")
def delete_jobs(deletion: JobsDeletion, user_id: UserId, services: Services) -> DeletionResult:
    return DeletionResult(deleted=services.jobs.delete_jobs(user_id, deletion.urls))


@router.get("/rejected-jobs")
def list_rejected_jobs(user_id: UserId, services: Services) -> list[RejectedJobRead]:
    return services.jobs.list_rejected_jobs(user_id)
