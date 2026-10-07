import sqlite3

from projet_recherche_emploi.config import DEFAULT_USER_ID
from projet_recherche_emploi.job_repository import JobRepository
from projet_recherche_emploi.query_repository import QueryRepository
from projet_recherche_emploi.rejected_job_repository import RejectedJobRepository


def columns(db_path, table: str) -> set[str]:
    connection = sqlite3.connect(db_path)
    try:
        return {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
    finally:
        connection.close()


def test_new_database_is_created_on_first_access(tmp_path):
    db_path = tmp_path / "jobs.db"

    assert JobRepository(db_path).list_jobs() == []
    assert RejectedJobRepository(db_path).list_rejected_jobs() == []
    queries = QueryRepository(db_path).list_queries()

    assert queries and all(query["user_id"] == DEFAULT_USER_ID for query in queries)
    assert {"user_id", "url", "deleted", "applied"} <= columns(db_path, "jobs")
    assert {"user_id", "url", "reject_reason"} <= columns(db_path, "rejected_jobs")
