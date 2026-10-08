from typing import TypedDict


class FoundPage(TypedDict):
    """Page trouvée par la recherche web, avec le texte de la recherche enregistrée qui l'a trouvée."""

    title: str
    url: str
    content: str
    raw_content: str | None
    score: float
    query: str


class KeptJob(FoundPage):
    # Contrat lu sur la page par le modèle, pas celui de la recherche
    contract_type: str | None
    match_reason: str


class RejectedPage(FoundPage):
    contract_type: str | None
    is_real_offer: bool
    matches_cv: bool
    reject_reason: str


class JobSearchState(TypedDict, total=False):
    user_id: int
    jobs: list[FoundPage]
    new_jobs: list[FoundPage]
    filtered_jobs: list[KeptJob]
    rejected_jobs: list[RejectedPage]
    inserted_count: int
