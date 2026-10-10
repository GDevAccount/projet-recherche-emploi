from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from jobgrep.data.models import CvText


class CvTextRepository:
    def __init__(self, session: Session, user_id: int):
        self.session = session
        # Chaque requête se limite à la ligne de cet utilisateur
        self.user_id = user_id

    def get_content(self) -> str | None:
        """Renvoie le texte du CV de l'utilisateur, coordonnées retirées, ou None s'il n'est pas enregistré."""
        return self.session.scalar(select(CvText.content).where(CvText.user_id == self.user_id))

    def get_updated_at(self) -> datetime | None:
        """Renvoie la date du dernier dépôt du CV de l'utilisateur, ou None s'il n'en a pas."""
        return self.session.scalar(select(CvText.updated_at).where(CvText.user_id == self.user_id))

    def save(self, content: str) -> None:
        """Enregistre le texte du CV de l'utilisateur, à la place du précédent, daté de maintenant."""
        statement = insert(CvText).values(user_id=self.user_id, content=content)
        self.session.execute(
            statement.on_conflict_do_update(
                index_elements=["user_id"],
                set_={"content": content, "updated_at": func.current_timestamp()},
            )
        )

    def delete(self) -> bool:
        """Efface le texte du CV de l'utilisateur, et renvoie faux s'il n'y en avait pas."""
        return self.session.execute(delete(CvText).where(CvText.user_id == self.user_id)).rowcount == 1
