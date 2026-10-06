import os
from pathlib import Path

# Dossier des données : le dossier courant en local, un volume persistant une fois hébergé
DATA_DIR = Path(os.environ.get("DATA_DIR", "."))

DB_PATH = DATA_DIR / "jobs.db"
CV_PATH = DATA_DIR / "cv.pdf"

FILTER_MODEL = "gpt-5-mini"
MAX_PAGE_CHARS = 8000

# Recherches enregistrées en base à sa création, modifiables ensuite
DEFAULT_QUERIES = [
    ("CDI", "offre d'emploi ingénieur IA en CDI en Ile-de-France"),
    ("CDI", "offre d'emploi AI engineer LLM en CDI en Ile-de-France"),
    ("freelance", "mission freelance AI engineer en Ile-de-France"),
    ("freelance", "mission freelance ingénieur intelligence artificielle"),
]
