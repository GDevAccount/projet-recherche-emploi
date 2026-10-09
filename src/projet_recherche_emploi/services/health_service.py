import logging
from datetime import UTC, datetime, timedelta

from projet_recherche_emploi.config import (
    BUDGET_ALERT_FIRST_DAY,
    DAILY_COST_ALERT_USD,
    DEFAULT_USER_ID,
    INTERRUPTION_ALERT_MINUTES,
    SERVER_ERROR_DAYS,
)
from projet_recherche_emploi.data.database import Database
from projet_recherche_emploi.data.repositories.health_repository import HealthRepository
from projet_recherche_emploi.schemas import HealthOverview, RunFailureGroup, ServerErrorGroup
from projet_recherche_emploi.services.alert_service import AlertService
from projet_recherche_emploi.services.search_service import UNKNOWN_LABEL, SearchService, rate
from projet_recherche_emploi.services.usage_service import UsageService

logger = logging.getLogger(__name__)

FAILED = "failed"
# À partir de ce code, c'est le serveur qui est en faute, pas la demande
FIRST_FAILURE_STATUS = 500


class HealthService:
    """Santé de l'instance, pour les administrateurs : comme UsageService, il ne prend pas d'utilisateur.

    C'est à l'interface de n'y laisser lire qu'un administrateur (AuthService.is_admin).
    """

    def __init__(self, database: Database, search: SearchService, usage: UsageService, alerts: AlertService):
        self.database = database
        self.search = search
        self.usage = usage
        self.alerts = alerts

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
        # Après l'enregistrement, et même s'il a échoué : une base qui ne répond plus est justement une panne
        if status_code >= FIRST_FAILURE_STATUS:
            where = f"{method} {route}" if route else "une route inconnue"
            self.alerts.notify(f"error:{method}:{route}:{error_type}", "Panne du serveur", f"{error_type} sur {where}")

    def search_closed(self, user_id: int, status: str, error: str | None = None) -> None:
        """Prévient d'une recherche échouée, et d'un coût anormal sur les dernières 24 heures. Ne lève jamais.

        Appelé par SearchService à la fin de chaque lancement, réussi ou non.
        """
        try:
            if status == FAILED:
                whose = "du propriétaire" if user_id == DEFAULT_USER_ID else "d'un invité"
                self.alerts.notify(
                    f"search:{error}", "Recherche échouée", f"{error or UNKNOWN_LABEL} pendant une recherche {whose}"
                )
            if self.alerts.enabled:
                self._alert_on_daily_cost()
                self._alert_on_budget()
        except Exception:
            logger.exception("L'alerte de fin de recherche a échoué")

    def _alert_on_daily_cost(self) -> None:
        overview = self.usage.get_overview(days=1)
        # Sans tarif connu pour le modèle, il reste le coût du moteur de recherche : un plancher
        cost = overview.search_cost_usd if overview.cost_usd is None else overview.cost_usd
        if cost >= DAILY_COST_ALERT_USD:
            message = f"{cost:.2f} $ en 24 heures pour {overview.runs} recherches, tous comptes réunis"
            self.alerts.notify("cost", "Coût anormal", message, quiet=timedelta(days=1))

    def _alert_on_budget(self) -> None:
        budget = self.usage.get_budget()
        # Le mois est dans la clé : le délai d'un mois ne retient pas l'alerte du mois suivant
        month = budget.month_start.isoformat()
        if budget.over_budget:
            message = f"{budget.spent_usd:.2f} $ dépensés ce mois-ci pour un budget de {budget.budget_usd:.2f} $"
            self.alerts.notify(f"budget:spent:{month}", "Budget dépassé", message, quiet=timedelta(days=31))
        elif budget.projected_over_budget and budget.day_of_month >= BUDGET_ALERT_FIRST_DAY:
            message = (
                f"À ce rythme, {budget.projected_usd:.2f} $ en fin de mois pour un budget de {budget.budget_usd:.2f} $"
            )
            self.alerts.notify(f"budget:projection:{month}", "Budget menacé", message, quiet=timedelta(days=7))

    def alert_on_interrupted_runs(self, now: datetime | None = None) -> int:
        """Prévient des recherches que ce démarrage du serveur vient de couper, et renvoie leur nombre.

        À appeler au démarrage, quand aucune recherche ne tourne encore. Ne lève jamais.
        """
        since = (now or datetime.now(UTC)) - timedelta(minutes=INTERRUPTION_ALERT_MINUTES)
        try:
            with self.database.session() as session:
                interrupted = len(HealthRepository(session).list_unfinished_runs(since))
        except Exception:
            logger.exception("Les recherches interrompues n'ont pas pu être comptées")
            return 0
        if interrupted:
            message = f"{interrupted} recherche(s) coupée(s) par un redémarrage du serveur"
            self.alerts.notify("interrupted", "Recherche interrompue", message)
        return interrupted

    def send_test_alert(self) -> bool:
        """Envoie une alerte d'essai, et dit si elle est partie : faux aussi quand aucune alerte n'est réglée."""
        return self.alerts.send_test()

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
            alerts_enabled=self.alerts.enabled,
        )
