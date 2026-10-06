import sqlite3
from pathlib import Path


class JobRepository:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)

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
                    "SELECT * FROM jobs WHERE deleted = 0 ORDER BY created_at DESC"
                ).fetchall()
                return [dict(row) for row in rows]
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
                    WHERE url = :url
                    """,
                    {"url": url, "applied": int(applied)},
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
                    "UPDATE jobs SET deleted = 1 WHERE url = ? AND deleted = 0",
                    [(url,) for url in urls],
                )
                return cursor.rowcount
        finally:
            connection.close()

    def _create_table(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                url TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                content TEXT,
                score REAL,
                contract_type TEXT,
                query TEXT,
                match_reason TEXT,
                applied INTEGER NOT NULL DEFAULT 0,
                applied_at TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                deleted INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        # Migration : les bases créées avant la suppression d'offres n'ont pas la colonne deleted
        existing_columns = {row[1] for row in connection.execute("PRAGMA table_info(jobs)")}
        if "deleted" not in existing_columns:
            connection.execute("ALTER TABLE jobs ADD COLUMN deleted INTEGER NOT NULL DEFAULT 0")

    def _insert_job(self, connection: sqlite3.Connection, job: dict) -> int:
        # url est la clé primaire : une offre déjà en base est ignorée
        cursor = connection.execute(
            """
            INSERT OR IGNORE INTO jobs (url, title, content, score, contract_type, query, match_reason)
            VALUES (:url, :title, :content, :score, :contract_type, :query, :match_reason)
            """,
            job,
        )
        return cursor.rowcount
