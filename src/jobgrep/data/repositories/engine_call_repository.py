from collections.abc import Iterable, Mapping

from sqlalchemy import delete, insert, select
from sqlalchemy.orm import Session

from jobgrep.data.models import EngineCall

INSERTED_FIELDS = (
    "query",
    "search_text",
    "international",
    "found_count",
    "unique_count",
    "new_count",
    "kept_count",
    "duration_ms",
)


class EngineCallRepository:
    def __init__(self, session: Session, user_id: int):
        self.session = session
        # Chaque requête se limite aux lignes de cet utilisateur
        self.user_id = user_id

    def insert_calls(self, search_run_id: int, calls: Iterable[Mapping]) -> int:
        """Enregistre les appels au moteur de recherche de ce lancement, et renvoie leur nombre."""
        rows = [
            {
                "user_id": self.user_id,
                "search_run_id": search_run_id,
                **{field: call.get(field) for field in INSERTED_FIELDS},
            }
            for call in calls
        ]
        if rows:
            self.session.execute(insert(EngineCall), rows)
        return len(rows)

    def list_all(self) -> list[EngineCall]:
        """Renvoie tous les appels de l'utilisateur, dans l'ordre de leur enregistrement."""
        return list(
            self.session.scalars(select(EngineCall).where(EngineCall.user_id == self.user_id).order_by(EngineCall.id))
        )

    def delete_all(self) -> int:
        """Efface tous les appels de l'utilisateur, et renvoie leur nombre."""
        return self.session.execute(delete(EngineCall).where(EngineCall.user_id == self.user_id)).rowcount
