"""Objets échangés entre les services et les interfaces. L'API les sert tels quels en JSON."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field

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


# Motif d'une suppression d'offre. Une liste fermée, pas un texte libre : c'est ce qui permet de les compter
DeleteReason = Literal["not_my_job", "profile", "location", "contract", "not_an_offer", "not_interested"]
DELETE_REASONS: dict[DeleteReason, str] = {
    "not_my_job": "Ce n'est pas mon métier",
    "profile": "Compétences ou niveau qui ne collent pas",
    "location": "Lieu qui ne convient pas",
    "contract": "Contrat qui ne convient pas",
    "not_an_offer": "Annonce expirée, ou page sans offre",
    "not_interested": "Elle ne m'intéresse pas",
}
# Motifs qui ne reprochent rien au tri : l'offre était bien une offre pour ce profil
DELETE_REASONS_WITHOUT_ERROR: frozenset[DeleteReason] = frozenset({"not_interested"})
DELETE_REASON_NOT_GIVEN = "Sans motif"

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
    # Parts des jetons d'entrée lues ou écrites en cache, et part des jetons de sortie passée en raisonnement
    cache_read_tokens: int | None
    cache_write_tokens: int | None
    reasoning_tokens: int | None
    # Durée de la recherche, toutes étapes franchies réunies ; None si aucune n'a été mesurée
    duration_ms: int | None = None
    # Coûts en dollars, calculés aux tarifs actuels ; None quand une consommation ou un tarif n'est pas connu
    search_cost_usd: float | None = None
    model_cost_usd: float | None = None
    cost_usd: float | None = None


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
    cache_read_tokens: int | None
    cache_write_tokens: int | None
    reasoning_tokens: int | None
    duration_ms: int | None
    # Coût de l'appel au modèle en dollars, aux tarifs actuels ; None si ses jetons ou son tarif ne sont pas connus
    model_cost_usd: float | None = None
    created_at: datetime


class EvaluationGroup(BaseModel):
    """Pages évaluées qui partagent un trait : même recherche, même site, même nature."""

    label: str
    evaluated: int
    kept: int
    # Pages qui n'étaient pas des offres : listes, articles, offres expirées…
    not_an_offer: int
    # Offres écartées pour leur métier, leur contrat, leur lieu ou le CV
    rejected_offers: int
    input_tokens: int
    output_tokens: int
    model_cost_usd: float | None


class SearchYield(BaseModel):
    """Ce qu'un texte envoyé au moteur de recherche a rapporté, tous lancements réunis.

    Les pages rendues se partagent en quatre : déjà rendues par un autre appel du même lancement, déjà
    connues (offres ou rejets d'une recherche passée), évaluées puis écartées, évaluées puis retenues.
    """

    # Phrase saisie par l'utilisateur, et texte réellement envoyé
    query: str
    search_text: str
    # Variante en anglais d'une recherche en télétravail complet
    international: bool
    calls: int
    found: int
    repeated: int
    known: int
    rejected: int
    kept: int
    # Coût de ces appels en dollars, et ce que chaque offre retenue a coûté en appels ; None sans offre retenue
    search_cost_usd: float
    cost_per_kept_usd: float | None


class OutcomeGroup(BaseModel):
    """Ce que sont devenues des offres retenues par le tri : c'est ce qui dit s'il retient les bonnes.

    Les offres se partagent en quatre : entretien obtenu, candidature envoyée sans entretien, encore à
    traiter, supprimée sans candidature. Une page que l'utilisateur a remise lui-même n'y figure pas.
    """

    label: str
    kept: int
    # Candidatures envoyées, quelle que soit leur suite, et parmi elles celles refusées par l'employeur
    applied: int
    refused: int
    interviews: int
    pending: int
    deleted: int
    # Parts des offres retenues qui ont mené à une candidature, et des candidatures à un entretien
    applied_rate: float | None
    interview_rate: float | None


class CorrectionStats(BaseModel):
    """Ce que l'utilisateur a corrigé du tri rendu avec une version du prompt.

    Les taux sont des planchers : une erreur que l'utilisateur n'a pas signalée n'y est pas.
    """

    # None : pages évaluées avant le suivi, dont la version du prompt n'est pas connue
    prompt_version: str | None
    # Pages jugées avec cette version, d'après le journal
    evaluated: int
    kept: int
    rejected: int
    # Pages écartées que l'utilisateur a remises dans ses offres
    restored: int
    # Offres retenues que l'utilisateur a supprimées en reprochant quelque chose au tri
    wrongly_kept: int
    # Offres supprimées sans motif, ou parce qu'elles ne l'intéressaient pas
    other_deleted: int
    # Parts des pages écartées remises, et des offres retenues à tort ; None sans page à comparer
    restored_rate: float | None
    wrongly_kept_rate: float | None


class ReasonCount(BaseModel):
    label: str
    count: int


class WeekStats(BaseModel):
    """Une semaine de recherches d'un utilisateur, du lundi au dimanche à l'heure de Paris."""

    # Lundi à minuit, heure de Paris
    start: datetime
    runs: int
    # Recherches échouées ou interrompues
    failed_runs: int
    # None si le coût d'une recherche de la semaine n'est pas connu
    cost_usd: float | None
    found: int
    evaluated: int
    # Part des pages trouvées qui étaient déjà connues : proche de 1, les recherches ne ramènent plus rien de neuf
    known_rate: float | None
    kept: int
    # Part des pages évaluées qui ont été retenues
    kept_rate: float | None
    # Candidatures envoyées pendant la semaine, quelle que soit la date où l'offre a été trouvée
    applications: int


class SearchStats(BaseModel):
    """Synthèse de toutes les recherches suivies d'un utilisateur. Les coûts sont en dollars, aux tarifs actuels."""

    # Lancements dont le bilan a été enregistré, et parmi eux ceux qui ont échoué ou ont été interrompus
    runs: int
    unfinished_runs: int
    found_count: int
    new_count: int
    kept_count: int
    rejected_count: int
    search_calls: int
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    reasoning_tokens: int
    search_cost_usd: float
    # None dès qu'un lancement a consommé des jetons d'un modèle sans tarif connu
    model_cost_usd: float | None
    cost_usd: float | None
    cost_per_kept_usd: float | None
    # Durée moyenne d'une recherche terminée, toutes étapes réunies
    average_duration_ms: int | None
    # Répartitions des pages évaluées, le groupe le plus fourni en premier
    by_query: list[EvaluationGroup]
    by_site: list[EvaluationGroup]
    by_page_kind: list[EvaluationGroup]
    # Selon le texte lu par le modèle : page entière, page tronquée, ou extrait du moteur de recherche
    by_text: list[EvaluationGroup]
    # Les dernières semaines, la plus ancienne en premier, celle en cours en dernier ; une semaine vide y figure
    weeks: list[WeekStats]
    # Devenir de toutes les offres retenues, puis par poste recherché, par site et par version du prompt
    outcomes: OutcomeGroup
    outcomes_by_query: list[OutcomeGroup]
    outcomes_by_site: list[OutcomeGroup]
    outcomes_by_prompt: list[OutcomeGroup]
    # Coût total rapporté aux candidatures nées des recherches suivies ; None sans candidature ou sans coût connu
    cost_per_application_usd: float | None
    # Rendement de chaque texte envoyé au moteur de recherche, le moins rentable en premier
    by_search: list[SearchYield]
    # Corrections du tri par version du prompt, la plus récente en premier
    corrections: list[CorrectionStats]
    # Motifs des suppressions d'offres, le plus fréquent en premier
    delete_reasons: list[ReasonCount]


class SearchSummary(BaseModel):
    found: int
    new: int
    kept: int
    rejected: int
    inserted: int


# « available » : un essai sans compte peut s'ouvrir ; « exhausted » : plus aujourd'hui, pour personne
TrialStatus = Literal["available", "exhausted"]


class AppConfig(BaseModel):
    """Ce qu'un front doit savoir avant toute connexion. Servi sans identité : rien de secret ici."""

    # Preuve d'identité attendue par « POST /api/session » ; None si l'instance n'est pas protégée, et refuse tout
    login_mode: Literal["google", "password"] | None
    # Identifiant public de l'application chez Google, pour le bouton de connexion ; None hors connexion Google
    google_client_id: str | None
    # Essai sans compte, par « POST /api/session/trial » ; None si l'instance n'en propose pas
    trial: TrialStatus | None
    contract_types: list[str]
    # Motifs proposés à la suppression d'une offre, dans l'ordre où les présenter
    delete_reasons: list["DeleteReasonOption"]


class DeleteReasonOption(BaseModel):
    code: DeleteReason
    label: str


# Formule d'un compte. Il n'y a pas encore de paiement : tout compte est « free » (DEFAULT_PLAN de config.py),
# sauf un compte d'essai, ouvert sans connexion, qui est « trial » (TRIAL_PLAN)
AccountPlan = Literal["free", "paid", "trial"]


class AccountUsage(BaseModel):
    """Ce qu'un compte a consommé et coûté sur la période. Des nombres seulement, plus l'adresse du compte."""

    user_id: int
    # None pour le propriétaire, que la table des comptes ne connaît pas par son adresse, pour un compte
    # d'essai, qui n'en a pas, et pour un compte supprimé
    email: str | None
    is_owner: bool
    # Compte supprimé : seuls ses totaux restent, et « last_search_at » n'est plus connu
    deleted: bool
    # Formule du compte, ou celle qu'il avait à sa suppression
    plan: AccountPlan
    # Lancements suivis, échecs compris : ils ont pu consommer des crédits
    runs: int
    found_count: int
    kept_count: int
    search_calls: int
    input_tokens: int
    output_tokens: int
    search_cost_usd: float
    # None dès qu'un lancement a consommé des jetons d'un modèle sans tarif connu
    model_cost_usd: float | None
    cost_usd: float | None
    last_search_at: datetime | None


class UsageOverview(BaseModel):
    """Consommation de tous les comptes, pour les administrateurs. Les coûts sont en dollars, aux tarifs actuels."""

    # Début de la période ; None quand tout l'historique est compté
    since: datetime | None
    # Les comptes qui ont lancé une recherche sur la période, supprimés depuis ou non, le plus coûteux en premier
    accounts: list[AccountUsage]
    runs: int
    kept_count: int
    search_cost_usd: float
    model_cost_usd: float | None
    cost_usd: float | None
    # Part du coût due aux comptes autres que celui du propriétaire
    guests_cost_usd: float | None


class RunFailureGroup(BaseModel):
    """Recherches échouées sur une même erreur, tous comptes réunis."""

    # Type de l'erreur, jamais son message
    error_type: str
    count: int
    accounts: int
    last_at: datetime | None


class ServerErrorGroup(BaseModel):
    """Erreurs d'un même type rendues par une même route de l'API, tous comptes réunis."""

    method: str
    # Modèle de la route, jamais l'adresse appelée ; None quand aucune route n'a été trouvée
    route: str | None
    status_code: int
    error_type: str
    # Vrai pour une panne du serveur, faux pour une demande qu'il a refusée
    is_failure: bool
    count: int
    # Comptes identifiés qui l'ont rencontrée
    accounts: int
    last_at: datetime | None


# Ce que le front peut dire d'une erreur : des noms et des positions, rien qui puisse porter un contenu
CLIENT_ERROR_TYPE_PATTERN = r"^[A-Za-z_][A-Za-z0-9_.]*$"
CLIENT_ROUTE_PATTERN = r"^/[A-Za-z0-9/_-]*$"
CLIENT_SOURCE_PATTERN = r"^[A-Za-z0-9_.-]+\.js:\d+(:\d+)?$"


class ClientErrorReport(BaseModel):
    """Erreur survenue dans le navigateur, telle que le front la signale. Jamais son message."""

    error_type: str = Field(max_length=80, pattern=CLIENT_ERROR_TYPE_PATTERN)
    # Écran du front, sans paramètre
    route: str | None = Field(default=None, max_length=120, pattern=CLIENT_ROUTE_PATTERN)
    # Fichier du front et position dans ce fichier
    source: str | None = Field(default=None, max_length=120, pattern=CLIENT_SOURCE_PATTERN)


class ClientErrorGroup(BaseModel):
    """Erreurs du front d'un même type, au même endroit du code et sur le même écran, tous comptes réunis."""

    route: str | None
    error_type: str
    source: str | None
    count: int
    accounts: int
    last_at: datetime | None


class HealthOverview(BaseModel):
    """Santé de l'instance, pour les administrateurs : ce qui a échoué, sur tous les comptes, en nombres seulement."""

    # Début de la période ; None quand tout l'historique est compté
    since: datetime | None
    # Recherches échouées ou interrompues, pannes du serveur et erreurs du front ; une demande refusée n'en est pas un
    incidents: int
    healthy: bool
    runs: int
    failed_runs: int
    # Recherches coupées par un redémarrage du serveur
    interrupted_runs: int
    # Part des recherches échouées ou interrompues ; None sans recherche
    failure_rate: float | None
    interrupted_accounts: int
    last_interrupted_at: datetime | None
    # Recherches échouées par type d'erreur, le plus fréquent en premier
    run_failures: list[RunFailureGroup]
    # Réponses 5xx de l'API hors d'une recherche, puis demandes refusées (4xx)
    failures: int
    refusals: int
    # Les pannes d'abord, puis le plus fréquent en premier
    server_errors: list[ServerErrorGroup]
    # Erreurs survenues dans le navigateur des utilisateurs, la plus fréquente en premier
    client_failures: int
    client_errors: list[ClientErrorGroup]
    # Modèles utilisés sur la période dont le tarif manque (MODEL_PRICES_USD) : leurs coûts ne sont pas comptés
    unpriced_models: list[str]
    # Vrai quand un incident prévient quelqu'un (NTFY_TOPIC) ; faux, il ne se voit qu'ici
    alerts_enabled: bool


class AlertTest(BaseModel):
    """Issue d'une alerte d'essai."""

    sent: bool


class JourneyStep(BaseModel):
    """Une étape du parcours, et les comptes qui l'ont franchie."""

    label: str
    count: int
    # Part des comptes comptés ; None sans aucun
    rate: float | None


class AccountJourney(BaseModel):
    """Où en est un compte : des nombres seulement, plus l'adresse du compte."""

    user_id: int
    # None pour le propriétaire, que la table des comptes ne connaît pas par son adresse, et pour un compte d'essai
    email: str | None
    is_owner: bool
    # Compte d'essai, ouvert sans connexion : il n'est pas compté parmi les utilisateurs
    is_trial: bool
    created_at: datetime
    # Au jour près
    last_seen_at: datetime | None
    has_cv: bool
    queries: int
    runs: int
    # Offres retenues par le tri ou remises par l'utilisateur, supprimées comprises
    kept: int
    # Offres dont l'annonce a été ouverte depuis l'application
    opened: int
    applied: int
    interviews: int
    corrections: int
    # Vu un autre jour que celui de la création du compte
    returned: bool
    # Jours où le compte s'est servi de l'application ; 0 pour le propriétaire, dont l'activité n'est pas datée
    active_days: int
    # Dernière étape du parcours franchie, et jours écoulés depuis la dernière visite
    step: str
    idle_days: int | None


class JourneyEvent(BaseModel):
    """Un moment du parcours d'un compte : ce qu'il a fait, jamais sur quoi."""

    at: datetime
    # account, cv, query, search, opened, applied, interview, refused, restored, deleted, error
    kind: str
    label: str
    detail: str | None = None


class RejectionCount(BaseModel):
    """Pages écartées pour une raison donnée. Une page peut en avoir plusieurs."""

    label: str
    count: int
    # Part des pages écartées
    rate: float | None


class AccountDetail(BaseModel):
    """Fiche d'un compte, pour les administrateurs : sa chronologie et ce qui écarte ses pages.

    Des dates, des nombres et des motifs : ni intitulé d'offre, ni lien, ni phrase de recherche.
    """

    account: AccountJourney
    evaluated: int
    rejected: int
    # Pourquoi ses pages sont écartées, la raison la plus fréquente en premier
    rejections: list[RejectionCount]
    # Le plus récent en premier
    events: list[JourneyEvent]


class JourneyOverview(BaseModel):
    """Parcours des utilisateurs, pour les administrateurs : qui va jusqu'à postuler, et qui revient."""

    guests: int
    # Du compte créé au retour un autre jour, dans l'ordre du parcours ; ni le propriétaire ni les comptes
    # d'essai n'y sont comptés
    steps: list[JourneyStep]
    # Comptes d'essai encore en place, et les mêmes étapes comptées sur eux seuls
    trials: int
    trial_steps: list[JourneyStep]
    # Tous les comptes, le dernier vu en premier ; un compte supprimé n'y est plus
    accounts: list[AccountJourney]


class BudgetOverview(BaseModel):
    """Dépense du mois en cours, tous comptes réunis, face au budget de l'instance. Montants en dollars."""

    # Premier jour du mois à minuit, heure de Paris
    month_start: datetime
    # 0 : aucun budget n'est fixé, et les parts et dépassements ci-dessous restent vides ou faux
    budget_usd: float
    runs: int
    spent_usd: float
    # Vrai quand le tarif d'un modèle manque : la dépense ne compte alors que le moteur de recherche
    partial: bool
    # Part due aux comptes autres que celui du propriétaire ; None si elle n'est pas connue
    guests_spent_usd: float | None
    day_of_month: int
    days_left: int
    daily_average_usd: float
    # Dépense à la fin du mois si le rythme des jours écoulés se maintient
    projected_usd: float
    spent_rate: float | None
    projected_rate: float | None
    over_budget: bool
    projected_over_budget: bool
    # Budget du jour, à l'heure de Paris, et ce qui en est dépensé. 0 : aucun budget du jour n'est fixé.
    # Atteint, il refuse les recherches jusqu'au lendemain, sauf celles du propriétaire
    daily_budget_usd: float
    today_spent_usd: float
    daily_budget_reached: bool


class Account(BaseModel):
    user_id: int
    is_owner: bool
    # Compte d'essai, ouvert sans connexion : reconnu par son seul cookie, et limité à MAX_TRIAL_SEARCHES recherches
    is_trial: bool
    # Le propriétaire, ou une adresse d'ADMIN_EMAILS : il a accès au suivi des recherches et des coûts
    is_admin: bool
    # Adresse, nom et photo du compte Google ; None avec le mot de passe de l'instance
    email: str | None
    name: str | None
    picture: str | None
    # Un CV et au moins un poste recherché sont enregistrés
    can_search: bool
    # Une recherche de cet utilisateur tourne sur le serveur : il ne peut pas en lancer une autre
    search_running: bool
    # None pour le propriétaire, qui n'a pas de quota. Pour un compte d'essai, ce qu'il lui reste en tout,
    # et non pour aujourd'hui
    remaining_searches: int | None
    max_searches_per_day: int


# Longueur d'une question à l'assistant : au-delà, ce n'est plus une question, et chaque caractère est payé
MAX_QUESTION_CHARS = 500
# « answered » : l'assistant a répondu à partir des textes du site ; « unknown » : la question porte sur
# l'application, mais les textes n'y répondent pas ; « off_topic » : elle ne porte pas sur l'application
AssistantOutcome = Literal["answered", "unknown", "off_topic"]


class AssistantQuestion(BaseModel):
    question: str = Field(min_length=1, max_length=MAX_QUESTION_CHARS)


class AssistantSource(BaseModel):
    """Texte du site d'où vient une réponse de l'assistant."""

    title: str
    # Section du texte ; None pour son introduction
    section: str | None
    # Adresse de la page ; None pour le guide d'utilisation, qui n'est pas une page du site
    url: str | None


class AssistantMessageRead(BaseModel):
    id: int
    created_at: datetime
    question: str
    answer: str
    outcome: AssistantOutcome
    sources: list[AssistantSource]


class AssistantConversation(BaseModel):
    """Ce que l'assistant affiche à son ouverture : les derniers échanges, et ce qui peut encore être demandé."""

    messages: list[AssistantMessageRead]
    # None pour le propriétaire, qui n'a pas de quota
    remaining_questions: int | None
    max_questions_per_day: int
    max_question_chars: int
    # Nombre de jours pendant lesquels le texte d'une question est gardé
    retention_days: int


class AssistantReply(BaseModel):
    message: AssistantMessageRead
    remaining_questions: int | None


class AssistantJournalEntry(BaseModel):
    """Question posée à l'assistant, telle que la lit un administrateur : sans le compte qui l'a posée."""

    created_at: datetime
    question: str
    answer: str
    outcome: AssistantOutcome
    sources: list[AssistantSource]
    # Textes d'où venaient les passages donnés au modèle, le plus proche en premier : ceux de « sources »
    # en font partie. Vide pour une question d'avant leur enregistrement
    retrieved: list[AssistantSource]


class AssistantOverview(BaseModel):
    """Usage de l'assistant, tous comptes réunis : ce qu'on lui demande, et ce qu'il ne sait pas dire."""

    # Début de la période comptée ; None quand tout l'historique l'est
    since: datetime | None
    questions: int
    answered: int
    # Questions sur l'application restées sans réponse : ce qui manque aux textes du site
    unknown: int
    off_topic: int
    # Comptes qui ont posé au moins une question
    accounts: int
    # Coût en dollars ; None si le tarif d'un modèle manque
    cost_usd: float | None
    # Dernières questions encore lisibles, la plus récente en premier
    entries: list[AssistantJournalEntry]


class AssistantEvaluationRead(BaseModel):
    """Passage du banc d'évaluation de l'assistant. Les parts vont de 0 à 1 ; None quand rien n'était à mesurer."""

    id: int
    created_at: datetime
    # Ce qui a été mesuré, et le modèle qui a noté les réponses
    model: str
    embedding_model: str
    judge_model: str
    prompt_version: str
    cases: int
    # Questions auxquelles rien n'est à reprocher
    passed: int
    pass_rate: float | None
    # L'issue (réponse, renvoi vers l'exploitant, refus) est celle attendue
    outcome_rate: float | None
    # La section attendue est parmi les passages retrouvés ; et son rang moyen, 1 quand elle arrive toujours en tête
    retrieval_rate: float | None
    mean_reciprocal_rank: float | None
    # La réponse cite la section attendue
    citation_rate: float | None
    # La réponse dit ce que dit la réponse de référence
    correct_rate: float | None
    # La réponse ne dit que ce que disent les passages
    faithful_rate: float | None
    # Les questions hors sujet sont refusées
    refusal_rate: float | None
    duration_ms: int
    # Coût en dollars ; None si le tarif d'un modèle manque
    cost_usd: float | None


class AssistantEvaluationCase(BaseModel):
    """Ce qu'une question de référence a donné pendant une évaluation."""

    id: str
    question: str
    expected_outcome: AssistantOutcome
    outcome: AssistantOutcome
    passed: bool
    answer: str
    # Titres des passages donnés au modèle, le plus proche en premier
    retrieved: list[str]
    # Rang de la section attendue parmi eux ; None si elle n'y est pas, ou si la question n'en attend pas
    rank: int | None
    # La réponse cite-t-elle la section attendue ; None si la question n'en attend pas
    cited: bool | None
    # Avis du juge, et sa raison ; None quand il n'a pas été consulté
    faithful: bool | None
    correct: bool | None
    judge_reason: str


class AssistantEvaluationDetail(AssistantEvaluationRead):
    # Les questions qui échouent en premier
    results: list[AssistantEvaluationCase]
