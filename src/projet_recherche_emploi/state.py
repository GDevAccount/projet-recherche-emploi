from typing import TypedDict


class JobSearchState(TypedDict, total=False):
    query: str
    jobs: list[dict]
    filtered_jobs: list[dict]
    inserted_count: int
