from datetime import datetime

from sqlalchemy import func, or_, select, update
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from projet_recherche_emploi.config import DEFAULT_USER_ID
from projet_recherche_emploi.data.models import User


class UserRepository:
    """Seul dépôt sans utilisateur : il sert justement à trouver celui d'une adresse."""

    def __init__(self, session: Session):
        self.session = session

    def get_or_create_user_id(self, email: str) -> int:
        """Renvoie l'identifiant du compte lié à cette adresse, en le créant à la première connexion."""
        new_user = insert(User).values(email=email, last_seen_at=func.current_timestamp())
        self.session.execute(new_user.on_conflict_do_nothing())
        return self.session.scalars(select(User.id).where(User.email == email)).one()

    def list_users(self) -> list[User]:
        """Renvoie les comptes, dans l'ordre de création."""
        return list(self.session.scalars(select(User).order_by(User.id)))

    def forget_user(self, user_id: int) -> bool:
        """Détache ce compte de son adresse, et renvoie faux s'il n'en avait pas.

        La ligne reste, vide : son identifiant ne sera pas redonné, donc personne n'héritera de ce qu'une
        recherche encore en cours écrirait sous cet identifiant.
        """
        statement = update(User).where(User.id == user_id, User.email.is_not(None)).values(email=None)
        return self.session.execute(statement).rowcount == 1

    def record_activity(self, user_id: int, now: datetime, not_since: datetime) -> bool:
        """Date la dernière activité du compte, et renvoie faux si elle l'était déjà depuis « not_since ».

        Chaque requête passe par ici : la date n'est récrite que si elle est ancienne, pas à chaque appel.
        """
        stale = or_(User.last_seen_at.is_(None), User.last_seen_at < not_since)
        statement = update(User).where(User.id == user_id, stale).values(last_seen_at=now)
        return self.session.execute(statement).rowcount == 1

    def list_inactive_user_ids(self, since: datetime) -> list[int]:
        """Renvoie les comptes d'invités sans activité depuis cette date.

        Jamais le propriétaire, ni une ligne sans adresse (compte déjà supprimé), ni un compte sans date.
        """
        statement = (
            select(User.id)
            .where(User.id != DEFAULT_USER_ID, User.email.is_not(None), User.last_seen_at < since)
            .order_by(User.id)
        )
        return list(self.session.scalars(statement))
