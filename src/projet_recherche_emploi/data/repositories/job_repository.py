from collections.abc import Iterable, Mapping

from sqlalchemy import delete, false, func, select, update
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from projet_recherche_emploi.data.models import Job

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

    def get_job(self, job_id: int) -> Job | None:
        """Renvoie l'offre, ou None si elle est inconnue ou supprimée."""
        statement = (
            select(Job)
            .where(Job.user_id == self.user_id, Job.id == job_id, Job.deleted == false())
            # L'offre a pu être modifiée dans cette session : on relit la ligne, pas l'objet déjà chargé
            .execution_options(populate_existing=True)
        )
        return self.session.scalar(statement)

    def list_known_urls(self) -> set[str]:
        """Renvoie les URL de toutes les offres en base, y compris celles supprimées."""
        return set(self.session.scalars(select(Job.url).where(Job.user_id == self.user_id)))

    def set_applied(self, job_id: int, applied: bool) -> bool:
        """Marque l'offre comme postulée ou non, et renvoie faux si elle est inconnue ou supprimée."""
        statement = (
            update(Job)
            .where(Job.user_id == self.user_id, Job.id == job_id, Job.deleted == false())
            # applied_at est daté quand on postule, et vidé quand on décoche
            .values(applied=applied, applied_at=func.current_timestamp() if applied else None)
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
