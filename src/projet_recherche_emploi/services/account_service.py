import logging
from datetime import UTC, datetime, timedelta

from projet_recherche_emploi.config import INACTIVE_ACCOUNT_DAYS
from projet_recherche_emploi.data.cv_storage import CvStorage
from projet_recherche_emploi.data.database import Database
from projet_recherche_emploi.data.job_repository import JobRepository
from projet_recherche_emploi.data.query_repository import QueryRepository
from projet_recherche_emploi.data.rejected_job_repository import RejectedJobRepository
from projet_recherche_emploi.data.search_run_repository import SearchRunRepository
from projet_recherche_emploi.data.user_repository import UserRepository
from projet_recherche_emploi.errors import ConflictError
from projet_recherche_emploi.services.search_service import SearchService

logger = logging.getLogger(__name__)


class AccountService:
    def __init__(self, database: Database, cv_storage: CvStorage, search: SearchService):
        self.database = database
        self.cv_storage = cv_storage
        self.search = search

    def delete_account(self, user_id: int) -> None:
        """Efface tout ce que l'application garde de l'utilisateur : CV, recherches, offres, rejets, adresse.

        Rien n'est récupérable ensuite. Le propriétaire garde son identifiant, réservé, mais perd ses données
        comme un autre ; un invité encore autorisé qui se reconnecte reçoit un compte neuf.
        """
        # Une recherche en cours écrirait ses offres après l'effacement
        if self.search.is_running(user_id):
            raise ConflictError("Une recherche est en cours : attendez qu'elle se termine pour supprimer le compte.")

        # Le CV d'abord : si la suite échoue, il reste un compte sans CV plutôt qu'un CV sans compte
        self.cv_storage.delete(user_id)
        with self.database.session() as session:
            JobRepository(session, user_id).delete_all()
            RejectedJobRepository(session, user_id).clear()
            QueryRepository(session, user_id).delete_all()
            SearchRunRepository(session, user_id).delete_all()
            UserRepository(session).forget_user(user_id)
        # Les copies d'avant migration contiennent encore ses données : elles restent, sans lui
        self.database.purge_user_from_backups(user_id)

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
