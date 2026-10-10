"""Erreurs destinées à l'utilisateur : leur message, en français, est affichable tel quel.

L'interface les montre avec st.error, l'API les traduit en code HTTP (voir api/main.py).
"""


class AppError(Exception):
    pass


class InvalidInputError(AppError):
    """La demande est refusée : donnée vide, fichier illisible, condition préalable manquante."""


class NotFoundError(AppError):
    """L'élément visé n'existe pas, ou appartient à un autre utilisateur."""


class ConflictError(AppError):
    """L'élément existe déjà."""


class QuotaExceededError(AppError):
    """Le quota de recherches de l'utilisateur, ou celui des essais sans compte, est atteint."""


class BudgetReachedError(AppError):
    """Le budget du jour de l'instance est atteint : plus de recherche avant le lendemain."""


class ConfigurationError(AppError):
    """L'instance est mal réglée : seul son exploitant peut corriger."""


class AssistantUnavailableError(AppError):
    """L'assistant n'a pas pu répondre : le modèle est en panne, trop lent, ou a rendu une réponse illisible."""
