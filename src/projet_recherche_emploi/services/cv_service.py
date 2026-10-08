from collections.abc import Iterable

from projet_recherche_emploi.data.cv_storage import CvStorage
from projet_recherche_emploi.data.cv_text_repository import CvTextRepository
from projet_recherche_emploi.data.database import Database
from projet_recherche_emploi.data.rejected_job_repository import RejectedJobRepository
from projet_recherche_emploi.errors import InvalidInputError
from projet_recherche_emploi.schemas import CvStatus
from projet_recherche_emploi.services.cv_anonymizer import CvAnonymizer

# Un CV pèse quelques centaines de ko : au-delà, ce n'en est pas un, et le fichier est lu en mémoire
MAX_CV_BYTES = 10 * 1024 * 1024


class CvService:
    def __init__(self, database: Database, cv_storage: CvStorage, anonymizer: CvAnonymizer):
        self.database = database
        self.cv_storage = cv_storage
        self.anonymizer = anonymizer

    def save_cv(self, user_id: int, data: bytes, names: Iterable[str] = ()) -> CvStatus:
        """Remplace le CV de l'utilisateur par ce PDF. Refuse un fichier illisible ou sans texte.

        Son texte est enregistré sans ses coordonnées, à la place de celui de l'ancien CV. « names » donne
        les noms connus de l'utilisateur, à retirer aussi.
        """
        if len(data) > MAX_CV_BYTES:
            raise InvalidInputError(f"Le CV dépasse {MAX_CV_BYTES // (1024 * 1024)} Mo.")
        self.cv_storage.save(user_id, data)
        content = self.anonymizer.anonymize(self.cv_storage.read_text(user_id), names)
        with self.database.session() as session:
            CvTextRepository(session, user_id).save(content)
            # Les rejets valaient pour l'ancien CV : ces pages peuvent convenir au nouveau
            RejectedJobRepository(session, user_id).clear()
        return self.get_status(user_id)

    def read_text(self, user_id: int) -> str:
        """Renvoie le texte du CV de l'utilisateur, coordonnées retirées : celui qui peut être envoyé au modèle."""
        with self.database.session() as session:
            content = CvTextRepository(session, user_id).get_content()
        if content is None:
            # CV déposé avant que son texte soit enregistré : il l'est à cette première lecture. Sans le nom
            # de l'utilisateur, inconnu ici, il ne le sera qu'au prochain dépôt
            content = self.anonymizer.anonymize(self.cv_storage.read_text(user_id))
            with self.database.session() as session:
                CvTextRepository(session, user_id).save(content)
        return content

    def get_status(self, user_id: int) -> CvStatus:
        """Dit si l'utilisateur a un CV en place, et depuis quand."""
        return CvStatus(updated_at=self.cv_storage.updated_at(user_id))
