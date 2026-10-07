from io import BytesIO
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PyPdfError


class CV_reader:
    def __init__(self, cv_path: str | Path):
        self.cv_path = Path(cv_path)

    def get_cv_content(self) -> str:
        pdf = self._load_pdf()
        return self._parse_pdf(pdf)

    def save_cv(self, data: bytes) -> None:
        """Remplace le CV par le PDF fourni, après avoir vérifié qu'il est lisible."""
        try:
            pdf = PdfReader(BytesIO(data))
            # Le CV actuel n'est écrasé que si le nouveau contient bien du texte
            self._parse_pdf(pdf)
        except PyPdfError as error:
            raise ValueError("Le fichier fourni n'est pas un PDF valide") from error
        self.cv_path.parent.mkdir(parents=True, exist_ok=True)
        self.cv_path.write_bytes(data)

    def _load_pdf(self) -> PdfReader:
        if not self.cv_path.is_file():
            raise FileNotFoundError(f"CV introuvable : {self.cv_path}")
        if self.cv_path.suffix.lower() != ".pdf":
            raise ValueError(f"Le CV doit être un fichier PDF : {self.cv_path}")
        return PdfReader(self.cv_path)

    def _parse_pdf(self, pdf: PdfReader) -> str:
        pages = [page.extract_text() for page in pdf.pages]
        content = "\n\n".join(text.strip() for text in pages if text.strip())
        if not content:
            raise ValueError(f"Aucun texte extrait du CV (PDF scanné ?) : {self.cv_path}")
        return content
