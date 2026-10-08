"""Objets échangés entre les services et les interfaces. L'API les sert tels quels en JSON."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class _FromRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class JobRead(_FromRow):
    id: int
    url: str
    title: str
    content: str | None
    score: float | None
    contract_type: str | None
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
    reject_reason: str | None
    created_at: datetime


class SearchQueryRead(_FromRow):
    id: int
    contract_type: str
    query: str
    created_at: datetime


class CvStatus(BaseModel):
    # None tant que l'utilisateur n'a pas déposé de CV
    updated_at: datetime | None


class SearchProgress(BaseModel):
    message: str
    # Renseignés quand l'avancement se mesure
    done: int | None = None
    total: int | None = None


class SearchSummary(BaseModel):
    found: int
    new: int
    kept: int
    rejected: int
    inserted: int


class Account(BaseModel):
    user_id: int
    is_owner: bool
    # None pour le propriétaire, qui n'a pas de quota
    remaining_searches: int | None
    max_searches_per_day: int
