import pytest
from helpers import blank_pdf
from langchain_core.runnables import RunnableLambda

from projet_recherche_emploi.agent.adapters import OpenAIJobEvaluator
from projet_recherche_emploi.agent.nodes import build_search_text
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
                return schema(is_real_offer=True, matches_cv=False, reason="hors profil")

            return RunnableLambda(evaluate)

    pages = [
        {"title": "Titre", "url": "https://x/1", "content": "extrait", "raw_content": "p" * (MAX_PAGE_CHARS + 50)},
        {"title": "Autre", "url": "https://x/2", "content": "extrait seul", "raw_content": None},
    ]

    verdicts = dict(OpenAIJobEvaluator(FakeChat()).evaluate("texte du CV", pages))

    assert set(verdicts) == {0, 1} and verdicts[0].reason == "hors profil"
    first, second = sorted(prompts, key=lambda prompt: "https://x/2" in prompt)
    assert "texte du CV" in first and "https://x/1" in first
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
