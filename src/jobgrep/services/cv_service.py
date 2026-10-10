from collections.abc import Iterable

from jobgrep.data.cv_ingestion.ingestion import CvIngestion
from jobgrep.data.database import Database
from jobgrep.data.repositories.cv_text_repository import CvTextRepository
from jobgrep.data.repositories.rejected_job_repository import RejectedJobRepository
from jobgrep.errors import InvalidInputError
from jobgrep.schemas import CvStatus

# Un CV pèse quelques centaines de ko : au-delà, ce n'en est pas un, et le fichier est lu en mémoire
MAX_CV_BYTES = 10 * 1024 * 1024


class CvService:
    def __init__(self, database: Database, ingestion: CvIngestion):
        self.database = database
        self.ingestion = ingestion

    def save_cv(self, user_id: int, data: bytes, names: Iterable[str] = ()) -> CvStatus:
        """Remplace le CV de l'utilisateur par ce PDF. Refuse un fichier illisible ou sans texte.

        Seul son texte est gardé, sans ses coordonnées : le PDF n'est pas conservé. « names » donne les noms
        connus de l'utilisateur, à retirer aussi.
        """
        if len(data) > MAX_CV_BYTES:
            raise InvalidInputError(f"Le CV dépasse {MAX_CV_BYTES // (1024 * 1024)} Mo.")
        with self.database.session() as session:
            self.ingestion.ingest(session, user_id, data, names)
            # Les rejets valaient pour l'ancien CV : ces pages peuvent convenir au nouveau
            RejectedJobRepository(session, user_id).clear()
        return self.get_status(user_id)

    def read_text(self, user_id: int) -> str:
        """Renvoie le texte du CV de l'utilisateur, coordonnées retirées : celui qui peut être envoyé au modèle."""
        with self.database.session() as session:
            content = CvTextRepository(session, user_id).get_content()
        if content is None:
            raise InvalidInputError("Aucun CV enregistré.")
        return content

    def get_status(self, user_id: int) -> CvStatus:
        """Dit si l'utilisateur a un CV en place, et depuis quand."""
        with self.database.session() as session:
            return CvStatus(updated_at=CvTextRepository(session, user_id).get_updated_at())
