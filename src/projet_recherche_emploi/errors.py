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
    """Le quota journalier de recherches de l'utilisateur est atteint."""


class ConfigurationError(AppError):
    """L'instance est mal réglée : seul son exploitant peut corriger."""
