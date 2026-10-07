import sqlite3
from pathlib import Path

from projet_recherche_emploi.config import DEFAULT_USER_ID


class UserRepository:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)

    def get_or_create_user_id(self, email: str) -> int:
        """Renvoie l'identifiant du compte lié à cette adresse, en le créant à la première connexion."""
        connection = sqlite3.connect(self.db_path)
        try:
            with connection:
                self._create_table(connection)
                connection.execute("INSERT OR IGNORE INTO users (email) VALUES (?)", (email,))
                return connection.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()[0]
        finally:
            connection.close()

    def list_users(self) -> list[dict]:
        """Renvoie les comptes, dans l'ordre de création."""
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                self._create_table(connection)
                return [dict(row) for row in connection.execute("SELECT * FROM users ORDER BY id")]
        finally:
            connection.close()

    def _create_table(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                email TEXT UNIQUE,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        # L'identifiant de l'utilisateur par défaut est réservé : ses données existaient avant les comptes,
        # et son adresse vient de OWNER_EMAIL. Sans cette ligne, le premier invité recevrait son identifiant.
        connection.execute("INSERT OR IGNORE INTO users (id) VALUES (?)", (DEFAULT_USER_ID,))
