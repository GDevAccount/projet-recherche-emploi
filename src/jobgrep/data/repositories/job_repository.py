from collections.abc import Iterable, Mapping
from datetime import datetime

from sqlalchemy import delete, false, select, update
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from jobgrep.data.models import Job

INSERTED_FIELDS = ("url", "title", "content", "score", "contract_type", "work_location", "query", "match_reason")


class JobRepository:
    def __init__(self, session: Session, user_id: int):
        self.session = session
        # Chaque requête se limite aux lignes de cet utilisateur
        self.user_id = user_id

    def insert_jobs(self, jobs: Iterable[Mapping]) -> int:
        """Insère les offres et renvoie le nombre réellement ajouté (hors doublons d'URL)."""
        inserted = 0
        for job in jobs:
            values = {field: job.get(field) for field in INSERTED_FIELDS}
            # Utilisateur + URL est unique : une offre déjà en base est ignorée
            statement = (
                insert(Job)
                .values(user_id=self.user_id, **values)
                .on_conflict_do_nothing(index_elements=["user_id", "url"])
            )
            inserted += self.session.execute(statement).rowcount
        return inserted

    def list_jobs(self) -> list[Job]:
        """Renvoie les offres non supprimées, les plus récentes en premier."""
        statement = (
            select(Job)
            .where(Job.user_id == self.user_id, Job.deleted == false())
            .order_by(Job.created_at.desc(), Job.id.desc())
        )
        return list(self.session.scalars(statement))

    def list_all(self) -> list[Job]:
        """Renvoie toutes les offres retenues, supprimées comprises, pour en mesurer le devenir."""
        return list(self.session.scalars(select(Job).where(Job.user_id == self.user_id).order_by(Job.id)))

    def get_job(self, job_id: int) -> Job | None:
        """Renvoie l'offre, ou None si elle est inconnue ou supprimée."""
        statement = (
            select(Job)
            .where(Job.user_id == self.user_id, Job.id == job_id, Job.deleted == false())
            # L'offre a pu être modifiée dans cette session : on relit la ligne, pas l'objet déjà chargé
            .execution_options(populate_existing=True)
        )
        return self.session.scalar(statement)

    def get_job_by_url(self, url: str) -> Job | None:
        """Renvoie l'offre à cette adresse, ou None si elle est inconnue ou supprimée."""
        statement = select(Job).where(Job.user_id == self.user_id, Job.url == url, Job.deleted == false())
        return self.session.scalar(statement)

    def list_known_urls(self) -> set[str]:
        """Renvoie les URL de toutes les offres en base, y compris celles supprimées."""
        return set(self.session.scalars(select(Job.url).where(Job.user_id == self.user_id)))

    def mark_opened(self, job_id: int, now: datetime) -> bool:
        """Date la première ouverture de l'annonce, et renvoie faux si elle l'était déjà ou si l'offre est inconnue."""
        statement = (
            update(Job)
            .where(Job.id == job_id, Job.user_id == self.user_id, Job.opened_at.is_(None))
            .values(opened_at=now)
        )
        return self.session.execute(statement).rowcount == 1

    def set_tracking(
        self,
        job_id: int,
        status: str,
        applied_at: datetime | None,
        interview_at: datetime | None,
        rejected_at: datetime | None,
    ) -> bool:
        """Enregistre l'état de la candidature et la date de chaque étape, et renvoie faux si l'offre est inconnue.

        Une offre supprimée est inconnue. Le dépôt écrit ce qu'on lui donne : quel état peut suivre quel autre
        est décidé par JobService.
        """
        statement = (
            update(Job)
            .where(Job.user_id == self.user_id, Job.id == job_id, Job.deleted == false())
            .values(status=status, applied_at=applied_at, interview_at=interview_at, rejected_at=rejected_at)
        )
        return self.session.execute(statement).rowcount == 1

    def delete_jobs(self, job_ids: Iterable[int]) -> int:
        """Supprime les offres de la liste, et renvoie le nombre réellement supprimé."""
        # La ligne est conservée : son URL empêche l'offre de revenir à la recherche suivante
        statement = (
            update(Job)
            .where(Job.user_id == self.user_id, Job.id.in_(list(job_ids)), Job.deleted == false())
            .values(deleted=True)
        )
        return self.session.execute(statement).rowcount

    def delete_all(self) -> int:
        """Efface pour de bon toutes les offres de l'utilisateur, supprimées comprises, et renvoie leur nombre."""
        return self.session.execute(delete(Job).where(Job.user_id == self.user_id)).rowcount
