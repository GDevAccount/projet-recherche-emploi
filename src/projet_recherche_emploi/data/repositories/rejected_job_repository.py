from collections.abc import Iterable, Mapping

from sqlalchemy import delete, false, or_, select, true
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from projet_recherche_emploi.data.models import RejectedJob

INSERTED_FIELDS = (
    "url",
    "title",
    "contract_type",
    "work_location",
    "query",
    "is_real_offer",
    "page_kind",
    "matches_cv",
    "matches_search",
    "matches_contract",
    "matches_skills",
    "matches_level",
    "matches_location",
    "reject_reason",
)


class RejectedJobRepository:
    def __init__(self, session: Session, user_id: int):
        self.session = session
        # Chaque requête se limite aux lignes de cet utilisateur
        self.user_id = user_id

    def insert_rejected_jobs(self, jobs: Iterable[Mapping]) -> int:
        """Enregistre les pages rejetées et renvoie le nombre réellement ajouté (hors doublons d'URL)."""
        inserted = 0
        for job in jobs:
            values = {field: job.get(field) for field in INSERTED_FIELDS}
            # Utilisateur + URL est la clé primaire : une page déjà rejetée est ignorée
            statement = insert(RejectedJob).values(user_id=self.user_id, **values).on_conflict_do_nothing()
            inserted += self.session.execute(statement).rowcount
        return inserted

    def list_rejected_jobs(self) -> list[RejectedJob]:
        """Renvoie toutes les pages rejetées, les plus récentes en premier."""
        statement = (
            select(RejectedJob).where(RejectedJob.user_id == self.user_id).order_by(RejectedJob.created_at.desc())
        )
        return list(self.session.scalars(statement))

    def get_rejected_job(self, url: str) -> RejectedJob | None:
        """Renvoie la page rejetée à cette adresse, ou None si elle est inconnue."""
        statement = select(RejectedJob).where(RejectedJob.user_id == self.user_id, RejectedJob.url == url)
        return self.session.scalar(statement)

    def delete_rejected_job(self, url: str) -> bool:
        """Oublie le rejet de cette page, et renvoie faux si elle est inconnue."""
        statement = delete(RejectedJob).where(RejectedJob.user_id == self.user_id, RejectedJob.url == url)
        return self.session.execute(statement).rowcount == 1

    def list_known_urls(self) -> set[str]:
        """Renvoie les URL de toutes les pages déjà rejetées."""
        return set(self.session.scalars(select(RejectedJob.url).where(RejectedJob.user_id == self.user_id)))

    def clear(self) -> int:
        """Oublie tous les rejets de l'utilisateur, et renvoie le nombre de pages qui seront réévaluées."""
        return self.session.execute(delete(RejectedJob).where(RejectedJob.user_id == self.user_id)).rowcount

    def clear_search_dependent_rejections(self) -> int:
        """Oublie les rejets qui ne tiennent qu'aux recherches enregistrées : métier, contrat ou lieu.

        Renvoie le nombre de pages qui seront réévaluées. Les rejets dus au CV restent.
        """
        statement = delete(RejectedJob).where(
            RejectedJob.user_id == self.user_id,
            RejectedJob.is_real_offer == true(),
            RejectedJob.matches_cv == true(),
            or_(
                RejectedJob.matches_search == false(),
                RejectedJob.matches_contract == false(),
                RejectedJob.matches_location == false(),
            ),
        )
        return self.session.execute(statement).rowcount
