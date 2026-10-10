"""Textes du site, écrits en Markdown dans texts/ : pages publiques, et guide que seul l'assistant lit.

Les pages publiques les servent en HTML (api/public_pages.py) et l'assistant y cherche ses réponses : les deux
lisent le même texte, avec les mêmes valeurs à la place des champs entre accolades.
"""

from dataclasses import dataclass
from pathlib import Path

from markdown.extensions.toc import slugify

from jobgrep.config import (
    ASSISTANT_MESSAGE_DAYS,
    INACTIVE_ACCOUNT_DAYS,
    JOB_SITES,
    MAX_ASSISTANT_ACCOUNT_QUESTIONS_PER_DAY,
    MAX_ASSISTANT_QUESTIONS_PER_DAY,
    MAX_ASSISTANT_QUESTIONS_PER_MINUTE,
    MAX_SEARCHES_PER_DAY,
    MAX_TRIAL_SEARCHES,
    SERVER_ERROR_DAYS,
    TRIAL_ACCOUNT_DAYS,
    TRIAL_START_DAYS,
)

TEXTS_DIR = Path(__file__).parent / "texts"
# Le guide d'utilisation, que seul l'assistant lit
GUIDE_NAME = "aide"


@dataclass(frozen=True)
class SiteText:
    name: str
    # Vrai pour une page servie à l'adresse « /<name> » ; faux pour un texte que seul l'assistant lit
    public: bool = True

    @property
    def url(self) -> str | None:
        return f"/{self.name}" if self.public else None


# Dans l'ordre des liens du pied de page, le guide en dernier
SITE_TEXTS = {
    text.name: text
    for text in (
        SiteText("fonctionnement"),
        SiteText("confidentialite"),
        SiteText("conditions"),
        SiteText(GUIDE_NAME, public=False),
    )
}


# Écran de l'application dont parle une section du guide, quand il y en a un : l'assistant y renvoie.
# Les chemins sont ceux du front (frontend/src/app/core/paths.ts)
GUIDE_SCREENS = {
    "Déposer ou remplacer son CV": "/profil",
    "Ajouter ou supprimer un poste recherché": "/profil",
    "Suivre ses candidatures": "/offres",
    "Supprimer une offre": "/offres",
    "Retrouver une offre écartée à tort": "/rejets",
    "Aucune offre retenue après une recherche": "/rejets",
    "Supprimer son compte et ses données": "/compte",
}

def section_anchor(section: str) -> str:
    """Renvoie l'ancre d'une section dans sa page : celle que le rendu en HTML donne à son titre."""
    return slugify(section, "-")


def section_url(name: str, section: str) -> str | None:
    """Renvoie l'adresse d'une section d'un texte du site, ou None si ce texte n'est pas une page."""
    url = SITE_TEXTS[name].url
    return f"{url}#{section_anchor(section)}" if url and section else url


def section_screen(name: str, section: str) -> str | None:
    """Renvoie l'écran de l'application dont parle cette section du guide, ou None."""
    return GUIDE_SCREENS.get(section) if name == GUIDE_NAME else None


def fill_fields(text: str, contact_email: str = "") -> str:
    """Remplace les champs entre accolades d'un texte par les valeurs en vigueur."""
    values = {
        "contact": contact_email or "adressez-vous à l'exploitant de l'application",
        "max_searches": MAX_SEARCHES_PER_DAY,
        "job_sites": ", ".join(JOB_SITES),
        "inactive_months": INACTIVE_ACCOUNT_DAYS // 30,
        "server_error_days": SERVER_ERROR_DAYS,
        "trial_searches": MAX_TRIAL_SEARCHES,
        "trial_days": TRIAL_ACCOUNT_DAYS,
        "trial_start_hours": TRIAL_START_DAYS * 24,
        "max_questions": MAX_ASSISTANT_QUESTIONS_PER_DAY,
        "max_account_questions": MAX_ASSISTANT_ACCOUNT_QUESTIONS_PER_DAY,
        "max_questions_per_minute": MAX_ASSISTANT_QUESTIONS_PER_MINUTE,
        "assistant_days": ASSISTANT_MESSAGE_DAYS,
    }
    for field, value in values.items():
        text = text.replace(f"{{{field}}}", str(value))
    return text


def read_site_text(name: str, contact_email: str = "") -> str:
    """Renvoie le texte demandé, en Markdown, ses champs remplacés par les valeurs en vigueur."""
    text = (TEXTS_DIR / f"{SITE_TEXTS[name].name}.md").read_text(encoding="utf-8")
    return fill_fields(text, contact_email)
