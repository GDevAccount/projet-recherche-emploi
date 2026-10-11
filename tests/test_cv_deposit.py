"""Dépôt d'un CV : le graph qui le lit, en retire les coordonnées, l'enregistre et en tire les postes recherchés."""

from datetime import UTC, datetime, timedelta

import pytest
from helpers import blank_pdf
from sqlalchemy import select

from jobgrep.config import (
    DEFAULT_QUERIES,
    DEFAULT_USER_ID,
    MAX_CV_EXTRACTIONS_PER_DAY,
    MAX_DRAFTED_TITLE_CHARS,
    MAX_PROFILE_JOBS,
    MAX_SKILLS_PER_QUERY,
)
from jobgrep.cv_agent.ports import DraftedJob, DraftedProfile
from jobgrep.cv_agent.prompts import prompt_version
from jobgrep.data.models import ArchivedUsage, CvExtraction, ServerError
from jobgrep.data.repositories.cv_extraction_repository import CvExtractionRepository
from jobgrep.errors import InvalidInputError
from jobgrep.schemas import CvDeposit, CvProgress
from jobgrep.services.cv_service import MAX_CV_BYTES

BOB = 2
CAROL = 3
LONG_AGO = datetime(2000, 1, 1, tzinfo=UTC)


def profile(*jobs, location="Rhône", remote=False) -> DraftedProfile:
    return DraftedProfile(jobs=list(jobs), location=location, remote=remote)


def drafted(title, contract_type="CDI", skills=()) -> DraftedJob:
    return DraftedJob(title=title, contract_type=contract_type, skills=list(skills))


def extractions(container, user_id) -> list[CvExtraction]:
    with container.database.session() as session:
        rows = session.scalars(select(CvExtraction).where(CvExtraction.user_id == user_id).order_by(CvExtraction.id))
        return [session.expunge(row) or row for row in rows]


def summary(container, user_id) -> list[tuple]:
    queries = container.queries.list_queries(user_id)
    return [(query.contract_type, query.query, query.location, query.remote, query.skills) for query in queries]


def test_first_cv_fills_the_searched_jobs_from_what_the_model_reads(container, profile_extractor, valid_pdf):
    profile_extractor.profile = profile(
        drafted("  ingénieur   IA ", skills=["langchain", "python", "RAG"]),
        drafted("AI engineer", "freelance", ["LangGraph"]),
    )

    *steps, deposit = container.cv.stream_deposit(BOB, valid_pdf)

    assert steps == [CvProgress(step=step) for step in ("read", "anonymize", "save", "extract", "queries")]
    assert isinstance(deposit, CvDeposit) and deposit.updated_at is not None
    assert deposit.queries_outcome == "created" and deposit.message.startswith("CV enregistré.")
    # Chaque poste prend la zone lue sur le CV, une majuscule, et ses compétences l'écriture du référentiel
    assert summary(container, BOB) == [
        ("CDI", "Ingénieur IA", "Rhône", False, ["LangChain", "Python", "RAG"]),
        ("freelance", "AI engineer", "Rhône", False, ["LangGraph"]),
    ]
    assert [query.id for query in deposit.queries] == [query.id for query in container.queries.list_queries(BOB)]
    # Le modèle n'a reçu que le CV sans coordonnées, celui qui est enregistré
    [sent] = profile_extractor.cvs
    assert sent == container.cv.read_text(BOB) and "[e-mail]" in sent and "legall.guilla" not in sent
    # La lecture est comptée, avec ce qu'elle a coûté et la version des consignes, sans rien du CV
    [extraction] = extractions(container, BOB)
    assert (extraction.queries_count, extraction.input_tokens, extraction.output_tokens) == (2, 1000, 100)
    assert (extraction.model, extraction.prompt_version) == ("faux-modèle", prompt_version())
    assert container.queries.list_queries(CAROL) == []


def test_searched_jobs_already_there_are_replaced_only_on_request(container, profile_extractor, valid_pdf):
    profile_extractor.profile = profile(drafted("comptable", skills=["SAP"]))
    container.queries.add_query(BOB, "CDD", "auditeur", "Lyon")

    kept = container.cv.save_cv(BOB, valid_pdf)

    # Sans demande, le modèle n'est pas appelé : rien à payer, et les postes restent
    assert kept.queries_outcome == "kept" and kept.queries == [] and kept.updated_at is not None
    assert profile_extractor.cvs == [] and extractions(container, BOB) == []
    assert summary(container, BOB) == [("CDD", "auditeur", "Lyon", False, [])]

    replaced = container.cv.save_cv(BOB, valid_pdf, replace_queries=True)

    assert replaced.queries_outcome == "created"
    assert summary(container, BOB) == [("CDI", "Comptable", "Rhône", False, ["SAP"])]


def test_what_the_model_proposes_follows_the_rules_of_a_typed_job(container, profile_extractor, valid_pdf):
    many_skills = [f"Compétence {index}" for index in range(MAX_SKILLS_PER_QUERY + 2)]
    profile_extractor.profile = profile(
        drafted("comptable", skills=[*many_skills]),
        drafted("   "),
        drafted("x" * (MAX_DRAFTED_TITLE_CHARS + 1)),
        drafted("comptable", "CDD"),
        drafted("auditeur", skills=["sap", "SAP", "y" * 41]),
        drafted("contrôleur de gestion"),
        drafted("trésorier"),
        location="x" * 101,
    )

    container.cv.save_cv(BOB, valid_pdf)

    # Ni titre vide ou démesuré, ni doublon, ni compétence en trop ; un lieu qui n'en est pas un vaut toute la France
    assert summary(container, BOB) == [
        ("CDI", "Comptable", "", False, many_skills[:MAX_SKILLS_PER_QUERY]),
        ("CDI", "Auditeur", "", False, ["SAP"]),
    ]
    assert len(summary(container, BOB)) <= MAX_PROFILE_JOBS

    # Un CV qui ne demande que du télétravail complet : le lieu ne compte plus
    profile_extractor.profile = profile(drafted("développeur Python"), location="Rhône", remote=True)
    container.cv.save_cv(BOB, valid_pdf, replace_queries=True)
    assert summary(container, BOB) == [("CDI", "Développeur Python", "", True, [])]


def test_a_cv_that_gives_no_job_leaves_the_searched_jobs_in_place(container, profile_extractor, valid_pdf):
    container.queries.add_query(BOB, "CDI", "auditeur")

    deposit = container.cv.save_cv(BOB, valid_pdf, replace_queries=True)

    assert deposit.queries_outcome == "empty" and deposit.updated_at is not None
    assert summary(container, BOB) == [("CDI", "auditeur", "", False, [])]
    # La lecture a été payée : elle compte
    assert [extraction.queries_count for extraction in extractions(container, BOB)] == [0]


def test_a_model_failure_keeps_the_cv_and_leaves_a_trace_without_its_message(container, profile_extractor, valid_pdf):
    profile_extractor.error = RuntimeError("le texte du CV de Bob")

    *steps, deposit = container.cv.stream_deposit(BOB, valid_pdf)

    assert [step.step for step in steps] == ["read", "anonymize", "save", "extract"]
    assert deposit.queries_outcome == "failed" and deposit.updated_at is not None
    assert "à la main" in deposit.message and "Bob" not in deposit.message
    assert container.cv.read_text(BOB) and summary(container, BOB) == []
    # Une lecture qui n'a rien rendu ne compte pas dans la limite du jour
    assert extractions(container, BOB) == []
    with container.database.session() as session:
        [error] = session.scalars(select(ServerError))
        assert (error.user_id, error.status_code, error.error_type) == (BOB, 503, "RuntimeError")


def test_extractions_are_limited_per_day_but_the_cv_is_always_saved(container, profile_extractor, valid_pdf):
    profile_extractor.profile = profile(drafted("comptable"))
    morning = datetime(2026, 10, 12, 8, tzinfo=UTC)
    for _ in range(MAX_CV_EXTRACTIONS_PER_DAY):
        *_, deposit = container.cv.stream_deposit(BOB, valid_pdf, replace_queries=True, now=morning)
        assert deposit.queries_outcome == "created"
    with container.database.session() as session:
        for extraction in session.scalars(select(CvExtraction)):
            extraction.created_at = morning

    *steps, refused = container.cv.stream_deposit(BOB, valid_pdf, replace_queries=True, now=morning)

    assert [step.step for step in steps] == ["read", "anonymize", "save"]
    assert refused.queries_outcome == "limit" and refused.updated_at is not None
    assert str(MAX_CV_EXTRACTIONS_PER_DAY) in refused.message
    assert len(profile_extractor.cvs) == MAX_CV_EXTRACTIONS_PER_DAY
    # La limite est celle de Bob, et celle du jour de Paris
    *_, carol = container.cv.stream_deposit(CAROL, valid_pdf, now=morning)
    *_, next_day = container.cv.stream_deposit(BOB, valid_pdf, replace_queries=True, now=morning + timedelta(days=1))
    assert (carol.queries_outcome, next_day.queries_outcome) == ("created", "created")


def test_the_daily_budget_stops_extractions_for_everyone_but_the_owner(container, profile_extractor, valid_pdf):
    profile_extractor.profile = profile(drafted("comptable"))
    container.cv.budget_reached = lambda: True

    guest = container.cv.save_cv(BOB, valid_pdf)
    owner = container.cv.save_cv(DEFAULT_USER_ID, valid_pdf, replace_queries=True)

    assert guest.queries_outcome == "budget" and guest.updated_at is not None and summary(container, BOB) == []
    assert owner.queries_outcome == "created"
    assert len(summary(container, DEFAULT_USER_ID)) == 1 != len(DEFAULT_QUERIES)
    # Le propriétaire n'a pas non plus de limite par jour
    for _ in range(MAX_CV_EXTRACTIONS_PER_DAY + 1):
        assert container.cv.save_cv(DEFAULT_USER_ID, valid_pdf, replace_queries=True).queries_outcome == "created"


def test_a_refused_file_changes_neither_the_cv_nor_the_searched_jobs(container, profile_extractor, valid_pdf):
    profile_extractor.profile = profile(drafted("comptable"))
    container.cv.save_cv(BOB, valid_pdf)
    before = container.cv.get_status(BOB), summary(container, BOB)
    profile_extractor.profile = profile(drafted("auditeur"))

    # Trop gros : refusé à l'appel, avant le premier élément du déroulement
    with pytest.raises(InvalidInputError):
        container.cv.stream_deposit(BOB, b"x" * (MAX_CV_BYTES + 1), replace_queries=True)
    with pytest.raises(InvalidInputError):
        container.cv.save_cv(BOB, blank_pdf(), replace_queries=True)

    assert (container.cv.get_status(BOB), summary(container, BOB)) == before
    assert len(profile_extractor.cvs) == 1


def test_deleting_an_account_erases_its_extractions_and_keeps_their_cost(container, profile_extractor, valid_pdf):
    profile_extractor.profile = profile(drafted("comptable"))
    for user_id in (BOB, CAROL):
        container.cv.save_cv(user_id, valid_pdf)

    container.account.delete_account(BOB)

    with container.database.session() as session:
        assert CvExtractionRepository(session, BOB).count_since(LONG_AGO) == 0
        assert CvExtractionRepository(session, CAROL).count_since(LONG_AGO) == 1
        # Ce que la lecture a coûté reste, en totaux du mois que rien ne relie à Bob
        [archived] = session.scalars(select(ArchivedUsage))
        assert (archived.model, archived.input_tokens, archived.output_tokens) == ("faux-modèle", 1000, 100)
