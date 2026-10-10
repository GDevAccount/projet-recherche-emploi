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

# Un compte d'essai, ouvert sans connexion, n'a droit qu'à ce nombre de recherches, en tout et pour tout
MAX_TRIAL_SEARCHES = 1
# Comptes d'essai qu'une même adresse IP peut ouvrir par jour : effacer son cookie ne redonne pas un essai sans fin.
# Pas un seul : une adresse est partagée par un foyer ou une entreprise
MAX_TRIALS_PER_IP_PER_DAY = 3
# Un compte d'essai n'est reconnu que par son cookie : une fois celui-ci expiré, plus personne ne peut y revenir
TRIAL_ACCOUNT_DAYS = SESSION_DAYS
# Durée de conservation de l'empreinte de l'adresse IP d'un essai : le plafond se compte par jour.
# Les règles de confidentialité affichent cette durée : elles suivent cette valeur.
TRIAL_START_DAYS = 2

# Un compte d'invité resté sans connexion aussi longtemps est supprimé, avec toutes ses données.
# Les règles de confidentialité affichent cette durée : elles suivent cette valeur.
INACTIVE_ACCOUNT_DAYS = 365

# Durée de conservation des erreurs rendues par l'API (table server_errors) : au-delà, elles ne disent plus rien
# de la santé de l'instance. Les règles de confidentialité affichent cette durée : elles suivent cette valeur.
SERVER_ERROR_DAYS = 90

# Une même alerte n'est pas renvoyée avant ce délai : une panne qui se répète ne doit pas noyer le téléphone
ALERT_QUIET_MINUTES = 60
# Coût de toutes les recherches des dernières 24 heures, en dollars, à partir duquel une alerte part, une fois
# par jour. Une recherche coûte quelques centimes : ce seuil n'est franchi que par un usage anormal
DAILY_COST_ALERT_USD = 1.0
# Nombre de semaines de la rubrique Suivi, celle en cours comprise
WEEKS_SHOWN = 12
# Avant ce jour du mois, la projection de fin de mois repose sur trop peu de jours pour déclencher une alerte
BUDGET_ALERT_FIRST_DAY = 5
# Au démarrage, une recherche restée « en cours » depuis moins longtemps vient d'être coupée par ce redémarrage
INTERRUPTION_ALERT_MINUTES = 60

# Erreurs du front qu'un même compte peut signaler en 24 heures : au-delà, elles sont ignorées, pour qu'une
# page qui échoue en boucle ne remplisse pas la table
CLIENT_ERRORS_PER_DAY = 50

# Formule d'un compte (AccountPlan de schemas.py). Il n'y a pas encore de paiement : tout compte a celle-ci.
# Elle est déjà gardée avec la consommation d'un compte supprimé, pour savoir plus tard ce que coûtaient
# les comptes gratuits et les payants
DEFAULT_PLAN = "free"
# Celle d'un compte d'essai : gardée de même, pour savoir ce que coûtent les essais
TRIAL_PLAN = "trial"

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

    # Sujet ntfy où partent les alertes (recherche échouée, panne, coût anormal). Vide : aucune alerte.
    # Sans compte ntfy, qui connaît ce nom peut lire le sujet : il se choisit long et aléatoire, comme un secret
    ntfy_topic: str = Field(default="", repr=False)
    ntfy_url: str = "https://ntfy.sh"
    # Budget mensuel de l'instance, en dollars, tous comptes réunis : Tavily et OpenAI. 0 : pas de budget
    monthly_budget_usd: float = 10.0
    # Budget d'un jour, à l'heure de Paris, tous comptes réunis. Atteint, il refuse les recherches jusqu'au
    # lendemain, sauf celles du propriétaire. 0 : pas de budget
    daily_budget_usd: float = 0.5
    # Comptes d'essai, sans connexion, que l'instance accepte d'ouvrir par jour. 0 : aucun essai sans compte
    max_trials_per_day: int = 0

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
