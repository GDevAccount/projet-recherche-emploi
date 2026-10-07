import sqlite3
from pathlib import Path

from projet_recherche_emploi.config import DEFAULT_USER_ID

# La clé est le couple utilisateur + URL : la même offre peut être retenue pour plusieurs utilisateurs
CREATE_JOBS_TABLE = f"""
    CREATE TABLE IF NOT EXISTS jobs (
        user_id INTEGER NOT NULL DEFAULT {DEFAULT_USER_ID},
        url TEXT NOT NULL,
        title TEXT NOT NULL,
        content TEXT,
        score REAL,
        contract_type TEXT,
        query TEXT,
        match_reason TEXT,
        applied INTEGER NOT NULL DEFAULT 0,
        applied_at TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        deleted INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (user_id, url)
    )
"""


class JobRepository:
    def __init__(self, db_path: str | Path, user_id: int = DEFAULT_USER_ID):
        self.db_path = Path(db_path)
        # Chaque requête se limite aux lignes de cet utilisateur
        self.user_id = user_id

    def insert_jobs(self, jobs: list[dict]) -> int:
        """Insère les offres et renvoie le nombre réellement ajouté (hors doublons d'URL)."""
        connection = sqlite3.connect(self.db_path)
        try:
            # "with connection" valide la transaction, ou l'annule en cas d'erreur
            with connection:
                self._create_table(connection)
                return sum(self._insert_job(connection, job) for job in jobs)
        finally:
            connection.close()

    def list_jobs(self) -> list[dict]:
        """Renvoie toutes les offres, les plus récentes en premier."""
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                self._create_table(connection)
                rows = connection.execute(
                    "SELECT * FROM jobs WHERE user_id = ? AND deleted = 0 ORDER BY created_at DESC",
                    (self.user_id,),
                ).fetchall()
                return [dict(row) for row in rows]
        finally:
            connection.close()

    def list_known_urls(self) -> set[str]:
        """Renvoie les URL de toutes les offres en base, y compris celles supprimées."""
        connection = sqlite3.connect(self.db_path)
        try:
            with connection:
                self._create_table(connection)
                rows = connection.execute("SELECT url FROM jobs WHERE user_id = ?", (self.user_id,))
                return {row[0] for row in rows}
        finally:
            connection.close()

    def set_applied(self, url: str, applied: bool) -> bool:
        """Marque l'offre comme postulée ou non, et renvoie faux si l'URL est inconnue."""
        connection = sqlite3.connect(self.db_path)
        try:
            with connection:
                self._create_table(connection)
                # applied_at est daté quand on postule, et vidé quand on décoche
                cursor = connection.execute(
                    """
                    UPDATE jobs
                    SET applied = :applied,
                        applied_at = CASE WHEN :applied THEN CURRENT_TIMESTAMP END
                    WHERE user_id = :user_id AND url = :url
                    """,
                    {"user_id": self.user_id, "url": url, "applied": int(applied)},
                )
                return cursor.rowcount == 1
        finally:
            connection.close()

    def delete_jobs(self, urls: list[str]) -> int:
        """Supprime les offres de la liste, et renvoie le nombre réellement supprimé."""
        connection = sqlite3.connect(self.db_path)
        try:
            with connection:
                self._create_table(connection)
                # La ligne est conservée : son URL empêche l'offre de revenir à la recherche suivante
                cursor = connection.executemany(
                    "UPDATE jobs SET deleted = 1 WHERE user_id = ? AND url = ? AND deleted = 0",
                    [(self.user_id, url) for url in urls],
                )
                return cursor.rowcount
        finally:
            connection.close()

    def _create_table(self, connection: sqlite3.Connection) -> None:
        connection.execute(CREATE_JOBS_TABLE)

    def _insert_job(self, connection: sqlite3.Connection, job: dict) -> int:
        # Utilisateur + URL est la clé primaire : une offre déjà en base est ignorée
        cursor = connection.execute(
            """
            INSERT OR IGNORE INTO jobs (user_id, url, title, content, score, contract_type, query, match_reason)
            VALUES (:user_id, :url, :title, :content, :score, :contract_type, :query, :match_reason)
            """,
            {**job, "user_id": self.user_id},
        )
        return cursor.rowcount
