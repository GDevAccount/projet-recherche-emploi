from fastapi import APIRouter, status
from pydantic import BaseModel

from projet_recherche_emploi.api.security import Services, UserId
from projet_recherche_emploi.schemas import JobRead, RejectedJobRead

router = APIRouter(tags=["offres"])


class AppliedUpdate(BaseModel):
    applied: bool


@router.get("/jobs")
def list_jobs(user_id: UserId, services: Services) -> list[JobRead]:
    return services.jobs.list_jobs(user_id)


@router.patch("/jobs/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def set_applied(job_id: int, update: AppliedUpdate, user_id: UserId, services: Services) -> None:
    services.jobs.set_applied(user_id, job_id, update.applied)


@router.delete("/jobs/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_job(job_id: int, user_id: UserId, services: Services) -> None:
    services.jobs.delete_job(user_id, job_id)


@router.get("/rejected-jobs")
def list_rejected_jobs(user_id: UserId, services: Services) -> list[RejectedJobRead]:
    return services.jobs.list_rejected_jobs(user_id)
