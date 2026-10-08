import logging
from pathlib import Path
from typing import Literal, get_args

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DB_FILE_NAME = "jobs.db"

# Les données créées avant les comptes appartiennent à cet utilisateur : le propriétaire
DEFAULT_USER_ID = 1

# Fuseau des dates affichées et du quota journalier : la base, elle, enregistre en UTC
LOCAL_TIMEZONE = "Europe/Paris"

# Nombre de recherches par jour pour chaque utilisateur invité (le propriétaire n'est pas limité)
MAX_SEARCHES_PER_DAY = 2

# Durée d'une session de l'API, après quoi le front redemande une connexion
SESSION_DAYS = 30

ContractType = Literal["CDI", "freelance", "CDD", "alternance", "stage"]
CONTRACT_TYPES = list(get_args(ContractType))

# Sites auxquels la recherche Tavily est limitée
JOB_SITES = [
    "welcometothejungle.com",
    "free-work.com",
    "malt.fr",
    "linkedin.com",
    "indeed.com",
    "apec.fr",
    "hellowork.com",
    "jobteaser.com",
    "monster.fr",
    "francetravail.fr",
    "jobijoba.com",
    "regionsjob.com",
    "cadremploi.fr",
    "keljob.com",
    "jobintree.com",
    "collective.work",
    "lehibou.com",
    "careerbuilder.com",
    "tekkit.io/offres",
    "fr.talent.com",
    "glassdoor.fr",
    "wellfound.com",
    "foorilla.com",
    "jobs.stationf.co",
]

FILTER_MODEL = "gpt-5-mini"
MAX_PAGE_CHARS = 8000

# Recherches enregistrées en base à sa création, modifiables ensuite
DEFAULT_QUERIES = [
    ("CDI", "offre d'emploi ingénieur IA en CDI en Ile-de-France"),
    ("CDI", "offre d'emploi AI engineer LLM en CDI en Ile-de-France"),
    ("freelance", "mission freelance AI engineer en Ile-de-France"),
    ("freelance", "mission freelance ingénieur intelligence artificielle"),
]


class Settings(BaseSettings):
    """Réglages lus dans les variables d'environnement, une fois, à la construction du conteneur.

    Le fichier .env n'est pas lu ici : chaque point d'entrée appelle load_dotenv() avant, ce qui
    rend aussi TAVILY_API_KEY et OPENAI_API_KEY visibles des bibliothèques qui les lisent elles-mêmes.
    """

    model_config = SettingsConfigDict(extra="ignore")

    # Dossier de la base et des CV : le dossier courant en local, un volume persistant une fois hébergé
    data_dir: Path = Path(".")

    app_password: str = Field(default="", repr=False)

    google_client_id: str = ""
    google_client_secret: str = Field(default="", repr=False)
    auth_cookie_secret: str = Field(default="", repr=False)
    auth_redirect_uri: str = ""
    owner_email: str = ""
    # Adresses des invités séparées par des virgules, ou « * » pour accepter tout compte Google
    allowed_emails: str = ""

    contact_email: str = ""
    google_site_verification_file: str = ""

    # Origines autorisées à appeler l'API depuis un navigateur, séparées par des virgules
    cors_origins: str = ""

    @field_validator("*", mode="before")
    @classmethod
    def _strip(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @property
    def db_path(self) -> Path:
        return self.data_dir / DB_FILE_NAME

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


def configure_logging() -> None:
    """Règle le format des logs. À appeler par chaque point d'entrée, pas à l'import d'un module."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
