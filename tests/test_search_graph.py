import pytest
from helpers import blank_pdf
from langchain_core.runnables import RunnableLambda

from projet_recherche_emploi.agent.adapters import OpenAIJobEvaluator
from projet_recherche_emploi.agent.nodes import (
    ANYWHERE_IN_FRANCE,
    accepts_full_remote,
    build_criteria,
    build_search_text,
    contract_is_accepted,
    describe_accepted_areas,
    format_work_location,
    location_is_accepted,
)
from projet_recherche_emploi.agent.ports import JobEvaluation, SearchCriteria
from projet_recherche_emploi.config import MAX_PAGE_CHARS
from projet_recherche_emploi.data.cv_storage import CvStorage
from projet_recherche_emploi.data.job_repository import JobRepository
from projet_recherche_emploi.data.query_repository import QueryRepository
from projet_recherche_emploi.data.rejected_job_repository import RejectedJobRepository
from projet_recherche_emploi.errors import InvalidInputError

ALICE = 1
BOB = 2


@pytest.fixture
def graph(container, monkeypatch):
    # Le texte du CV est remplacé par le nom du fichier, pour voir quel CV le filtre a lu
    monkeypatch.setattr(CvStorage, "read_text", lambda self, user_id: f"CV:{self.path_for(user_id).name}")
    return container.graph


def test_search_uses_the_queries_and_cv_of_its_user(graph, container, evaluator):
    with container.database.session() as session:
        QueryRepository(session, BOB).add_query("CDI", "recherche de bob")

    result = graph.invoke({"user_id": BOB})

    assert {job["query"] for job in result["jobs"]} == {"recherche de bob"}
    assert [cv for cv, _ in evaluator.evaluated] == ["CV:2.pdf", "CV:2.pdf"]
    with container.database.session() as session:
        assert [job.url for job in JobRepository(session, BOB).list_jobs()] == ["https://x/recherche de bob CDI/0"]
        assert RejectedJobRepository(session, BOB).list_known_urls() == {"https://x/recherche de bob CDI/1"}
        assert JobRepository(session, ALICE).list_jobs() == []
        assert RejectedJobRepository(session, ALICE).list_known_urls() == set()


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
    assert {cv for cv, _ in evaluator.evaluated} == {"CV:cv.pdf"}


def test_openai_evaluator_sends_the_cv_and_the_truncated_page_to_the_model():
    prompts = []

    class FakeChat:
        def with_structured_output(self, schema):
            def evaluate(prompt):
                prompts.append(prompt.to_string())
                return schema(
                    is_real_offer=True,
                    matches_search=True,
                    matches_skills=False,
                    matches_level=True,
                    reason="hors profil",
                )

            return RunnableLambda(evaluate)

    pages = [
        {"title": "Titre", "url": "https://x/1", "content": "extrait", "raw_content": "p" * (MAX_PAGE_CHARS + 50)},
        {"title": "Autre", "url": "https://x/2", "content": "extrait seul", "raw_content": None},
    ]

    criteria = SearchCriteria(sought_jobs=("ingénieur IA", "AI engineer"), accepted_areas="Lyon ; Nantes")
    verdicts = dict(OpenAIJobEvaluator(FakeChat()).evaluate("texte du CV", criteria, pages))

    assert set(verdicts) == {0, 1} and verdicts[0].reason == "hors profil"
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


def test_default_user_keeps_the_original_cv_location(tmp_path):
    storage = CvStorage(tmp_path)

    assert storage.path_for(ALICE) == tmp_path / "cv.pdf"
    assert storage.path_for(BOB) == tmp_path / "cv" / "2.pdf"


def test_saving_a_cv_creates_the_user_folder(tmp_path, valid_pdf):
    storage = CvStorage(tmp_path)
    assert storage.updated_at(BOB) is None

    storage.save(BOB, valid_pdf)

    assert storage.read_text(BOB)
    assert storage.updated_at(BOB).tzinfo is not None
    assert storage.updated_at(ALICE) is None


def test_refused_cv_writes_nothing(tmp_path):
    storage = CvStorage(tmp_path)

    # Un PDF sans texte est refusé avant toute écriture : le dossier n'est même pas créé
    with pytest.raises(InvalidInputError):
        storage.save(BOB, blank_pdf())
    with pytest.raises(InvalidInputError):
        storage.save(BOB, b"pas un PDF")
    assert not (tmp_path / "cv").exists()


def test_reading_a_missing_cv_is_a_user_error(tmp_path):
    with pytest.raises(InvalidInputError):
        CvStorage(tmp_path).read_text(BOB)


@pytest.mark.parametrize(
    ("contract_type", "query", "sent"),
    [
        ("CDI", "data engineer à Paris", "data engineer à Paris CDI"),
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
        ("data engineer", "Lyon", False, "data engineer CDI Lyon"),
        ("data engineer", "", False, "data engineer CDI"),
        # Le lieu déjà écrit dans la recherche n'est pas répété, avec ou sans accent
        ("data engineer en Ile-de-France", "Île-de-France", False, "data engineer en Ile-de-France CDI"),
        ("data engineer", "", True, "data engineer CDI télétravail complet"),
        ("data engineer full remote", "", True, "data engineer full remote CDI"),
        ("data engineer en teletravail", "", True, "data engineer en teletravail CDI"),
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
        is_real_offer=True, matches_search=True, matches_skills=True, matches_level=True, reason="ok", **facts
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
        [saved] = JobRepository(session, BOB).list_jobs()
        assert saved.work_location == "Remote (Los Angeles, États-Unis)"
        assert saved.url == "https://x/recherche de bob CDI télétravail complet/0"


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
