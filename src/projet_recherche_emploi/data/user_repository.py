from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from projet_recherche_emploi.data.models import User


class UserRepository:
    """Seul dépôt sans utilisateur : il sert justement à trouver celui d'une adresse."""

    def __init__(self, session: Session):
        self.session = session

    def get_or_create_user_id(self, email: str) -> int:
        """Renvoie l'identifiant du compte lié à cette adresse, en le créant à la première connexion."""
        self.session.execute(insert(User).values(email=email).on_conflict_do_nothing())
        return self.session.scalars(select(User.id).where(User.email == email)).one()

    def list_users(self) -> list[User]:
        """Renvoie les comptes, dans l'ordre de création."""
        return list(self.session.scalars(select(User).order_by(User.id)))
