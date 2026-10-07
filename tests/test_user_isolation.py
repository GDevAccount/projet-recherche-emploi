import pytest

from projet_recherche_emploi.config import DEFAULT_QUERIES
from projet_recherche_emploi.job_repository import JobRepository
from projet_recherche_emploi.query_repository import QueryRepository
from projet_recherche_emploi.rejected_job_repository import RejectedJobRepository

ALICE = 1
BOB = 2


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "jobs.db"


def job(url: str) -> dict:
    return {
        "url": url,
        "title": f"Offre {url}",
        "content": "c",
        "score": 1.0,
        "contract_type": "CDI",
        "query": "q",
        "match_reason": "r",
    }


def rejected_job(url: str) -> dict:
    return {
        "url": url,
        "title": f"Page {url}",
        "contract_type": "CDI",
        "query": "q",
        "is_real_offer": True,
        "matches_cv": False,
        "reject_reason": "Hors profil",
    }


def test_user_id_defaults_to_the_first_user(db_path):
    JobRepository(db_path).insert_jobs([job("https://a/1")])

    assert [row["url"] for row in JobRepository(db_path, ALICE).list_jobs()] == ["https://a/1"]
    assert JobRepository(db_path, BOB).list_jobs() == []


def test_each_user_sees_only_their_jobs(db_path):
    alice, bob = JobRepository(db_path, ALICE), JobRepository(db_path, BOB)
    alice.insert_jobs([job("https://a/1"), job("https://a/2")])
    bob.insert_jobs([job("https://b/1")])

    assert {row["url"] for row in alice.list_jobs()} == {"https://a/1", "https://a/2"}
    assert {row["url"] for row in bob.list_jobs()} == {"https://b/1"}
    assert alice.list_known_urls() == {"https://a/1", "https://a/2"}
    assert bob.list_known_urls() == {"https://b/1"}


def test_same_offer_can_be_kept_by_two_users(db_path):
    alice, bob = JobRepository(db_path, ALICE), JobRepository(db_path, BOB)

    assert alice.insert_jobs([job("https://a/1")]) == 1
    assert bob.insert_jobs([job("https://a/1")]) == 1
    assert alice.insert_jobs([job("https://a/1")]) == 0


def test_applying_does_not_touch_another_user(db_path):
    alice, bob = JobRepository(db_path, ALICE), JobRepository(db_path, BOB)
    alice.insert_jobs([job("https://a/1")])
    bob.insert_jobs([job("https://a/1")])

    assert bob.set_applied("https://a/1", True) is True
    assert bob.set_applied("https://a/inconnue", True) is False

    assert alice.list_jobs()[0]["applied"] == 0
    assert bob.list_jobs()[0]["applied"] == 1


def test_deleting_does_not_touch_another_user(db_path):
    alice, bob = JobRepository(db_path, ALICE), JobRepository(db_path, BOB)
    alice.insert_jobs([job("https://a/1")])
    bob.insert_jobs([job("https://a/1")])

    assert bob.delete_jobs(["https://a/1"]) == 1

    assert len(alice.list_jobs()) == 1
    assert bob.list_jobs() == []
    # L'offre supprimée reste connue de celui qui l'a supprimée, pour ne pas lui revenir
    assert bob.list_known_urls() == {"https://a/1"}


def test_each_user_has_their_own_rejections(db_path):
    alice, bob = RejectedJobRepository(db_path, ALICE), RejectedJobRepository(db_path, BOB)
    alice.insert_rejected_jobs([rejected_job("https://r/1"), rejected_job("https://r/2")])
    assert bob.insert_rejected_jobs([rejected_job("https://r/1")]) == 1

    assert alice.list_known_urls() == {"https://r/1", "https://r/2"}
    assert [row["url"] for row in bob.list_rejected_jobs()] == ["https://r/1"]

    # Un nouveau CV chez l'un ne fait pas réévaluer les pages de l'autre
    assert bob.clear() == 1
    assert bob.list_known_urls() == set()
    assert alice.list_known_urls() == {"https://r/1", "https://r/2"}


def test_default_queries_go_to_the_first_user_only(db_path):
    # Même si un autre utilisateur est le premier à ouvrir la base
    assert QueryRepository(db_path, BOB).list_queries() == []

    alice_queries = QueryRepository(db_path, ALICE).list_queries()
    assert [(row["contract_type"], row["query"]) for row in alice_queries] == DEFAULT_QUERIES


def test_each_user_has_their_own_queries(db_path):
    alice, bob = QueryRepository(db_path, ALICE), QueryRepository(db_path, BOB)
    alice_query = alice.list_queries()[0]

    # Bob peut enregistrer la même recherche qu'Alice, mais pas deux fois
    assert bob.add_query(alice_query["contract_type"], alice_query["query"]) is True
    assert bob.add_query(alice_query["contract_type"], alice_query["query"]) is False
    assert len(bob.list_queries()) == 1

    # Bob ne peut pas supprimer une recherche d'Alice en devinant son identifiant
    assert bob.delete_query(alice_query["id"]) is False
    assert len(alice.list_queries()) == len(DEFAULT_QUERIES)

    assert bob.delete_query(bob.list_queries()[0]["id"]) is True
    assert bob.list_queries() == []
    assert len(alice.list_queries()) == len(DEFAULT_QUERIES)
