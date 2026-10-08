"""Ce que le graph attend de l'extérieur. Les tests y branchent des faux, sans réseau ni facture."""

from collections.abc import Iterator, Sequence
from typing import Protocol

from pydantic import BaseModel

from projet_recherche_emploi.agent.state import FoundPage


class JobEvaluation(BaseModel):
    is_real_offer: bool
    matches_cv: bool
    reason: str


class JobSearchEngine(Protocol):
    def search(self, query: str) -> list[dict]:
        """Renvoie les pages trouvées pour cette recherche : title, url, content, raw_content, score."""
        ...


class JobEvaluator(Protocol):
    def evaluate(self, cv: str, pages: Sequence[FoundPage]) -> Iterator[tuple[int, JobEvaluation]]:
        """Évalue chaque page au regard du CV.

        Les verdicts arrivent dans le désordre, chacun avec l'indice de sa page.
        """
        ...
