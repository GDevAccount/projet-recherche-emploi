from collections.abc import Callable, Sequence

from langgraph.config import get_stream_writer

from jobgrep.assistant.passages import IndexedPassage, rank_passages
from jobgrep.assistant.ports import AnswerModel, Embedder, Outcome
from jobgrep.assistant.state import AssistantState
from jobgrep.config import ASSISTANT_PASSAGES

OFF_TOPIC_ANSWER = (
    "Je ne réponds qu'aux questions sur JobGrep : son fonctionnement, vos données et vos droits. "
    "Pour le reste, je ne peux pas vous aider."
)
UNKNOWN_ANSWER = "Je n'ai pas trouvé la réponse dans les textes de JobGrep. Pour cette question, {contact}."
NO_CONTACT = "adressez-vous à l'exploitant de l'application"


class AssistantNodes:
    """Nœuds du graph de l'assistant. Ils ne touchent pas à la base : les passages leur sont donnés."""

    def __init__(
        self,
        embedder: Embedder,
        answer_model: AnswerModel,
        index: Callable[[], Sequence[IndexedPassage]],
        contact_email: str = "",
    ):
        self.embedder = embedder
        self.answer_model = answer_model
        # Rend les passages des textes du site avec leur vecteur : ils ne sont calculés qu'à la première question
        self.index = index
        self.contact_email = contact_email

    def retrieve_passages(self, state: AssistantState) -> AssistantState:
        """Situe la question parmi les passages des textes du site, et garde les plus proches."""
        get_stream_writer()({"step": "retrieve"})
        index = self.index()
        question = state["question"]
        # Une question qui renvoie à la précédente (« et pour un essai ? ») ne se situe qu'avec elle. Mais une
        # question qui change de sujet serait noyée dans la précédente : elle est donc située seule aussi, et
        # les passages sont pris à tour de rôle, ceux de la question seule d'abord
        texts = [question, *(f"{exchange.question}\n{question}" for exchange in state.get("history", [])[-1:])]
        vectors, tokens = self.embedder.embed(texts)
        return {"passages": rank_passages(vectors, index, ASSISTANT_PASSAGES), "embedding_tokens": tokens}

    def generate_answer(self, state: AssistantState) -> AssistantState:
        """Demande au modèle de répondre à partir des seuls passages retenus."""
        write_progress = get_stream_writer()
        write_progress({"step": "generate"})
        draft, usage = self.answer_model.answer(
            state["question"],
            state["passages"],
            state.get("history", []),
            on_answer=lambda text: write_progress({"step": "generate", "answer": text}),
        )
        return {"draft": draft, "usage": usage}

    def route_by_outcome(self, state: AssistantState) -> Outcome:
        """Dit quelle suite donner à ce que le modèle a rendu."""
        draft = state["draft"]
        # Une réponse vide n'en est pas une
        if draft.outcome == "answered" and not draft.answer.strip():
            return "unknown"
        return draft.outcome

    def cite_sources(self, state: AssistantState) -> AssistantState:
        """Garde la réponse du modèle, et les passages qu'il dit avoir utilisés."""
        draft, passages = state["draft"], state["passages"]
        # Un numéro que le modèle invente ne désigne aucun passage
        cited = [passages[number - 1] for number in draft.passages if 1 <= number <= len(passages)]
        return {"outcome": "answered", "answer": draft.answer.strip(), "cited": cited}

    def decline_question(self, state: AssistantState) -> AssistantState:
        """Refuse une question qui ne porte pas sur l'application, avec des mots que le modèle n'écrit pas."""
        return {"outcome": "off_topic", "answer": OFF_TOPIC_ANSWER, "cited": []}

    def refer_to_operator(self, state: AssistantState) -> AssistantState:
        """Renvoie vers l'exploitant une question sur l'application à laquelle les textes ne répondent pas."""
        contact = f"écrivez à {self.contact_email}" if self.contact_email else NO_CONTACT
        return {"outcome": "unknown", "answer": UNKNOWN_ANSWER.format(contact=contact), "cited": []}
