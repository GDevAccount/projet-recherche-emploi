import os
from pathlib import Path

# Dossier des données : le dossier courant en local, un volume persistant une fois hébergé
DATA_DIR = Path(os.environ.get("DATA_DIR", "."))

DB_PATH = DATA_DIR / "jobs.db"

# Les données créées avant les comptes appartiennent à cet utilisateur
DEFAULT_USER_ID = 1


def cv_path(user_id: int) -> Path:
    # Le CV de l'utilisateur par défaut garde son emplacement d'avant les comptes
    if user_id == DEFAULT_USER_ID:
        return DATA_DIR / "cv.pdf"
    return DATA_DIR / "cv" / f"{user_id}.pdf"

# Nombre de recherches par jour pour chaque utilisateur invité (le propriétaire n'est pas limité)
MAX_SEARCHES_PER_DAY = 2

FILTER_MODEL = "gpt-5-mini"
MAX_PAGE_CHARS = 8000

# Recherches enregistrées en base à sa création, modifiables ensuite
DEFAULT_QUERIES = [
    ("CDI", "offre d'emploi ingénieur IA en CDI en Ile-de-France"),
    ("CDI", "offre d'emploi AI engineer LLM en CDI en Ile-de-France"),
    ("freelance", "mission freelance AI engineer en Ile-de-France"),
    ("freelance", "mission freelance ingénieur intelligence artificielle"),
]
