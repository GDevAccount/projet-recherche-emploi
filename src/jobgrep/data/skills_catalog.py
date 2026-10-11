"""Référentiel des compétences proposées à la saisie d'un poste recherché : son fichier, et la forme de recherche."""

import unicodedata
from pathlib import Path

CATALOG_PATH = Path(__file__).parent / "skills_catalog.txt"


def fold_skill(text: str) -> str:
    """Renvoie une compétence telle qu'on la cherche : sans accent, sans majuscule, sans espace superflu."""
    decomposed = unicodedata.normalize("NFKD", " ".join(text.split()))
    return "".join(char for char in decomposed if not unicodedata.combining(char)).casefold()


def read_catalog() -> list[str]:
    """Renvoie les compétences du fichier, dans son ordre, sans commentaire ni doublon."""
    skills: dict[str, str] = {}
    for line in CATALOG_PATH.read_text(encoding="utf-8").splitlines():
        name = " ".join(line.split())
        if name and not name.startswith("#"):
            skills.setdefault(fold_skill(name), name)
    return list(skills.values())
