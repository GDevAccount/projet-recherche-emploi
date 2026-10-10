"""Ce que l'assistant attend de l'extérieur. Les tests y branchent des faux, sans réseau ni facture."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.tools import BaseTool
from pydantic import BaseModel, ConfigDict

from jobgrep.assistant.passages import Passage

# « answered » : la réponse est dans les passages ; « unknown » : la question porte sur l'application, mais
# les passages n'y répondent pas ; « off_topic » : elle ne porte pas sur l'application
Outcome = Literal["answered", "unknown", "off_topic"]


class DraftAnswer(BaseModel):
    """Ce que le modèle rend pour une question. Les champs sont dans l'ordre où il les écrit.

    Il dit d'abord ce qu'il en est, puis répond : c'est le service qui écrit le refus d'une question hors sujet.
    """

    # Aucun champ en plus ni en moins : c'est ce qu'OpenAI exige pour garantir la forme de la réponse
    model_config = ConfigDict(extra="forbid")

    outcome: Outcome
    answer: str
    # Numéros des passages d'où vient la réponse, tels qu'ils lui ont été donnés
    passages: list[int]


@dataclass(frozen=True)
class Exchange:
    """Échange précédent de la conversation, rappelé au modèle."""

    question: str
    answer: str


@dataclass(frozen=True)
class ModelUsage:
    """Ce qu'a coûté un appel au modèle qui répond. None quand il ne le dit pas."""

    input_tokens: int | None = None
    output_tokens: int | None = None
    # Part des jetons d'entrée lue ou écrite en cache, facturée à un autre tarif
    cache_read_tokens: int | None = None
    cache_write_tokens: int | None = None
    duration_ms: int | None = None


@dataclass(frozen=True)
class ModelTurn:
    """Ce que le modèle rend à un tour : sa réponse, ou la demande d'un outil."""

    # Son message, à remettre dans l'échange quand il demande un outil : c'est lui qui porte la demande
    message: AIMessage
    # None quand il demande un outil au lieu de répondre
    draft: DraftAnswer | None


class AccountReader(Protocol):
    def describe(self, user_id: int) -> str:
        """Renvoie la situation de ce compte, telle que le modèle peut la lire : des nombres et des dates."""
        ...


class Embedder(Protocol):
    # Nom du modèle interrogé : deux modèles ne placent pas un texte au même endroit
    model_name: str

    def embed(self, texts: Sequence[str]) -> tuple[list[list[float]], int | None]:
        """Renvoie le vecteur de chaque texte, dans l'ordre, et le nombre de jetons lus, None s'il n'est pas connu."""
        ...


class AnswerModel(Protocol):
    # Nom du modèle interrogé, enregistré avec chaque question
    model_name: str

    def answer(
        self,
        question: str,
        passages: Sequence[Passage],
        history: Sequence[Exchange],
        transcript: Sequence[BaseMessage] = (),
        tools: Sequence[BaseTool] = (),
        on_answer: Callable[[str], None] | None = None,
    ) -> tuple[ModelTurn, ModelUsage]:
        """Répond à la question à partir de ces passages, numérotés à partir de 1, ou demande un outil.

        « tools » sont les outils qu'il peut demander, « transcript » ce qu'il a déjà demandé pour cette
        question et ce qu'ils ont rendu.

        « on_answer » reçoit le texte de la réponse à mesure qu'il s'écrit, entier à chaque fois, et seulement
        quand le modèle répond : un refus ou un renvoi vers l'exploitant ne s'écrit pas ici.
        """
        ...


class Verdict(BaseModel):
    """Ce que le juge dit d'une réponse de l'assistant. La raison vient d'abord : il réfléchit avant de trancher."""

    reason: str
    # Tout ce que la réponse affirme est-il appuyé par ce que le modèle a reçu : passages, situation du compte
    faithful: bool
    # La réponse dit-elle l'essentiel de la réponse de référence, sans la contredire
    correct: bool


class AnswerJudge(Protocol):
    # Nom du modèle interrogé, enregistré avec chaque évaluation
    model_name: str

    def judge(
        self, question: str, passages: Sequence[Passage], answer: str, reference: str, account: str = ""
    ) -> tuple[Verdict, ModelUsage]:
        """Note une réponse de l'assistant au regard de ce qu'il a reçu et de la réponse attendue.

        « account » est la situation du compte qu'un outil lui a rendue ; vide s'il n'a rien consulté.
        """
        ...
