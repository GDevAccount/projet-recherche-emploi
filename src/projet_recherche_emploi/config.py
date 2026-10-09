import logging
from pathlib import Path
from typing import Literal, NamedTuple, get_args

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

# Un compte d'invité resté sans connexion aussi longtemps est supprimé, avec toutes ses données.
# Les règles de confidentialité affichent cette durée : elles suivent cette valeur.
INACTIVE_ACCOUNT_DAYS = 365

# Formule d'un compte (AccountPlan de schemas.py). Il n'y a pas encore de paiement : tout compte a celle-ci.
# Elle est déjà gardée avec la consommation d'un compte supprimé, pour savoir plus tard ce que coûtaient
# les comptes gratuits et les payants
DEFAULT_PLAN = "free"

ContractType = Literal["CDI", "freelance", "CDD", "alternance", "stage"]
CONTRACT_TYPES = list(get_args(ContractType))

WorkMode = Literal["sur site", "hybride", "télétravail complet"]
FULL_REMOTE_MODE = "télétravail complet"

# Nature d'une page trouvée : seule une offre est comparée au CV et aux recherches
PageKind = Literal[
    "offre", "liste d'offres", "article", "fiche métier", "page d'accueil", "offre expirée", "formation", "autre"
]
OFFER_PAGE_KIND = "offre"

# Contrats de formation : une offre de ce type n'est retenue que si une recherche le demande
TRAINING_CONTRACTS = ("stage", "alternance")

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

# Sites ajoutés pour la variante en anglais d'une recherche en télétravail complet
REMOTE_JOB_SITES = [
    "weworkremotely.com",
    "remoteok.com",
    "remotive.com",
    "himalayas.app",
    "workingnomads.com",
    "euremotejobs.com",
    "jobgether.com",
]

FILTER_MODEL = "gpt-6-luna"
MAX_PAGE_CHARS = 8000


class ModelPrice(NamedTuple):
    """Tarif d'un modèle, en dollars par million de jetons."""

    input: float
    output: float
    cache_read: float
    cache_write: float


# Tarifs relevés le 2026-10-09. Les coûts sont calculés à la lecture (services/search_costs.py) : corriger un
# tarif ici corrige aussi le coût affiché des recherches passées. Un modèle absent n'a pas de coût affiché.
MODEL_PRICES_USD = {
    "gpt-6-luna": ModelPrice(input=0.10, output=0.50, cache_read=0.01, cache_write=0.125),
}
TAVILY_CREDIT_PRICE_USD = 0.008
# Une recherche en profondeur « advanced », celle de TavilyJobSearch, coûte deux crédits
TAVILY_CREDITS_PER_SEARCH = 2

# Recherches enregistrées en base à sa création, modifiables ensuite.
# Une phrase nomme un métier et ses spécialités : le filtre ne retient que les offres de ce métier.
# Ni contrat ni lieu, qui sont ajoutés au texte envoyé au moteur de recherche. Ces recherches reçoivent
# l'Île-de-France pour lieu (migration 0003). L'intitulé anglais ramène les annonces rédigées en anglais.
DEFAULT_QUERIES = [
    ("CDI", "ingénieur IA générative LLM RAG"),
    ("CDI", "AI engineer LLM agents"),
    ("freelance", "mission ingénieur IA générative LLM RAG"),
    ("freelance", "mission AI engineer LLM agents"),
]


class Settings(BaseSettings):
    """Réglages lus dans les variables d'environnement, une fois, à la construction du conteneur.

    Le fichier .env n'est pas lu ici : chaque point d'entrée appelle load_dotenv() avant, ce qui
    rend aussi TAVILY_API_KEY et OPENAI_API_KEY visibles des bibliothèques qui les lisent elles-mêmes.
    """

    model_config = SettingsConfigDict(extra="ignore")

    # Dossier de la base et des CV : le dossier courant en local, un volume persistant une fois hébergé
    data_dir: Path = Path(".")

    # Build du front Angular (npm run build dans frontend/). Absent : le front n'est pas servi
    frontend_dir: Path = Path("frontend/dist/frontend/browser")

    app_password: str = Field(default="", repr=False)

    # Identifiant public de l'application chez Google : le définir active la connexion Google
    google_client_id: str = ""
    # Signe le cookie de session
    auth_cookie_secret: str = Field(default="", repr=False)
    owner_email: str = ""
    # Adresses des invités séparées par des virgules, ou « * » pour accepter tout compte Google
    allowed_emails: str = ""
    # Adresses des administrateurs, séparées par des virgules : ils voient le suivi des recherches et la
    # consommation de tous les comptes, comme le propriétaire, et peuvent se connecter sans figurer parmi les invités
    admin_emails: str = ""

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
