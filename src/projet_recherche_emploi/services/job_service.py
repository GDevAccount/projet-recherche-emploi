from collections.abc import Iterable

from projet_recherche_emploi.data.database import Database
from projet_recherche_emploi.data.job_repository import JobRepository
from projet_recherche_emploi.data.rejected_job_repository import RejectedJobRepository
from projet_recherche_emploi.errors import NotFoundError
from projet_recherche_emploi.schemas import JobRead, RejectedJobRead


class JobService:
    def __init__(self, database: Database):
        self.database = database

    def list_jobs(self, user_id: int) -> list[JobRead]:
        """Renvoie les offres retenues de l'utilisateur, les plus récentes en premier."""
        with self.database.session() as session:
            return [JobRead.model_validate(job) for job in JobRepository(session, user_id).list_jobs()]

    def set_applied(self, user_id: int, url: str, applied: bool) -> None:
        """Marque l'offre comme postulée ou non."""
        with self.database.session() as session:
            if not JobRepository(session, user_id).set_applied(url, applied):
                raise NotFoundError("Cette offre n'existe pas.")

    def delete_jobs(self, user_id: int, urls: Iterable[str]) -> int:
        """Supprime les offres de la liste, et renvoie le nombre réellement supprimé."""
        with self.database.session() as session:
            return JobRepository(session, user_id).delete_jobs(urls)

    def list_rejected_jobs(self, user_id: int) -> list[RejectedJobRead]:
        """Renvoie les pages rejetées par le modèle pour cet utilisateur, les plus récentes en premier."""
        with self.database.session() as session:
            rejected_jobs = RejectedJobRepository(session, user_id).list_rejected_jobs()
            return [RejectedJobRead.model_validate(job) for job in rejected_jobs]
