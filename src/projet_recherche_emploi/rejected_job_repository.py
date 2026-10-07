import sqlite3
from pathlib import Path

from projet_recherche_emploi.migration import DEFAULT_USER_ID, add_user_id

# La clé est le couple utilisateur + URL : un rejet dépend du CV, donc de l'utilisateur
CREATE_REJECTED_JOBS_TABLE = f"""
    CREATE TABLE IF NOT EXISTS rejected_jobs (
        user_id INTEGER NOT NULL DEFAULT {DEFAULT_USER_ID},
        url TEXT NOT NULL,
        title TEXT NOT NULL,
        contract_type TEXT,
        query TEXT,
        is_real_offer INTEGER NOT NULL,
        matches_cv INTEGER NOT NULL,
        reject_reason TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (user_id, url)
    )
"""


class RejectedJobRepository:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)

    def insert_rejected_jobs(self, jobs: list[dict]) -> int:
        """Enregistre les pages rejetées et renvoie le nombre réellement ajouté (hors doublons d'URL)."""
        connection = sqlite3.connect(self.db_path)
        try:
            with connection:
                self._create_table(connection)
                return sum(self._insert_rejected_job(connection, job) for job in jobs)
        finally:
            connection.close()

    def list_rejected_jobs(self) -> list[dict]:
        """Renvoie toutes les pages rejetées, les plus récentes en premier."""
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                self._create_table(connection)
                rows = connection.execute("SELECT * FROM rejected_jobs ORDER BY created_at DESC").fetchall()
                return [dict(row) for row in rows]
        finally:
            connection.close()

    def list_known_urls(self) -> set[str]:
        """Renvoie les URL de toutes les pages déjà rejetées."""
        connection = sqlite3.connect(self.db_path)
        try:
            with connection:
                self._create_table(connection)
                return {row[0] for row in connection.execute("SELECT url FROM rejected_jobs")}
        finally:
            connection.close()

    def clear(self) -> int:
        """Oublie tous les rejets, et renvoie le nombre de pages qui seront réévaluées."""
        connection = sqlite3.connect(self.db_path)
        try:
            with connection:
                self._create_table(connection)
                return connection.execute("DELETE FROM rejected_jobs").rowcount
        finally:
            connection.close()

    def _create_table(self, connection: sqlite3.Connection) -> None:
        connection.execute(CREATE_REJECTED_JOBS_TABLE)
        # Migration : les bases créées avant les comptes n'ont pas la colonne user_id
        add_user_id(connection, "rejected_jobs", CREATE_REJECTED_JOBS_TABLE)

    def _insert_rejected_job(self, connection: sqlite3.Connection, job: dict) -> int:
        # Utilisateur + URL est la clé primaire : une page déjà rejetée est ignorée
        cursor = connection.execute(
            """
            INSERT OR IGNORE INTO rejected_jobs (url, title, contract_type, query, is_real_offer, matches_cv, reject_reason)
            VALUES (:url, :title, :contract_type, :query, :is_real_offer, :matches_cv, :reject_reason)
            """,
            job,
        )
        return cursor.rowcount
