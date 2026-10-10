"""Branchements réels du graph : Tavily pour chercher, OpenAI pour évaluer.

Les clients ne sont créés qu'au premier appel : construire le conteneur ne demande aucune clé API.
"""

import logging
import time
from collections.abc import Iterator, Sequence
from functools import cached_property

from langchain_core.language_models import BaseChatModel
from langchain_core.runnables import RunnableConfig, RunnableLambda
from langchain_openai import ChatOpenAI
from langchain_tavily import TavilySearch

from jobgrep.agent.ports import EvaluationUsage, JobEvaluation, SearchCriteria, page_text
from jobgrep.agent.prompts import FILTER_PROMPT, describe_area_rule, describe_sought_jobs
from jobgrep.agent.state import FoundPage
from jobgrep.config import FILTER_MODEL, JOB_SITES, MAX_PAGE_CHARS, REMOTE_JOB_SITES

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
    model_name = FILTER_MODEL

    def __init__(self, chat_model: BaseChatModel | None = None):
        self._injected_chat_model = chat_model

    @cached_property
    def _chat_model(self) -> BaseChatModel:
        return self._injected_chat_model or ChatOpenAI(model=FILTER_MODEL)

    def evaluate(
        self, cv: str, criteria: SearchCriteria, pages: Sequence[FoundPage]
    ) -> Iterator[tuple[int, JobEvaluation, EvaluationUsage]]:
        # La réponse brute accompagne le verdict : c'est elle qui porte le nombre de jetons
        chain = FILTER_PROMPT | self._chat_model.with_structured_output(JobEvaluation, include_raw=True)

        def evaluate_page(inputs: dict, config: RunnableConfig) -> tuple[JobEvaluation, EvaluationUsage]:
            started = time.perf_counter()
            answer = chain.invoke(inputs, config)
            duration_ms = round((time.perf_counter() - started) * 1000)
            if answer["parsing_error"]:
                raise answer["parsing_error"]
            usage = getattr(answer["raw"], "usage_metadata", None) or {}
            input_details = usage.get("input_token_details") or {}
            output_details = usage.get("output_token_details") or {}
            return answer["parsed"], EvaluationUsage(
                input_tokens=usage.get("input_tokens"),
                output_tokens=usage.get("output_tokens"),
                duration_ms=duration_ms,
                cache_read_tokens=input_details.get("cache_read"),
                cache_write_tokens=input_details.get("cache_creation"),
                reasoning_tokens=output_details.get("reasoning"),
            )

        results = RunnableLambda(evaluate_page).batch_as_completed(
            [
                {
                    "cv": cv,
                    "sought_jobs": describe_sought_jobs(criteria.sought_jobs),
                    "area_rule": describe_area_rule(criteria.accepted_areas),
                    "title": page["title"],
                    "url": page["url"],
                    "page": page_text(page)[:MAX_PAGE_CHARS],
                }
                for page in pages
            ],
            config={"max_concurrency": 5},
        )
        for index, (evaluation, usage) in results:
            yield index, evaluation, usage
