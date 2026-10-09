from collections.abc import Mapping

from sqlalchemy import delete, insert, select
from sqlalchemy.orm import Session

from projet_recherche_emploi.data.models import Correction

INSERTED_FIELDS = (
    "kind",
    "url",
    "title",
    "query",
    "reason",
    "page_kind",
    "matches_search",
    "matches_contract",
    "matches_skills",
    "matches_level",
    "matches_location",
    "model_reason",
    "search_run_id",
    "model",
    "prompt_version",
)


class CorrectionRepository:
    def __init__(self, session: Session, user_id: int):
        self.session = session
        # Chaque requête se limite aux lignes de cet utilisateur
        self.user_id = user_id

    def insert_correction(self, correction: Mapping) -> None:
        """Enregistre une correction du tri."""
        values = {field: correction.get(field) for field in INSERTED_FIELDS}
        self.session.execute(insert(Correction).values(user_id=self.user_id, **values))

    def list_all(self) -> list[Correction]:
        """Renvoie toutes les corrections de l'utilisateur, dans l'ordre de leur enregistrement."""
        statement = select(Correction).where(Correction.user_id == self.user_id).order_by(Correction.id)
        return list(self.session.scalars(statement))

    def delete_all(self) -> int:
        """Efface toutes les corrections de l'utilisateur, et renvoie leur nombre."""
        return self.session.execute(delete(Correction).where(Correction.user_id == self.user_id)).rowcount
