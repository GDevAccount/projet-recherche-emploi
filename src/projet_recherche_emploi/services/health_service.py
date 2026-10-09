import logging
from datetime import UTC, datetime, timedelta

from projet_recherche_emploi.config import SERVER_ERROR_DAYS
from projet_recherche_emploi.data.database import Database
from projet_recherche_emploi.data.repositories.health_repository import HealthRepository
from projet_recherche_emploi.schemas import HealthOverview, RunFailureGroup, ServerErrorGroup
from projet_recherche_emploi.services.search_service import UNKNOWN_LABEL, SearchService, rate

logger = logging.getLogger(__name__)

FAILED = "failed"
# À partir de ce code, c'est le serveur qui est en faute, pas la demande
FIRST_FAILURE_STATUS = 500


class HealthService:
    """Santé de l'instance, pour les administrateurs : comme UsageService, il ne prend pas d'utilisateur.

    C'est à l'interface de n'y laisser lire qu'un administrateur (AuthService.is_admin).
    """

    def __init__(self, database: Database, search: SearchService):
        self.database = database
        self.search = search

    def record_error(
        self,
        user_id: int | None,
        method: str,
        route: str | None,
        status_code: int,
        error_type: str,
        now: datetime | None = None,
    ) -> None:
        """Garde la trace d'une erreur rendue par l'API, et oublie celles de plus de SERVER_ERROR_DAYS.

        Seul le type de l'erreur est gardé : son message peut contenir ce que l'utilisateur a envoyé. Ne lève
        jamais : la réponse d'erreur doit partir même si la base ne répond plus.
        """
        limit = (now or datetime.now(UTC)) - timedelta(days=SERVER_ERROR_DAYS)
        try:
            with self.database.session() as session:
                repository = HealthRepository(session)
                repository.record_error(user_id, method, route, status_code, error_type)
                repository.delete_errors_before(limit)
        except Exception:
            logger.exception("L'erreur %s de %s %s n'a pas pu être enregistrée", error_type, method, route)

    def get_overview(self, days: int | None = None, now: datetime | None = None) -> HealthOverview:
        """Renvoie ce qui a échoué sur l'instance, tous comptes réunis. Sans nombre de jours, tout est compté."""
        since = None if days is None else (now or datetime.now(UTC)) - timedelta(days=days)
        with self.database.session() as session:
            repository = HealthRepository(session)
            run_rows = repository.summarize_runs(since)
            unfinished = repository.list_unfinished_runs(since)
            error_rows = repository.summarize_errors(since)

        # Le dernier lancement d'un compte qui cherche tourne encore : tout autre resté « en cours » a été coupé
        last_unfinished = {run.user_id: run.id for run in unfinished}
        interrupted = [
            run
            for run in unfinished
            if not (run.id == last_unfinished[run.user_id] and self.search.is_running(run.user_id))
        ]
        run_failures = [
            RunFailureGroup(
                error_type=row.error or UNKNOWN_LABEL, count=row.count, accounts=row.accounts, last_at=row.last_at
            )
            for row in run_rows
            if row.status == FAILED
        ]
        server_errors = [
            ServerErrorGroup(
                method=row.method,
                route=row.route,
                status_code=row.status_code,
                error_type=row.error_type,
                is_failure=row.status_code >= FIRST_FAILURE_STATUS,
                count=row.count,
                accounts=row.accounts,
                last_at=row.last_at,
            )
            for row in error_rows
        ]
        # Le tri est stable : dans chaque moitié, l'ordre du dépôt reste, le plus fréquent en premier
        server_errors.sort(key=lambda group: not group.is_failure)

        runs = sum(row.count for row in run_rows)
        failed_runs = sum(group.count for group in run_failures)
        failures = sum(group.count for group in server_errors if group.is_failure)
        incidents = failed_runs + len(interrupted) + failures
        return HealthOverview(
            since=since,
            incidents=incidents,
            healthy=incidents == 0,
            runs=runs,
            failed_runs=failed_runs,
            interrupted_runs=len(interrupted),
            failure_rate=rate(failed_runs + len(interrupted), runs),
            interrupted_accounts=len({run.user_id for run in interrupted}),
            last_interrupted_at=max((run.created_at for run in interrupted), default=None),
            run_failures=run_failures,
            failures=failures,
            refusals=sum(group.count for group in server_errors if not group.is_failure),
            server_errors=server_errors,
        )
