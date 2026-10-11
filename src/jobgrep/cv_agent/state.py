from collections.abc import Sequence
from typing import TypedDict

from jobgrep.cv_agent.ports import Extraction, QueriesOutcome


class CvDepositState(TypedDict, total=False):
    user_id: int
    # Le PDF déposé : lu en mémoire, jamais enregistré
    data: bytes
    # Noms connus de l'utilisateur, à retirer du texte avec ses coordonnées
    names: list[str]
    # Vrai si les postes recherchés doivent être tirés du CV ; c'est le service qui le décide, avant le graph
    extract: bool
    # Texte du PDF, puis le même sans coordonnées : seul le second est enregistré et envoyé au modèle
    raw_text: str
    text: str
    # Ce que le modèle a tiré du CV ; absent s'il n'a pas été appelé ou n'a pas répondu
    extraction: Extraction
    # Type de l'erreur qui a empêché l'extraction, jamais son message
    error_type: str
    # Ce qu'il est advenu des postes recherchés, et ceux qui ont été créés
    outcome: QueriesOutcome
    queries: Sequence
