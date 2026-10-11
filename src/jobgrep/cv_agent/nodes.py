import logging

from langgraph.config import get_stream_writer

from jobgrep.cv_agent.ports import Anonymizer, CvStore, Extraction, PdfReader, ProfileExtractor, ProfileStore
from jobgrep.cv_agent.prompts import prompt_version
from jobgrep.cv_agent.state import CvDepositState

logger = logging.getLogger(__name__)


class CvDepositNodes:
    """Les nœuds du graph du dépôt d'un CV. Chacun annonce son étape, que le front affiche en direct."""

    def __init__(
        self,
        pdf_reader: PdfReader,
        anonymizer: Anonymizer,
        extractor: ProfileExtractor,
        cv_store: CvStore,
        profile_store: ProfileStore,
    ):
        self.pdf_reader = pdf_reader
        self.anonymizer = anonymizer
        self.extractor = extractor
        self.cv_store = cv_store
        self.profile_store = profile_store

    def read_cv(self, state: CvDepositState) -> CvDepositState:
        """Lit le texte du PDF. Un fichier illisible arrête tout ici : le CV en place reste."""
        get_stream_writer()({"step": "read"})
        return {"raw_text": self.pdf_reader.read_text(state["data"])}

    def anonymize_cv(self, state: CvDepositState) -> CvDepositState:
        """Retire du texte les coordonnées de la personne : rien d'autre ne sort d'ici vers la base ou le modèle."""
        get_stream_writer()({"step": "anonymize"})
        return {"text": self.anonymizer.anonymize(state["raw_text"], state.get("names", []))}

    def save_cv(self, state: CvDepositState) -> CvDepositState:
        """Enregistre le CV avant de le donner au modèle : une panne de l'extraction ne le fait pas perdre."""
        get_stream_writer()({"step": "save"})
        self.cv_store.store_text(state["user_id"], state["text"])
        return {}

    def extract_profile(self, state: CvDepositState) -> CvDepositState:
        """Demande au modèle les postes que le CV permet de viser. Une panne laisse le CV en place, sans postes."""
        get_stream_writer()({"step": "extract"})
        try:
            profile, usage = self.extractor.extract(state["text"])
        except Exception as error:
            # Le message peut reprendre le CV : seul le type de l'erreur est journalisé
            logger.error("Les postes n'ont pas pu être tirés du CV : %s", type(error).__name__)
            return {"outcome": "failed", "error_type": type(error).__name__}
        return {"extraction": Extraction(profile, usage, self.extractor.model_name, prompt_version())}

    def save_queries(self, state: CvDepositState) -> CvDepositState:
        """Remplace les postes recherchés par ceux tirés du CV. S'il n'en sort aucun, ceux en place restent."""
        get_stream_writer()({"step": "queries"})
        queries = self.profile_store.apply_profile(state["user_id"], state["extraction"])
        return {"outcome": "created" if queries else "empty", "queries": queries}


def route_after_save(state: CvDepositState) -> str:
    """Dit si le graph continue vers l'extraction, que le service a autorisée ou non avant de le lancer."""
    return "extract" if state.get("extract") else "stop"


def route_after_extract(state: CvDepositState) -> str:
    """Dit si le modèle a rendu de quoi créer des postes."""
    return "save" if state.get("extraction") else "stop"
