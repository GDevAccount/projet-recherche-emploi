from collections.abc import Mapping
from datetime import datetime

from sqlalchemy import delete, func, insert, literal, select, update
from sqlalchemy.orm import Session

from projet_recherche_emploi.data.models import SearchRun

# État d'un lancement à son enregistrement : c'est le service qui le fait passer à la suite
RUN_RUNNING = "running"


class SearchRunRepository:
    def __init__(self, session: Session, user_id: int):
        self.session = session
        # Chaque requête se limite aux lignes de cet utilisateur
        self.user_id = user_id

    def count_runs_since(self, since: datetime) -> int:
        """Renvoie le nombre de recherches lancées par l'utilisateur depuis cette date."""
        return self.session.scalar(self._count_since(since))

    def record_run(self, since: datetime | None = None, limit: int | None = None) -> int | None:
        """Enregistre le lancement d'une recherche et renvoie son identifiant, ou None si le quota est atteint.

        Le quota se compte depuis la date donnée. Sans limite, le lancement est toujours enregistré.
        """
        if limit is None:
            result = self.session.execute(insert(SearchRun).values(user_id=self.user_id, status=RUN_RUNNING))
            return result.inserted_primary_key[0]

        # Le compte et l'insertion tiennent en une seule requête :
        # deux clics simultanés ne peuvent pas dépasser le quota
        allowed = select(literal(self.user_id), literal(RUN_RUNNING)).where(
            self._count_since(since).scalar_subquery() < limit
        )
        result = self.session.execute(insert(SearchRun).from_select(["user_id", "status"], allowed))
        return result.lastrowid if result.rowcount == 1 else None

    def finish_run(self, run_id: int, values: Mapping) -> bool:
        """Écrit le bilan d'un lancement, et renvoie faux s'il n'existe pas pour cet utilisateur."""
        statement = update(SearchRun).where(SearchRun.id == run_id, SearchRun.user_id == self.user_id).values(**values)
        return self.session.execute(statement).rowcount == 1

    def get_run(self, run_id: int) -> SearchRun | None:
        """Renvoie ce lancement, ou None s'il n'existe pas pour cet utilisateur."""
        return self.session.scalar(select(SearchRun).where(SearchRun.id == run_id, SearchRun.user_id == self.user_id))

    def list_runs(self, limit: int | None = None) -> list[SearchRun]:
        """Renvoie les derniers lancements de l'utilisateur, le plus récent en premier ; tous, sans limite."""
        statement = (
            select(SearchRun).where(SearchRun.user_id == self.user_id).order_by(SearchRun.id.desc()).limit(limit)
        )
        return list(self.session.scalars(statement))

    def _count_since(self, since: datetime):
        return (
            select(func.count())
            .select_from(SearchRun)
            .where(SearchRun.user_id == self.user_id, SearchRun.created_at >= since)
        )

    def delete_all(self) -> int:
        """Efface tous les lancements de recherche de l'utilisateur, et renvoie leur nombre."""
        return self.session.execute(delete(SearchRun).where(SearchRun.user_id == self.user_id)).rowcount
