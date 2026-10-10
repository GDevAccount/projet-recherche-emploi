from collections.abc import Mapping
from datetime import datetime

from sqlalchemy import Row, delete, distinct, func, insert, select, update
from sqlalchemy.orm import Session

from jobgrep.data.models import AssistantMessage

INSERTED_FIELDS = (
    "question",
    "answer",
    "sources",
    "retrieved",
    "consulted",
    "outcome",
    "starts_conversation",
    "model",
    "prompt_version",
    "input_tokens",
    "output_tokens",
    "cache_read_tokens",
    "cache_write_tokens",
    "embedding_model",
    "embedding_tokens",
    "duration_ms",
    "created_at",
)


class AssistantMessageRepository:
    def __init__(self, session: Session, user_id: int):
        self.session = session
        # Chaque requête se limite aux lignes de cet utilisateur
        self.user_id = user_id

    def insert_message(self, message: Mapping) -> int:
        """Enregistre une question et sa réponse, et renvoie l'identifiant de la ligne."""
        # Un champ absent garde la valeur que la base lui donne
        values = {field: message[field] for field in INSERTED_FIELDS if field in message}
        result = self.session.execute(insert(AssistantMessage).values(user_id=self.user_id, **values))
        return result.inserted_primary_key[0]

    def count_since(self, since: datetime) -> int:
        """Renvoie le nombre de questions posées par l'utilisateur depuis cette date."""
        statement = select(func.count()).where(
            AssistantMessage.user_id == self.user_id, AssistantMessage.created_at >= since
        )
        return self.session.scalar(statement)

    def count_consulting_since(self, since: datetime) -> int:
        """Renvoie le nombre de questions de l'utilisateur qui ont consulté son compte depuis cette date."""
        statement = select(func.count()).where(
            AssistantMessage.user_id == self.user_id,
            AssistantMessage.created_at >= since,
            AssistantMessage.consulted.is_not(None),
        )
        return self.session.scalar(statement)

    def list_recent(self, limit: int, since: datetime | None = None) -> list[AssistantMessage]:
        """Renvoie les dernières questions de l'utilisateur encore lisibles, la plus ancienne en premier."""
        statement = (
            select(AssistantMessage)
            .where(AssistantMessage.user_id == self.user_id, AssistantMessage.question.is_not(None))
            .order_by(AssistantMessage.id.desc())
            .limit(limit)
        )
        if since is not None:
            statement = statement.where(AssistantMessage.created_at >= since)
        return list(self.session.scalars(statement))[::-1]

    def set_feedback(self, message_id: int, feedback: str | None) -> bool:
        """Note une réponse reçue par l'utilisateur, ou retire sa note, et renvoie faux si elle n'est pas à lui."""
        statement = (
            update(AssistantMessage)
            .where(AssistantMessage.user_id == self.user_id, AssistantMessage.id == message_id)
            .values(feedback=feedback)
        )
        return self.session.execute(statement).rowcount == 1

    def delete_all(self) -> int:
        """Efface toutes les questions de l'utilisateur, et renvoie leur nombre."""
        return self.session.execute(delete(AssistantMessage).where(AssistantMessage.user_id == self.user_id)).rowcount


class AssistantJournalRepository:
    """Questions posées à l'assistant par tous les comptes, pour les administrateurs : sans utilisateur.

    Il rend le texte des questions et des réponses, jamais le compte qui les a posées : c'est ce qui permet
    de les lire. Ne rien y ajouter qui relie une question à un compte.
    """

    def __init__(self, session: Session):
        self.session = session

    def forget_texts_before(self, limit: datetime) -> int:
        """Efface le texte des questions antérieures à cette date, pas leurs compteurs, et renvoie leur nombre."""
        statement = (
            update(AssistantMessage)
            .where(AssistantMessage.created_at < limit, AssistantMessage.question.is_not(None))
            .values(question=None, answer=None, sources=None, retrieved=None)
        )
        return self.session.execute(statement).rowcount

    def list_recent(self, limit: int, since: datetime | None = None) -> list[Row]:
        """Renvoie les dernières questions encore lisibles, la plus récente en premier, sans leur compte."""
        statement = (
            select(
                AssistantMessage.created_at,
                AssistantMessage.question,
                AssistantMessage.answer,
                AssistantMessage.sources,
                AssistantMessage.retrieved,
                AssistantMessage.consulted,
                AssistantMessage.outcome,
                AssistantMessage.feedback,
            )
            .where(AssistantMessage.question.is_not(None))
            .order_by(AssistantMessage.id.desc())
            .limit(limit)
        )
        if since is not None:
            statement = statement.where(AssistantMessage.created_at >= since)
        return list(self.session.execute(statement))

    def summarize(self, since: datetime | None = None) -> list[Row]:
        """Renvoie le nombre de questions par issue."""
        statement = select(AssistantMessage.outcome, func.count().label("count")).group_by(AssistantMessage.outcome)
        if since is not None:
            statement = statement.where(AssistantMessage.created_at >= since)
        return list(self.session.execute(statement))

    def count_consulting(self, since: datetime | None = None) -> int:
        """Renvoie le nombre de questions qui ont consulté le compte de leur auteur."""
        statement = select(func.count()).where(AssistantMessage.consulted.is_not(None))
        if since is not None:
            statement = statement.where(AssistantMessage.created_at >= since)
        return self.session.scalar(statement)

    def count_feedback(self, since: datetime | None = None) -> list[Row]:
        """Renvoie le nombre de réponses par note donnée ; celles qui n'en ont pas n'y sont pas."""
        statement = (
            select(AssistantMessage.feedback, func.count().label("count"))
            .where(AssistantMessage.feedback.is_not(None))
            .group_by(AssistantMessage.feedback)
        )
        if since is not None:
            statement = statement.where(AssistantMessage.created_at >= since)
        return list(self.session.execute(statement))

    def count_accounts(self, since: datetime | None = None) -> int:
        """Renvoie le nombre de comptes qui ont posé au moins une question."""
        statement = select(func.count(distinct(AssistantMessage.user_id)))
        if since is not None:
            statement = statement.where(AssistantMessage.created_at >= since)
        return self.session.scalar(statement)
