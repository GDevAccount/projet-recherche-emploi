import sqlite3

import pytest

from projet_recherche_emploi import migration
from projet_recherche_emploi.job_repository import JobRepository
from projet_recherche_emploi.query_repository import QueryRepository
from projet_recherche_emploi.rejected_job_repository import RejectedJobRepository

# Schéma d'avant les comptes, tel qu'il existe sur les bases déjà déployées
OLD_SCHEMA = """
    CREATE TABLE jobs (
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
    );
    CREATE TABLE rejected_jobs (
        url TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        contract_type TEXT,
        query TEXT,
        is_real_offer INTEGER NOT NULL,
        matches_cv INTEGER NOT NULL,
        reject_reason TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE search_queries (
        id INTEGER PRIMARY KEY,
        contract_type TEXT NOT NULL,
        query TEXT NOT NULL UNIQUE,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    INSERT INTO jobs (url, title, applied, applied_at, created_at, deleted) VALUES
        ('https://a/1', 'Offre postulée', 1, '2026-09-02 08:00:00', '2026-09-01 10:00:00', 0),
        ('https://a/2', 'Offre supprimée', 0, NULL, '2026-09-03 10:00:00', 1);
    INSERT INTO rejected_jobs (url, title, is_real_offer, matches_cv, reject_reason, created_at) VALUES
        ('https://r/1', 'Liste', 0, 0, 'Liste d''offres', '2026-09-04 10:00:00');
    INSERT INTO search_queries (id, contract_type, query, created_at) VALUES
        (3, 'CDI', 'data engineer', '2026-08-01 10:00:00'),
        (7, 'freelance', 'mission IA', '2026-08-02 10:00:00');
"""


@pytest.fixture
def old_db(tmp_path):
    db_path = tmp_path / "jobs.db"
    connection = sqlite3.connect(db_path)
    connection.executescript(OLD_SCHEMA)
    connection.close()
    return db_path


def read(db_path, sql):
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        return [dict(row) for row in connection.execute(sql)]
    finally:
        connection.close()


def test_old_rows_are_kept_and_belong_to_default_user(old_db):
    before = {
        table: read(old_db, f"SELECT * FROM {table} ORDER BY 1")
        for table in ("jobs", "rejected_jobs", "search_queries")
    }

    JobRepository(old_db).list_jobs()
    RejectedJobRepository(old_db).list_rejected_jobs()
    QueryRepository(old_db).list_queries()

    for table, old_rows in before.items():
        new_rows = read(old_db, f"SELECT * FROM {table} ORDER BY {'id' if table == 'search_queries' else 'url'}")
        assert [row.pop("user_id") for row in new_rows] == [migration.DEFAULT_USER_ID] * len(old_rows)
        assert new_rows == old_rows
    assert read(old_db, "SELECT name FROM sqlite_master WHERE name LIKE '%_old'") == []


def test_app_behaves_the_same_after_migration(old_db):
    jobs = JobRepository(old_db)
    assert [job["url"] for job in jobs.list_jobs()] == ["https://a/1"]
    assert jobs.list_known_urls() == {"https://a/1", "https://a/2"}
    # Une offre supprimée ne revient pas, une offre déjà en base n'est pas réinsérée
    known_jobs = [
        {"url": url, "title": "t", "content": "c", "score": 1.0, "contract_type": "CDI", "query": "q", "match_reason": "r"}
        for url in ("https://a/1", "https://a/2")
    ]
    assert jobs.insert_jobs(known_jobs) == 0
    assert jobs.set_applied("https://a/1", False) is True

    queries = QueryRepository(old_db)
    assert [query["id"] for query in queries.list_queries()] == [3, 7]
    assert queries.add_query("CDI", "data engineer") is False
    assert queries.add_query("CDI", "nouvelle recherche") is True

    assert RejectedJobRepository(old_db).list_known_urls() == {"https://r/1"}


def test_migration_runs_only_once(old_db):
    JobRepository(old_db).list_jobs()
    # Une ligne d'un autre utilisateur ne doit pas être ramenée à l'utilisateur par défaut par un second passage
    connection = sqlite3.connect(old_db)
    with connection:
        connection.execute("INSERT INTO jobs (user_id, url, title) VALUES (2, 'https://a/1', 'Même offre')")
    connection.close()

    JobRepository(old_db).list_jobs()

    assert read(old_db, "SELECT user_id FROM jobs WHERE url = 'https://a/1' ORDER BY user_id") == [
        {"user_id": 1},
        {"user_id": 2},
    ]


def test_failed_migration_leaves_the_table_untouched(old_db):
    before = read(old_db, "SELECT * FROM jobs ORDER BY url")
    broken_statement = "CREATE TABLE jobs (user_id INTEGER NOT NULL DEFAULT 1, url TEXT NOT NULL)"

    connection = sqlite3.connect(old_db)
    with pytest.raises(sqlite3.Error):
        with connection:
            migration.add_user_id(connection, "jobs", broken_statement)
    connection.close()

    assert read(old_db, "SELECT * FROM jobs ORDER BY url") == before
    assert read(old_db, "SELECT name FROM sqlite_master WHERE name = 'jobs_old'") == []


def test_new_database_gets_the_new_schema(tmp_path):
    db_path = tmp_path / "jobs.db"

    assert JobRepository(db_path).list_jobs() == []
    assert RejectedJobRepository(db_path).list_rejected_jobs() == []
    queries = QueryRepository(db_path).list_queries()

    assert queries and all(query["user_id"] == migration.DEFAULT_USER_ID for query in queries)
    for table in ("jobs", "rejected_jobs"):
        assert "user_id" in {row["name"] for row in read(db_path, f"PRAGMA table_info({table})")}
