from datetime import datetime

from sqlalchemy import Row, delete, distinct, func, insert, literal, select
from sqlalchemy.orm import Session

from projet_recherche_emploi.data.models import ClientError, SearchRun, ServerError

RUNNING = "running"


class HealthRepository:
    """Échecs et erreurs de tous les comptes, pour les administrateurs : sans utilisateur, comme UsageRepository.

    Il ne rend que des nombres, des types d'erreur et des dates, jamais une ligne d'un utilisateur. Ne rien y
    ajouter qui en sorte.
    """

    def __init__(self, session: Session):
        self.session = session

    def ping(self) -> bool:
        """Dit si la base répond, en lui faisant lire une table."""
        self.session.execute(select(literal(1)).select_from(ServerError).limit(1))
        return True

    def record_error(
        self, user_id: int | None, method: str, route: str | None, status_code: int, error_type: str
    ) -> None:
        """Enregistre une erreur rendue par l'API. L'appelant peut ne pas avoir été identifié."""
        self.session.execute(
            insert(ServerError).values(
                user_id=user_id, method=method, route=route, status_code=status_code, error_type=error_type
            )
        )

    def record_client_error(self, user_id: int, route: str | None, error_type: str, source: str | None) -> None:
        """Enregistre une erreur survenue dans le navigateur de ce compte."""
        self.session.execute(
            insert(ClientError).values(user_id=user_id, route=route, error_type=error_type, source=source)
        )

    def count_client_errors(self, user_id: int, since: datetime) -> int:
        """Renvoie le nombre d'erreurs du front signalées par ce compte depuis cette date."""
        statement = select(func.count()).where(ClientError.user_id == user_id, ClientError.created_at >= since)
        return self.session.scalar(statement)

    def delete_errors_before(self, limit: datetime) -> int:
        """Efface les erreurs du serveur et du front antérieures à cette date, et renvoie leur nombre."""
        return sum(
            self.session.execute(delete(table).where(table.created_at < limit)).rowcount
            for table in (ServerError, ClientError)
        )

    def forget_user(self, user_id: int) -> int:
        """Efface les erreurs du serveur et du front rencontrées par ce compte, et renvoie leur nombre."""
        return sum(
            self.session.execute(delete(table).where(table.user_id == user_id)).rowcount
            for table in (ServerError, ClientError)
        )

    def summarize_client_errors(self, since: datetime | None = None) -> list[Row]:
        """Renvoie, par écran, type et emplacement, le nombre d'erreurs du front, leurs comptes et la dernière."""
        statement = (
            select(
                ClientError.route,
                ClientError.error_type,
                ClientError.source,
                func.count().label("count"),
                func.count(distinct(ClientError.user_id)).label("accounts"),
                func.max(ClientError.created_at).label("last_at"),
            )
            .group_by(ClientError.route, ClientError.error_type, ClientError.source)
            .order_by(func.count().desc(), ClientError.route, ClientError.error_type, ClientError.source)
        )
        if since is not None:
            statement = statement.where(ClientError.created_at >= since)
        return list(self.session.execute(statement))

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
