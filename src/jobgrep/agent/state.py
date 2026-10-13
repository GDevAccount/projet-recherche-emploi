import operator
from typing import Annotated, Any, NotRequired, TypedDict


class FoundPage(TypedDict):
    """Page trouvée par la recherche web, avec le texte de la recherche enregistrée qui l'a trouvée."""

    title: str
    url: str
    content: str
    raw_content: str | None
    score: float
    query: str
    # Rang, dans le lancement, de l'appel au moteur qui l'a rendue le premier (« searches » de l'état)
    search_index: int
    # Empreinte du texte entier de la page (agent/duplicates.py) ; None quand le moteur n'a rendu que l'extrait
    text_fingerprint: NotRequired[list[int] | None]


class KeptJob(FoundPage):
    # Contrat et lieu lus sur la page par le modèle, pas ceux de la recherche
    contract_type: str | None
    work_location: str | None
    match_reason: str


class RejectedPage(FoundPage):
    contract_type: str | None
    work_location: str | None
    is_real_offer: bool
    page_kind: str
    # Compétences et niveau réunis
    matches_cv: bool
    matches_search: bool
    matches_contract: bool
    matches_skills: bool
    matches_level: bool
    matches_location: bool
    reject_reason: str
    # Vrai pour une page écartée sans évaluation : la même annonce a déjà été vue sur un autre site
    duplicate: NotRequired[bool]


class JobSearchState(TypedDict, total=False):
    user_id: int
    # Lancement enregistré par SearchService, auquel le journal des évaluations se rattache
    run_id: int | None
    jobs: list[FoundPage]
    # Un élément par appel au moteur de recherche, dans l'ordre : texte envoyé, pages rendues, durée
    searches: list[dict]
    # Ce que l'utilisateur cherche, toutes recherches confondues (SearchCriteria de ports.py)
    criteria: Any
    new_jobs: list[FoundPage]
    # Pages qui reprennent une annonce déjà vue sur un autre site : écartées sans être évaluées
    duplicates: list[RejectedPage]
    filtered_jobs: list[KeptJob]
    rejected_jobs: list[RejectedPage]
    inserted_count: int
    # Une ligne par page évaluée, retenue ou non, pour le journal (table page_evaluations)
    evaluations: list[dict]
    # Mesures du lancement, complétées par chaque nœud : durées, appels, jetons, modèle
    metrics: Annotated[dict[str, Any], operator.or_]
