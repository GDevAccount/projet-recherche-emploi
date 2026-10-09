from pathlib import Path

import pytest
from helpers import blank_pdf
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from projet_recherche_emploi.agent.adapters import OpenAIJobEvaluator
from projet_recherche_emploi.agent.nodes import (
    ANYWHERE_IN_FRANCE,
    accepts_full_remote,
    build_criteria,
    build_international_search_text,
    build_search_text,
    contract_is_accepted,
    describe_accepted_areas,
    format_work_location,
    location_is_accepted,
)
from projet_recherche_emploi.agent.ports import EvaluationUsage, JobEvaluation, SearchCriteria
from projet_recherche_emploi.config import FILTER_MODEL, MAX_PAGE_CHARS
from projet_recherche_emploi.data.cv_ingestion.pdf_reader import CvPdfReader
from projet_recherche_emploi.data.repositories.cv_text_repository import CvTextRepository
from projet_recherche_emploi.data.repositories.job_repository import JobRepository
from projet_recherche_emploi.data.repositories.page_evaluation_repository import PageEvaluationRepository
from projet_recherche_emploi.data.repositories.query_repository import QueryRepository
from projet_recherche_emploi.data.repositories.rejected_job_repository import RejectedJobRepository
from projet_recherche_emploi.errors import InvalidInputError
from projet_recherche_emploi.schemas import SearchProgress
from projet_recherche_emploi.services.search_costs import model_cost_usd, search_cost_usd, total_cost_usd
from projet_recherche_emploi.services.search_service import site_of

ALICE = 1
BOB = 2
VALID_PDF = Path(__file__).parent / "fixtures" / "cv.pdf"


@pytest.fixture
def graph(container):
    # Chaque utilisateur a un CV qui porte son identifiant, pour voir lequel le filtre a lu
    with container.database.session() as session:
        for user_id in (ALICE, BOB):
            CvTextRepository(session, user_id).save(f"CV de {user_id}")
    return container.graph


def test_search_uses_the_queries_and_cv_of_its_user(graph, container, evaluator):
    with container.database.session() as session:
        QueryRepository(session, BOB).add_query("CDI", "recherche de bob")

    result = graph.invoke({"user_id": BOB})

    assert {job["query"] for job in result["jobs"]} == {"recherche de bob"}
    assert [cv for cv, _ in evaluator.evaluated] == ["CV de 2", "CV de 2"]
    with container.database.session() as session:
        assert [job.url for job in JobRepository(session, BOB).list_jobs()] == [
            "https://x/offre d'emploi recherche de bob CDI/0"
        ]
        assert RejectedJobRepository(session, BOB).list_known_urls() == {
            "https://x/offre d'emploi recherche de bob CDI/1"
        }
        assert JobRepository(session, ALICE).list_jobs() == []
        assert RejectedJobRepository(session, ALICE).list_known_urls() == set()


def test_progress_names_each_step_and_gives_the_verdict_page_by_page(graph, container):
    with container.database.session() as session:
        QueryRepository(session, BOB).add_query("CDI", "recherche de bob")

    progress = [SearchProgress(**event) for event in graph.stream({"user_id": BOB}, stream_mode="custom")]

    # Une interface suit le graph par l'étape annoncée, sans lire le message
    assert [event.step for event in progress] == ["search", "dedupe", "evaluate", "evaluate", "evaluate", "save"]
    search, dedupe, start, first, second, _ = progress
    assert (search.done, search.total, search.found) == (0, 1, 0)
    assert (dedupe.found, dedupe.new) == (2, 2)
    assert (start.done, start.total, start.title, start.kept) == (0, 2, None, None)
    assert (first.done, first.title, first.kept) == (1, "offre d'emploi recherche de bob CDI 0", True)
    assert (second.done, second.title, second.kept) == (2, "offre d'emploi recherche de bob CDI 1", False)


def test_a_page_evaluated_for_one_user_is_still_evaluated_for_another(graph, container, evaluator):
    with container.database.session() as session:
        alice_query, *others = QueryRepository(session, ALICE).list_queries()
        for query in others:
            QueryRepository(session, ALICE).delete_query(query.id)
        QueryRepository(session, BOB).add_query(alice_query.contract_type, alice_query.query)

    graph.invoke({"user_id": ALICE})
    assert len(evaluator.evaluated) == 2

    # Le verdict dépend du CV : les mêmes pages repassent par le modèle pour Bob
    graph.invoke({"user_id": BOB})
    assert len(evaluator.evaluated) == 4

    # Mais pas une seconde fois pour le même utilisateur
    graph.invoke({"user_id": BOB})
    assert len(evaluator.evaluated) == 4


def test_deleted_offer_is_not_evaluated_again(graph, container, evaluator):
    graph.invoke({"user_id": ALICE})
    evaluated = len(evaluator.evaluated)
    with container.database.session() as session:
        jobs = JobRepository(session, ALICE)
        jobs.delete_jobs([job.id for job in jobs.list_jobs()])

    result = graph.invoke({"user_id": ALICE})

    assert result["new_jobs"] == [] and result["inserted_count"] == 0
    assert len(evaluator.evaluated) == evaluated


def test_search_without_user_is_for_the_default_user(graph, container, evaluator):
    result = graph.invoke({})

    with container.database.session() as session:
        assert result["inserted_count"] == len(JobRepository(session, ALICE).list_jobs()) > 0
    assert {cv for cv, _ in evaluator.evaluated} == {"CV de 1"}


def test_openai_evaluator_sends_the_cv_and_the_truncated_page_to_the_model():
    prompts = []

    class FakeChat:
        def with_structured_output(self, schema, include_raw):
            def evaluate(prompt):
                prompts.append(prompt.to_string())
                parsed = schema(
                    page_kind="offre",
                    matches_search=True,
                    matches_skills=False,
                    matches_level=True,
                    reason="hors profil",
                )
                usage = {
                    "input_tokens": 1200,
                    "output_tokens": 80,
                    "total_tokens": 1280,
                    "input_token_details": {"cache_read": 700},
                    "output_token_details": {"reasoning": 30},
                }
                return {"raw": AIMessage(content="", usage_metadata=usage), "parsed": parsed, "parsing_error": None}

            return RunnableLambda(evaluate)

    pages = [
        {"title": "Titre", "url": "https://x/1", "content": "extrait", "raw_content": "p" * (MAX_PAGE_CHARS + 50)},
        {"title": "Autre", "url": "https://x/2", "content": "extrait seul", "raw_content": None},
    ]

    criteria = SearchCriteria(sought_jobs=("ingénieur IA", "AI engineer"), accepted_areas="Lyon ; Nantes")
    results = list(OpenAIJobEvaluator(FakeChat()).evaluate("texte du CV", criteria, pages))
    verdicts = {index: evaluation for index, evaluation, _ in results}

    assert set(verdicts) == {0, 1} and verdicts[0].reason == "hors profil"
    # Chaque verdict vient avec ce que son appel a consommé
    for _, _, usage in results:
        assert (usage.input_tokens, usage.output_tokens) == (1200, 80) and usage.duration_ms >= 0
        # Le détail aussi : les jetons lus en cache coûtent moins, ceux du raisonnement ne se voient pas
        assert (usage.cache_read_tokens, usage.cache_write_tokens, usage.reasoning_tokens) == (700, None, 30)
    first, second = sorted(prompts, key=lambda prompt: "https://x/2" in prompt)
    assert "texte du CV" in first and "https://x/1" in first
    assert "Lyon ; Nantes" in first and "Lyon ; Nantes" in second
    # Le modèle lit les recherches du candidat : le CV ne dit pas quel métier il vise
    assert "- ingénieur IA\n- AI engineer" in first
    # Sans zone géographique, le prompt n'en cite aucune : la consigne dit seulement de répondre faux
    prompts.clear()
    list(OpenAIJobEvaluator(FakeChat()).evaluate("texte du CV", SearchCriteria(), pages[:1]))
    assert "toujours faux" in prompts[0] and "zones géographiques, acceptées" not in prompts[0]
    assert "p" * MAX_PAGE_CHARS in first and "p" * (MAX_PAGE_CHARS + 1) not in first
    # Sans contenu complet, c'est l'extrait de Tavily qui est évalué
    assert "extrait seul" in second


def test_pdf_reader_returns_the_text_of_a_cv(valid_pdf):
    assert CvPdfReader().read_text(valid_pdf).strip()


def test_pdf_reader_refuses_a_file_without_text_or_that_is_not_a_pdf():
    with pytest.raises(InvalidInputError):
        CvPdfReader().read_text(blank_pdf())
    with pytest.raises(InvalidInputError):
        CvPdfReader().read_text(b"pas un PDF")


@pytest.mark.parametrize(
    ("contract_type", "query", "sent"),
    [
        ("CDI", "data engineer à Paris", "offre d'emploi data engineer à Paris CDI"),
        ("CDI", "offre d'emploi ingénieur IA en cdi", "offre d'emploi ingénieur IA en cdi"),
        ("freelance", "mission Freelance AI engineer", "mission Freelance AI engineer"),
    ],
)
def test_contract_type_is_added_to_the_search_unless_already_there(contract_type, query, sent):
    assert build_search_text(contract_type, query) == sent


def test_saved_contract_is_the_one_read_on_the_page_not_the_one_of_the_search(graph, container, evaluator):
    with container.database.session() as session:
        QueryRepository(session, BOB).add_query("CDI", "recherche de bob")

    graph.invoke({"user_id": BOB})
    with container.database.session() as session:
        # La recherche demandait un CDI, le faux modèle a lu « freelance » sur les pages
        assert [job.contract_type for job in JobRepository(session, BOB).list_jobs()] == ["freelance"]
        assert [page.contract_type for page in RejectedJobRepository(session, BOB).list_rejected_jobs()] == [
            "freelance"
        ]
        # La recherche d'origine reste le texte saisi, sans le contrat ajouté pour le moteur
        assert [job.query for job in JobRepository(session, BOB).list_jobs()] == ["recherche de bob"]


def test_a_page_that_does_not_state_its_contract_is_saved_without_one(graph, container, evaluator):
    evaluator.contract_type = None
    with container.database.session() as session:
        QueryRepository(session, BOB).add_query("stage", "recherche de bob")

    graph.invoke({"user_id": BOB})

    with container.database.session() as session:
        assert [job.contract_type for job in JobRepository(session, BOB).list_jobs()] == [None]


@pytest.mark.parametrize(
    ("query", "location", "remote", "sent"),
    [
        ("data engineer", "Lyon", False, "offre d'emploi data engineer CDI Lyon"),
        ("data engineer", "", False, "offre d'emploi data engineer CDI"),
        # Une phrase qui vise déjà des annonces ne reçoit pas « offre d'emploi »
        ("mission data engineer", "Lyon", False, "mission data engineer CDI Lyon"),
        ("AI engineer job", "", False, "AI engineer job CDI"),
        # Le lieu déjà écrit dans la recherche n'est pas répété, avec ou sans accent
        ("emploi data engineer en Ile-de-France", "Île-de-France", False, "emploi data engineer en Ile-de-France CDI"),
        ("data engineer", "", True, "offre d'emploi data engineer CDI télétravail complet"),
        ("data engineer full remote", "", True, "offre d'emploi data engineer full remote CDI"),
        ("data engineer en teletravail", "", True, "offre d'emploi data engineer en teletravail CDI"),
    ],
)
def test_location_is_added_to_the_search_unless_already_there(query, location, remote, sent):
    assert build_search_text("CDI", query, location, remote) == sent


def test_accepted_areas_are_those_of_every_search_together(container):
    def accepted(*places):
        with container.database.session() as session:
            queries = QueryRepository(session, BOB)
            for query in queries.list_queries():
                queries.delete_query(query.id)
            for index, (location, remote) in enumerate(places):
                queries.add_query("CDI", f"recherche {index}", location, remote)
            saved = queries.list_queries()
            return describe_accepted_areas(saved), accepts_full_remote(saved)

    assert accepted(("Lyon", False), ("Nantes", False), ("Lyon", False)) == ("Lyon ; Nantes", False)
    # Le télétravail complet n'est pas une zone : il est accepté à part
    assert accepted(("Lyon", False), ("", True)) == ("Lyon", True)
    assert accepted(("", True)) == ("", True)
    # Une seule recherche sans lieu ouvre toute la France
    assert accepted(("Lyon", False), ("", False), ("", True)) == (ANYWHERE_IN_FRANCE, True)


def evaluation(**facts) -> JobEvaluation:
    return JobEvaluation(
        page_kind="offre", matches_search=True, matches_skills=True, matches_level=True, reason="ok", **facts
    )


@pytest.mark.parametrize(
    ("facts", "accepted_areas", "accepts_remote", "accepted"),
    [
        # Une région choisie : le poste doit s'y trouver
        ({"in_accepted_area": True}, "Lyon", False, True),
        ({"in_accepted_area": False}, "Lyon", False, False),
        # Télétravail complet accepté : le pays ne compte plus
        ({"work_mode": "télétravail complet", "in_accepted_area": False}, "Lyon", True, True),
        ({"work_mode": "télétravail complet", "in_accepted_area": False}, "", True, True),
        # Sauf s'il est réservé aux candidats d'un pays sans la France
        (
            {"work_mode": "télétravail complet", "open_to_candidates_in_france": False, "in_accepted_area": False},
            "Lyon",
            True,
            False,
        ),
        # Sans recherche en télétravail, un poste à distance passe si l'employeur est dans la zone
        ({"work_mode": "télétravail complet", "in_accepted_area": True}, "Lyon", False, True),
        ({"work_mode": "télétravail complet", "in_accepted_area": False}, "Lyon", False, False),
        # Mais un poste hybride ou sur site reste soumis à la zone, même à l'étranger
        ({"work_mode": "hybride", "in_accepted_area": False}, "Lyon", True, False),
        ({"work_mode": "hybride", "in_accepted_area": True}, "Lyon", True, True),
        # Recherches en télétravail seulement : sans mode écrit sur la page, rien n'est acquis
        ({"in_accepted_area": True}, "", True, False),
        ({"work_mode": "sur site", "in_accepted_area": True}, "", True, False),
    ],
)
def test_location_rules_are_applied_by_the_graph_not_by_the_model(facts, accepted_areas, accepts_remote, accepted):
    assert location_is_accepted(evaluation(**facts), accepted_areas, accepts_remote) is accepted


@pytest.mark.parametrize(
    ("facts", "shown"),
    [
        ({"work_city": "Lyon", "work_country": "France", "work_mode": "hybride"}, "Lyon"),
        ({"work_city": "Berlin", "work_country": "Allemagne"}, "Berlin, Allemagne"),
        ({"work_mode": "télétravail complet"}, "Remote"),
        (
            {"work_city": "Los Angeles", "work_country": "États-Unis", "work_mode": "télétravail complet"},
            "Remote (Los Angeles, États-Unis)",
        ),
        ({"work_city": "Paris", "work_country": "France", "work_mode": "télétravail complet"}, "Remote (Paris)"),
        ({}, None),
    ],
)
def test_shown_location_is_the_city_or_remote(facts, shown):
    assert format_work_location(evaluation(**facts)) == shown


def test_offer_outside_the_accepted_areas_is_rejected_for_its_location(graph, container, evaluator):
    evaluator.in_accepted_area = False
    with container.database.session() as session:
        QueryRepository(session, BOB).add_query("CDI", "recherche de bob", "Nantes")

    result = graph.invoke({"user_id": BOB})

    assert evaluator.criteria.accepted_areas == "Nantes"
    assert result["filtered_jobs"] == []
    with container.database.session() as session:
        assert JobRepository(session, BOB).list_jobs() == []
        rejected = RejectedJobRepository(session, BOB).list_rejected_jobs()
        assert {(page.matches_location, page.work_location) for page in rejected} == {(False, "Lyon")}
        # La raison du modèle est précédée de la règle de lieu, que le graph applique
        assert sorted(page.reject_reason for page in rejected) == [
            "Lieu de travail hors des lieux recherchés (Lyon). hors profil",
            "Lieu de travail hors des lieux recherchés (Lyon). ok",
        ]
        # Seule la page qui convenait au CV sera réévaluée si une recherche s'ajoute
        assert RejectedJobRepository(session, BOB).clear_search_dependent_rejections() == 1


def test_full_remote_offer_abroad_is_kept_for_a_remote_search(graph, container, evaluator):
    evaluator.work_city, evaluator.work_country = "Los Angeles", "États-Unis"
    evaluator.work_mode = "télétravail complet"
    evaluator.in_accepted_area = False
    with container.database.session() as session:
        QueryRepository(session, BOB).add_query("CDI", "recherche de bob", remote=True)

    graph.invoke({"user_id": BOB})

    # Aucune zone géographique : le filtre le lit, et seul le télétravail complet passe
    assert (evaluator.criteria.accepted_areas, evaluator.criteria.accepts_full_remote) == ("", True)
    with container.database.session() as session:
        saved = JobRepository(session, BOB).list_jobs()
        assert {job.work_location for job in saved} == {"Remote (Los Angeles, États-Unis)"}
        # La recherche est partie deux fois : en français, puis en anglais sur les sites internationaux
        assert {job.url for job in saved} == {
            "https://x/offre d'emploi recherche de bob CDI télétravail complet/0",
            "https://x/recherche de bob remote job/0",
        }


def test_remote_offer_reserved_to_another_country_is_rejected(graph, container, evaluator):
    evaluator.work_city, evaluator.work_country = "Los Angeles", "États-Unis"
    evaluator.work_mode = "télétravail complet"
    evaluator.in_accepted_area = False
    evaluator.open_to_candidates_in_france = False
    with container.database.session() as session:
        QueryRepository(session, BOB).add_query("CDI", "recherche de bob", remote=True)

    graph.invoke({"user_id": BOB})

    with container.database.session() as session:
        assert JobRepository(session, BOB).list_jobs() == []
        reasons = {page.reject_reason for page in RejectedJobRepository(session, BOB).list_rejected_jobs()}
        assert "Télétravail réservé aux candidats d'un pays ou d'une zone sans la France. ok" in reasons


def test_criteria_gather_what_every_search_looks_for(container):
    with container.database.session() as session:
        queries = QueryRepository(session, BOB)
        queries.add_query("CDI", "ingénieur IA", "Lyon")
        queries.add_query("freelance", "AI engineer", remote=True)

        criteria = build_criteria(queries.list_queries())

    assert criteria == SearchCriteria(
        sought_jobs=("ingénieur IA", "AI engineer"),
        contract_types=frozenset({"CDI", "freelance"}),
        accepted_areas="Lyon",
        accepts_full_remote=True,
    )


@pytest.mark.parametrize(
    ("contract_type", "searched", "accepted"),
    [
        # Un stage ou une alternance ne passe que si une recherche le demande
        ("stage", {"CDI", "freelance"}, False),
        ("alternance", {"CDI"}, False),
        ("stage", {"CDI", "stage"}, True),
        # Les autres contrats ne sont pas tranchés : une recherche de CDI ramène aussi des missions
        ("freelance", {"CDI"}, True),
        ("CDD", {"CDI"}, True),
        (None, {"CDI"}, True),
    ],
)
def test_internship_is_rejected_unless_a_search_asks_for_one(contract_type, searched, accepted):
    assert contract_is_accepted(contract_type, searched) is accepted


def test_offer_for_another_job_than_those_searched_is_rejected_even_if_the_cv_fits(graph, container, evaluator):
    evaluator.matches_search = False
    with container.database.session() as session:
        QueryRepository(session, BOB).add_query("CDI", "ingénieur IA")

    result = graph.invoke({"user_id": BOB})

    # Le modèle a reçu les recherches : c'est sur elles qu'il dit si le métier est le bon
    assert evaluator.criteria.sought_jobs == ("ingénieur IA",)
    assert result["filtered_jobs"] == []
    with container.database.session() as session:
        rejected = RejectedJobRepository(session, BOB).list_rejected_jobs()
        # Le détail du verdict est enregistré : la page aux bonnes compétences n'est écartée que pour son métier
        assert sorted((page.matches_search, page.matches_skills, page.matches_cv) for page in rejected) == [
            (False, False, False),
            (False, True, True),
        ]
        assert {(page.matches_level, page.matches_contract, page.matches_location) for page in rejected} == {
            (True, True, True)
        }


def test_internship_found_by_a_search_for_a_permanent_job_is_rejected(graph, container, evaluator):
    evaluator.contract_type = "stage"
    with container.database.session() as session:
        QueryRepository(session, BOB).add_query("CDI", "ingénieur IA")

    graph.invoke({"user_id": BOB})

    with container.database.session() as session:
        assert JobRepository(session, BOB).list_jobs() == []
        rejected = RejectedJobRepository(session, BOB).list_rejected_jobs()
        assert {page.matches_contract for page in rejected} == {False}
        assert "Contrat non recherché (stage). ok" in {page.reject_reason for page in rejected}


def test_every_evaluated_page_is_logged_with_what_was_read_and_what_it_cost(container, evaluator, search_engine):
    container.cv.save_cv(BOB, VALID_PDF.read_bytes())
    container.queries.add_query(BOB, "CDI", "ingénieur IA", "Lyon")
    evaluator.work_city, evaluator.in_accepted_area = "Berlin", False
    search_engine.raw_content = "p" * (MAX_PAGE_CHARS + 1)

    container.search.run_search(BOB)

    [run] = container.search.list_runs(BOB)
    assert (run.status, run.error, run.model) == ("done", None, "faux-modèle")
    assert (run.found_count, run.new_count, run.kept_count, run.rejected_count, run.inserted_count) == (2, 2, 0, 2, 0)
    assert (run.search_calls, run.input_tokens, run.output_tokens) == (1, 2000, 100)
    assert run.finished_at >= run.created_at and len(run.prompt_version) == 12
    assert all(duration is not None for duration in (run.search_ms, run.dedupe_ms, run.evaluate_ms, run.save_ms))
    assert run.duration_ms == run.search_ms + run.dedupe_ms + run.evaluate_ms + run.save_ms

    evaluations = container.search.list_evaluations(BOB, run.id)
    assert {page.search_run_id for page in evaluations} == {run.id}
    # Les faits lus et la règle qui a tranché sont gardés, même pour une page écartée
    assert {(page.kept, page.work_city, page.in_accepted_area, page.matches_location) for page in evaluations} == {
        (False, "Berlin", False, False)
    }
    assert {(page.page_kind, page.work_mode, page.open_to_candidates_in_france) for page in evaluations} == {
        ("offre", "sur site", True)
    }
    assert {(page.input_tokens, page.output_tokens, page.duration_ms) for page in evaluations} == {(1000, 50, 120)}
    assert {(page.page_chars, page.truncated, page.full_page) for page in evaluations} == {
        (MAX_PAGE_CHARS + 1, True, True)
    }
    assert {page.score for page in evaluations} == {1.0}


def test_costs_follow_the_prices_and_the_cache(container, evaluator):
    assert search_cost_usd(3) == 0.048 and search_cost_usd(None) is None
    # La recherche réelle du 2026-10-09 : 94 967 jetons d'entrée, 10 625 de sortie
    assert model_cost_usd(FILTER_MODEL, 94967, 10625) == 0.014809
    # Les jetons lus en cache font partie de l'entrée, à un dixième du prix
    assert model_cost_usd(FILTER_MODEL, 1000, 100, cache_read_tokens=600) == 0.000096
    assert model_cost_usd("modèle sans tarif", 1000, 100) is None
    assert model_cost_usd(FILTER_MODEL, None, None) is None
    # Une recherche arrêtée avant l'évaluation n'a coûté que ses appels au moteur de recherche
    assert total_cost_usd(0.048, None, has_model_usage=False) == 0.048
    assert total_cost_usd(0.048, None, has_model_usage=True) is None
    assert site_of("https://www.welcometothejungle.com/fr/jobs/1") == "welcometothejungle.com"


def test_stats_gather_every_search_of_the_user(container, evaluator):
    evaluator.model_name = FILTER_MODEL
    evaluator.usage = EvaluationUsage(1000, 50, 120, cache_read_tokens=600, reasoning_tokens=20)
    container.cv.save_cv(BOB, VALID_PDF.read_bytes())
    container.queries.add_query(BOB, "CDI", "ingénieur IA")
    assert container.search.get_stats(BOB).runs == 0

    container.search.run_search(BOB)

    [run] = container.search.list_runs(BOB)
    assert (run.cache_read_tokens, run.cache_write_tokens, run.reasoning_tokens) == (1200, None, 40)
    assert (run.search_cost_usd, run.model_cost_usd, run.cost_usd) == (0.016, 0.000142, 0.016142)
    assert {page.model_cost_usd for page in container.search.list_evaluations(BOB, run.id)} == {0.000071}

    stats = container.search.get_stats(BOB)
    assert (stats.runs, stats.unfinished_runs, stats.found_count, stats.kept_count, stats.rejected_count) == (
        1,
        0,
        2,
        1,
        1,
    )
    assert (stats.search_calls, stats.input_tokens, stats.cache_read_tokens, stats.reasoning_tokens) == (
        1,
        2000,
        1200,
        40,
    )
    assert (stats.search_cost_usd, stats.model_cost_usd, stats.cost_usd, stats.cost_per_kept_usd) == (
        0.016,
        0.000142,
        0.016142,
        0.016142,
    )
    assert stats.average_duration_ms is not None
    [site] = stats.by_site
    assert (site.label, site.evaluated, site.kept, site.not_an_offer, site.rejected_offers) == ("x", 2, 1, 0, 1)
    assert (site.input_tokens, site.output_tokens, site.model_cost_usd) == (2000, 100, 0.000142)
    assert [(group.label, group.evaluated) for group in stats.by_query] == [("ingénieur IA", 2)]
    assert [(group.label, group.evaluated) for group in stats.by_page_kind] == [("offre", 2)]
    assert [(group.label, group.evaluated) for group in stats.by_text] == [("Extrait seul", 2)]
    assert container.search.get_stats(ALICE).runs == 0


def test_the_log_survives_a_new_cv_but_not_the_account(container):
    container.cv.save_cv(BOB, VALID_PDF.read_bytes())
    container.queries.add_query(BOB, "CDI", "ingénieur IA")
    container.search.run_search(BOB)
    [run] = container.search.list_runs(BOB)
    [kept, rejected] = sorted(container.search.list_evaluations(BOB, run.id), key=lambda page: not page.kept)
    assert (kept.kept, rejected.kept, rejected.matches_skills) == (True, False, False)
    # Sans texte complet, c'est l'extrait du moteur de recherche qui a été lu
    assert (kept.full_page, kept.truncated, kept.page_chars) == (False, False, 1)

    # Un nouveau CV vide les rejets, pas le journal : il raconte ce qui s'est passé
    container.cv.save_cv(BOB, VALID_PDF.read_bytes())
    assert container.jobs.list_rejected_jobs(BOB) == []
    assert len(container.search.list_evaluations(BOB, run.id)) == 2

    container.account.delete_account(BOB)
    assert container.search.list_runs(BOB) == []
    with container.database.session() as session:
        assert PageEvaluationRepository(session, BOB).list_for_run(run.id) == []


def test_a_page_that_is_not_an_offer_is_rejected_with_its_kind(graph, container, evaluator):
    evaluator.page_kind = "liste d'offres"
    container.queries.add_query(BOB, "CDI", "ingénieur IA")

    graph.invoke({"user_id": BOB})

    with container.database.session() as session:
        assert JobRepository(session, BOB).list_jobs() == []
        rejected = RejectedJobRepository(session, BOB).list_rejected_jobs()
        assert rejected and {(page.is_real_offer, page.page_kind) for page in rejected} == {(False, "liste d'offres")}
    assert {page.motive for page in container.jobs.list_rejected_jobs(BOB)} == {"Liste ou page de résultats"}
    # Ce n'est pas un rejet dû aux recherches : en ajouter une ne la fait pas réévaluer
    container.queries.add_query(BOB, "CDI", "data engineer")
    assert len(container.jobs.list_rejected_jobs(BOB)) == len(rejected)


@pytest.mark.parametrize(
    ("contract_type", "query", "sent"),
    [
        ("CDI", "AI engineer", "AI engineer remote job"),
        ("freelance", "AI engineer", "AI engineer remote freelance"),
        ("CDI", "remote AI engineer job", "remote AI engineer job"),
    ],
)
def test_international_search_is_written_for_foreign_job_boards(contract_type, query, sent):
    assert build_international_search_text(contract_type, query) == sent


def test_only_a_remote_search_is_also_sent_to_international_job_boards(graph, container, search_engine):
    with container.database.session() as session:
        queries = QueryRepository(session, BOB)
        queries.add_query("CDI", "AI engineer", "Lyon")
        queries.add_query("CDI", "AI engineer", remote=True)

    graph.invoke({"user_id": BOB})

    assert search_engine.searches == [
        ("offre d'emploi AI engineer CDI Lyon", False),
        ("offre d'emploi AI engineer CDI télétravail complet", False),
        ("AI engineer remote job", True),
    ]
