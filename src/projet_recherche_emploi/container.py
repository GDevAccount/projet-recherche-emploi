"""Assemblage de l'application : le seul endroit où réglages, base, graph et services sont reliés.

Chaque point d'entrée (interface, API, commande) appelle get_container() ; les tests construisent
le leur avec build_container(), sur une base temporaire et avec de faux Tavily et OpenAI.
"""

import threading
from functools import cached_property

from langgraph.graph.state import CompiledStateGraph

from projet_recherche_emploi.agent.adapters import OpenAIJobEvaluator, TavilyJobSearch
from projet_recherche_emploi.agent.graph import build_graph
from projet_recherche_emploi.agent.nodes import SearchNodes
from projet_recherche_emploi.agent.ports import JobEvaluator, JobSearchEngine
from projet_recherche_emploi.config import Settings
from projet_recherche_emploi.data.cv_ingestion.anonymizer import CvAnonymizer
from projet_recherche_emploi.data.cv_ingestion.ingestion import CvIngestion
from projet_recherche_emploi.data.cv_ingestion.pdf_reader import CvPdfReader
from projet_recherche_emploi.data.database import Database
from projet_recherche_emploi.services.account_service import AccountService
from projet_recherche_emploi.services.auth_service import AuthService
from projet_recherche_emploi.services.cv_service import CvService
from projet_recherche_emploi.services.health_service import HealthService
from projet_recherche_emploi.services.job_service import JobService
from projet_recherche_emploi.services.query_service import QueryService
from projet_recherche_emploi.services.search_service import SearchService
from projet_recherche_emploi.services.usage_service import UsageService


class Container:
    def __init__(
        self,
        settings: Settings,
        search_engine: JobSearchEngine | None = None,
        evaluator: JobEvaluator | None = None,
    ):
        self.settings = settings
        self.database = Database(settings.db_path)
        self.cv_ingestion = CvIngestion(CvPdfReader(), CvAnonymizer())
        self._search_engine = search_engine or TavilyJobSearch()
        self._evaluator = evaluator or OpenAIJobEvaluator()

        self.auth = AuthService(settings, self.database)
        self.jobs = JobService(self.database)
        self.queries = QueryService(self.database)
        self.cv = CvService(self.database, self.cv_ingestion)
        self.search = SearchService(self.database, lambda: self.graph)
        self.account = AccountService(self.database, self.search)
        self.usage = UsageService(self.database)
        self.health = HealthService(self.database, self.search)

    @cached_property
    def graph(self) -> CompiledStateGraph:
        # Le graph lit le CV par le service : il n'en reçoit que le texte sans coordonnées
        nodes = SearchNodes(self.database, self.cv, self._search_engine, self._evaluator)
        return build_graph(nodes)


def build_container(
    settings: Settings | None = None,
    search_engine: JobSearchEngine | None = None,
    evaluator: JobEvaluator | None = None,
) -> Container:
    """Construit l'application et met sa base à jour."""
    container = Container(settings or Settings(), search_engine, evaluator)
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
