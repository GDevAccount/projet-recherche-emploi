"""Ce que l'assistant attend de l'extérieur. Les tests y branchent des faux, sans réseau ni facture."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

from pydantic import BaseModel

from jobgrep.assistant.passages import Passage

# « answered » : la réponse est dans les passages ; « unknown » : la question porte sur l'application, mais
# les passages n'y répondent pas ; « off_topic » : elle ne porte pas sur l'application
Outcome = Literal["answered", "unknown", "off_topic"]


class DraftAnswer(BaseModel):
    """Ce que le modèle rend pour une question. Les champs sont dans l'ordre où il les écrit.

    Il dit d'abord ce qu'il en est, puis répond : c'est le service qui écrit le refus d'une question hors sujet.
    """

    outcome: Outcome
    answer: str
    # Numéros des passages d'où vient la réponse, tels qu'ils lui ont été donnés
    passages: list[int] = []


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
        self, question: str, passages: Sequence[Passage], history: Sequence[Exchange]
    ) -> tuple[DraftAnswer, ModelUsage]:
        """Répond à la question à partir de ces seuls passages, numérotés à partir de 1."""
        ...


class Verdict(BaseModel):
    """Ce que le juge dit d'une réponse de l'assistant. La raison vient d'abord : il réfléchit avant de trancher."""

    reason: str
    # Tout ce que la réponse affirme est-il appuyé par les passages donnés au modèle
    faithful: bool
    # La réponse dit-elle l'essentiel de la réponse de référence, sans la contredire
    correct: bool


class AnswerJudge(Protocol):
    # Nom du modèle interrogé, enregistré avec chaque évaluation
    model_name: str

    def judge(
        self, question: str, passages: Sequence[Passage], answer: str, reference: str
    ) -> tuple[Verdict, ModelUsage]:
        """Note une réponse de l'assistant au regard des passages qu'il a reçus et de la réponse attendue."""
        ...
