from collections.abc import Iterable

from sqlalchemy import case, select
from sqlalchemy.orm import Session

from jobgrep.data.models import Skill


class SkillRepository:
    """Référentiel des compétences : sans utilisateur, puisqu'aucune ligne ne vient de l'un d'eux."""

    def __init__(self, session: Session):
        self.session = session

    def search(self, folded_text: str, limit: int) -> list[Skill]:
        """Renvoie les compétences qui contiennent ce texte, déjà mis sous sa forme de recherche (fold_skill).

        Celles qui commencent par lui d'abord, puis celles dont un mot commence par lui, puis les autres.
        """
        rank = case(
            (Skill.search_name.startswith(folded_text, autoescape=True), 0),
            (Skill.search_name.contains(f" {folded_text}", autoescape=True), 1),
            else_=2,
        )
        statement = (
            select(Skill)
            .where(Skill.search_name.contains(folded_text, autoescape=True))
            .order_by(rank, Skill.search_name)
            .limit(limit)
        )
        return list(self.session.scalars(statement))

    def find(self, folded_names: Iterable[str]) -> list[Skill]:
        """Renvoie les compétences du référentiel qui portent l'un de ces noms, sous leur forme de recherche."""
        folded_names = list(folded_names)
        if not folded_names:
            return []
        return list(self.session.scalars(select(Skill).where(Skill.search_name.in_(folded_names))))
