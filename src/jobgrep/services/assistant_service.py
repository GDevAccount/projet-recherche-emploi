"""Assistant : il répond aux questions sur l'application à partir des seuls textes du site.

Le graph de assistant/ cherche les passages et répond ; ce service en tient les abords : quota, budget,
passages gardés en base, journal des questions. Rien d'un compte n'entre dans une question.
"""

import json
import logging
import threading
from collections.abc import Callable, Iterator, Sequence
from datetime import UTC, datetime, timedelta
from functools import cached_property
from zoneinfo import ZoneInfo

from langchain_core.messages import ToolMessage
from langgraph.graph.state import CompiledStateGraph

from jobgrep.assistant.graph import build_graph
from jobgrep.assistant.nodes import AssistantNodes
from jobgrep.assistant.passages import IndexedPassage, Passage, split_text
from jobgrep.assistant.ports import AccountReader, AnswerModel, Embedder, Exchange
from jobgrep.assistant.prompts import prompt_version
from jobgrep.assistant.tools import (
    ACCOUNT_STATUS_TOOL,
    CV_TOOL,
    OFFERS_TOOL,
    QUERIES_TOOL,
    REJECTIONS_TOOL,
    build_account_tools,
)
from jobgrep.config import (
    ASSISTANT_HISTORY_MINUTES,
    ASSISTANT_HISTORY_TURNS,
    ASSISTANT_MESSAGE_DAYS,
    DEFAULT_USER_ID,
    LOCAL_TIMEZONE,
    MAX_ASSISTANT_ACCOUNT_QUESTIONS_PER_DAY,
    MAX_ASSISTANT_QUESTIONS_PER_DAY,
    MAX_ASSISTANT_QUESTIONS_PER_MINUTE,
)
from jobgrep.data.cv_ingestion.anonymizer import CvAnonymizer
from jobgrep.data.database import Database
from jobgrep.data.models import AssistantMessage
from jobgrep.data.repositories.assistant_message_repository import (
    AssistantJournalRepository,
    AssistantMessageRepository,
)
from jobgrep.data.repositories.assistant_passage_repository import AssistantPassageRepository
from jobgrep.data.repositories.health_repository import HealthRepository
from jobgrep.data.repositories.usage_repository import UsageRepository
from jobgrep.errors import (
    AssistantAccountLimitError,
    AssistantDailyLimitError,
    AssistantRateLimitError,
    AssistantUnavailableError,
    BudgetReachedError,
    InvalidInputError,
    NotFoundError,
)
from jobgrep.schemas import (
    MAX_QUESTION_CHARS,
    AssistantConversation,
    AssistantFeedback,
    AssistantJournalEntry,
    AssistantLimit,
    AssistantMessageRead,
    AssistantOverview,
    AssistantProgress,
    AssistantReply,
    AssistantSource,
)
from jobgrep.services.search_costs import model_cost_usd, sum_costs
from jobgrep.site_texts import SITE_TEXTS, read_site_text, section_screen, section_url

logger = logging.getLogger(__name__)

UNAVAILABLE_MESSAGE = "L'assistant ne répond pas pour l'instant. Réessayez dans un moment."
DAILY_LIMIT_MESSAGE = "Vous avez atteint votre limite de questions pour aujourd'hui : revenez demain."
# Ce que l'assistant a consulté du compte, tel qu'il est dit à l'utilisateur
TOOL_LABELS = {
    ACCOUNT_STATUS_TOOL: "État de votre compte",
    OFFERS_TOOL: "Vos offres",
    REJECTIONS_TOOL: "Vos pages écartées",
    QUERIES_TOOL: "Vos postes recherchés",
    CV_TOOL: "Votre CV",
}
# Limites opposées à une question, telles que la rubrique Suivi les nomme
LIMIT_LABELS = {
    AssistantDailyLimitError.__name__: "Questions du jour épuisées",
    AssistantAccountLimitError.__name__: "Consultations du compte épuisées",
    AssistantRateLimitError.__name__: "Questions trop rapprochées",
}
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
        AssistantSource(
            title=page_title,
            section=section or None,
            url=section_url(source, section),
            screen=section_screen(source, section),
        )
        for source, page_title, section in sections
    ]


def _read_consulted(consulted: str | None) -> list[str]:
    """Renvoie ce que l'assistant a consulté du compte, dans les mots dits à l'utilisateur."""
    return [TOOL_LABELS.get(name, name) for name in json.loads(consulted or "[]")]


def _current_conversation(rows: Sequence[AssistantMessage]) -> Sequence[AssistantMessage]:
    """Renvoie, parmi ces questions de la plus ancienne à la plus récente, celles de la conversation en cours."""
    starts = [position for position, row in enumerate(rows) if row.starts_conversation]
    return rows[starts[-1] :] if starts else rows


def _read_message(row: AssistantMessage) -> AssistantMessageRead:
    return AssistantMessageRead(
        id=row.id,
        created_at=row.created_at,
        question=row.question,
        answer=row.answer,
        outcome=row.outcome,
        sources=_read_sources(row.sources),
        consulted=_read_consulted(row.consulted),
        feedback=row.feedback,
    )


def _count_limits(refusals: Sequence) -> list[AssistantLimit]:
    """Additionne, par limite, les refus que les deux routes de l'assistant ont rendus."""
    limits: dict[str, AssistantLimit] = {}
    for row in refusals:
        label = LIMIT_LABELS[row.error_type]
        limit = limits.setdefault(row.error_type, AssistantLimit(label=label, count=0, accounts=0))
        limit.count += row.count
        # Le même compte peut être refusé par les deux routes : c'est un plafond, pas un décompte exact
        limit.accounts = max(limit.accounts, row.accounts)
    return sorted(limits.values(), key=lambda limit: -limit.count)


class AssistantService:
    def __init__(
        self,
        database: Database,
        embedder: Embedder,
        answer_model: AnswerModel,
        contact_email: str = "",
        budget_reached: Callable[[], bool] = lambda: False,
        anonymizer: CvAnonymizer | None = None,
        account: AccountReader | None = None,
    ):
        self.database = database
        # Lit la situation du compte de l'appelant pour le modèle ; None : l'assistant ne sait rien de lui
        self.account = account
        # Retire d'une question ce qui a la forme d'une coordonnée, comme d'un CV
        self.anonymizer = anonymizer or CvAnonymizer()
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
        return self.graph_for(self.account)

    def graph_for(self, account: AccountReader | None) -> CompiledStateGraph:
        """Construit le graph de l'assistant sur ce lecteur de comptes : le vrai, ou celui d'une évaluation."""
        tools = build_account_tools(account) if account else []
        return build_graph(AssistantNodes(self.embedder, self.answer_model, self._passages, self.contact_email, tools))

    def ask(
        self, user_id: int, question: str, now: datetime | None = None, new_conversation: bool = False
    ) -> AssistantReply:
        """Répond à une question sur l'application, l'enregistre, et dit ce que l'utilisateur peut encore demander.

        Une question hors sujet est comptée et enregistrée comme les autres : elle a coûté autant.
        """
        *_, reply = self.stream_answer(user_id, question, now, new_conversation)
        return reply

    def stream_answer(
        self, user_id: int, question: str, now: datetime | None = None, new_conversation: bool = False
    ) -> Iterator[AssistantProgress | AssistantReply]:
        """Répond à une question en disant où il en est : ses étapes, la réponse qui s'écrit, puis le bilan.

        Un refus (question vide, quota, budget) est levé à l'appel, avant le premier élément, pour que l'API
        puisse encore répondre par une erreur. « new_conversation » ouvre une conversation : les échanges
        précédents ne sont plus rappelés au modèle, ni réaffichés.
        """
        # À la seconde, comme la base l'enregistre : la réponse rendue ici est celle qui sera relue
        now = (now or datetime.now(UTC)).replace(microsecond=0)
        question = question.strip()
        if not question:
            raise InvalidInputError("Écrivez votre question.")
        if len(question) > MAX_QUESTION_CHARS:
            raise InvalidInputError(f"Une question tient en {MAX_QUESTION_CHARS} caractères au plus.")
        # Avant tout envoi et tout enregistrement : une question est lue par OpenAI, puis par les
        # administrateurs, qui n'ont à connaître ni l'adresse ni le téléphone de celui qui la pose
        question = self.anonymizer.anonymize(question)
        # Ni le budget ni le quota ne s'appliquent au propriétaire, qui paie les clés API
        limited = user_id != DEFAULT_USER_ID
        if limited and self.budget_reached():
            raise BudgetReachedError("Le budget du jour de l'application est atteint : revenez demain.")

        # Lecture seule : l'écriture a sa propre transaction, après le graph et ses appels au modèle
        with self.database.session() as session:
            messages = AssistantMessageRepository(session, user_id)
            today = _day_start(now)
            if limited and messages.count_since(today) >= MAX_ASSISTANT_QUESTIONS_PER_DAY:
                raise AssistantDailyLimitError(DAILY_LIMIT_MESSAGE)
            # Une question qui consulte le compte coûte un appel de plus : celles-là sont comptées à part, et
            # leur nombre atteint ferme la journée, quoi que la question suivante demande
            if limited and messages.count_consulting_since(today) >= MAX_ASSISTANT_ACCOUNT_QUESTIONS_PER_DAY:
                raise AssistantAccountLimitError(DAILY_LIMIT_MESSAGE)
            if limited and messages.count_since(now - timedelta(minutes=1)) >= MAX_ASSISTANT_QUESTIONS_PER_MINUTE:
                raise AssistantRateLimitError("Vous posez vos questions trop vite : attendez une minute.")
            recent = messages.list_recent(ASSISTANT_HISTORY_TURNS, now - timedelta(minutes=ASSISTANT_HISTORY_MINUTES))
            remembered = [] if new_conversation else _current_conversation(recent)
            history = [Exchange(row.question, row.answer) for row in remembered]

        return self._answer(user_id, question, history, limited, now, new_conversation)

    def _answer(
        self, user_id: int, question: str, history: list[Exchange], limited: bool, now: datetime, new_conversation: bool
    ) -> Iterator[AssistantProgress | AssistantReply]:
        result: dict = {}
        try:
            # Le compte de l'appelant est mis dans l'état par le serveur : c'est le seul que les outils lisent
            asked = {"user_id": user_id, "question": question, "history": history}
            events = self.graph.stream(asked, stream_mode=["custom", "values"])
            for mode, chunk in events:
                if mode == "custom":
                    yield AssistantProgress(**chunk)
                else:
                    result = chunk
        except Exception as error:
            # Le type seulement : le message d'une erreur du modèle peut reprendre la question posée
            logger.warning("L'assistant n'a pas pu répondre : %s", type(error).__name__)
            # Rien n'est enregistré : une question restée sans réponse ne compte pas dans le quota
            raise AssistantUnavailableError(UNAVAILABLE_MESSAGE) from error
        outcome, answer, usage = result["outcome"], result["answer"], result["usage"]
        sources, retrieved = _sources_of(result["cited"]), _sources_of(result["passages"])
        tools_called = [message.name for message in result.get("transcript", []) if isinstance(message, ToolMessage)]
        # Sans doublon, et vide plutôt que « [] » : c'est ce vide qui dit que le compte n'a pas été consulté
        consulted = json.dumps(list(dict.fromkeys(tools_called))) if tools_called else None

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
                    "consulted": consulted,
                    "outcome": outcome,
                    "starts_conversation": new_conversation,
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
            id=message_id,
            created_at=now,
            question=question,
            answer=answer,
            outcome=outcome,
            sources=sources,
            consulted=_read_consulted(consulted),
            feedback=None,
        )
        remaining = max(0, MAX_ASSISTANT_QUESTIONS_PER_DAY - used) if limited else None
        yield AssistantReply(message=message, remaining_questions=remaining)

    def set_feedback(self, user_id: int, message_id: int, feedback: AssistantFeedback | None) -> None:
        """Note une réponse de l'assistant, utile ou non, ou retire la note. Chacun ne note que ses réponses."""
        with self.database.session() as session:
            if not AssistantMessageRepository(session, user_id).set_feedback(message_id, feedback):
                raise NotFoundError("Cette réponse n'existe pas.")

    def get_conversation(self, user_id: int, now: datetime | None = None) -> AssistantConversation:
        """Renvoie la conversation en cours de l'utilisateur avec l'assistant, et ce qu'il peut encore demander."""
        now = now or datetime.now(UTC)
        with self.database.session() as session:
            messages = AssistantMessageRepository(session, user_id)
            # Un texte dont le délai est passé n'est plus montré, même si aucune question ne l'a encore effacé
            rows = messages.list_recent(MAX_SHOWN_MESSAGES, now - timedelta(days=ASSISTANT_MESSAGE_DAYS))
            used = messages.count_since(_day_start(now))
        remaining = None if user_id == DEFAULT_USER_ID else max(0, MAX_ASSISTANT_QUESTIONS_PER_DAY - used)
        return AssistantConversation(
            messages=[_read_message(row) for row in _current_conversation(rows)],
            remaining_questions=remaining,
            max_questions_per_day=MAX_ASSISTANT_QUESTIONS_PER_DAY,
            max_account_questions_per_day=MAX_ASSISTANT_ACCOUNT_QUESTIONS_PER_DAY,
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
            notes = {row.feedback: row.count for row in journal.count_feedback(since)}
            consulting = journal.count_consulting(since)
            # Un refus pour limite atteinte est une demande refusée comme une autre : il est déjà gardé, avec
            # sa route et son type, parmi les erreurs rendues par l'API
            errors = HealthRepository(session).summarize_errors(since)
            refusals = [row for row in errors if row.error_type in LIMIT_LABELS]
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
            consulting=consulting,
            limits=_count_limits(refusals),
            helpful=notes.get("up", 0),
            unhelpful=notes.get("down", 0),
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
                    consulted=_read_consulted(row.consulted),
                    feedback=row.feedback,
                )
                for row in rows
            ],
        )

    def index_texts(self) -> int:
        """Situe les passages des textes du site qui ne le sont pas encore, et renvoie le nombre de passages.

        La première question le ferait d'elle-même : le faire au déploiement lui épargne cette attente.
        """
        return len(self._passages())

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
