from fastapi import APIRouter, status
from pydantic import BaseModel

from projet_recherche_emploi.api.security import Services, UserId
from projet_recherche_emploi.schemas import JobRead, JobStatus, RejectedJobRead

router = APIRouter(tags=["offres"])


class StatusUpdate(BaseModel):
    status: JobStatus


@router.get("/jobs")
def list_jobs(user_id: UserId, services: Services) -> list[JobRead]:
    return services.jobs.list_jobs(user_id)


@router.patch("/jobs/{job_id}")
def set_status(job_id: int, update: StatusUpdate, user_id: UserId, services: Services) -> JobRead:
    # L'offre revient mise à jour : le front n'a pas à recharger toute la liste pour connaître ses dates
    return services.jobs.set_status(user_id, job_id, update.status)


@router.delete("/jobs/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_job(job_id: int, user_id: UserId, services: Services) -> None:
    services.jobs.delete_job(user_id, job_id)


@router.get("/rejected-jobs")
def list_rejected_jobs(user_id: UserId, services: Services) -> list[RejectedJobRead]:
    return services.jobs.list_rejected_jobs(user_id)
