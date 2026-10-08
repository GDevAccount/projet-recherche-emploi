"""Tables de la base. Les types reprennent ceux des bases créées avant SQLAlchemy (TEXT, INTEGER, REAL).

Changer une table ici ne change aucune base existante : il faut une migration (voir data/migrations).
"""

from datetime import UTC, datetime

from sqlalchemy import REAL, Integer, Text, UniqueConstraint, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator

from projet_recherche_emploi.config import DEFAULT_USER_ID

# Format de CURRENT_TIMESTAMP dans SQLite : les dates écrites par Python doivent se comparer aux siennes
SQLITE_TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"


class UtcDateTime(TypeDecorator):
    """Date enregistrée en texte UTC, rendue avec son fuseau."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect) -> str | None:
        if value is None:
            return None
        if value.tzinfo is not None:
            value = value.astimezone(UTC)
        return value.strftime(SQLITE_TIMESTAMP_FORMAT)

    def process_result_value(self, value: str | None, dialect) -> datetime | None:
        if value is None:
            return None
        return datetime.fromisoformat(value).replace(tzinfo=UTC)


class IntBool(TypeDecorator):
    """Booléen enregistré en 0 ou 1."""

    impl = Integer
    cache_ok = True

    def process_bind_param(self, value: bool | None, dialect) -> int | None:
        return None if value is None else int(value)

    def process_result_value(self, value: int | None, dialect) -> bool | None:
        return None if value is None else bool(value)


class Base(DeclarativeBase):
    pass


class Job(Base):
    """Offre retenue. Une URL est unique par utilisateur : la même offre peut être retenue par plusieurs."""

    __tablename__ = "jobs"
    __table_args__ = (UniqueConstraint("user_id", "url"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, server_default=text(str(DEFAULT_USER_ID)))
    url: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    content: Mapped[str | None] = mapped_column(Text)
    score: Mapped[float | None] = mapped_column(REAL)
    contract_type: Mapped[str | None] = mapped_column(Text)
    work_location: Mapped[str | None] = mapped_column(Text)
    query: Mapped[str | None] = mapped_column(Text)
    match_reason: Mapped[str | None] = mapped_column(Text)
    applied: Mapped[bool] = mapped_column(IntBool, server_default=text("0"))
    applied_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, server_default=text("CURRENT_TIMESTAMP"))
    deleted: Mapped[bool] = mapped_column(IntBool, server_default=text("0"))


class RejectedJob(Base):
    """Page rejetée par le modèle. Un rejet dépend du CV, donc de l'utilisateur."""

    __tablename__ = "rejected_jobs"

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True, server_default=text(str(DEFAULT_USER_ID)))
    url: Mapped[str] = mapped_column(Text, primary_key=True)
    title: Mapped[str] = mapped_column(Text)
    contract_type: Mapped[str | None] = mapped_column(Text)
    query: Mapped[str | None] = mapped_column(Text)
    is_real_offer: Mapped[bool] = mapped_column(IntBool)
    matches_cv: Mapped[bool] = mapped_column(IntBool)
    # Détail du verdict, vide pour les pages rejetées avant qu'il soit enregistré critère par critère.
    # matches_cv réunit les compétences et le niveau.
    matches_search: Mapped[bool | None] = mapped_column(IntBool)
    matches_contract: Mapped[bool | None] = mapped_column(IntBool)
    matches_skills: Mapped[bool | None] = mapped_column(IntBool)
    matches_level: Mapped[bool | None] = mapped_column(IntBool)
    matches_location: Mapped[bool | None] = mapped_column(IntBool)
    work_location: Mapped[str | None] = mapped_column(Text)
    reject_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, server_default=text("CURRENT_TIMESTAMP"))


class SearchQuery(Base):
    """Poste recherché. Une recherche est unique par utilisateur : deux utilisateurs peuvent enregistrer la même."""

    __tablename__ = "search_queries"
    __table_args__ = (UniqueConstraint("user_id", "query", "location", "remote"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, server_default=text(str(DEFAULT_USER_ID)))
    contract_type: Mapped[str] = mapped_column(Text)
    query: Mapped[str] = mapped_column(Text)
    # Vide : toute la France
    location: Mapped[str] = mapped_column(Text, server_default=text("''"))
    # Télétravail complet : le lieu ne compte plus
    remote: Mapped[bool] = mapped_column(IntBool, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, server_default=text("CURRENT_TIMESTAMP"))


class User(Base):
    """Compte d'un invité. La ligne 1, sans adresse, réserve l'identifiant du propriétaire."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str | None] = mapped_column(Text, unique=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, server_default=text("CURRENT_TIMESTAMP"))


class SearchRun(Base):
    """Lancement d'une recherche, compté par le quota journalier."""

    __tablename__ = "search_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, server_default=text("CURRENT_TIMESTAMP"))
