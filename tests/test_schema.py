import sqlite3
from contextlib import closing

import pytest
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext

from projet_recherche_emploi.config import DEFAULT_QUERIES, DEFAULT_USER_ID
from projet_recherche_emploi.data.database import Database
from projet_recherche_emploi.data.job_repository import JobRepository
from projet_recherche_emploi.data.models import Base
from projet_recherche_emploi.data.query_repository import QueryRepository
from projet_recherche_emploi.data.user_repository import UserRepository

TABLES = {"jobs", "rejected_jobs", "search_queries", "users", "search_runs"}

# Base telle que la créait l'application avant Alembic : chaque dépôt créait sa table à son premier usage,
# donc users et search_runs manquent tant que la connexion Google n'a pas servi
LEGACY_SCHEMA = """
    CREATE TABLE jobs (
        user_id INTEGER NOT NULL DEFAULT 1,
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
    );
    CREATE TABLE search_queries (
        id INTEGER PRIMARY KEY,
        user_id INTEGER NOT NULL DEFAULT 1,
        contract_type TEXT NOT NULL,
        query TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (user_id, query)
    );
    INSERT INTO jobs (url, title, applied, applied_at, created_at, deleted)
        VALUES ('https://a/2', 'Supprimée', 0, NULL, '2026-10-06 16:00:00', 1);
    INSERT INTO jobs (url, title, applied, applied_at, created_at, deleted)
        VALUES ('https://a/1', 'Offre', 1, '2026-10-07 08:16:21', '2026-10-06 15:01:03', 0);
    INSERT INTO jobs (user_id, url, title, created_at)
        VALUES (2, 'https://a/1', 'La même, pour un invité', '2026-10-08 09:00:00');
    INSERT INTO search_queries (contract_type, query) VALUES ('CDD', 'la seule recherche gardée');
"""


def table_names(db_path) -> set[str]:
    with closing(sqlite3.connect(db_path)) as connection:
        rows = connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        return {row[0] for row in rows}


def test_new_database_gets_every_table_and_the_owner_defaults(tmp_path):
    database = Database(tmp_path / "jobs.db")

    database.migrate()

    assert TABLES <= table_names(database.db_path)
    with database.session() as session:
        queries = QueryRepository(session, DEFAULT_USER_ID).list_queries()
        assert [(query.contract_type, query.query) for query in queries] == DEFAULT_QUERIES
        # Elles visent l'Île-de-France, comme leur texte le dit
        assert {(query.location, query.remote) for query in queries} == {("Île-de-France", False)}
        # L'identifiant du propriétaire est réservé, sans adresse
        assert [(user.id, user.email) for user in UserRepository(session).list_users()] == [(DEFAULT_USER_ID, None)]
    # Rien à sauvegarder avant de créer une base
    assert list(tmp_path.glob("*avant-migration*")) == []


def test_models_describe_the_migrated_schema(database):
    with database.engine.connect() as connection:
        differences = compare_metadata(MigrationContext.configure(connection), Base.metadata)

    # Une différence signifie qu'un modèle a changé sans sa migration
    assert differences == []


def test_migrating_twice_changes_nothing(database):
    with database.session() as session:
        QueryRepository(session, DEFAULT_USER_ID).delete_query(1)

    database.migrate()

    with database.session() as session:
        # Une recherche par défaut supprimée ne revient pas
        assert len(QueryRepository(session, DEFAULT_USER_ID).list_queries()) == len(DEFAULT_QUERIES) - 1


def test_database_from_before_alembic_keeps_its_rows(tmp_path):
    db_path = tmp_path / "jobs.db"
    with closing(sqlite3.connect(db_path)) as connection:
        connection.executescript(LEGACY_SCHEMA)
    database = Database(db_path)

    database.migrate()

    assert TABLES <= table_names(db_path)
    with database.session() as session:
        [job] = JobRepository(session, DEFAULT_USER_ID).list_jobs()
        assert (job.url, job.applied, job.deleted) == ("https://a/1", True, False)
        assert job.applied_at.isoformat() == "2026-10-07T08:16:21+00:00"
        # Les offres sont numérotées dans leur ordre d'arrivée, et l'offre supprimée reste connue
        assert job.id == 1
        assert JobRepository(session, DEFAULT_USER_ID).list_known_urls() == {"https://a/1", "https://a/2"}
        [guest_job] = JobRepository(session, 2).list_jobs()
        assert (guest_job.id, guest_job.url) == (3, "https://a/1")
        # La même URL ne s'insère toujours pas deux fois pour le même utilisateur
        assert JobRepository(session, 2).insert_jobs([{"url": "https://a/1", "title": "Doublon"}]) == 0
        # La table existait : les recherches par défaut ne sont pas ajoutées à celles de l'utilisateur
        queries = QueryRepository(session, DEFAULT_USER_ID).list_queries()
        assert [query.query for query in queries] == ["la seule recherche gardée"]
        # Avant le choix du lieu, le filtre imposait l'Île-de-France : la recherche la garde
        assert [(query.id, query.location, query.remote) for query in queries] == [(1, "Île-de-France", False)]
        assert [user.id for user in UserRepository(session).list_users()] == [DEFAULT_USER_ID]


def test_existing_database_is_copied_before_a_migration(tmp_path):
    db_path = tmp_path / "jobs.db"
    with closing(sqlite3.connect(db_path)) as connection:
        connection.executescript(LEGACY_SCHEMA)

    Database(db_path).migrate()

    [backup] = tmp_path.glob("jobs.avant-migration-*.db")
    # La copie est la base d'avant : sans les tables ajoutées par la migration
    assert table_names(backup) == {"jobs", "search_queries"}


def test_interrupted_schema_change_leaves_no_trace(database):
    # Database.migrate applique les migrations dans une transaction de ce moteur : sans le BEGIN explicite
    # de database.py, sqlite3 validerait chaque CREATE ou ALTER aussitôt, et la table resterait
    with pytest.raises(RuntimeError), database.engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE essai (id INTEGER)")
        raise RuntimeError("migration interrompue")

    assert "essai" not in table_names(database.db_path)
