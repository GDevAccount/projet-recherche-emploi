"""Reprise des CV gardés en PDF, du temps où l'application conservait le fichier déposé.

Le CV du propriétaire était « cv.pdf » dans le dossier des données, celui d'un autre « cv/<identifiant>.pdf ».
"""

import logging
from datetime import UTC, datetime
from pathlib import Path

from projet_recherche_emploi.config import DEFAULT_USER_ID
from projet_recherche_emploi.data.cv_ingestion.ingestion import CvIngestion
from projet_recherche_emploi.data.database import Database
from projet_recherche_emploi.data.repositories.cv_text_repository import CvTextRepository
from projet_recherche_emploi.errors import InvalidInputError

logger = logging.getLogger(__name__)

OWNER_FILE = "cv.pdf"
GUESTS_DIR = "cv"


def absorb_legacy_cv_files(database: Database, ingestion: CvIngestion, data_dir: Path) -> int:
    """Supprime les PDF restants, après avoir enregistré le texte de ceux qui ne l'étaient pas encore.

    Renvoie le nombre de fichiers supprimés. Un CV déjà en base n'est pas relu. Un PDF illisible est supprimé
    aussi : il ne servait déjà plus à rien.
    """
    files = _legacy_files(data_dir)
    for user_id, cv_file in files:
        try:
            # Une transaction par fichier : il n'est supprimé qu'une fois son texte enregistré
            with database.session() as session:
                if CvTextRepository(session, user_id).get_updated_at() is None:
                    # Sans le nom de l'utilisateur, inconnu ici : il sera retiré au prochain dépôt
                    deposited_at = datetime.fromtimestamp(cv_file.stat().st_mtime, tz=UTC)
                    ingestion.ingest(session, user_id, cv_file.read_bytes(), updated_at=deposited_at)
        except InvalidInputError:
            logger.warning("CV en PDF du compte %d illisible : supprimé sans être repris", user_id)
        else:
            logger.info("CV en PDF du compte %d supprimé, son texte est en base", user_id)
        cv_file.unlink()

    guests_dir = data_dir / GUESTS_DIR
    if guests_dir.is_dir() and not any(guests_dir.iterdir()):
        guests_dir.rmdir()
    return len(files)


def _legacy_files(data_dir: Path) -> list[tuple[int, Path]]:
    files = [(DEFAULT_USER_ID, data_dir / OWNER_FILE)]
    files += [(int(path.stem), path) for path in sorted((data_dir / GUESTS_DIR).glob("*.pdf")) if path.stem.isdigit()]
    return [(user_id, path) for user_id, path in files if path.is_file()]
