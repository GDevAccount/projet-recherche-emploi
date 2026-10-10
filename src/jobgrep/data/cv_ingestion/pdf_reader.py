from io import BytesIO

from pypdf import PdfReader
from pypdf.errors import PyPdfError

from jobgrep.errors import InvalidInputError


class CvPdfReader:
    """Lit le texte d'un CV déposé en PDF. Le fichier n'est lu qu'en mémoire : il n'est écrit nulle part."""

    def read_text(self, data: bytes) -> str:
        """Renvoie le texte du PDF. Refuse un fichier illisible, ou sans texte."""
        try:
            pages = [page.extract_text() for page in PdfReader(BytesIO(data)).pages]
        except PyPdfError as error:
            raise InvalidInputError("Le fichier fourni n'est pas un PDF valide.") from error
        content = "\n\n".join(text.strip() for text in pages if text.strip())
        if not content:
            raise InvalidInputError("Aucun texte n'a pu être extrait de ce PDF : est-ce un document scanné ?")
        return content
