from io import BytesIO
from pathlib import Path

import pytest
from langchain_core.runnables import RunnableLambda
from langgraph.graph import END, START, StateGraph
from pypdf import PdfWriter

from projet_recherche_emploi import config, node
from projet_recherche_emploi.cv_reader import CV_reader
from projet_recherche_emploi.job_repository import JobRepository
from projet_recherche_emploi.query_repository import QueryRepository
from projet_recherche_emploi.rejected_job_repository import RejectedJobRepository
from projet_recherche_emploi.state import JobSearchState

ALICE = 1
BOB = 2


class FakeTavily:
    """Renvoie deux pages par recherche, sans appeler Tavily."""

    def __init__(self, **kwargs):
        pass

    def invoke(self, payload):
        query = payload["query"]
        return {
            "results": [
                {"title": f"{query} {index}", "url": f"https://x/{query}/{index}", "content": "c", "score": 1.0}
                for index in range(2)
            ]
        }


class FakeCVReader:
    """Renvoie le chemin du CV à la place de son texte, pour voir quel CV le filtre a lu."""

    def __init__(self, cv_path):
        self.cv_path = cv_path

    def get_cv_content(self):
        return f"CV:{self.cv_path.name}"


@pytest.fixture
def graph(tmp_path, monkeypatch):
    prompts = []

    class FakeChat:
        """Retient une page sur deux, sans appeler OpenAI."""

        def __init__(self, **kwargs):
            pass

        def with_structured_output(self, schema):
            def evaluate(prompt):
                text = prompt.to_string()
                prompts.append(text)
                matches = "/0\n" in text
                return schema(is_real_offer=True, matches_cv=matches, reason="ok" if matches else "hors profil")

            return RunnableLambda(evaluate)

    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(node, "DB_PATH", tmp_path / "jobs.db")
    monkeypatch.setattr(node, "TavilySearch", FakeTavily)
    monkeypatch.setattr(node, "ChatOpenAI", FakeChat)
    monkeypatch.setattr(node, "CV_reader", FakeCVReader)

    # Le graph est reconstruit ici : importer main.py régénère graph.png par un service en ligne
    builder = StateGraph(JobSearchState)
    builder.add_node("searchJobs", node.search_jobs)
    builder.add_node("FilterDuplicates", node.filter_duplicates)
    builder.add_node("FilterJobs", node.filter_jobs)
    builder.add_node("InsertJobs", node.insert_jobs)
    builder.add_edge(START, "searchJobs")
    builder.add_edge("searchJobs", "FilterDuplicates")
    builder.add_edge("FilterDuplicates", "FilterJobs")
    builder.add_edge("FilterJobs", "InsertJobs")
    builder.add_edge("InsertJobs", END)
    compiled = builder.compile()
    compiled.prompts = prompts
    compiled.db_path = tmp_path / "jobs.db"
    return compiled


def test_search_uses_the_queries_and_cv_of_its_user(graph):
    QueryRepository(graph.db_path, BOB).add_query("CDI", "recherche de bob")

    result = graph.invoke({"user_id": BOB})

    assert {job["query"] for job in result["jobs"]} == {"recherche de bob"}
    assert len(graph.prompts) == 2
    assert all("CV:2.pdf" in prompt for prompt in graph.prompts)
    assert [job["url"] for job in JobRepository(graph.db_path, BOB).list_jobs()] == ["https://x/recherche de bob/0"]
    assert RejectedJobRepository(graph.db_path, BOB).list_known_urls() == {"https://x/recherche de bob/1"}
    assert JobRepository(graph.db_path, ALICE).list_jobs() == []
    assert RejectedJobRepository(graph.db_path, ALICE).list_known_urls() == set()


def test_a_page_evaluated_for_one_user_is_still_evaluated_for_another(graph):
    alice_query = QueryRepository(graph.db_path, ALICE).list_queries()[0]
    for query in QueryRepository(graph.db_path, ALICE).list_queries()[1:]:
        QueryRepository(graph.db_path, ALICE).delete_query(query["id"])
    QueryRepository(graph.db_path, BOB).add_query(alice_query["contract_type"], alice_query["query"])

    graph.invoke({"user_id": ALICE})
    assert len(graph.prompts) == 2

    # Le verdict dépend du CV : les mêmes pages repassent par le modèle pour Bob
    graph.invoke({"user_id": BOB})
    assert len(graph.prompts) == 4

    # Mais pas une seconde fois pour le même utilisateur
    graph.invoke({"user_id": BOB})
    assert len(graph.prompts) == 4


def test_search_without_user_is_for_the_default_user(graph):
    result = graph.invoke({})

    assert result["inserted_count"] == len(JobRepository(graph.db_path, ALICE).list_jobs()) > 0
    assert all("CV:cv.pdf" in prompt for prompt in graph.prompts)


def test_default_user_keeps_the_original_cv_location(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)

    assert config.cv_path(ALICE) == tmp_path / "cv.pdf"
    assert config.cv_path(BOB) == tmp_path / "cv" / "2.pdf"


def test_saving_a_cv_creates_the_user_folder(tmp_path):
    # Le CV versionné à la racine sert de PDF valide
    valid_pdf = (Path(__file__).parents[1] / "cv.pdf").read_bytes()
    reader = CV_reader(tmp_path / "cv" / "2.pdf")

    reader.save_cv(valid_pdf)

    assert reader.get_cv_content()


def test_refused_cv_writes_nothing(tmp_path):
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    blank_pdf = BytesIO()
    writer.write(blank_pdf)

    # Un PDF sans texte est refusé avant toute écriture : le dossier n'est même pas créé
    with pytest.raises(ValueError):
        CV_reader(tmp_path / "cv" / "2.pdf").save_cv(blank_pdf.getvalue())
    assert not (tmp_path / "cv").exists()
