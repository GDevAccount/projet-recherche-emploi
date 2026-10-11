"""Assemblage de l'application : le seul endroit où réglages, base, graph et services sont reliés.

Chaque point d'entrée (interface, API, commande) appelle get_container() ; les tests construisent
le leur avec build_container(), sur une base temporaire et avec de faux Tavily et OpenAI.
"""

import threading
from functools import cached_property

from langgraph.graph.state import CompiledStateGraph

from jobgrep.agent.adapters import OpenAIJobEvaluator, TavilyJobSearch
from jobgrep.agent.graph import build_graph
from jobgrep.agent.nodes import SearchNodes
from jobgrep.agent.ports import JobEvaluator, JobSearchEngine
from jobgrep.assistant.adapters import OpenAIAnswerJudge, OpenAIAnswerModel, OpenAIEmbedder
from jobgrep.assistant.ports import AnswerJudge, AnswerModel, Embedder
from jobgrep.config import Settings
from jobgrep.cv_agent.adapters import OpenAIProfileExtractor
from jobgrep.cv_agent.graph import build_cv_graph
from jobgrep.cv_agent.nodes import CvDepositNodes
from jobgrep.cv_agent.ports import ProfileExtractor
from jobgrep.data.cv_ingestion.anonymizer import CvAnonymizer
from jobgrep.data.cv_ingestion.pdf_reader import CvPdfReader
from jobgrep.data.database import Database
from jobgrep.services.account_service import AccountService
from jobgrep.services.account_status import AccountStatusReader
from jobgrep.services.alert_service import AlertService, Notifier, NtfyNotifier
from jobgrep.services.assistant_evaluation_service import AssistantEvaluationService
from jobgrep.services.assistant_service import AssistantService
from jobgrep.services.auth_service import AuthService
from jobgrep.services.cv_service import CvService
from jobgrep.services.health_service import HealthService
from jobgrep.services.job_service import JobService
from jobgrep.services.query_service import QueryService
from jobgrep.services.search_service import SearchService
from jobgrep.services.usage_service import UsageService

# Ce qui est noté dans server_errors quand le modèle n'a pas pu lire un CV : le dépôt, lui, a réussi
CV_EXTRACTION_ROUTE = "/api/cv (extraction)"
HTTP_SERVICE_UNAVAILABLE = 503


class Container:
    def __init__(
        self,
        settings: Settings,
        search_engine: JobSearchEngine | None = None,
        evaluator: JobEvaluator | None = None,
        notifier: Notifier | None = None,
        embedder: Embedder | None = None,
        answer_model: AnswerModel | None = None,
        judge: AnswerJudge | None = None,
        profile_extractor: ProfileExtractor | None = None,
    ):
        self.settings = settings
        self.database = Database(settings.db_path)
        self.cv_anonymizer = CvAnonymizer()
        self._profile_extractor = profile_extractor or OpenAIProfileExtractor()
        self._search_engine = search_engine or TavilyJobSearch()
        self._evaluator = evaluator or OpenAIJobEvaluator()

        self.usage = UsageService(self.database, settings.monthly_budget_usd, settings.daily_budget_usd)
        self.auth = AuthService(settings, self.database, budget_reached=self.usage.daily_budget_reached)
        self.jobs = JobService(self.database)
        self.queries = QueryService(self.database)
        # Le service de santé est construit plus bas : d'où l'appel différé
        self.cv = CvService(
            self.database,
            lambda: self.cv_graph,
            self.usage.daily_budget_reached,
            lambda user_id, error_type: self.health.record_error(
                user_id, "POST", CV_EXTRACTION_ROUTE, HTTP_SERVICE_UNAVAILABLE, error_type
            ),
        )
        # Sans sujet ntfy, aucune alerte ne part
        if notifier is None and settings.ntfy_topic:
            notifier = NtfyNotifier(settings.ntfy_url, settings.ntfy_topic)
        self.alerts = AlertService(notifier)
        # Le service de santé est construit après celui des recherches, dont il dépend : d'où l'appel différé
        self.search = SearchService(
            self.database,
            lambda: self.graph,
            lambda *run: self.health.search_closed(*run),
            self.usage.daily_budget_reached,
        )
        self.account = AccountService(self.database, self.search)
        self.assistant = AssistantService(
            self.database,
            embedder or OpenAIEmbedder(),
            answer_model or OpenAIAnswerModel(),
            settings.contact_email,
            self.usage.daily_budget_reached,
            self.cv_anonymizer,
            AccountStatusReader(self.database, self.search, self.cv, self.queries, self.jobs),
        )
        self.evaluation = AssistantEvaluationService(
            self.database,
            self.assistant.graph_for,
            judge or OpenAIAnswerJudge(),
            self.assistant.answer_model.model_name,
            self.assistant.embedder.model_name,
            settings.contact_email,
        )
        self.health = HealthService(self.database, self.search, self.usage, self.alerts)

    @cached_property
    def graph(self) -> CompiledStateGraph:
        # Le graph lit le CV par le service : il n'en reçoit que le texte sans coordonnées
        nodes = SearchNodes(self.database, self.cv, self._search_engine, self._evaluator)
        return build_graph(nodes)

    @cached_property
    def cv_graph(self) -> CompiledStateGraph:
        # Le graph n'écrit que par les services : le CV par l'un, les postes qu'il en tire par l'autre
        nodes = CvDepositNodes(CvPdfReader(), self.cv_anonymizer, self._profile_extractor, self.cv, self.queries)
        return build_cv_graph(nodes)


def build_container(
    settings: Settings | None = None,
    search_engine: JobSearchEngine | None = None,
    evaluator: JobEvaluator | None = None,
    notifier: Notifier | None = None,
    embedder: Embedder | None = None,
    answer_model: AnswerModel | None = None,
    judge: AnswerJudge | None = None,
    profile_extractor: ProfileExtractor | None = None,
) -> Container:
    """Construit l'application et met sa base à jour."""
    container = Container(
        settings or Settings(), search_engine, evaluator, notifier, embedder, answer_model, judge, profile_extractor
    )
    container.database.migrate()
    return container


_container: Container | None = None
_container_lock = threading.Lock()


def get_container() -> Container:
    """Renvoie l'application du processus, construite au premier appel."""
    global _container
    # Le verrou évite que deux premières requêtes simultanées lancent chacune la migration
    with _container_lock:
        if _container is None:
            _container = build_container()
        return _container
