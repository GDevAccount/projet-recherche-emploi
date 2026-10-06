import sqlite3
from pathlib import Path

from projet_recherche_emploi.config import DEFAULT_QUERIES


class QueryRepository:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)

    def list_queries(self) -> list[dict]:
        """Renvoie les recherches enregistrées, dans l'ordre de création."""
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                self._create_table(connection)
                rows = connection.execute("SELECT * FROM search_queries ORDER BY id").fetchall()
                return [dict(row) for row in rows]
        finally:
            connection.close()

    def add_query(self, contract_type: str, query: str) -> bool:
        """Enregistre une recherche, et renvoie faux si elle existe déjà."""
        connection = sqlite3.connect(self.db_path)
        try:
            with connection:
                self._create_table(connection)
                return self._insert_query(connection, contract_type, query) == 1
        finally:
            connection.close()

    def delete_query(self, query_id: int) -> bool:
        """Supprime une recherche, et renvoie faux si l'identifiant est inconnu."""
        connection = sqlite3.connect(self.db_path)
        try:
            with connection:
                self._create_table(connection)
                cursor = connection.execute("DELETE FROM search_queries WHERE id = ?", (query_id,))
                return cursor.rowcount == 1
        finally:
            connection.close()

    def _create_table(self, connection: sqlite3.Connection) -> None:
        table_exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'search_queries'"
        ).fetchone()
        if table_exists:
            return

        connection.execute(
            """
            CREATE TABLE search_queries (
                id INTEGER PRIMARY KEY,
                contract_type TEXT NOT NULL,
                query TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        # Recherches par défaut, ajoutées une seule fois : si l'utilisateur les supprime, elles ne reviennent pas
        for contract_type, query in DEFAULT_QUERIES:
            self._insert_query(connection, contract_type, query)

    def _insert_query(self, connection: sqlite3.Connection, contract_type: str, query: str) -> int:
        # query est unique : une recherche déjà enregistrée est ignorée
        cursor = connection.execute(
            "INSERT OR IGNORE INTO search_queries (contract_type, query) VALUES (?, ?)",
            (contract_type, query),
        )
        return cursor.rowcount
