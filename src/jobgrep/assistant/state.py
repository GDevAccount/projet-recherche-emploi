from typing import Annotated, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

from jobgrep.assistant.passages import Passage
from jobgrep.assistant.ports import DraftAnswer, Exchange, ModelUsage, Outcome


class AssistantState(TypedDict, total=False):
    # Compte de la personne qui pose la question : mis ici par le serveur, c'est lui que lisent les outils
    user_id: int
    question: str
    # Échanges précédents de la conversation, le plus ancien en premier
    history: list[Exchange]
    # Passages des textes du site les plus proches de la question, le plus proche en premier
    passages: list[Passage]
    # Jetons lus pour situer la question ; None si le modèle d'embedding ne le dit pas
    embedding_tokens: int | None
    # Ce que le modèle a demandé aux outils, et ce qu'ils ont rendu, dans l'ordre ; vide s'il n'a rien demandé
    transcript: Annotated[list[BaseMessage], add_messages]
    # Ce que le modèle a rendu, et ce qu'ont coûté tous ses appels pour cette question
    draft: DraftAnswer
    usage: ModelUsage
    # Ce qui est répondu à l'utilisateur, et les passages d'où vient la réponse
    outcome: Outcome
    answer: str
    cited: list[Passage]
