"""Branchements réels de l'assistant : OpenAI pour situer les textes et pour répondre.

Les clients ne sont créés qu'au premier appel : construire le conteneur ne demande aucune clé API.
"""

import time
from collections.abc import Sequence
from functools import cached_property
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.runnables import Runnable
from langchain_openai import ChatOpenAI
from openai import OpenAI

from jobgrep.assistant.passages import Passage
from jobgrep.assistant.ports import DraftAnswer, Exchange, ModelUsage, Verdict
from jobgrep.assistant.prompts import ANSWER_PROMPT, JUDGE_PROMPT, describe_passages
from jobgrep.config import ASSISTANT_MODEL, EMBEDDING_MODEL, JUDGE_MODEL


class OpenAIEmbedder:
    model_name = EMBEDDING_MODEL

    @cached_property
    def _client(self) -> OpenAI:
        return OpenAI()

    def embed(self, texts: Sequence[str]) -> tuple[list[list[float]], int | None]:
        response = self._client.embeddings.create(model=EMBEDDING_MODEL, input=list(texts))
        # La réponse ne garantit pas l'ordre des textes envoyés : chaque vecteur porte son rang
        vectors = [item.embedding for item in sorted(response.data, key=lambda item: item.index)]
        return vectors, response.usage.total_tokens


class OpenAIAnswerModel:
    model_name = ASSISTANT_MODEL

    def __init__(self, chat_model: BaseChatModel | None = None):
        self._injected_chat_model = chat_model

    @cached_property
    def _chat_model(self) -> BaseChatModel:
        return self._injected_chat_model or ChatOpenAI(model=ASSISTANT_MODEL)

    def answer(
        self, question: str, passages: Sequence[Passage], history: Sequence[Exchange]
    ) -> tuple[DraftAnswer, ModelUsage]:
        # La réponse brute accompagne le verdict : c'est elle qui porte le nombre de jetons
        chain = ANSWER_PROMPT | self._chat_model.with_structured_output(DraftAnswer, include_raw=True)
        messages: list[BaseMessage] = []
        for exchange in history:
            messages += [HumanMessage(exchange.question), AIMessage(exchange.answer)]

        inputs = {"passages": describe_passages(passages), "history": messages, "question": question}
        return _invoke(chain, inputs)


class OpenAIAnswerJudge:
    model_name = JUDGE_MODEL

    def __init__(self, chat_model: BaseChatModel | None = None):
        self._injected_chat_model = chat_model

    @cached_property
    def _chat_model(self) -> BaseChatModel:
        return self._injected_chat_model or ChatOpenAI(model=JUDGE_MODEL)

    def judge(
        self, question: str, passages: Sequence[Passage], answer: str, reference: str
    ) -> tuple[Verdict, ModelUsage]:
        chain = JUDGE_PROMPT | self._chat_model.with_structured_output(Verdict, include_raw=True)
        inputs = {
            "question": question,
            "passages": describe_passages(passages),
            "reference": reference,
            "answer": answer,
        }
        return _invoke(chain, inputs)


def _invoke(chain: Runnable, inputs: dict) -> tuple[Any, ModelUsage]:
    """Interroge le modèle, et renvoie ce qu'il a rendu avec ce que l'appel a coûté."""
    started = time.perf_counter()
    reply = chain.invoke(inputs)
    duration_ms = round((time.perf_counter() - started) * 1000)
    if reply["parsing_error"]:
        raise reply["parsing_error"]
    usage = getattr(reply["raw"], "usage_metadata", None) or {}
    input_details = usage.get("input_token_details") or {}
    return reply["parsed"], ModelUsage(
        input_tokens=usage.get("input_tokens"),
        output_tokens=usage.get("output_tokens"),
        cache_read_tokens=input_details.get("cache_read"),
        cache_write_tokens=input_details.get("cache_creation"),
        duration_ms=duration_ms,
    )
