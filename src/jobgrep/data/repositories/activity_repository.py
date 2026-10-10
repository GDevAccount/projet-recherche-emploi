from sqlalchemy import delete, select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from jobgrep.data.models import ActivityDay


class ActivityRepository:
    def __init__(self, session: Session, user_id: int):
        self.session = session
        # Chaque requête se limite aux lignes de cet utilisateur
        self.user_id = user_id

    def record_day(self, day: str) -> bool:
        """Note que l'utilisateur est venu ce jour-là (« AAAA-MM-JJ »), et renvoie faux si c'était déjà noté."""
        statement = insert(ActivityDay).values(user_id=self.user_id, day=day).on_conflict_do_nothing()
        return self.session.execute(statement).rowcount == 1

    def has_day(self, day: str) -> bool:
        """Dit si la venue de l'utilisateur ce jour-là est déjà notée."""
        statement = select(ActivityDay.id).where(ActivityDay.user_id == self.user_id, ActivityDay.day == day)
        return self.session.scalar(statement) is not None

    def list_days(self) -> list[str]:
        """Renvoie les jours où l'utilisateur est venu, le plus ancien en premier."""
        statement = select(ActivityDay.day).where(ActivityDay.user_id == self.user_id).order_by(ActivityDay.day)
        return list(self.session.scalars(statement))

    def delete_all(self) -> int:
        """Efface les jours d'activité de l'utilisateur, et renvoie leur nombre."""
        return self.session.execute(delete(ActivityDay).where(ActivityDay.user_id == self.user_id)).rowcount
