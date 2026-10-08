"""Objets échangés entre les services et les interfaces. L'API les sert tels quels en JSON."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, computed_field

REJECT_NOT_AN_OFFER = "Pas une offre valable"
# Motif des pages rejetées avant que le verdict soit enregistré critère par critère
REJECT_PROFILE_MISMATCH = "Hors profil"
# Critères du verdict, dans l'ordre où ils donnent le motif d'un rejet
REJECT_CRITERIA = {
    "matches_search": "Autre métier que ceux recherchés",
    "matches_contract": "Contrat non recherché",
    "matches_skills": "Compétences insuffisantes",
    "matches_level": "Niveau d'expérience incompatible",
    "matches_location": "Hors lieu recherché",
}


class _FromRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class JobRead(_FromRow):
    id: int
    url: str
    title: str
    content: str | None
    score: float | None
    contract_type: str | None
    # Ville lue sur l'annonce, ou « Remote » pour un poste en télétravail complet
    work_location: str | None
    query: str | None
    match_reason: str | None
    applied: bool
    applied_at: datetime | None
    created_at: datetime


class RejectedJobRead(_FromRow):
    url: str
    title: str
    contract_type: str | None
    query: str | None
    is_real_offer: bool
    matches_cv: bool
    # Détail du verdict : None pour les pages rejetées avant qu'il soit enregistré critère par critère
    matches_search: bool | None
    matches_contract: bool | None
    matches_skills: bool | None
    matches_level: bool | None
    matches_location: bool | None
    work_location: str | None
    reject_reason: str | None
    created_at: datetime

    @computed_field
    @property
    def failed_criteria(self) -> list[str]:
        """Motifs du rejet, le principal en premier."""
        # Une page qui n'est pas une offre n'a ni métier ni profil à comparer
        if not self.is_real_offer:
            return [REJECT_NOT_AN_OFFER]
        # Un critère à None n'a pas été évalué : il n'est pas en défaut
        failed = [label for criterion, label in REJECT_CRITERIA.items() if getattr(self, criterion) is False]
        return failed or [REJECT_PROFILE_MISMATCH]

    @computed_field
    @property
    def motive(self) -> str:
        """Motif principal du rejet : le premier critère en défaut."""
        return self.failed_criteria[0]


class SearchQueryRead(_FromRow):
    id: int
    contract_type: str
    query: str
    # Vide : toute la France
    location: str
    # Télétravail complet, sans condition de lieu
    remote: bool
    created_at: datetime


class CvStatus(BaseModel):
    # None tant que l'utilisateur n'a pas déposé de CV
    updated_at: datetime | None


# Étapes d'une recherche, dans l'ordre du graph : searchJobs, FilterDuplicates, FilterJobs, InsertJobs
SearchStep = Literal["search", "dedupe", "evaluate", "save"]


class SearchProgress(BaseModel):
    message: str
    # Étape du graph qui signale cet avancement : une interface n'a pas à la deviner dans le message
    step: SearchStep | None = None
    # Renseignés quand l'avancement de l'étape se mesure
    done: int | None = None
    total: int | None = None
    # Pages trouvées jusqu'ici, et, une fois les doublons écartés, celles qui restent à évaluer
    found: int | None = None
    new: int | None = None
    # Page qui vient d'être évaluée, et son verdict
    title: str | None = None
    kept: bool | None = None


class SearchSummary(BaseModel):
    found: int
    new: int
    kept: int
    rejected: int
    inserted: int


class AppConfig(BaseModel):
    """Ce qu'un front doit savoir avant toute connexion. Servi sans identité : rien de secret ici."""

    # Preuve d'identité attendue par « POST /api/session » ; None si l'instance n'est pas protégée, et refuse tout
    login_mode: Literal["google", "password"] | None
    # Identifiant public de l'application chez Google, pour le bouton de connexion ; None hors connexion Google
    google_client_id: str | None
    contract_types: list[str]


class Account(BaseModel):
    user_id: int
    is_owner: bool
    # Un CV et au moins un poste recherché sont enregistrés
    can_search: bool
    # None pour le propriétaire, qui n'a pas de quota
    remaining_searches: int | None
    max_searches_per_day: int
