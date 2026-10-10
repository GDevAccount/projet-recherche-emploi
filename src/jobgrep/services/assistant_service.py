"""Assistant : il répond aux questions sur l'application à partir des seuls textes du site.

Le graph de assistant/ cherche les passages et répond ; ce service en tient les abords : quota, budget,
passages gardés en base, journal des questions. Rien d'un compte n'entre dans une question.
"""

import json
import logging
import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from functools import cached_property
from zoneinfo import ZoneInfo

from langgraph.graph.state import CompiledStateGraph

from jobgrep.assistant.graph import build_graph
from jobgrep.assistant.nodes import AssistantNodes
from jobgrep.assistant.passages import IndexedPassage, Passage, split_text
from jobgrep.assistant.ports import AnswerModel, Embedder, Exchange
from jobgrep.assistant.prompts import prompt_version
from jobgrep.config import (
    ASSISTANT_HISTORY_MINUTES,
    ASSISTANT_HISTORY_TURNS,
    ASSISTANT_MESSAGE_DAYS,
    DEFAULT_USER_ID,
    LOCAL_TIMEZONE,
    MAX_ASSISTANT_QUESTIONS_PER_DAY,
)
from jobgrep.data.database import Database
from jobgrep.data.repositories.assistant_message_repository import (
    AssistantJournalRepository,
    AssistantMessageRepository,
)
from jobgrep.data.repositories.assistant_passage_repository import AssistantPassageRepository
from jobgrep.data.repositories.usage_repository import UsageRepository
from jobgrep.errors import AssistantUnavailableError, BudgetReachedError, InvalidInputError, QuotaExceededError
from jobgrep.schemas import (
    MAX_QUESTION_CHARS,
    AssistantConversation,
    AssistantJournalEntry,
    AssistantMessageRead,
    AssistantOverview,
    AssistantReply,
    AssistantSource,
)
from jobgrep.services.search_costs import model_cost_usd, sum_costs
from jobgrep.site_texts import SITE_TEXTS, read_site_text

logger = logging.getLogger(__name__)

UNAVAILABLE_MESSAGE = "L'assistant ne répond pas pour l'instant. Réessayez dans un moment."
# Derniers échanges réaffichés à l'ouverture de l'assistant
MAX_SHOWN_MESSAGES = 30
# Dernières questions lues par un administrateur
MAX_JOURNAL_ENTRIES = 200


def _day_start(now: datetime) -> datetime:
    """Renvoie minuit du jour en cours, à l'heure de Paris : le quota se compte par jour."""
    local = now.astimezone(ZoneInfo(LOCAL_TIMEZONE))
    return local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)


def _write_sources(sources: list[AssistantSource]) -> str:
    return json.dumps([source.model_dump() for source in sources], ensure_ascii=False)


def _read_sources(sources: str | None) -> list[AssistantSource]:
    return [AssistantSource(**source) for source in json.loads(sources or "[]")]


def _sources_of(passages: list[Passage]) -> list[AssistantSource]:
    """Renvoie les textes d'où viennent ces passages, sans doublon, dans leur ordre."""
    sections = dict.fromkeys((passage.source, passage.page_title, passage.section) for passage in passages)
    return [
        AssistantSource(title=page_title, section=section or None, url=SITE_TEXTS[source].url)
        for source, page_title, section in sections
    ]


class AssistantService:
    def __init__(
        self,
        database: Database,
        embedder: Embedder,
        answer_model: AnswerModel,
        contact_email: str = "",
        budget_reached: Callable[[], bool] = lambda: False,
    ):
        self.database = database
        self.embedder = embedder
        self.answer_model = answer_model
        self.contact_email = contact_email
        # Dit si le budget du jour de l'instance est atteint : plus de question pour personne, sauf le propriétaire
        self.budget_reached = budget_reached
        # Passages et vecteurs relus de la base à la première question : ils ne changent qu'avec le code
        self._index: list[IndexedPassage] | None = None
        self._index_lock = threading.Lock()

    @cached_property
    def graph(self) -> CompiledStateGraph:
        nodes = AssistantNodes(self.embedder, self.answer_model, self._passages, self.contact_email)
        return build_graph(nodes)

    def ask(self, user_id: int, question: str, now: datetime | None = None) -> AssistantReply:
        """Répond à une question sur l'application, l'enregistre, et dit ce que l'utilisateur peut encore demander.

        Une question hors sujet est comptée et enregistrée comme les autres : elle a coûté autant.
        """
        # À la seconde, comme la base l'enregistre : la réponse rendue ici est celle qui sera relue
        now = (now or datetime.now(UTC)).replace(microsecond=0)
        question = question.strip()
        if not question:
            raise InvalidInputError("Écrivez votre question.")
        if len(question) > MAX_QUESTION_CHARS:
            raise InvalidInputError(f"Une question tient en {MAX_QUESTION_CHARS} caractères au plus.")
        # Ni le budget ni le quota ne s'appliquent au propriétaire, qui paie les clés API
        limited = user_id != DEFAULT_USER_ID
        if limited and self.budget_reached():
            raise BudgetReachedError("Le budget du jour de l'application est atteint : revenez demain.")

        # Lecture seule : l'écriture a sa propre transaction, après le graph et ses appels au modèle
        with self.database.session() as session:
            messages = AssistantMessageRepository(session, user_id)
            if limited and messages.count_since(_day_start(now)) >= MAX_ASSISTANT_QUESTIONS_PER_DAY:
                raise QuotaExceededError("Vous avez posé toutes vos questions d'aujourd'hui : revenez demain.")
            recent = messages.list_recent(ASSISTANT_HISTORY_TURNS, now - timedelta(minutes=ASSISTANT_HISTORY_MINUTES))
            history = [Exchange(row.question, row.answer) for row in recent]

        try:
            result = self.graph.invoke({"question": question, "history": history})
        except Exception as error:
            # Le type seulement : le message d'une erreur du modèle peut reprendre la question posée
            logger.warning("L'assistant n'a pas pu répondre : %s", type(error).__name__)
            # Rien n'est enregistré : une question restée sans réponse ne compte pas dans le quota
            raise AssistantUnavailableError(UNAVAILABLE_MESSAGE) from error
        outcome, answer, usage = result["outcome"], result["answer"], result["usage"]
        sources, retrieved = _sources_of(result["cited"]), _sources_of(result["passages"])

        with self.database.session() as session:
            # L'écriture d'abord : SQLite refuse celle d'une transaction qui a lu pendant qu'une recherche écrit
            AssistantJournalRepository(session).forget_texts_before(now - timedelta(days=ASSISTANT_MESSAGE_DAYS))
            messages = AssistantMessageRepository(session, user_id)
            message_id = messages.insert_message(
                {
                    "question": question,
                    "answer": answer,
                    "sources": _write_sources(sources),
                    "retrieved": _write_sources(retrieved),
                    "outcome": outcome,
                    "model": self.answer_model.model_name,
                    "prompt_version": prompt_version(),
                    "input_tokens": usage.input_tokens,
                    "output_tokens": usage.output_tokens,
                    "cache_read_tokens": usage.cache_read_tokens,
                    "cache_write_tokens": usage.cache_write_tokens,
                    "embedding_model": self.embedder.model_name,
                    "embedding_tokens": result["embedding_tokens"],
                    "duration_ms": usage.duration_ms,
                    "created_at": now,
                }
            )
            used = messages.count_since(_day_start(now))

        message = AssistantMessageRead(
            id=message_id, created_at=now, question=question, answer=answer, outcome=outcome, sources=sources
        )
        remaining = max(0, MAX_ASSISTANT_QUESTIONS_PER_DAY - used) if limited else None
        return AssistantReply(message=message, remaining_questions=remaining)

    def get_conversation(self, user_id: int, now: datetime | None = None) -> AssistantConversation:
        """Renvoie les derniers échanges de l'utilisateur avec l'assistant, et ce qu'il peut encore demander."""
        now = now or datetime.now(UTC)
        with self.database.session() as session:
            messages = AssistantMessageRepository(session, user_id)
            # Un texte dont le délai est passé n'est plus montré, même si aucune question ne l'a encore effacé
            rows = messages.list_recent(MAX_SHOWN_MESSAGES, now - timedelta(days=ASSISTANT_MESSAGE_DAYS))
            used = messages.count_since(_day_start(now))
        remaining = None if user_id == DEFAULT_USER_ID else max(0, MAX_ASSISTANT_QUESTIONS_PER_DAY - used)
        return AssistantConversation(
            messages=[
                AssistantMessageRead(
                    id=row.id,
                    created_at=row.created_at,
                    question=row.question,
                    answer=row.answer,
                    outcome=row.outcome,
                    sources=_read_sources(row.sources),
                )
                for row in rows
            ],
            remaining_questions=remaining,
            max_questions_per_day=MAX_ASSISTANT_QUESTIONS_PER_DAY,
            max_question_chars=MAX_QUESTION_CHARS,
            retention_days=ASSISTANT_MESSAGE_DAYS,
        )

    def get_overview(self, days: int | None = None, now: datetime | None = None) -> AssistantOverview:
        """Renvoie l'usage de l'assistant sur tous les comptes, et les dernières questions posées.

        Sans utilisateur : c'est à l'interface de n'y laisser entrer qu'un administrateur. Il lit le texte des
        questions, jamais le compte qui les a posées. Sans nombre de jours, tout l'historique est compté.
        """
        now = now or datetime.now(UTC)
        since = None if days is None else now - timedelta(days=days)
        readable_since = now - timedelta(days=ASSISTANT_MESSAGE_DAYS)
        with self.database.session() as session:
            journal = AssistantJournalRepository(session)
            counts = {row.outcome: row.count for row in journal.summarize(since)}
            accounts = journal.count_accounts(since)
            rows = journal.list_recent(MAX_JOURNAL_ENTRIES, max(since or readable_since, readable_since))
            rows_used = UsageRepository(session).summarize_assistant(since)
        costs = [
            model_cost_usd(
                used.model, used.input_tokens, used.output_tokens, used.cache_read_tokens, used.cache_write_tokens
            )
            for used in rows_used
            if used.input_tokens is not None
        ]
        return AssistantOverview(
            since=since,
            questions=sum(counts.values()),
            answered=counts.get("answered", 0),
            unknown=counts.get("unknown", 0),
            off_topic=counts.get("off_topic", 0),
            accounts=accounts,
            cost_usd=sum_costs(costs),
            entries=[
                AssistantJournalEntry(
                    created_at=row.created_at,
                    question=row.question,
                    answer=row.answer,
                    outcome=row.outcome,
                    sources=_read_sources(row.sources),
                    retrieved=_read_sources(row.retrieved),
                )
                for row in rows
            ],
        )

    def _passages(self) -> list[IndexedPassage]:
        with self._index_lock:
            if self._index is None:
                self._index = self._load_index()
            return self._index

    def _load_index(self) -> list[IndexedPassage]:
        """Renvoie les passages des textes du site avec leur vecteur, en ne situant que ceux qui ont changé.

        Les vecteurs sont gardés en base : un redémarrage ne les recalcule pas, et un texte modifié ne fait
        recalculer que ses passages. Ce calcul-là n'est pas compté dans la consommation : il est sans utilisateur.
        """
        wanted = [
            passage for name in SITE_TEXTS for passage in split_text(name, read_site_text(name, self.contact_email))
        ]
        model = self.embedder.model_name
        with self.database.session() as session:
            stored = AssistantPassageRepository(session).list_passages()
        vectors = {row.content_hash: json.loads(row.embedding) for row in stored if row.embedding_model == model}
        hashes = {passage.content_hash for passage in wanted}
        stale = [row.id for row in stored if row.embedding_model != model or row.content_hash not in hashes]
        # Deux passages identiques n'en font qu'un à situer
        unknown = {passage.content_hash: passage for passage in wanted if passage.content_hash not in vectors}
        missing = list(unknown.values())

        if missing:
            computed, _ = self.embedder.embed([passage.embedding_text for passage in missing])
            vectors |= {passage.content_hash: vector for passage, vector in zip(missing, computed, strict=True)}
        if missing or stale:
            with self.database.session() as session:
                passages = AssistantPassageRepository(session)
                passages.delete_passages(stale)
                passages.insert_passages(
                    {
                        "source": passage.source,
                        "page_title": passage.page_title,
                        "section": passage.section,
                        "content": passage.content,
                        "content_hash": passage.content_hash,
                        "embedding_model": model,
                        "embedding": json.dumps(vectors[passage.content_hash]),
                    }
                    for passage in missing
                )
        return [(passage, vectors[passage.content_hash]) for passage in wanted]
