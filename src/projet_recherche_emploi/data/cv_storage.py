from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PyPdfError

from projet_recherche_emploi.config import DEFAULT_USER_ID
from projet_recherche_emploi.errors import InvalidInputError


class CvStorage:
    """CV des utilisateurs, un PDF par utilisateur dans le dossier des données."""

    def __init__(self, data_dir: str | Path):
        self.data_dir = Path(data_dir)

    def path_for(self, user_id: int) -> Path:
        # Le CV du propriétaire garde son emplacement d'avant les comptes
        if user_id == DEFAULT_USER_ID:
            return self.data_dir / "cv.pdf"
        return self.data_dir / "cv" / f"{user_id}.pdf"

    def updated_at(self, user_id: int) -> datetime | None:
        """Renvoie la date du dernier enregistrement du CV, ou None si l'utilisateur n'en a pas."""
        cv_file = self.path_for(user_id)
        if not cv_file.is_file():
            return None
        return datetime.fromtimestamp(cv_file.stat().st_mtime, tz=UTC)

    def read_text(self, user_id: int) -> str:
        """Renvoie le texte du CV de l'utilisateur."""
        cv_file = self.path_for(user_id)
        if not cv_file.is_file():
            raise InvalidInputError("Aucun CV enregistré.")
        return _extract_text(PdfReader(cv_file))

    def save(self, user_id: int, data: bytes) -> None:
        """Remplace le CV de l'utilisateur par ce PDF, après avoir vérifié qu'il est lisible."""
        try:
            # Le CV en place n'est écrasé que si le nouveau contient bien du texte
            _extract_text(PdfReader(BytesIO(data)))
        except PyPdfError as error:
            raise InvalidInputError("Le fichier fourni n'est pas un PDF valide.") from error
        cv_file = self.path_for(user_id)
        cv_file.parent.mkdir(parents=True, exist_ok=True)
        cv_file.write_bytes(data)

    def delete(self, user_id: int) -> bool:
        """Efface le CV de l'utilisateur, et renvoie faux s'il n'en avait pas."""
        cv_file = self.path_for(user_id)
        if not cv_file.is_file():
            return False
        cv_file.unlink()
        return True


def _extract_text(pdf: PdfReader) -> str:
    pages = [page.extract_text() for page in pdf.pages]
    content = "\n\n".join(text.strip() for text in pages if text.strip())
    if not content:
        raise InvalidInputError("Aucun texte n'a pu être extrait de ce PDF : est-ce un document scanné ?")
    return content
