import logging
import threading
from datetime import UTC, date, datetime, timedelta

from jobgrep.config import (
    ASSISTANT_MESSAGE_DAYS,
    DEFAULT_PLAN,
    INACTIVE_ACCOUNT_DAYS,
    SERVER_ERROR_DAYS,
    TRIAL_ACCOUNT_DAYS,
    TRIAL_PLAN,
    TRIAL_START_DAYS,
)
from jobgrep.data.database import Database
from jobgrep.data.repositories.activity_repository import ActivityRepository
from jobgrep.data.repositories.assistant_message_repository import (
    AssistantJournalRepository,
    AssistantMessageRepository,
)
from jobgrep.data.repositories.correction_repository import CorrectionRepository
from jobgrep.data.repositories.cv_text_repository import CvTextRepository
from jobgrep.data.repositories.engine_call_repository import EngineCallRepository
from jobgrep.data.repositories.health_repository import HealthRepository
from jobgrep.data.repositories.job_repository import JobRepository
from jobgrep.data.repositories.page_evaluation_repository import PageEvaluationRepository
from jobgrep.data.repositories.query_repository import QueryRepository
from jobgrep.data.repositories.rejected_job_repository import RejectedJobRepository
from jobgrep.data.repositories.search_run_repository import SearchRunRepository
from jobgrep.data.repositories.usage_repository import UsageRepository
from jobgrep.data.repositories.user_repository import UserRepository
from jobgrep.errors import ConflictError
from jobgrep.services.search_service import SearchService

logger = logging.getLogger(__name__)


class AccountService:
    def __init__(self, database: Database, search: SearchService):
        self.database = database
        self.search = search
        self._last_purge_day: date | None = None
        self._purge_lock = threading.Lock()

    def delete_account(self, user_id: int) -> None:
        """Efface tout ce que l'application garde de l'utilisateur : CV, recherches, offres, rejets, adresse.

        Rien n'est récupérable ensuite. Seule reste sa consommation, en totaux mensuels que rien ne relie
        à lui : le coût de l'instance doit rester connu après son départ. Le propriétaire garde son
        identifiant, réservé, mais perd ses données
        comme un autre ; un invité encore autorisé qui se reconnecte reçoit un compte neuf.
        """
        # Une recherche en cours écrirait ses offres après l'effacement
        if self.search.is_running(user_id):
            raise ConflictError("Une recherche est en cours : attendez qu'elle se termine pour supprimer le compte.")

        with self.database.session() as session:
            CvTextRepository(session, user_id).delete()
            JobRepository(session, user_id).delete_all()
            RejectedJobRepository(session, user_id).clear()
            QueryRepository(session, user_id).delete_all()
            # Avant d'effacer les lancements et les questions à l'assistant : ce qu'ils ont consommé reste,
            # en totaux mensuels sans adresse
            plan = TRIAL_PLAN if UserRepository(session).is_trial(user_id) else DEFAULT_PLAN
            deleted_at = datetime.now(UTC)
            UsageRepository(session).archive_account(user_id, plan, deleted_at)
            UsageRepository(session).archive_assistant(user_id, plan, deleted_at)
            SearchRunRepository(session, user_id).delete_all()
            AssistantMessageRepository(session, user_id).delete_all()
            PageEvaluationRepository(session, user_id).delete_all()
            CorrectionRepository(session, user_id).delete_all()
            EngineCallRepository(session, user_id).delete_all()
            HealthRepository(session).forget_user(user_id)
            ActivityRepository(session, user_id).delete_all()
            UserRepository(session).forget_user(user_id)
        # Les copies d'avant migration contiennent encore ses données : elles restent, sans lui
        self.database.purge_user_from_backups(user_id)

    def delete_inactive_accounts_if_due(self, now: datetime | None = None) -> None:
        """Supprime les comptes inactifs et ce dont la durée de conservation est passée, une fois par jour au plus.

        Faute de tâche planifiée, c'est le démarrage et chaque requête identifiée qui passent par ici : une
        machine mise en veille reprend sans redémarrer, le démarrage seul ne suffirait pas. Un échec est
        journalisé sans interrompre l'appelant, et retenté le lendemain ou au redémarrage suivant.
        """
        now = now or datetime.now(UTC)
        with self._purge_lock:
            if self._last_purge_day == now.date():
                return
            self._last_purge_day = now.date()
        try:
            self.delete_inactive_accounts(now)
        except Exception:
            logger.exception("La suppression des comptes inactifs a échoué")
        # À part : l'échec de l'une ne doit pas empêcher l'autre
        try:
            self.forget_expired_records(now)
        except Exception:
            logger.exception("L'effacement des données dont la durée de conservation est passée a échoué")

    def forget_expired_records(self, now: datetime | None = None) -> int:
        """Efface ce que les règles de confidentialité promettent d'effacer à date fixe, et renvoie le nombre de lignes.

        Le texte des questions à l'assistant, les erreurs rencontrées et les ouvertures d'essais sont aussi
        effacés quand une ligne du même genre s'écrit, mais cela ne suffit pas : sans question, sans erreur
        ou sans essai, rien ne partirait. Les copies d'avant migration sont nettoyées de même.
        """
        now = now or datetime.now(UTC)
        texts_before = now - timedelta(days=ASSISTANT_MESSAGE_DAYS)
        errors_before = now - timedelta(days=SERVER_ERROR_DAYS)
        trial_starts_before = now - timedelta(days=TRIAL_START_DAYS)
        with self.database.session() as session:
            forgotten = AssistantJournalRepository(session).forget_texts_before(texts_before)
            forgotten += HealthRepository(session).delete_errors_before(errors_before)
            forgotten += UserRepository(session).forget_trial_starts(trial_starts_before)
        self.database.purge_expired_from_backups(texts_before, errors_before, trial_starts_before)
        return forgotten

    def delete_inactive_accounts(self, now: datetime | None = None) -> int:
        """Supprime les comptes sans activité depuis INACTIVE_ACCOUNT_DAYS, et renvoie leur nombre.

        Le propriétaire n'est jamais concerné. Un utilisateur retiré de ALLOWED_EMAILS, qui ne peut plus
        se connecter, finit donc par être effacé sans avoir à le demander. Un compte d'essai, lui, part
        TRIAL_ACCOUNT_DAYS après son ouverture, actif ou non : son cookie a expiré, personne n'y reviendra.
        """
        now = now or datetime.now(UTC)
        with self.database.session() as session:
            users = UserRepository(session)
            inactive_ids = users.list_inactive_user_ids(now - timedelta(days=INACTIVE_ACCOUNT_DAYS))
            trial_ids = users.list_expired_trial_user_ids(now - timedelta(days=TRIAL_ACCOUNT_DAYS))
        for user_id in inactive_ids:
            self.delete_account(user_id)
            # L'identifiant seul : l'adresse vient d'être effacée, elle n'a rien à faire dans les logs
            logger.info("Compte %d supprimé après %d jours sans activité", user_id, INACTIVE_ACCOUNT_DAYS)
        for user_id in trial_ids:
            self.delete_account(user_id)
            logger.info("Compte d'essai %d supprimé %d jours après son ouverture", user_id, TRIAL_ACCOUNT_DAYS)
        return len(inactive_ids) + len(trial_ids)
