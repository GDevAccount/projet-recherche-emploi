import sqlite3
from pathlib import Path

from projet_recherche_emploi.config import DEFAULT_USER_ID


class SearchRunRepository:
    def __init__(self, db_path: str | Path, user_id: int = DEFAULT_USER_ID):
        self.db_path = Path(db_path)
        # Chaque requête se limite aux lignes de cet utilisateur
        self.user_id = user_id

    def count_runs_since(self, since: str) -> int:
        """Renvoie le nombre de recherches lancées par l'utilisateur depuis cette date (UTC)."""
        connection = sqlite3.connect(self.db_path)
        try:
            with connection:
                self._create_table(connection)
                return self._count_runs_since(connection, since)
        finally:
            connection.close()

    def record_run(self, since: str | None = None, limit: int | None = None) -> bool:
        """Enregistre le lancement d'une recherche, et renvoie faux si le quota depuis cette date (UTC) est atteint.

        Sans limite, le lancement est toujours enregistré.
        """
        connection = sqlite3.connect(self.db_path)
        try:
            with connection:
                self._create_table(connection)
                # Le compte et l'insertion se font sous le même verrou :
                # deux clics simultanés ne peuvent pas dépasser le quota
                connection.execute("BEGIN IMMEDIATE")
                if limit is not None and self._count_runs_since(connection, since) >= limit:
                    return False
                connection.execute("INSERT INTO search_runs (user_id) VALUES (?)", (self.user_id,))
                return True
        finally:
            connection.close()

    def _create_table(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS search_runs (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

    def _count_runs_since(self, connection: sqlite3.Connection, since: str) -> int:
        return connection.execute(
            "SELECT COUNT(*) FROM search_runs WHERE user_id = ? AND created_at >= ?",
            (self.user_id, since),
        ).fetchone()[0]
