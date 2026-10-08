from projet_recherche_emploi.data.cv_storage import CvStorage
from projet_recherche_emploi.data.database import Database
from projet_recherche_emploi.data.rejected_job_repository import RejectedJobRepository
from projet_recherche_emploi.errors import InvalidInputError
from projet_recherche_emploi.schemas import CvStatus

# Un CV pèse quelques centaines de ko : au-delà, ce n'en est pas un, et le fichier est lu en mémoire
MAX_CV_BYTES = 10 * 1024 * 1024


class CvService:
    def __init__(self, database: Database, cv_storage: CvStorage):
        self.database = database
        self.cv_storage = cv_storage

    def save_cv(self, user_id: int, data: bytes) -> CvStatus:
        """Remplace le CV de l'utilisateur par ce PDF. Refuse un fichier illisible ou sans texte."""
        if len(data) > MAX_CV_BYTES:
            raise InvalidInputError(f"Le CV dépasse {MAX_CV_BYTES // (1024 * 1024)} Mo.")
        self.cv_storage.save(user_id, data)
        # Les rejets valaient pour l'ancien CV : ces pages peuvent convenir au nouveau
        with self.database.session() as session:
            RejectedJobRepository(session, user_id).clear()
        return self.get_status(user_id)

    def get_status(self, user_id: int) -> CvStatus:
        """Dit si l'utilisateur a un CV en place, et depuis quand."""
        return CvStatus(updated_at=self.cv_storage.updated_at(user_id))
