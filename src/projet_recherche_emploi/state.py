from typing import TypedDict


class JobSearchState(TypedDict, total=False):
    user_id: int
    query: str
    jobs: list[dict]
    new_jobs: list[dict]
    filtered_jobs: list[dict]
    rejected_jobs: list[dict]
    inserted_count: int
