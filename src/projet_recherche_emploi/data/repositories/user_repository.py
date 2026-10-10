from datetime import datetime

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from projet_recherche_emploi.config import DEFAULT_USER_ID
from projet_recherche_emploi.data.models import TrialStart, User


class UserRepository:
    """Dépôt sans utilisateur : il sert justement à trouver celui d'une adresse, ou d'une clé d'essai.

    Il sert aussi trial_starts, le compte des essais ouverts, qui n'appartient à aucun compte.
    """

    def __init__(self, session: Session):
        self.session = session

    def get_or_create_user_id(self, email: str) -> int:
        """Renvoie l'identifiant du compte lié à cette adresse, en le créant à la première connexion."""
        new_user = insert(User).values(email=email, last_seen_at=func.current_timestamp())
        self.session.execute(new_user.on_conflict_do_nothing())
        return self.session.scalars(select(User.id).where(User.email == email)).one()

    def create_trial_user(self, trial_key: str) -> int:
        """Crée un compte d'essai reconnu par cette clé, et renvoie son identifiant."""
        self.session.execute(insert(User).values(trial_key=trial_key, last_seen_at=func.current_timestamp()))
        return self.session.scalars(select(User.id).where(User.trial_key == trial_key)).one()

    def get_trial_user_id(self, trial_key: str) -> int | None:
        """Renvoie le compte d'essai de cette clé, ou None s'il n'existe pas ou a été supprimé."""
        return self.session.scalar(select(User.id).where(User.trial_key == trial_key))

    def is_trial(self, user_id: int) -> bool:
        """Dit si ce compte est un compte d'essai, ouvert sans connexion."""
        statement = select(User.id).where(User.id == user_id, User.trial_key.is_not(None))
        return self.session.scalar(statement) is not None

    def list_users(self) -> list[User]:
        """Renvoie les comptes, dans l'ordre de création."""
        return list(self.session.scalars(select(User).order_by(User.id)))

    def forget_user(self, user_id: int) -> bool:
        """Détache ce compte de son adresse ou de sa clé d'essai, et renvoie faux s'il n'en avait pas.

        La ligne reste, vide : son identifiant ne sera pas redonné, donc personne n'héritera de ce qu'une
        recherche encore en cours écrirait sous cet identifiant.
        """
        identified = or_(User.email.is_not(None), User.trial_key.is_not(None))
        statement = update(User).where(User.id == user_id, identified).values(email=None, trial_key=None)
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

    def list_expired_trial_user_ids(self, created_before: datetime) -> list[int]:
        """Renvoie les comptes d'essai ouverts avant cette date : leur cookie a expiré, personne n'y reviendra."""
        statement = (
            select(User.id).where(User.trial_key.is_not(None), User.created_at < created_before).order_by(User.id)
        )
        return list(self.session.scalars(statement))

    def record_trial_start(self, ip_hash: str, now: datetime) -> None:
        """Note l'ouverture d'un compte d'essai depuis cette adresse, réduite à son empreinte."""
        self.session.add(TrialStart(ip_hash=ip_hash, created_at=now))

    def count_trial_starts(self, since: datetime, ip_hash: str | None = None) -> int:
        """Renvoie le nombre de comptes d'essai ouverts depuis cette date : par cette adresse, ou par toutes."""
        statement = select(func.count()).select_from(TrialStart).where(TrialStart.created_at >= since)
        if ip_hash is not None:
            statement = statement.where(TrialStart.ip_hash == ip_hash)
        return self.session.scalar(statement)

    def forget_trial_starts(self, before: datetime) -> int:
        """Efface les ouvertures d'essai antérieures à cette date, et renvoie leur nombre."""
        return self.session.execute(delete(TrialStart).where(TrialStart.created_at < before)).rowcount
