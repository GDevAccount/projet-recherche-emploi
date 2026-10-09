from typing import Any, TypedDict


class FoundPage(TypedDict):
    """Page trouvée par la recherche web, avec le texte de la recherche enregistrée qui l'a trouvée."""

    title: str
    url: str
    content: str
    raw_content: str | None
    score: float
    query: str


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


class JobSearchState(TypedDict, total=False):
    user_id: int
    jobs: list[FoundPage]
    # Ce que l'utilisateur cherche, toutes recherches confondues (SearchCriteria de ports.py)
    criteria: Any
    new_jobs: list[FoundPage]
    filtered_jobs: list[KeptJob]
    rejected_jobs: list[RejectedPage]
    inserted_count: int
