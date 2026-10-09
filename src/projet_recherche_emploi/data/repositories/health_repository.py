from datetime import datetime

from sqlalchemy import Row, delete, distinct, func, insert, select
from sqlalchemy.orm import Session

from projet_recherche_emploi.data.models import SearchRun, ServerError

RUNNING = "running"


class HealthRepository:
    """Échecs et erreurs de tous les comptes, pour les administrateurs : sans utilisateur, comme UsageRepository.

    Il ne rend que des nombres, des types d'erreur et des dates, jamais une ligne d'un utilisateur. Ne rien y
    ajouter qui en sorte.
    """

    def __init__(self, session: Session):
        self.session = session

    def record_error(
        self, user_id: int | None, method: str, route: str | None, status_code: int, error_type: str
    ) -> None:
        """Enregistre une erreur rendue par l'API. L'appelant peut ne pas avoir été identifié."""
        self.session.execute(
            insert(ServerError).values(
                user_id=user_id, method=method, route=route, status_code=status_code, error_type=error_type
            )
        )

    def delete_errors_before(self, limit: datetime) -> int:
        """Efface les erreurs antérieures à cette date, et renvoie leur nombre."""
        return self.session.execute(delete(ServerError).where(ServerError.created_at < limit)).rowcount

    def forget_user(self, user_id: int) -> int:
        """Efface les erreurs rencontrées par ce compte, et renvoie leur nombre."""
        return self.session.execute(delete(ServerError).where(ServerError.user_id == user_id)).rowcount

    def summarize_errors(self, since: datetime | None = None) -> list[Row]:
        """Renvoie, par route et par type d'erreur, leur nombre, les comptes touchés et la date de la dernière."""
        statement = (
            select(
                ServerError.method,
                ServerError.route,
                ServerError.status_code,
                ServerError.error_type,
                func.count().label("count"),
                func.count(distinct(ServerError.user_id)).label("accounts"),
                func.max(ServerError.created_at).label("last_at"),
            )
            .group_by(ServerError.method, ServerError.route, ServerError.status_code, ServerError.error_type)
            .order_by(func.count().desc(), ServerError.route, ServerError.method, ServerError.error_type)
        )
        if since is not None:
            statement = statement.where(ServerError.created_at >= since)
        return list(self.session.execute(statement))

    def summarize_runs(self, since: datetime | None = None) -> list[Row]:
        """Renvoie, par état et par type d'erreur, le nombre de lancements, leurs comptes et la date du dernier."""
        statement = (
            select(
                SearchRun.status,
                SearchRun.error,
                func.count().label("count"),
                func.count(distinct(SearchRun.user_id)).label("accounts"),
                func.max(SearchRun.created_at).label("last_at"),
            )
            # Un lancement d'avant le suivi n'a que sa date
            .where(SearchRun.status.is_not(None))
            .group_by(SearchRun.status, SearchRun.error)
            .order_by(func.count().desc(), SearchRun.error)
        )
        if since is not None:
            statement = statement.where(SearchRun.created_at >= since)
        return list(self.session.execute(statement))

    def list_unfinished_runs(self, since: datetime | None = None) -> list[Row]:
        """Renvoie le compte, l'identifiant et la date des lancements restés « en cours », le plus ancien en premier."""
        statement = (
            select(SearchRun.user_id, SearchRun.id, SearchRun.created_at)
            .where(SearchRun.status == RUNNING)
            .order_by(SearchRun.id)
        )
        if since is not None:
            statement = statement.where(SearchRun.created_at >= since)
        return list(self.session.execute(statement))
