from datetime import UTC, datetime

from helpers import job, rejected_job

from projet_recherche_emploi.config import DEFAULT_QUERIES
from projet_recherche_emploi.data.repositories.cv_text_repository import CvTextRepository
from projet_recherche_emploi.data.repositories.job_repository import JobRepository
from projet_recherche_emploi.data.repositories.query_repository import QueryRepository
from projet_recherche_emploi.data.repositories.rejected_job_repository import RejectedJobRepository
from projet_recherche_emploi.data.repositories.search_run_repository import SearchRunRepository

ALICE = 1
BOB = 2


def test_each_user_sees_only_their_jobs(session):
    alice, bob = JobRepository(session, ALICE), JobRepository(session, BOB)
    alice.insert_jobs([job("https://a/1"), job("https://a/2")])
    bob.insert_jobs([job("https://b/1")])

    assert {row.url for row in alice.list_jobs()} == {"https://a/1", "https://a/2"}
    assert {row.url for row in bob.list_jobs()} == {"https://b/1"}
    assert alice.list_known_urls() == {"https://a/1", "https://a/2"}
    assert bob.list_known_urls() == {"https://b/1"}


def test_same_offer_can_be_kept_by_two_users(session):
    alice, bob = JobRepository(session, ALICE), JobRepository(session, BOB)

    assert alice.insert_jobs([job("https://a/1")]) == 1
    assert bob.insert_jobs([job("https://a/1")]) == 1
    assert alice.insert_jobs([job("https://a/1")]) == 0


def test_applying_does_not_touch_another_user(session):
    alice, bob = JobRepository(session, ALICE), JobRepository(session, BOB)
    alice.insert_jobs([job("https://a/1")])
    bob.insert_jobs([job("https://a/1")])

    [alice_job], [bob_job] = alice.list_jobs(), bob.list_jobs()

    assert bob.set_applied(bob_job.id, True) is True
    # L'offre d'Alice existe, mais pas pour Bob : il ne peut ni la cocher ni la lire
    assert bob.set_applied(alice_job.id, True) is False
    assert bob.get_job(alice_job.id) is None
    # Relue dans la même session, l'offre de Bob porte déjà sa candidature
    assert bob.get_job(bob_job.id).applied is True
    session.expire_all()

    assert (alice_job.applied, alice_job.applied_at) == (False, None)
    assert bob_job.applied is True and bob_job.applied_at is not None


def test_unapplying_clears_the_application_date(session):
    jobs = JobRepository(session, BOB)
    jobs.insert_jobs([job("https://a/1")])
    [saved] = jobs.list_jobs()
    jobs.set_applied(saved.id, True)

    jobs.set_applied(saved.id, False)
    session.expire_all()

    [saved] = jobs.list_jobs()
    assert (saved.applied, saved.applied_at) == (False, None)


def test_deleting_does_not_touch_another_user(session):
    alice, bob = JobRepository(session, ALICE), JobRepository(session, BOB)
    alice.insert_jobs([job("https://a/1")])
    bob.insert_jobs([job("https://a/1")])

    [alice_job], [bob_job] = alice.list_jobs(), bob.list_jobs()

    assert bob.delete_jobs([bob_job.id, alice_job.id]) == 1
    # Une offre déjà supprimée n'est pas comptée une seconde fois, et ne se coche plus
    assert bob.delete_jobs([bob_job.id]) == 0
    assert bob.set_applied(bob_job.id, True) is False
    assert bob.get_job(bob_job.id) is None

    assert len(alice.list_jobs()) == 1
    assert bob.list_jobs() == []
    # L'offre supprimée reste connue de celui qui l'a supprimée, pour ne pas lui revenir
    assert bob.list_known_urls() == {"https://a/1"}
    assert bob.insert_jobs([job("https://a/1")]) == 0


def test_each_user_has_their_own_rejections(session):
    alice, bob = RejectedJobRepository(session, ALICE), RejectedJobRepository(session, BOB)
    alice.insert_rejected_jobs([rejected_job("https://r/1"), rejected_job("https://r/2")])
    assert bob.insert_rejected_jobs([rejected_job("https://r/1")]) == 1

    assert alice.list_known_urls() == {"https://r/1", "https://r/2"}
    assert [row.url for row in bob.list_rejected_jobs()] == ["https://r/1"]

    # Un nouveau CV chez l'un ne fait pas réévaluer les pages de l'autre
    assert bob.clear() == 1
    assert bob.list_known_urls() == set()
    assert alice.list_known_urls() == {"https://r/1", "https://r/2"}


def test_search_dependent_rejections_are_forgotten_per_user(session):
    alice, bob = RejectedJobRepository(session, ALICE), RejectedJobRepository(session, BOB)
    out_of_area = {**rejected_job("https://r/1"), "matches_cv": True, "matches_location": False}
    alice.insert_rejected_jobs([out_of_area])
    bob.insert_rejected_jobs([out_of_area, rejected_job("https://r/2")])

    assert bob.clear_search_dependent_rejections() == 1
    assert bob.list_known_urls() == {"https://r/2"}
    assert alice.list_known_urls() == {"https://r/1"}


def test_default_queries_go_to_the_first_user_only(session):
    assert QueryRepository(session, BOB).list_queries() == []

    alice_queries = QueryRepository(session, ALICE).list_queries()
    assert [(row.contract_type, row.query) for row in alice_queries] == DEFAULT_QUERIES


def test_each_user_has_their_own_queries(session):
    alice, bob = QueryRepository(session, ALICE), QueryRepository(session, BOB)
    alice_query = alice.list_queries()[0]

    # Bob peut enregistrer la même recherche qu'Alice, mais pas deux fois
    created = bob.add_query(alice_query.contract_type, alice_query.query)
    assert created.id != alice_query.id
    assert bob.add_query(alice_query.contract_type, alice_query.query) is None
    # La même phrase pour un autre lieu est une autre recherche
    assert bob.delete_query(bob.add_query(alice_query.contract_type, alice_query.query, "Lyon").id) is True
    assert len(bob.list_queries()) == 1

    # Bob ne peut pas supprimer une recherche d'Alice en devinant son identifiant
    assert bob.delete_query(alice_query.id) is False
    assert len(alice.list_queries()) == len(DEFAULT_QUERIES)

    assert bob.delete_query(created.id) is True
    assert bob.list_queries() == []
    assert len(alice.list_queries()) == len(DEFAULT_QUERIES)


def test_quota_is_per_user_and_per_day(session):
    alice, bob = SearchRunRepository(session, ALICE), SearchRunRepository(session, BOB)
    today = datetime(2000, 1, 1, tzinfo=UTC)

    assert alice.record_run(today, limit=2) is True
    assert alice.record_run(today, limit=2) is True
    assert alice.record_run(today, limit=2) is False
    assert alice.count_runs_since(today) == 2

    assert bob.count_runs_since(today) == 0
    assert bob.record_run(today, limit=2) is True

    # Les recherches d'avant minuit ne comptent plus le lendemain
    tomorrow = datetime(2999, 1, 1, tzinfo=UTC)
    assert alice.count_runs_since(tomorrow) == 0


def test_run_without_limit_is_always_recorded(session):
    owner = SearchRunRepository(session, ALICE)

    assert all(owner.record_run() for _ in range(5))
    assert owner.count_runs_since(datetime(2000, 1, 1, tzinfo=UTC)) == 5


def test_erasing_everything_does_not_touch_another_user(session):
    for user_id in (ALICE, BOB):
        JobRepository(session, user_id).insert_jobs([job("https://a/1")])
        RejectedJobRepository(session, user_id).insert_rejected_jobs([rejected_job("https://a/2")])
        QueryRepository(session, user_id).add_query("CDI", "data engineer")
        SearchRunRepository(session, user_id).record_run()
    alice_queries = len(QueryRepository(session, ALICE).list_queries())

    assert JobRepository(session, BOB).delete_all() == 1
    assert QueryRepository(session, BOB).delete_all() == 1
    assert SearchRunRepository(session, BOB).delete_all() == 1
    RejectedJobRepository(session, BOB).clear()

    since = datetime(2000, 1, 1, tzinfo=UTC)
    assert JobRepository(session, BOB).list_known_urls() == set()
    assert SearchRunRepository(session, BOB).count_runs_since(since) == 0
    assert len(JobRepository(session, ALICE).list_jobs()) == 1
    assert len(RejectedJobRepository(session, ALICE).list_rejected_jobs()) == 1
    assert len(QueryRepository(session, ALICE).list_queries()) == alice_queries
    assert SearchRunRepository(session, ALICE).count_runs_since(since) == 1


def test_each_user_has_their_own_cv_text(session):
    alice, bob = CvTextRepository(session, ALICE), CvTextRepository(session, BOB)
    alice.save("CV d'Alice")
    bob.save("CV de Bob")

    bob.save("Nouveau CV de Bob")

    assert (alice.get_content(), bob.get_content()) == ("CV d'Alice", "Nouveau CV de Bob")
    assert bob.delete() is True
    assert bob.delete() is False
    assert (alice.get_content(), bob.get_content()) == ("CV d'Alice", None)
    assert alice.get_updated_at() is not None and bob.get_updated_at() is None
