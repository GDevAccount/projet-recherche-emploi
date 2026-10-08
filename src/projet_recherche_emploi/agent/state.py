from typing import TypedDict


class FoundPage(TypedDict):
    """Page trouvée par la recherche web, avec la recherche enregistrée qui l'a trouvée."""

    title: str
    url: str
    content: str
    raw_content: str | None
    score: float
    contract_type: str
    query: str


class KeptJob(FoundPage):
    match_reason: str


class RejectedPage(FoundPage):
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
