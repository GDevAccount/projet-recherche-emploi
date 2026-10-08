import logging
import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import URL, Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def alembic_config() -> Config:
    config = Config()
    # Le « % » est un caractère réservé des fichiers de configuration
    config.set_main_option("script_location", str(MIGRATIONS_DIR).replace("%", "%%"))
    return config


class Database:
    """Base SQLite de l'application : ouvre les sessions et applique les migrations."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        # Sans pool, chaque session ouvre et ferme sa connexion : le fichier n'est jamais gardé ouvert
        self.engine = create_engine(URL.create("sqlite", database=str(self.db_path)), poolclass=NullPool)
        _use_explicit_transactions(self.engine)
        self._session_factory = sessionmaker(self.engine, expire_on_commit=False)

    @contextmanager
    def session(self) -> Iterator[Session]:
        """Ouvre une session, valide sa transaction en sortie ou l'annule en cas d'erreur, puis ferme."""
        with self._session_factory.begin() as session:
            yield session

    def migrate(self) -> None:
        """Crée la base ou l'amène à la dernière version du schéma. Sans effet si elle y est déjà."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        existed = self.db_path.is_file() and self.db_path.stat().st_size > 0

        config = alembic_config()
        head = ScriptDirectory.from_config(config).get_current_head()
        with self.engine.connect() as connection:
            current = MigrationContext.configure(connection).get_current_revision()
        if current == head:
            return

        if existed:
            self._backup(head)
        logger.info("Migration de la base %s : %s -> %s", self.db_path, current, head)
        with self.engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")

    def delete_backups(self) -> int:
        """Efface les copies faites avant les migrations, et renvoie leur nombre.

        Elles contiennent les données de tous les utilisateurs, y compris de ceux qui ont supprimé leur compte.
        """
        backups = list(self.db_path.parent.glob(f"{self.db_path.stem}.avant-migration-*.db"))
        for backup in backups:
            backup.unlink()
        if backups:
            logger.info("%d copie(s) d'avant migration effacée(s)", len(backups))
        return len(backups)

    def _backup(self, target_revision: str) -> None:
        # Une copie par migration : une montée de version ratée ne doit rien coûter à l'utilisateur
        backup_path = self.db_path.with_name(f"{self.db_path.stem}.avant-migration-{target_revision}.db")
        with closing(sqlite3.connect(self.db_path)) as source, closing(sqlite3.connect(backup_path)) as target:
            source.backup(target)
        logger.info("Base sauvegardée dans %s avant migration", backup_path)


def _use_explicit_transactions(engine: Engine) -> None:
    # Le pilote sqlite3 n'ouvre pas de transaction pour un SELECT, un CREATE ou un ALTER : une migration
    # interrompue laisserait la base à moitié modifiée. SQLAlchemy émet donc lui-même le BEGIN.
    @event.listens_for(engine, "connect")
    def disable_driver_transactions(dbapi_connection, connection_record) -> None:
        dbapi_connection.isolation_level = None

    @event.listens_for(engine, "begin")
    def begin(connection) -> None:
        connection.exec_driver_sql("BEGIN")
