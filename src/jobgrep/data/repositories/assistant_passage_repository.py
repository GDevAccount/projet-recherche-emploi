from collections.abc import Iterable, Mapping

from sqlalchemy import delete, insert, select
from sqlalchemy.orm import Session

from jobgrep.data.models import AssistantPassage


class AssistantPassageRepository:
    """Passages des textes du site : sans utilisateur, puisqu'aucune ligne ne vient de l'un d'eux."""

    def __init__(self, session: Session):
        self.session = session

    def list_passages(self) -> list[AssistantPassage]:
        """Renvoie tous les passages enregistrés, dans l'ordre de leur enregistrement."""
        return list(self.session.scalars(select(AssistantPassage).order_by(AssistantPassage.id)))

    def insert_passages(self, passages: Iterable[Mapping]) -> int:
        """Enregistre des passages avec leur vecteur, et renvoie leur nombre."""
        rows = [dict(passage) for passage in passages]
        if rows:
            self.session.execute(insert(AssistantPassage), rows)
        return len(rows)

    def delete_passages(self, ids: Iterable[int]) -> int:
        """Efface les passages désignés, et renvoie leur nombre."""
        ids = list(ids)
        if not ids:
            return 0
        return self.session.execute(delete(AssistantPassage).where(AssistantPassage.id.in_(ids))).rowcount
