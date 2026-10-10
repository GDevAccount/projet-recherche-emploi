from typing import TypedDict

from jobgrep.assistant.passages import Passage
from jobgrep.assistant.ports import DraftAnswer, Exchange, ModelUsage, Outcome


class AssistantState(TypedDict, total=False):
    question: str
    # Échanges précédents de la conversation, le plus ancien en premier
    history: list[Exchange]
    # Passages des textes du site les plus proches de la question, le plus proche en premier
    passages: list[Passage]
    # Jetons lus pour situer la question ; None si le modèle d'embedding ne le dit pas
    embedding_tokens: int | None
    # Ce que le modèle a rendu, et ce que l'appel a coûté
    draft: DraftAnswer
    usage: ModelUsage
    # Ce qui est répondu à l'utilisateur, et les passages d'où vient la réponse
    outcome: Outcome
    answer: str
    cited: list[Passage]
