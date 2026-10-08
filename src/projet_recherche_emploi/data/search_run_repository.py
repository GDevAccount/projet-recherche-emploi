from datetime import datetime

from sqlalchemy import func, insert, literal, select
from sqlalchemy.orm import Session

from projet_recherche_emploi.data.models import SearchRun


class SearchRunRepository:
    def __init__(self, session: Session, user_id: int):
        self.session = session
        # Chaque requête se limite aux lignes de cet utilisateur
        self.user_id = user_id

    def count_runs_since(self, since: datetime) -> int:
        """Renvoie le nombre de recherches lancées par l'utilisateur depuis cette date."""
        return self.session.scalar(self._count_since(since))

    def record_run(self, since: datetime | None = None, limit: int | None = None) -> bool:
        """Enregistre le lancement d'une recherche, et renvoie faux si le quota depuis cette date est atteint.

        Sans limite, le lancement est toujours enregistré.
        """
        if limit is None:
            self.session.execute(insert(SearchRun).values(user_id=self.user_id))
            return True

        # Le compte et l'insertion tiennent en une seule requête :
        # deux clics simultanés ne peuvent pas dépasser le quota
        allowed = select(literal(self.user_id)).where(self._count_since(since).scalar_subquery() < limit)
        statement = insert(SearchRun).from_select(["user_id"], allowed)
        return self.session.execute(statement).rowcount == 1

    def _count_since(self, since: datetime):
        return (
            select(func.count())
            .select_from(SearchRun)
            .where(SearchRun.user_id == self.user_id, SearchRun.created_at >= since)
        )
