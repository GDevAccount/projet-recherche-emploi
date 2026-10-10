import re
import unicodedata
import zlib
from pathlib import Path

import pytest

from jobgrep.agent.ports import EvaluationUsage, JobEvaluation
from jobgrep.assistant.ports import DraftAnswer, ModelUsage, Verdict
from jobgrep.config import MODEL_PRICES_USD, ModelPrice, Settings
from jobgrep.container import build_container
from jobgrep.data.database import Database


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


class FakeEmbedder:
    """Situe un texte d'après ses mots, sans appeler OpenAI : deux textes qui en partagent sont proches."""

    model_name = "faux-embedding"
    SIZE = 256

    def __init__(self):
        self.embedded: list[list[str]] = []

    def embed(self, texts):
        self.embedded.append(list(texts))
        return [self._vector(text) for text in texts], sum(len(text.split()) for text in texts)

    def _vector(self, text):
        plain = unicodedata.normalize("NFD", text.lower()).encode("ascii", "ignore").decode()
        vector = [0.0] * self.SIZE
        # Les mots courts (le, de, un) sont partout : ils ne situent rien
        for word in re.findall(r"[a-z]{4,}", plain):
            vector[zlib.crc32(word.encode()) % self.SIZE] += 1.0
        return vector


class FakeAnswerModel:
    """Répond en citant le premier passage reçu, sans appeler OpenAI, et garde ce qu'on lui a demandé."""

    model_name = "faux-assistant"

    def __init__(self):
        self.asked = []
        # Ce que le modèle est censé dire de chaque question
        self.outcome = "answered"
        self.cited = [1]
        # Texte de sa réponse ; None : une phrase qui nomme le premier passage reçu
        self.text = None
        self.usage = ModelUsage(input_tokens=2000, output_tokens=100, duration_ms=300)

    def answer(self, question, passages, history):
        self.asked.append((question, list(passages), list(history)))
        answer = f"Voir « {passages[0].heading} »." if self.outcome == "answered" else ""
        if self.text is not None:
            answer = self.text
        return DraftAnswer(outcome=self.outcome, answer=answer, passages=self.cited), self.usage


class FakeJudge:
    """Note les réponses de l'assistant sans appeler OpenAI, et garde ce qu'on lui a soumis."""

    model_name = "faux-juge"

    def __init__(self):
        self.judged = []
        # Ce qu'il dit de chaque réponse
        self.faithful = True
        self.correct = True
        self.usage = ModelUsage(input_tokens=1500, output_tokens=40)

    def judge(self, question, passages, answer, reference):
        self.judged.append((question, answer, reference))
        return Verdict(reason="Conforme.", faithful=self.faithful, correct=self.correct), self.usage


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
def embedder():
    return FakeEmbedder()


@pytest.fixture
def answer_model():
    return FakeAnswerModel()


@pytest.fixture
def judge():
    return FakeJudge()


@pytest.fixture
def container(settings, search_engine, evaluator, embedder, answer_model, judge):
    return build_container(
        settings, search_engine, evaluator, embedder=embedder, answer_model=answer_model, judge=judge
    )


@pytest.fixture
def notifier():
    return FakeNotifier()


@pytest.fixture
def alerting(settings, search_engine, evaluator, notifier, embedder, answer_model, monkeypatch):
    """Application dont les alertes arrivent, sans attendre, au faux destinataire.

    Le faux modèle y a un tarif, nul : sans lui, chaque recherche préviendrait d'un tarif manquant.
    """
    monkeypatch.setitem(MODEL_PRICES_USD, FakeEvaluator.model_name, ModelPrice(0, 0, 0, 0))
    container = build_container(settings, search_engine, evaluator, notifier, embedder, answer_model)
    container.alerts.dispatch = lambda send: send()
    return container


@pytest.fixture
def valid_pdf():
    # Un vrai CV, avec du texte : le PDF valide des tests
    return (Path(__file__).parent / "fixtures" / "cv.pdf").read_bytes()
