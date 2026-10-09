"""Tables de la base. Les types reprennent ceux des bases créées avant SQLAlchemy (TEXT, INTEGER, REAL).

Changer une table ici ne change aucune base existante : il faut une migration (voir data/migrations).
"""

from datetime import UTC, datetime

from sqlalchemy import REAL, Index, Integer, Text, UniqueConstraint, text
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
    # État de la candidature : todo, applied, interview ou rejected (JobStatus de schemas.py)
    status: Mapped[str] = mapped_column(Text, server_default=text("'todo'"))
    # Date de chaque étape franchie ; vide tant qu'elle ne l'est pas
    applied_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    interview_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    rejected_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
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
    # Nature de la page (PageKind), vide pour les pages rejetées avant qu'elle soit enregistrée
    page_kind: Mapped[str | None] = mapped_column(Text)
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
    # Dernière requête identifiée, au jour près : sert à supprimer les comptes inactifs
    last_seen_at: Mapped[datetime | None] = mapped_column(UtcDateTime)


class CvText(Base):
    """Texte du CV d'un utilisateur, coordonnées retirées. C'est lui que le filtre envoie au modèle, pas le PDF."""

    __tablename__ = "cv_texts"

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    content: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime, server_default=text("CURRENT_TIMESTAMP"))


class SearchRun(Base):
    """Lancement d'une recherche : compté par le quota journalier, puis complété par son bilan.

    Tout sauf la date est vide pour les lancements d'avant le suivi.
    """

    __tablename__ = "search_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, server_default=text("CURRENT_TIMESTAMP"))
    # « running » à l'enregistrement, puis « done » ou « failed » : un lancement interrompu reste « running »
    status: Mapped[str | None] = mapped_column(Text)
    # Type de l'erreur d'une recherche échouée, sans son message : le détail est dans les logs
    error: Mapped[str | None] = mapped_column(Text)
    finished_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    model: Mapped[str | None] = mapped_column(Text)
    prompt_version: Mapped[str | None] = mapped_column(Text)
    found_count: Mapped[int | None] = mapped_column(Integer)
    new_count: Mapped[int | None] = mapped_column(Integer)
    kept_count: Mapped[int | None] = mapped_column(Integer)
    rejected_count: Mapped[int | None] = mapped_column(Integer)
    inserted_count: Mapped[int | None] = mapped_column(Integer)
    # Durée de chaque étape du graph, en millisecondes
    search_ms: Mapped[int | None] = mapped_column(Integer)
    dedupe_ms: Mapped[int | None] = mapped_column(Integer)
    evaluate_ms: Mapped[int | None] = mapped_column(Integer)
    save_ms: Mapped[int | None] = mapped_column(Integer)
    # Ce que la recherche a consommé : appels au moteur de recherche, jetons du modèle
    search_calls: Mapped[int | None] = mapped_column(Integer)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    # Parts des jetons d'entrée lues ou écrites en cache, et part des jetons de sortie passée en raisonnement
    cache_read_tokens: Mapped[int | None] = mapped_column(Integer)
    cache_write_tokens: Mapped[int | None] = mapped_column(Integer)
    reasoning_tokens: Mapped[int | None] = mapped_column(Integer)


class PageEvaluation(Base):
    """Journal des pages évaluées, retenues ou non : ce que le modèle a lu, le verdict, et ce que l'appel a coûté.

    Contrairement à rejected_jobs, il n'est pas vidé au changement de CV : il raconte ce qui s'est passé.
    """

    __tablename__ = "page_evaluations"
    __table_args__ = (Index("ix_page_evaluations_run", "user_id", "search_run_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer)
    # Vide pour une recherche lancée sans passer par SearchService
    search_run_id: Mapped[int | None] = mapped_column(Integer)
    url: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    query: Mapped[str | None] = mapped_column(Text)
    # Score donné par le moteur de recherche
    score: Mapped[float | None] = mapped_column(REAL)
    kept: Mapped[bool] = mapped_column(IntBool)
    # Faits lus sur la page par le modèle
    page_kind: Mapped[str | None] = mapped_column(Text)
    contract_type: Mapped[str | None] = mapped_column(Text)
    work_city: Mapped[str | None] = mapped_column(Text)
    work_country: Mapped[str | None] = mapped_column(Text)
    work_mode: Mapped[str | None] = mapped_column(Text)
    in_accepted_area: Mapped[bool | None] = mapped_column(IntBool)
    open_to_candidates_in_france: Mapped[bool | None] = mapped_column(IntBool)
    # Avis du modèle
    matches_search: Mapped[bool | None] = mapped_column(IntBool)
    matches_skills: Mapped[bool | None] = mapped_column(IntBool)
    matches_level: Mapped[bool | None] = mapped_column(IntBool)
    # Règles appliquées par le graph
    matches_contract: Mapped[bool | None] = mapped_column(IntBool)
    matches_location: Mapped[bool | None] = mapped_column(IntBool)
    reason: Mapped[str | None] = mapped_column(Text)
    # Longueur du texte disponible ; au-delà de MAX_PAGE_CHARS, le modèle n'en a lu que le début
    page_chars: Mapped[int | None] = mapped_column(Integer)
    truncated: Mapped[bool | None] = mapped_column(IntBool)
    # Faux quand seul l'extrait du moteur de recherche était disponible
    full_page: Mapped[bool | None] = mapped_column(IntBool)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    # Parts des jetons d'entrée lues ou écrites en cache, et part des jetons de sortie passée en raisonnement
    cache_read_tokens: Mapped[int | None] = mapped_column(Integer)
    cache_write_tokens: Mapped[int | None] = mapped_column(Integer)
    reasoning_tokens: Mapped[int | None] = mapped_column(Integer)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, server_default=text("CURRENT_TIMESTAMP"))


class EngineCall(Base):
    """Appel au moteur de recherche pendant un lancement : ce qu'il a rendu, et ce que ses pages sont devenues.

    Chaque appel est payé, qu'il ramène du neuf ou non : c'est ce qui dit quel poste recherché rapporte.
    """

    __tablename__ = "engine_calls"
    __table_args__ = (Index("ix_engine_calls_user", "user_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer)
    search_run_id: Mapped[int] = mapped_column(Integer)
    # Phrase saisie par l'utilisateur, et texte réellement envoyé au moteur
    query: Mapped[str] = mapped_column(Text)
    search_text: Mapped[str] = mapped_column(Text)
    # Variante en anglais d'une recherche en télétravail complet, sur les sites internationaux
    international: Mapped[bool] = mapped_column(IntBool)
    # Pages rendues par l'appel
    found_count: Mapped[int] = mapped_column(Integer)
    # Parmi elles, celles qu'aucun appel précédent du lancement n'avait déjà rendues
    unique_count: Mapped[int | None] = mapped_column(Integer)
    # Parmi celles-là, les pages encore inconnues, donc évaluées ; vide si le lancement s'est arrêté avant
    new_count: Mapped[int | None] = mapped_column(Integer)
    kept_count: Mapped[int | None] = mapped_column(Integer)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, server_default=text("CURRENT_TIMESTAMP"))


class Correction(Base):
    """Correction du tri par l'utilisateur : une page écartée qu'il a remise dans ses offres, ou une offre supprimée.

    Elle garde le verdict qu'elle contredit et la version du prompt qui l'avait rendu : c'est ce qui mesure
    la qualité du tri. Le journal des pages évaluées dit ce que le modèle a décidé, ceci s'il avait raison.
    """

    __tablename__ = "corrections"
    __table_args__ = (Index("ix_corrections_user", "user_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer)
    # « restored » : page écartée remise dans les offres ; « deleted » : offre retenue puis supprimée
    kind: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    query: Mapped[str | None] = mapped_column(Text)
    # Motif choisi à la suppression (DeleteReason) ; vide s'il n'a pas été précisé, et pour une page remise
    reason: Mapped[str | None] = mapped_column(Text)
    # Verdict contredit : nature de la page et critères d'une page écartée, vides pour une offre supprimée
    page_kind: Mapped[str | None] = mapped_column(Text)
    matches_search: Mapped[bool | None] = mapped_column(IntBool)
    matches_contract: Mapped[bool | None] = mapped_column(IntBool)
    matches_skills: Mapped[bool | None] = mapped_column(IntBool)
    matches_level: Mapped[bool | None] = mapped_column(IntBool)
    matches_location: Mapped[bool | None] = mapped_column(IntBool)
    # Justification que le modèle avait donnée
    model_reason: Mapped[str | None] = mapped_column(Text)
    # Lancement qui avait évalué la page, avec son modèle et son prompt ; vides si le journal ne la connaît pas
    search_run_id: Mapped[int | None] = mapped_column(Integer)
    model: Mapped[str | None] = mapped_column(Text)
    prompt_version: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, server_default=text("CURRENT_TIMESTAMP"))


class ServerError(Base):
    """Erreur rendue par l'API hors d'une recherche : une demande refusée, ou une panne du serveur.

    Les logs de l'hébergeur ne sont pas conservés : sans cette table, une panne chez un invité ne se verrait pas.
    Jamais le message de l'erreur, qui peut contenir ce que l'utilisateur a envoyé : son type seulement.
    """

    __tablename__ = "server_errors"
    __table_args__ = (Index("ix_server_errors_user", "user_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Vide quand l'appelant n'a pas été identifié
    user_id: Mapped[int | None] = mapped_column(Integer)
    method: Mapped[str] = mapped_column(Text)
    # Modèle de la route (« /api/jobs/{job_id} »), jamais l'adresse appelée ; vide si aucune route n'a été trouvée
    route: Mapped[str | None] = mapped_column(Text)
    status_code: Mapped[int] = mapped_column(Integer)
    error_type: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, server_default=text("CURRENT_TIMESTAMP"))


class ClientError(Base):
    """Erreur survenue dans le navigateur d'un utilisateur, signalée par le front.

    Le serveur ne voit pas ces erreurs : un écran blanc chez un invité ne laisserait aucune trace. Comme pour
    server_errors, jamais le message, qui peut contenir ce que la page affichait.
    """

    __tablename__ = "client_errors"
    __table_args__ = (Index("ix_client_errors_user", "user_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer)
    # Écran du front où l'erreur est survenue (« /offres »)
    route: Mapped[str | None] = mapped_column(Text)
    error_type: Mapped[str] = mapped_column(Text)
    # Fichier du front et position dans ce fichier (« main-5UFRYBOQ.js:1:23456 ») ; vide si le navigateur ne les dit pas
    source: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, server_default=text("CURRENT_TIMESTAMP"))


class ArchivedUsage(Base):
    """Consommation d'un compte supprimé, additionnée par mois et par modèle : ni adresse, ni contenu, ni date précise.

    Écrite à la suppression du compte, juste avant l'effacement de ses lancements. Elle n'est jamais effacée :
    c'est ce qui garde le coût de l'instance connu dans la durée.
    """

    __tablename__ = "archived_usage"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Ancien identifiant du compte : il ne désigne plus personne, sa ligne de users n'a plus d'adresse.
    # Pas « user_id » : cette table n'est pas vidée à la suppression d'un compte, elle en naît.
    account_id: Mapped[int] = mapped_column(Integer)
    # Formule du compte à sa suppression (AccountPlan)
    plan: Mapped[str] = mapped_column(Text)
    # Mois des lancements additionnés, « AAAA-MM »
    month: Mapped[str] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(Text)
    runs: Mapped[int | None] = mapped_column(Integer)
    found_count: Mapped[int | None] = mapped_column(Integer)
    kept_count: Mapped[int | None] = mapped_column(Integer)
    search_calls: Mapped[int | None] = mapped_column(Integer)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    cache_read_tokens: Mapped[int | None] = mapped_column(Integer)
    cache_write_tokens: Mapped[int | None] = mapped_column(Integer)
    deleted_at: Mapped[datetime] = mapped_column(UtcDateTime)
