import pytest
from helpers import blank_pdf, job, rejected_job

from projet_recherche_emploi.config import DEFAULT_QUERIES, DEFAULT_USER_ID, MAX_SEARCHES_PER_DAY
from projet_recherche_emploi.data.job_repository import JobRepository
from projet_recherche_emploi.data.rejected_job_repository import RejectedJobRepository
from projet_recherche_emploi.data.user_repository import UserRepository
from projet_recherche_emploi.errors import ConflictError, InvalidInputError, NotFoundError, QuotaExceededError
from projet_recherche_emploi.schemas import SearchProgress, SearchSummary
from projet_recherche_emploi.services import cv_service
from projet_recherche_emploi.services.search_service import SearchService

BOB = 2
CAROL = 3


class FakeGraph:
    """Rejoue une recherche sans appeler Tavily ni OpenAI, et retient les états reçus."""

    def __init__(self):
        self.inputs = []

    def stream(self, state, stream_mode):
        self.inputs.append(state)
        yield "custom", {"message": "Recherche 1/1", "done": 0, "total": 1}
        yield "values", {"jobs": []}
        yield "custom", {"message": "1 page(s) nouvelle(s) sur 1 trouvée(s)"}
        yield "values", {"jobs": [{"url": "https://x/1"}], "new_jobs": [{"url": "https://x/1"}], "inserted_count": 1}


class BrokenGraph:
    def stream(self, state, stream_mode):
        raise RuntimeError("Tavily search failed")


@pytest.fixture
def graph():
    return FakeGraph()


@pytest.fixture
def search(container, graph):
    return SearchService(container.database, container.cv_storage, lambda: graph)


@pytest.fixture
def ready_users(container, valid_pdf):
    """Donne à chaque utilisateur un CV et un poste recherché : de quoi lancer une recherche."""
    for user_id in (DEFAULT_USER_ID, BOB, CAROL):
        container.cv.save_cv(user_id, valid_pdf)
        if user_id != DEFAULT_USER_ID:
            container.queries.add_query(user_id, "CDI", "une recherche")


def insert_rejected(container, user_id: int, url: str) -> None:
    with container.database.session() as session:
        RejectedJobRepository(session, user_id).insert_rejected_jobs([rejected_job(url)])


def test_search_runs_for_its_user_and_reports_progress(search, graph, ready_users):
    events = []

    summary = search.run_search(BOB, events.append)

    assert graph.inputs == [{"user_id": BOB}]
    assert events == [
        SearchProgress(message="Recherche 1/1", done=0, total=1),
        SearchProgress(message="1 page(s) nouvelle(s) sur 1 trouvée(s)"),
    ]
    # Le bilan vient du dernier état émis par le graph
    assert summary == SearchSummary(found=1, new=1, kept=0, rejected=0, inserted=1)


def test_search_stream_ends_with_the_summary(search, ready_users):
    *progress, summary = search.stream_search(BOB)

    assert all(isinstance(event, SearchProgress) for event in progress)
    assert isinstance(summary, SearchSummary)


def test_guest_is_stopped_at_the_daily_quota_before_the_graph_runs(search, graph, ready_users):
    for _ in range(MAX_SEARCHES_PER_DAY):
        search.run_search(BOB)
    assert search.remaining_searches(BOB) == 0

    # Le refus tombe à l'appel, pas à la lecture du déroulement : l'API peut encore répondre par une erreur
    with pytest.raises(QuotaExceededError):
        search.stream_search(BOB)

    assert len(graph.inputs) == MAX_SEARCHES_PER_DAY
    # Le quota de l'un n'entame pas celui de l'autre
    assert search.remaining_searches(CAROL) == MAX_SEARCHES_PER_DAY


def test_failed_search_still_counts(container, ready_users):
    search = SearchService(container.database, container.cv_storage, BrokenGraph)

    with pytest.raises(RuntimeError):
        search.run_search(BOB)

    assert search.remaining_searches(BOB) == MAX_SEARCHES_PER_DAY - 1


def test_owner_has_no_quota(search, graph, ready_users):
    for _ in range(MAX_SEARCHES_PER_DAY + 1):
        search.run_search(DEFAULT_USER_ID)

    assert search.remaining_searches(DEFAULT_USER_ID) is None
    assert len(graph.inputs) == MAX_SEARCHES_PER_DAY + 1


def test_search_without_cv_or_query_is_refused_without_using_the_quota(container, search, graph, valid_pdf):
    container.queries.add_query(BOB, "CDI", "une recherche")
    container.cv.save_cv(CAROL, valid_pdf)

    # Bob n'a pas de CV, Carol pas de poste recherché
    for user_id in (BOB, CAROL):
        assert search.can_search(user_id) is False
        with pytest.raises(InvalidInputError):
            search.run_search(user_id)
        assert search.remaining_searches(user_id) == MAX_SEARCHES_PER_DAY
    assert graph.inputs == []


def test_real_graph_runs_behind_the_service(container, ready_users):
    summary = container.search.run_search(BOB)

    # Le faux Tavily renvoie deux pages par recherche, le faux modèle en retient une sur deux
    assert summary == SearchSummary(found=2, new=2, kept=1, rejected=1, inserted=1)
    assert [job.url for job in container.jobs.list_jobs(BOB)] == ["https://x/offre d'emploi une recherche CDI/0"]
    rejected_urls = [job.url for job in container.jobs.list_rejected_jobs(BOB)]
    assert rejected_urls == ["https://x/offre d'emploi une recherche CDI/1"]
    assert container.jobs.list_jobs(CAROL) == []


def test_saving_a_cv_forgets_the_rejections_of_its_user_only(container, valid_pdf):
    insert_rejected(container, BOB, "https://r/1")
    insert_rejected(container, CAROL, "https://r/1")
    assert container.cv.get_status(BOB).updated_at is None

    status = container.cv.save_cv(BOB, valid_pdf)

    assert status.updated_at is not None
    assert container.cv.get_status(CAROL).updated_at is None
    assert container.jobs.list_rejected_jobs(BOB) == []
    assert [job.url for job in container.jobs.list_rejected_jobs(CAROL)] == ["https://r/1"]


def test_refused_cv_keeps_the_rejections(container, valid_pdf, monkeypatch):
    insert_rejected(container, BOB, "https://r/1")

    with pytest.raises(InvalidInputError):
        container.cv.save_cv(BOB, blank_pdf())
    monkeypatch.setattr(cv_service, "MAX_CV_BYTES", len(valid_pdf) - 1)
    with pytest.raises(InvalidInputError, match="dépasse"):
        container.cv.save_cv(BOB, valid_pdf)

    assert len(container.jobs.list_rejected_jobs(BOB)) == 1
    assert container.cv.get_status(BOB).updated_at is None


def test_queries_are_validated_and_private(container):
    created = container.queries.add_query(BOB, "CDI", "  data engineer à Paris  ")

    assert created.query == "data engineer à Paris"
    assert [query.id for query in container.queries.list_queries(BOB)] == [created.id]
    assert len(container.queries.list_queries(DEFAULT_USER_ID)) == len(DEFAULT_QUERIES)

    with pytest.raises(ConflictError):
        container.queries.add_query(BOB, "CDD", "data engineer à Paris")
    with pytest.raises(InvalidInputError):
        container.queries.add_query(BOB, "CDI", "   ")
    with pytest.raises(InvalidInputError):
        container.queries.add_query(BOB, "bénévolat", "data engineer")

    # Carol ne peut pas supprimer la recherche de Bob en devinant son identifiant
    with pytest.raises(NotFoundError):
        container.queries.delete_query(CAROL, created.id)
    container.queries.delete_query(BOB, created.id)
    assert container.queries.list_queries(BOB) == []


def test_jobs_are_tracked_and_private(container):
    with container.database.session() as session:
        JobRepository(session, BOB).insert_jobs([job("https://a/1"), job("https://a/2")])

    ids = {saved.url: saved.id for saved in container.jobs.list_jobs(BOB)}

    container.jobs.set_applied(BOB, ids["https://a/1"], True)
    with pytest.raises(NotFoundError):
        container.jobs.set_applied(CAROL, ids["https://a/1"], True)
    assert container.jobs.delete_jobs(CAROL, [ids["https://a/2"]]) == 0
    with pytest.raises(NotFoundError):
        container.jobs.delete_job(CAROL, ids["https://a/2"])
    container.jobs.delete_job(BOB, ids["https://a/2"])
    with pytest.raises(NotFoundError):
        container.jobs.delete_job(BOB, ids["https://a/2"])

    [saved] = container.jobs.list_jobs(BOB)
    assert (saved.url, saved.applied) == ("https://a/1", True)
    assert saved.applied_at.tzinfo is not None and saved.created_at.tzinfo is not None
    assert container.jobs.list_jobs(CAROL) == []


def test_query_is_saved_for_a_location_or_for_full_remote(container):
    in_lyon = container.queries.add_query(BOB, "CDI", "data engineer", " Lyon ")
    remote = container.queries.add_query(BOB, "CDI", "data engineer", "Lyon", remote=True)
    anywhere = container.queries.add_query(BOB, "CDI", "data engineer")

    # En télétravail complet, le lieu saisi est ignoré
    assert [(query.location, query.remote) for query in (in_lyon, remote, anywhere)] == [
        ("Lyon", False),
        ("", True),
        ("", False),
    ]
    with pytest.raises(ConflictError):
        container.queries.add_query(BOB, "CDI", "data engineer", "Lyon")
    with pytest.raises(InvalidInputError):
        container.queries.add_query(BOB, "CDI", "data engineer", "x" * 101)


def test_adding_a_query_forgets_the_rejections_that_depend_on_the_searches(container):
    out_of_area = {**rejected_job("https://r/lieu"), "matches_cv": True, "matches_location": False}
    other_job = {**rejected_job("https://r/metier"), "matches_cv": True, "matches_search": False}
    internship = {**rejected_job("https://r/stage"), "matches_cv": True, "matches_contract": False}
    # Un rejet dû au CV reste, même si le métier n'était pas le bon non plus
    unfit = {**rejected_job("https://r/profil"), "matches_search": False}
    with container.database.session() as session:
        RejectedJobRepository(session, BOB).insert_rejected_jobs([unfit, out_of_area, other_job, internship])
        RejectedJobRepository(session, CAROL).insert_rejected_jobs([out_of_area])

    container.queries.add_query(BOB, "CDI", "data engineer", "Lyon")

    assert [page.url for page in container.jobs.list_rejected_jobs(BOB)] == ["https://r/profil"]
    assert len(container.jobs.list_rejected_jobs(CAROL)) == 1


def test_rejected_page_tells_why_it_was_rejected(container):
    def motives(**verdict):
        with container.database.session() as session:
            RejectedJobRepository(session, BOB).clear()
            RejectedJobRepository(session, BOB).insert_rejected_jobs([{**rejected_job("https://r/1"), **verdict}])
        [page] = container.jobs.list_rejected_jobs(BOB)
        return page.motive, page.failed_criteria

    assert motives(is_real_offer=False, matches_search=False) == ("Pas une offre valable", ["Pas une offre valable"])
    # Le motif est le premier critère en défaut, la liste les donne tous
    assert motives(matches_search=False, matches_skills=False, matches_level=True) == (
        "Autre métier que ceux recherchés",
        ["Autre métier que ceux recherchés", "Compétences insuffisantes"],
    )
    assert motives(matches_cv=True, matches_location=False) == ("Hors lieu recherché", ["Hors lieu recherché"])
    # Une page rejetée avant le verdict détaillé n'a que le motif général
    assert motives(matches_location=None) == ("Hors profil", ["Hors profil"])


def test_deleting_an_account_leaves_nothing_behind(container, valid_pdf):
    with container.database.session() as session:
        user_id = UserRepository(session).get_or_create_user_id("alice@exemple.fr")
    container.cv.save_cv(user_id, valid_pdf)
    container.queries.add_query(user_id, "CDI", "data engineer")
    container.search.run_search(user_id)
    backup = container.settings.db_path.with_name("jobs.avant-migration-0001.db")
    backup.write_bytes(b"copie")

    container.account.delete_account(user_id)

    assert container.jobs.list_jobs(user_id) == [] and container.jobs.list_rejected_jobs(user_id) == []
    assert container.queries.list_queries(user_id) == []
    assert container.cv.get_status(user_id).updated_at is None
    assert not container.cv_storage.path_for(user_id).exists()
    # Le quota repart de zéro : les lancements sont effacés aussi
    assert container.search.remaining_searches(user_id) == MAX_SEARCHES_PER_DAY
    # Les copies d'avant migration contenaient encore ses données
    assert not backup.exists()
    with container.database.session() as session:
        users = UserRepository(session).list_users()
        # La ligne reste, sans adresse : l'identifiant n'est pas redonné au compte suivant
        assert [user.email for user in users if user.id == user_id] == [None]
        assert UserRepository(session).get_or_create_user_id("alice@exemple.fr") != user_id


def test_owner_can_erase_their_data_and_keeps_their_identifier(container, valid_pdf):
    container.cv.save_cv(DEFAULT_USER_ID, valid_pdf)
    assert container.queries.list_queries(DEFAULT_USER_ID)

    container.account.delete_account(DEFAULT_USER_ID)

    assert container.queries.list_queries(DEFAULT_USER_ID) == []
    assert container.cv.get_status(DEFAULT_USER_ID).updated_at is None
    with container.database.session() as session:
        assert [user.id for user in UserRepository(session).list_users()] == [DEFAULT_USER_ID]


def test_account_is_not_deleted_while_its_search_runs(container, valid_pdf):
    container.cv.save_cv(DEFAULT_USER_ID, valid_pdf)
    events = container.search.stream_search(DEFAULT_USER_ID)
    next(events)

    assert container.search.is_running(DEFAULT_USER_ID)
    with pytest.raises(ConflictError):
        container.account.delete_account(DEFAULT_USER_ID)
    # Rien n'a été effacé par la tentative
    assert container.cv.get_status(DEFAULT_USER_ID).updated_at is not None

    list(events)
    assert not container.search.is_running(DEFAULT_USER_ID)
    container.account.delete_account(DEFAULT_USER_ID)
