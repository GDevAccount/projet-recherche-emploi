"""Branchements réels de l'assistant : OpenAI pour situer les textes et pour répondre.

Les clients ne sont créés qu'au premier appel : construire le conteneur ne demande aucune clé API.
"""

import time
from collections.abc import Callable, Mapping, Sequence
from functools import cached_property
from typing import Any

from langchain_core.callbacks import UsageMetadataCallbackHandler
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    BaseMessageChunk,
    HumanMessage,
    message_chunk_to_message,
)
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool
from langchain_core.utils.json import parse_partial_json
from langchain_openai import ChatOpenAI
from openai import OpenAI

from jobgrep.assistant.passages import Passage
from jobgrep.assistant.ports import DraftAnswer, Exchange, ModelTurn, ModelUsage, Verdict
from jobgrep.assistant.prompts import ANSWER_PROMPT, JUDGE_PROMPT, describe_passages
from jobgrep.config import (
    ASSISTANT_MODEL,
    ASSISTANT_RETRIES,
    ASSISTANT_TIMEOUT_SECONDS,
    EMBEDDING_MODEL,
    JUDGE_MODEL,
    JUDGE_TIMEOUT_SECONDS,
)

# Forme de la réponse, garantie par OpenAI : tous les champs, et aucun autre
RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {"name": "DraftAnswer", "schema": DraftAnswer.model_json_schema(), "strict": True},
}


class OpenAIEmbedder:
    model_name = EMBEDDING_MODEL

    @cached_property
    def _client(self) -> OpenAI:
        return OpenAI(timeout=ASSISTANT_TIMEOUT_SECONDS, max_retries=ASSISTANT_RETRIES)

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
        # stream_usage : sans lui, une réponse lue en flux ne dit pas ses jetons
        return self._injected_chat_model or ChatOpenAI(
            model=ASSISTANT_MODEL, timeout=ASSISTANT_TIMEOUT_SECONDS, max_retries=ASSISTANT_RETRIES, stream_usage=True
        )

    def answer(
        self,
        question: str,
        passages: Sequence[Passage],
        history: Sequence[Exchange],
        transcript: Sequence[BaseMessage] = (),
        tools: Sequence[BaseTool] = (),
        on_answer: Callable[[str], None] | None = None,
    ) -> tuple[ModelTurn, ModelUsage]:
        messages: list[BaseMessage] = []
        for exchange in history:
            messages += [HumanMessage(exchange.question), AIMessage(exchange.answer)]
        prompt = ANSWER_PROMPT.format_messages(
            passages=describe_passages(passages), history=messages, question=question, transcript=list(transcript)
        )
        # Un schéma JSON, que la réponse suit champ après champ : elle se lit ainsi à mesure qu'elle s'écrit.
        # Avec des outils, le modèle rend soit la demande d'un outil, soit cette réponse
        if tools:
            model = self._chat_model.bind_tools(list(tools), response_format=RESPONSE_FORMAT, strict=True)
        else:
            model = self._chat_model.bind(response_format=RESPONSE_FORMAT)

        usage = UsageMetadataCallbackHandler()
        started = time.perf_counter()
        whole: BaseMessageChunk | None = None
        for chunk in model.stream(prompt, config={"callbacks": [usage]}):
            whole = chunk if whole is None else whole + chunk
            written = _written_answer(str(whole.text))
            if on_answer and written:
                on_answer(written)
        duration_ms = round((time.perf_counter() - started) * 1000)
        consumed = next(iter(usage.usage_metadata.values()), {})

        message = message_chunk_to_message(whole)
        draft = None if message.tool_calls else DraftAnswer.model_validate_json(str(message.text))
        return ModelTurn(message, draft), _describe_usage(consumed, duration_ms)


def _written_answer(text: str) -> str:
    """Renvoie le texte de la réponse déjà écrit dans ce JSON inachevé, ou rien tant que le modèle ne répond pas."""
    try:
        draft = parse_partial_json(text) if text else None
    except ValueError:
        return ""
    # L'issue s'écrit avant la réponse : tant qu'elle n'est pas « answered » en entier, rien n'est montré
    if isinstance(draft, dict) and draft.get("outcome") == "answered":
        return draft.get("answer") or ""
    return ""


class OpenAIAnswerJudge:
    model_name = JUDGE_MODEL

    def __init__(self, chat_model: BaseChatModel | None = None):
        self._injected_chat_model = chat_model

    @cached_property
    def _chat_model(self) -> BaseChatModel:
        return self._injected_chat_model or ChatOpenAI(
            model=JUDGE_MODEL, timeout=JUDGE_TIMEOUT_SECONDS, max_retries=ASSISTANT_RETRIES
        )

    def judge(
        self, question: str, passages: Sequence[Passage], answer: str, reference: str, account: str = ""
    ) -> tuple[Verdict, ModelUsage]:
        chain = JUDGE_PROMPT | self._chat_model.with_structured_output(Verdict, include_raw=True)
        inputs = {
            "question": question,
            "passages": describe_passages(passages),
            "reference": reference,
            "answer": answer,
            "account": account or "aucune : il n'a pas consulté le compte",
        }
        return _invoke(chain, inputs)


def _invoke(chain: Runnable, inputs: dict) -> tuple[Any, ModelUsage]:
    """Interroge le modèle, et renvoie ce qu'il a rendu avec ce que l'appel a coûté."""
    started = time.perf_counter()
    reply = chain.invoke(inputs)
    duration_ms = round((time.perf_counter() - started) * 1000)
    if reply["parsing_error"]:
        raise reply["parsing_error"]
    return reply["parsed"], _describe_usage(getattr(reply["raw"], "usage_metadata", None) or {}, duration_ms)


def _describe_usage(usage: Mapping, duration_ms: int) -> ModelUsage:
    input_details = usage.get("input_token_details") or {}
    return ModelUsage(
        input_tokens=usage.get("input_tokens"),
        output_tokens=usage.get("output_tokens"),
        cache_read_tokens=input_details.get("cache_read"),
        cache_write_tokens=input_details.get("cache_creation"),
        duration_ms=duration_ms,
    )
