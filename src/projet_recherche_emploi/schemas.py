"""Objets échangés entre les services et les interfaces. L'API les sert tels quels en JSON."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, computed_field

# Motif d'une page qui n'est pas une offre, quand sa nature n'est pas connue ou n'a pas de motif à elle
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
# Motif d'une page qui n'est pas une offre, selon sa nature (PageKind)
REJECT_PAGE_KINDS = {
    "liste d'offres": "Liste ou page de résultats",
    "article": "Article",
    "fiche métier": "Fiche métier",
    "page d'accueil": "Page d'accueil",
    "offre expirée": "Offre expirée",
    # Une formation n'est pas un emploi : elle est rangée avec les stages et les alternances non demandés
    "formation": REJECT_CRITERIA["matches_contract"],
}


# État d'une candidature : à traiter, postulée, entretien obtenu, refusée par l'employeur
JobStatus = Literal["todo", "applied", "interview", "rejected"]


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
    status: JobStatus
    # Date de chaque étape franchie par la candidature ; None tant qu'elle ne l'est pas
    applied_at: datetime | None
    interview_at: datetime | None
    rejected_at: datetime | None
    created_at: datetime
    # États que l'offre peut prendre maintenant : les interfaces n'en proposent pas d'autre
    next_statuses: list[JobStatus] = []


class RejectedJobRead(_FromRow):
    url: str
    title: str
    contract_type: str | None
    query: str | None
    is_real_offer: bool
    # None pour les pages rejetées avant que leur nature soit enregistrée
    page_kind: str | None
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
            return [REJECT_PAGE_KINDS.get(self.page_kind, REJECT_NOT_AN_OFFER)]
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


# État d'un lancement : en cours, terminé, échoué, ou interrompu par un redémarrage du serveur
SearchRunStatus = Literal["running", "done", "failed", "interrupted"]


class SearchRunRead(_FromRow):
    """Bilan d'un lancement : ce qu'il a trouvé, ce qu'il a duré et ce qu'il a consommé.

    Tout sauf la date est None pour un lancement d'avant le suivi ; une recherche échouée ou interrompue
    n'a que les mesures des étapes qu'elle a franchies.
    """

    id: int
    created_at: datetime
    finished_at: datetime | None
    status: SearchRunStatus | None
    # Type de l'erreur d'une recherche échouée, sans son message
    error: str | None
    model: str | None
    # Empreinte du prompt du filtre : deux lancements qui la partagent ont été jugés avec les mêmes consignes
    prompt_version: str | None
    found_count: int | None
    new_count: int | None
    kept_count: int | None
    rejected_count: int | None
    inserted_count: int | None
    # Durée de chaque étape, en millisecondes
    search_ms: int | None
    dedupe_ms: int | None
    evaluate_ms: int | None
    save_ms: int | None
    # Appels au moteur de recherche, et jetons du modèle
    search_calls: int | None
    input_tokens: int | None
    output_tokens: int | None


class PageEvaluationRead(_FromRow):
    """Une page évaluée pendant un lancement, retenue ou non."""

    id: int
    search_run_id: int | None
    url: str
    title: str
    query: str | None
    score: float | None
    kept: bool
    # Faits lus sur la page par le modèle
    page_kind: str | None
    contract_type: str | None
    work_city: str | None
    work_country: str | None
    work_mode: str | None
    in_accepted_area: bool | None
    open_to_candidates_in_france: bool | None
    # Avis du modèle
    matches_search: bool | None
    matches_skills: bool | None
    matches_level: bool | None
    # Règles appliquées par le graph
    matches_contract: bool | None
    matches_location: bool | None
    reason: str | None
    # Longueur du texte disponible ; « truncated » si le modèle n'en a lu que le début
    page_chars: int | None
    truncated: bool | None
    # Faux quand seul l'extrait du moteur de recherche était disponible
    full_page: bool | None
    input_tokens: int | None
    output_tokens: int | None
    duration_ms: int | None
    created_at: datetime


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
    # Adresse, nom et photo du compte Google ; None avec le mot de passe de l'instance
    email: str | None
    name: str | None
    picture: str | None
    # Un CV et au moins un poste recherché sont enregistrés
    can_search: bool
    # Une recherche de cet utilisateur tourne sur le serveur : il ne peut pas en lancer une autre
    search_running: bool
    # None pour le propriétaire, qui n'a pas de quota
    remaining_searches: int | None
    max_searches_per_day: int
