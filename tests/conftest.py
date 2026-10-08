from pathlib import Path

import pytest

from projet_recherche_emploi.agent.ports import JobEvaluation
from projet_recherche_emploi.config import Settings
from projet_recherche_emploi.container import build_container
from projet_recherche_emploi.data.database import Database


class FakeSearchEngine:
    """Renvoie deux pages par recherche, sans appeler Tavily."""

    def search(self, query):
        return [
            {"title": f"{query} {index}", "url": f"https://x/{query}/{index}", "content": "c", "score": 1.0}
            for index in range(2)
        ]


class FakeEvaluator:
    """Retient une page sur deux, sans appeler OpenAI, et garde le CV reçu à chaque évaluation."""

    def __init__(self):
        self.evaluated = []

    def evaluate(self, cv, pages):
        for index, page in enumerate(pages):
            self.evaluated.append((cv, page["url"]))
            matches = page["url"].endswith("/0")
            reason = "ok" if matches else "hors profil"
            yield index, JobEvaluation(is_real_offer=True, matches_cv=matches, reason=reason)


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch):
    # Les réglages de la machine (ou d'un .env déjà chargé) ne doivent pas fuir dans les tests
    for name in Settings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)


@pytest.fixture
def settings(tmp_path):
    return Settings(data_dir=tmp_path)


@pytest.fixture
def database(tmp_path):
    database = Database(tmp_path / "jobs.db")
    database.migrate()
    return database


@pytest.fixture
def session(database):
    with database.session() as session:
        yield session


@pytest.fixture
def evaluator():
    return FakeEvaluator()


@pytest.fixture
def container(settings, evaluator):
    return build_container(settings, FakeSearchEngine(), evaluator)


@pytest.fixture
def valid_pdf():
    # Le CV versionné à la racine sert de PDF valide
    return (Path(__file__).parents[1] / "cv.pdf").read_bytes()
