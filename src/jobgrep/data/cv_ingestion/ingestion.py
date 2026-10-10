"""Ingestion d'un CV : du PDF déposé au texte enregistré en base, coordonnées retirées.

Le PDF n'est pas conservé. Seul son texte anonymisé l'est, dans la table cv_texts : c'est ce que le filtre
envoie au modèle, et sa date dit depuis quand le CV est en place.
"""

from collections.abc import Iterable

from sqlalchemy.orm import Session

from jobgrep.data.cv_ingestion.anonymizer import CvAnonymizer
from jobgrep.data.cv_ingestion.pdf_reader import CvPdfReader
from jobgrep.data.repositories.cv_text_repository import CvTextRepository


class CvIngestion:
    def __init__(self, pdf_reader: CvPdfReader, anonymizer: CvAnonymizer):
        self.pdf_reader = pdf_reader
        self.anonymizer = anonymizer

    def ingest(self, session: Session, user_id: int, data: bytes, names: Iterable[str] = ()) -> None:
        """Enregistre le texte de ce PDF, sans ses coordonnées, à la place du CV de l'utilisateur.

        Le PDF est lu avant toute écriture : un fichier refusé laisse le CV en place. « names » donne les noms
        connus de l'utilisateur, à retirer aussi. Comme un dépôt, ne valide pas la transaction.
        """
        content = self.anonymizer.anonymize(self.pdf_reader.read_text(data), names)
        CvTextRepository(session, user_id).save(content)
