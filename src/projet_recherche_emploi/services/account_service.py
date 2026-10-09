import logging
import threading
from datetime import UTC, date, datetime, timedelta

from projet_recherche_emploi.config import INACTIVE_ACCOUNT_DAYS
from projet_recherche_emploi.data.database import Database
from projet_recherche_emploi.data.repositories.cv_text_repository import CvTextRepository
from projet_recherche_emploi.data.repositories.job_repository import JobRepository
from projet_recherche_emploi.data.repositories.page_evaluation_repository import PageEvaluationRepository
from projet_recherche_emploi.data.repositories.query_repository import QueryRepository
from projet_recherche_emploi.data.repositories.rejected_job_repository import RejectedJobRepository
from projet_recherche_emploi.data.repositories.search_run_repository import SearchRunRepository
from projet_recherche_emploi.data.repositories.user_repository import UserRepository
from projet_recherche_emploi.errors import ConflictError
from projet_recherche_emploi.services.search_service import SearchService

logger = logging.getLogger(__name__)


class AccountService:
    def __init__(self, database: Database, search: SearchService):
        self.database = database
        self.search = search
        self._last_purge_day: date | None = None
        self._purge_lock = threading.Lock()

    def delete_account(self, user_id: int) -> None:
        """Efface tout ce que l'application garde de l'utilisateur : CV, recherches, offres, rejets, adresse.

        Rien n'est récupérable ensuite. Le propriétaire garde son identifiant, réservé, mais perd ses données
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
            SearchRunRepository(session, user_id).delete_all()
            PageEvaluationRepository(session, user_id).delete_all()
            UserRepository(session).forget_user(user_id)
        # Les copies d'avant migration contiennent encore ses données : elles restent, sans lui
        self.database.purge_user_from_backups(user_id)

    def delete_inactive_accounts_if_due(self, now: datetime | None = None) -> None:
        """Supprime les comptes inactifs, au plus une fois par jour.

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

    def delete_inactive_accounts(self, now: datetime | None = None) -> int:
        """Supprime les comptes d'invités sans activité depuis INACTIVE_ACCOUNT_DAYS, et renvoie leur nombre.

        Le propriétaire n'est jamais concerné. Un invité retiré de ALLOWED_EMAILS, qui ne peut plus
        se connecter, finit donc par être effacé sans avoir à le demander.
        """
        since = (now or datetime.now(UTC)) - timedelta(days=INACTIVE_ACCOUNT_DAYS)
        with self.database.session() as session:
            user_ids = UserRepository(session).list_inactive_user_ids(since)
        for user_id in user_ids:
            self.delete_account(user_id)
            # L'identifiant seul : l'adresse vient d'être effacée, elle n'a rien à faire dans les logs
            logger.info("Compte %d supprimé après %d jours sans activité", user_id, INACTIVE_ACCOUNT_DAYS)
        return len(user_ids)
