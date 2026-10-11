from collections.abc import Mapping
from datetime import datetime

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.orm import Session

from jobgrep.data.models import CvExtraction

INSERTED_FIELDS = (
    "model",
    "prompt_version",
    "input_tokens",
    "output_tokens",
    "cache_read_tokens",
    "cache_write_tokens",
    "duration_ms",
    "created_at",
)


class CvExtractionRepository:
    def __init__(self, session: Session, user_id: int):
        self.session = session
        # Chaque requête se limite aux lignes de cet utilisateur
        self.user_id = user_id

    def insert_extraction(self, extraction: Mapping) -> int:
        """Enregistre une lecture de CV par le modèle, et renvoie l'identifiant de la ligne."""
        values = {field: extraction[field] for field in INSERTED_FIELDS if field in extraction}
        result = self.session.execute(insert(CvExtraction).values(user_id=self.user_id, **values))
        return result.inserted_primary_key[0]

    def set_queries_count(self, extraction_id: int, count: int) -> bool:
        """Note le nombre de postes créés par une lecture de l'utilisateur, et renvoie faux si elle n'est pas à lui."""
        statement = (
            update(CvExtraction)
            .where(CvExtraction.user_id == self.user_id, CvExtraction.id == extraction_id)
            .values(queries_count=count)
        )
        return self.session.execute(statement).rowcount == 1

    def count_since(self, since: datetime) -> int:
        """Renvoie le nombre de lectures de CV faites pour l'utilisateur depuis cette date."""
        statement = select(func.count()).where(CvExtraction.user_id == self.user_id, CvExtraction.created_at >= since)
        return self.session.scalar(statement)

    def delete_all(self) -> int:
        """Efface toutes les lectures de CV de l'utilisateur, et renvoie leur nombre."""
        return self.session.execute(delete(CvExtraction).where(CvExtraction.user_id == self.user_id)).rowcount
