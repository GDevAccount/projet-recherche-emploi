"""Découpe les textes du site en passages, et retrouve ceux qui répondent à une question.

Un passage est une section d'un texte, ou une part de section quand elle est longue : assez court pour ne
parler que d'un sujet, assez long pour se comprendre seul.
"""

import hashlib
import math
import re
from collections.abc import Sequence
from dataclasses import dataclass

from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter

# Au-delà, une section est coupée en plusieurs passages
MAX_PASSAGE_CHARS = 1200
LINK_PATTERN = re.compile(r"\[([^\]]+)\]\([^)]+\)")


@dataclass(frozen=True)
class Passage:
    # Nom du texte d'où il vient (SITE_TEXTS), et titre de ce texte
    source: str
    page_title: str
    # Titre de sa section ; vide pour l'introduction du texte
    section: str
    content: str

    @property
    def heading(self) -> str:
        return f"{self.page_title} · {self.section}" if self.section else self.page_title

    @property
    def embedding_text(self) -> str:
        """Texte situé par le modèle d'embedding : le passage précédé de ses titres, qui disent de quoi il parle."""
        return f"{self.heading}\n{self.content}"

    @property
    def content_hash(self) -> str:
        """Empreinte du passage : elle change dès qu'un mot change, et dit alors qu'il faut le resituer."""
        return hashlib.sha256(f"{self.source}\n{self.embedding_text}".encode()).hexdigest()


def split_text(source: str, markdown_text: str, max_chars: int = MAX_PASSAGE_CHARS) -> list[Passage]:
    """Renvoie les passages d'un texte écrit en Markdown, dans l'ordre : un titre « ## » ouvre une section."""
    by_heading = MarkdownHeaderTextSplitter([("#", "page_title"), ("##", "section")])
    # Seul le saut de ligne sépare : une section trop longue est coupée entre deux paragraphes ou deux puces,
    # jamais au milieu d'une phrase, et un paragraphe plus long que la limite reste entier
    by_size = RecursiveCharacterTextSplitter(
        chunk_size=max_chars, chunk_overlap=0, separators=["\n"], keep_separator=False
    )
    documents = by_size.split_documents(by_heading.split_text(markdown_text))
    return [
        Passage(
            source,
            document.metadata.get("page_title", source),
            document.metadata.get("section", ""),
            _plain(document.page_content),
        )
        for document in documents
    ]


def _plain(content: str) -> str:
    # Un lien ne garde que son texte, et le gras disparaît : le modèle lit des phrases, pas une mise en forme
    lines = (line.strip() for line in content.splitlines())
    return LINK_PATTERN.sub(r"\1", "\n".join(line for line in lines if line)).replace("**", "")


# Passage et vecteur qui le situe
IndexedPassage = tuple[Passage, Sequence[float]]


def similarity(first: Sequence[float], second: Sequence[float]) -> float:
    """Renvoie le cosinus de l'angle entre deux vecteurs : 1 quand ils pointent dans la même direction."""
    norms = math.sqrt(sum(value * value for value in first)) * math.sqrt(sum(value * value for value in second))
    if not norms:
        return 0.0
    return sum(left * right for left, right in zip(first, second, strict=True)) / norms


def rank_passages(
    questions: Sequence[Sequence[float]], indexed: Sequence[IndexedPassage], count: int
) -> list[Passage]:
    """Renvoie les passages les plus proches de ces questions, à tour de rôle : le meilleur de la première,
    le meilleur de la deuxième, le suivant de la première, et ainsi de suite, sans doublon.

    Chaque question garde ainsi sa part des passages retenus, quelle que soit la longueur de son texte : les
    proximités de deux questions ne se comparent pas entre elles.
    """
    rankings = [
        sorted(indexed, key=lambda item, question=question: similarity(question, item[1]), reverse=True)
        for question in questions
    ]
    # Un dictionnaire garde l'ordre d'arrivée et écarte un passage déjà pris par une autre question
    passages = dict.fromkeys(passage for turn in zip(*rankings, strict=True) for passage, _ in turn)
    return list(passages)[:count]
