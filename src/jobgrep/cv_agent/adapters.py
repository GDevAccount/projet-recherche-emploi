"""Version OpenAI du modèle qui tire d'un CV les postes à rechercher. Le client est créé à son premier usage."""

import time
from functools import cached_property

from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI

from jobgrep.config import PROFILE_CV_CHARS, PROFILE_MODEL, PROFILE_RETRIES, PROFILE_TIMEOUT_SECONDS
from jobgrep.cv_agent.ports import DraftedProfile, ExtractionUsage
from jobgrep.cv_agent.prompts import PROFILE_PROMPT, render_prompt


class OpenAIProfileExtractor:
    model_name = PROFILE_MODEL

    def __init__(self, chat_model: BaseChatModel | None = None):
        self._injected_chat_model = chat_model

    @cached_property
    def _chat_model(self) -> BaseChatModel:
        return self._injected_chat_model or ChatOpenAI(
            model=PROFILE_MODEL, timeout=PROFILE_TIMEOUT_SECONDS, max_retries=PROFILE_RETRIES
        )

    def extract(self, cv: str) -> tuple[DraftedProfile, ExtractionUsage]:
        # La réponse brute accompagne le profil : c'est elle qui porte le nombre de jetons
        chain = PROFILE_PROMPT | self._chat_model.with_structured_output(DraftedProfile, include_raw=True)
        started = time.perf_counter()
        answer = chain.invoke(render_prompt(cv[:PROFILE_CV_CHARS]))
        duration_ms = round((time.perf_counter() - started) * 1000)
        if answer["parsing_error"]:
            raise answer["parsing_error"]
        usage = getattr(answer["raw"], "usage_metadata", None) or {}
        input_details = usage.get("input_token_details") or {}
        return answer["parsed"], ExtractionUsage(
            input_tokens=usage.get("input_tokens"),
            output_tokens=usage.get("output_tokens"),
            cache_read_tokens=input_details.get("cache_read"),
            cache_write_tokens=input_details.get("cache_creation"),
            duration_ms=duration_ms,
        )
