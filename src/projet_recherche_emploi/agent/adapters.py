"""Branchements réels du graph : Tavily pour chercher, OpenAI pour évaluer.

Les clients ne sont créés qu'au premier appel : construire le conteneur ne demande aucune clé API.
"""

import logging
from collections.abc import Iterator, Sequence
from functools import cached_property

from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI
from langchain_tavily import TavilySearch

from projet_recherche_emploi.agent.ports import JobEvaluation, SearchCriteria
from projet_recherche_emploi.agent.prompts import FILTER_PROMPT, describe_area_rule, describe_sought_jobs
from projet_recherche_emploi.agent.state import FoundPage
from projet_recherche_emploi.config import FILTER_MODEL, JOB_SITES, MAX_PAGE_CHARS, REMOTE_JOB_SITES

logger = logging.getLogger(__name__)


class TavilyJobSearch:
    # Les sites se fixent à la création du client Tavily : il en faut un par liste
    @cached_property
    def _client(self) -> TavilySearch:
        return self._build_client(JOB_SITES)

    @cached_property
    def _international_client(self) -> TavilySearch:
        return self._build_client([*JOB_SITES, *REMOTE_JOB_SITES])

    @staticmethod
    def _build_client(sites: list[str]) -> TavilySearch:
        return TavilySearch(
            max_results=20,
            search_depth="advanced",
            time_range="week",
            include_domains=sites,
            include_raw_content=True,
        )

    def search(self, query: str, international: bool = False) -> list[dict]:
        client = self._international_client if international else self._client
        response = client.invoke({"query": query})

        # Sans résultat, l'outil Tavily renvoie un message texte au lieu du dict habituel
        if isinstance(response, str):
            logger.warning("Recherche sans résultat (%s) : %s", query, response)
            return []

        if "error" in response:
            raise RuntimeError(f"Tavily search failed: {response['error']}")

        return response["results"]


class OpenAIJobEvaluator:
    def __init__(self, chat_model: BaseChatModel | None = None):
        self._injected_chat_model = chat_model

    @cached_property
    def _chat_model(self) -> BaseChatModel:
        return self._injected_chat_model or ChatOpenAI(model=FILTER_MODEL)

    def evaluate(
        self, cv: str, criteria: SearchCriteria, pages: Sequence[FoundPage]
    ) -> Iterator[tuple[int, JobEvaluation]]:
        evaluator = FILTER_PROMPT | self._chat_model.with_structured_output(JobEvaluation)
        yield from evaluator.batch_as_completed(
            [
                {
                    "cv": cv,
                    "sought_jobs": describe_sought_jobs(criteria.sought_jobs),
                    "area_rule": describe_area_rule(criteria.accepted_areas),
                    "title": page["title"],
                    "url": page["url"],
                    "page": (page.get("raw_content") or page["content"])[:MAX_PAGE_CHARS],
                }
                for page in pages
            ],
            config={"max_concurrency": 5},
        )
