from collections.abc import Iterable
from datetime import UTC, datetime

from projet_recherche_emploi.data.database import Database
from projet_recherche_emploi.data.models import Job
from projet_recherche_emploi.data.repositories.job_repository import JobRepository
from projet_recherche_emploi.data.repositories.rejected_job_repository import RejectedJobRepository
from projet_recherche_emploi.errors import InvalidInputError, NotFoundError
from projet_recherche_emploi.schemas import JobRead, JobStatus, RejectedJobRead


def next_statuses(status: str, had_interview: bool) -> list[JobStatus]:
    """Renvoie les états qu'une candidature peut prendre depuis celui-ci, l'étape suivante en premier.

    Une candidature avance d'une étape, ou revient à la précédente pour corriger une erreur. Un refus se
    déclare une fois la candidature envoyée ; le défaire la rend à l'étape où elle en était.
    """
    if status == "todo":
        return ["applied"]
    if status == "applied":
        return ["interview", "rejected", "todo"]
    if status == "interview":
        return ["rejected", "applied"]
    return ["interview"] if had_interview else ["applied"]


def _read(job: Job) -> JobRead:
    read = JobRead.model_validate(job)
    read.next_statuses = next_statuses(job.status, job.interview_at is not None)
    return read


class JobService:
    def __init__(self, database: Database):
        self.database = database

    def list_jobs(self, user_id: int) -> list[JobRead]:
        """Renvoie les offres retenues de l'utilisateur, les plus récentes en premier."""
        with self.database.session() as session:
            return [_read(job) for job in JobRepository(session, user_id).list_jobs()]

    def set_status(self, user_id: int, job_id: int, status: JobStatus, now: datetime | None = None) -> JobRead:
        """Fait passer la candidature à cet état, et renvoie l'offre à jour, dates comprises.

        Chaque étape est datée quand elle est franchie, et sa date effacée quand on revient en arrière.
        Refuse un état que l'offre ne peut pas prendre depuis le sien.
        """
        now = now or datetime.now(UTC)
        with self.database.session() as session:
            jobs = JobRepository(session, user_id)
            job = jobs.get_job(job_id)
            if job is None:
                raise NotFoundError("Cette offre n'existe pas.")
            if status != job.status:
                if status not in next_statuses(job.status, job.interview_at is not None):
                    raise InvalidInputError("Cette offre ne peut pas passer à cet état depuis le sien.")
                reached_interview = status == "interview" or (status == "rejected" and job.interview_at is not None)
                jobs.set_tracking(
                    job_id,
                    status,
                    applied_at=None if status == "todo" else job.applied_at or now,
                    interview_at=(job.interview_at or now) if reached_interview else None,
                    rejected_at=now if status == "rejected" else None,
                )
            return _read(jobs.get_job(job_id))

    def delete_job(self, user_id: int, job_id: int) -> None:
        """Supprime l'offre."""
        if self.delete_jobs(user_id, [job_id]) == 0:
            raise NotFoundError("Cette offre n'existe pas.")

    def delete_jobs(self, user_id: int, job_ids: Iterable[int]) -> int:
        """Supprime les offres de la liste, et renvoie le nombre réellement supprimé."""
        with self.database.session() as session:
            return JobRepository(session, user_id).delete_jobs(job_ids)

    def list_rejected_jobs(self, user_id: int) -> list[RejectedJobRead]:
        """Renvoie les pages rejetées par le modèle pour cet utilisateur, les plus récentes en premier."""
        with self.database.session() as session:
            rejected_jobs = RejectedJobRepository(session, user_id).list_rejected_jobs()
            return [RejectedJobRead.model_validate(job) for job in rejected_jobs]
