from pathlib import Path

import pytest

from projet_recherche_emploi.agent.ports import EvaluationUsage, JobEvaluation
from projet_recherche_emploi.config import Settings
from projet_recherche_emploi.container import build_container
from projet_recherche_emploi.data.database import Database


class FakeSearchEngine:
    """Renvoie deux pages par recherche, sans appeler Tavily, et garde les recherches reçues."""

    def __init__(self):
        self.searches = []
        # Texte complet de chaque page ; None quand le moteur n'a rendu que l'extrait
        self.raw_content = None

    def search(self, query, international=False):
        self.searches.append((query, international))
        return [
            {
                "title": f"{query} {index}",
                "url": f"https://x/{query}/{index}",
                "content": "c",
                "raw_content": self.raw_content,
                "score": 1.0,
            }
            for index in range(2)
        ]


class FakeEvaluator:
    """Retient une page sur deux, sans appeler OpenAI, et garde le CV reçu à chaque évaluation."""

    model_name = "faux-modèle"

    def __init__(self):
        self.evaluated = []
        # Contrat que le modèle est censé lire sur chaque page
        self.contract_type = "freelance"
        # Lieu et mode de travail que le modèle est censé lire sur chaque page
        self.work_city = "Lyon"
        self.work_country = "France"
        self.work_mode = "sur site"
        # La nature qu'il donne à chaque page
        self.page_kind = "offre"
        # Ce que chaque appel est censé avoir coûté
        self.usage = EvaluationUsage(input_tokens=1000, output_tokens=50, duration_ms=120)
        # Son avis sur la géographie : le lieu est-il dans une zone acceptée
        self.in_accepted_area = True
        self.open_to_candidates_in_france = True
        # Son avis sur le métier et le niveau ; les compétences, elles, ne conviennent qu'une page sur deux
        self.matches_search = True
        self.matches_level = True
        # Ce que le graph lui a transmis des recherches de l'utilisateur
        self.criteria = None

    def evaluate(self, cv, criteria, pages):
        self.criteria = criteria
        for index, page in enumerate(pages):
            self.evaluated.append((cv, page["url"]))
            matches = page["url"].endswith("/0")
            reason = "ok" if matches else "hors profil"
            yield (
                index,
                JobEvaluation(
                    page_kind=self.page_kind,
                    contract_type=self.contract_type,
                    work_city=self.work_city,
                    work_country=self.work_country,
                    work_mode=self.work_mode,
                    in_accepted_area=self.in_accepted_area,
                    open_to_candidates_in_france=self.open_to_candidates_in_france,
                    matches_search=self.matches_search,
                    matches_skills=matches,
                    matches_level=self.matches_level,
                    reason=reason,
                ),
                self.usage,
            )


class FakeNotifier:
    """Destinataire des alertes : il garde ce qu'il reçoit, ou refuse tout si « works » est faux."""

    def __init__(self, works: bool = True):
        self.works = works
        self.sent: list[tuple[str, str]] = []

    def send(self, title: str, message: str) -> bool:
        if self.works:
            self.sent.append((title, message))
        return self.works


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
def search_engine():
    return FakeSearchEngine()


@pytest.fixture
def container(settings, search_engine, evaluator):
    return build_container(settings, search_engine, evaluator)


@pytest.fixture
def notifier():
    return FakeNotifier()


@pytest.fixture
def alerting(settings, search_engine, evaluator, notifier):
    """Application dont les alertes arrivent, sans attendre, au faux destinataire."""
    container = build_container(settings, search_engine, evaluator, notifier)
    container.alerts.dispatch = lambda send: send()
    return container


@pytest.fixture
def valid_pdf():
    # Un vrai CV, avec du texte : le PDF valide des tests
    return (Path(__file__).parent / "fixtures" / "cv.pdf").read_bytes()
