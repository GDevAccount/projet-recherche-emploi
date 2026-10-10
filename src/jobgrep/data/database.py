import logging
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import closing, contextmanager
from datetime import UTC, datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import URL, Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from jobgrep.config import DEFAULT_USER_ID
from jobgrep.data.models import SQLITE_TIMESTAMP_FORMAT

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).parent / "migrations"
# Tables de données qui existaient avant la colonne user_id : une copie ancienne peut les contenir sans elle
PRE_ACCOUNT_TABLES = {"jobs", "rejected_jobs", "search_queries"}


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

    def purge_user_from_backups(self, user_id: int) -> int:
        """Retire les données de cet utilisateur des copies faites avant les migrations, et renvoie leur nombre.

        Les copies restent : elles servent à revenir en arrière après une migration ratée, pour tous les autres.
        """
        return self._clean_backups(lambda backup: _purge_user(backup, user_id))

    def purge_expired_from_backups(
        self, texts_before: datetime, errors_before: datetime, trial_starts_before: datetime
    ) -> int:
        """Retire de ces copies ce dont la durée de conservation est passée, et renvoie leur nombre.

        Ce que la base efface à date fixe (texte des questions à l'assistant, erreurs, ouvertures d'essais)
        ne doit pas survivre dans une copie.
        """
        return self._clean_backups(
            lambda backup: _purge_expired(backup, texts_before, errors_before, trial_starts_before)
        )

    def _clean_backups(self, clean: Callable[[Path], None]) -> int:
        backups = list(self.db_path.parent.glob(f"{self.db_path.stem}.avant-migration-*.db"))
        for backup in backups:
            try:
                clean(backup)
            except sqlite3.Error:
                # Une copie illisible ne peut pas être nettoyée : on ne garde pas des données qu'on a promis d'effacer
                logger.exception("Copie %s illisible : effacée faute de pouvoir la nettoyer", backup)
                backup.unlink()
        return len(backups)

    def _backup(self, target_revision: str) -> None:
        # Une copie par migration : une montée de version ratée ne doit rien coûter à l'utilisateur
        backup_path = self.db_path.with_name(f"{self.db_path.stem}.avant-migration-{target_revision}.db")
        with closing(sqlite3.connect(self.db_path)) as source, closing(sqlite3.connect(backup_path)) as target:
            source.backup(target)
        logger.info("Base sauvegardée dans %s avant migration", backup_path)


def _purge_user(backup: Path, user_id: int) -> None:
    """Retire d'une copie tout ce qui appartient à cet utilisateur, quel que soit le schéma qu'elle avait alors."""
    with closing(sqlite3.connect(backup)) as connection:
        tables = [name for (name,) in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")]
        for table in tables:
            # Les noms viennent de la copie elle-même, pas d'une saisie
            columns = {column[1] for column in connection.execute(f'PRAGMA table_info("{table}")')}
            if "user_id" in columns:
                connection.execute(f'DELETE FROM "{table}" WHERE user_id = ?', (user_id,))
            elif table == "users":
                # Comme dans la base : la ligne reste, sans adresse ni clé d'essai
                connection.execute("UPDATE users SET email = NULL WHERE id = ?", (user_id,))
                if "trial_key" in columns:
                    connection.execute("UPDATE users SET trial_key = NULL WHERE id = ?", (user_id,))
            elif table in PRE_ACCOUNT_TABLES and user_id == DEFAULT_USER_ID:
                # Une table d'avant les comptes ne contient que les données du propriétaire
                connection.execute(f'DELETE FROM "{table}"')
        connection.commit()
        # Sans cela, les lignes effacées restent lisibles dans les pages libres du fichier
        connection.execute("VACUUM")


# Colonnes de assistant_messages qui portent le texte d'un échange : vidées, la ligne garde ses compteurs
ASSISTANT_TEXT_COLUMNS = ("question", "answer", "sources", "retrieved")
ERROR_TABLES = ("server_errors", "client_errors")


def _purge_expired(
    backup: Path, texts_before: datetime, errors_before: datetime, trial_starts_before: datetime
) -> None:
    """Retire d'une copie ce que la base n'a plus le droit de garder, quel que soit le schéma qu'elle avait alors."""
    with closing(sqlite3.connect(backup)) as connection:
        tables = {name for (name,) in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        changed = 0
        if "assistant_messages" in tables:
            columns = {column[1] for column in connection.execute('PRAGMA table_info("assistant_messages")')}
            emptied = ", ".join(f"{column} = NULL" for column in ASSISTANT_TEXT_COLUMNS if column in columns)
            changed += connection.execute(
                f"UPDATE assistant_messages SET {emptied} WHERE created_at < ? AND question IS NOT NULL",
                (_timestamp(texts_before),),
            ).rowcount
        limits = dict.fromkeys(ERROR_TABLES, errors_before) | {"trial_starts": trial_starts_before}
        for table, limit in limits.items():
            if table in tables:
                changed += connection.execute(
                    f'DELETE FROM "{table}" WHERE created_at < ?', (_timestamp(limit),)
                ).rowcount
        connection.commit()
        if changed:
            # Sans cela, les lignes effacées restent lisibles dans les pages libres du fichier. Seulement
            # quand il y a eu quelque chose à retirer : ce passage a lieu chaque jour
            connection.execute("VACUUM")


def _timestamp(moment: datetime) -> str:
    # Les dates sont du texte UTC : elles se comparent comme du texte, au même format
    return moment.astimezone(UTC).strftime(SQLITE_TIMESTAMP_FORMAT)


def _use_explicit_transactions(engine: Engine) -> None:
    # Le pilote sqlite3 n'ouvre pas de transaction pour un SELECT, un CREATE ou un ALTER : une migration
    # interrompue laisserait la base à moitié modifiée. SQLAlchemy émet donc lui-même le BEGIN.
    @event.listens_for(engine, "connect")
    def disable_driver_transactions(dbapi_connection, connection_record) -> None:
        dbapi_connection.isolation_level = None

    @event.listens_for(engine, "begin")
    def begin(connection) -> None:
        connection.exec_driver_sql("BEGIN")
