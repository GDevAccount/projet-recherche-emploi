import gc
import json
import sqlite3
import threading
from contextlib import closing
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from conftest import FakeEvaluator, FakeNotifier, FakeSearchEngine
from helpers import blank_pdf, job, rejected_job
from sqlalchemy import update

from projet_recherche_emploi.agent.prompts import prompt_version
from projet_recherche_emploi.config import (
    DEFAULT_QUERIES,
    DEFAULT_USER_ID,
    INACTIVE_ACCOUNT_DAYS,
    MAX_SEARCHES_PER_DAY,
    SERVER_ERROR_DAYS,
    WEEKS_SHOWN,
    Settings,
)
from projet_recherche_emploi.container import build_container
from projet_recherche_emploi.data.cv_ingestion.pdf_reader import CvPdfReader
from projet_recherche_emploi.data.models import EngineCall, SearchRun, ServerError
from projet_recherche_emploi.data.repositories.activity_repository import ActivityRepository
from projet_recherche_emploi.data.repositories.correction_repository import CorrectionRepository
from projet_recherche_emploi.data.repositories.cv_text_repository import CvTextRepository
from projet_recherche_emploi.data.repositories.engine_call_repository import EngineCallRepository
from projet_recherche_emploi.data.repositories.job_repository import JobRepository
from projet_recherche_emploi.data.repositories.rejected_job_repository import RejectedJobRepository
from projet_recherche_emploi.data.repositories.search_run_repository import SearchRunRepository
from projet_recherche_emploi.data.repositories.user_repository import UserRepository
from projet_recherche_emploi.errors import ConflictError, InvalidInputError, NotFoundError, QuotaExceededError
from projet_recherche_emploi.schemas import BudgetOverview, ClientErrorReport, SearchProgress, SearchSummary
from projet_recherche_emploi.services import cv_service, health_service
from projet_recherche_emploi.services.alert_service import AlertService, NtfyNotifier
from projet_recherche_emploi.services.search_service import (
    SearchService,
    describe_engine_calls,
    start_of_local_week,
    summarize_engine_calls,
)

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
        call = {"query": "une recherche", "search_text": "offre une recherche", "international": False}
        yield (
            "values",
            {
                "jobs": [{"url": "https://x/1", "search_index": 0}],
                "searches": [{**call, "found_count": 1, "duration_ms": 12}],
                "metrics": {"search_ms": 12, "search_calls": 1},
            },
        )
        raise RuntimeError("Tavily search failed : clé sk-secrete")


@pytest.fixture
def graph():
    return FakeGraph()


@pytest.fixture
def search(container, graph):
    return SearchService(container.database, lambda: graph)


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


def test_a_rejected_page_can_be_put_back_among_the_offers(container):
    with container.database.session() as session:
        unfit = {**rejected_job("https://r/1"), "matches_skills": False}
        RejectedJobRepository(session, BOB).insert_rejected_jobs([unfit])
    insert_rejected(container, CAROL, "https://r/1")

    with pytest.raises(NotFoundError):
        container.jobs.restore_rejected_job(BOB, "https://r/inconnue")
    restored = container.jobs.restore_rejected_job(BOB, "https://r/1")

    assert (restored.url, restored.status, restored.next_statuses) == ("https://r/1", "todo", ["applied"])
    assert [saved.url for saved in container.jobs.list_jobs(BOB)] == ["https://r/1"]
    assert container.jobs.list_rejected_jobs(BOB) == []
    # Le rejet du même lien par un autre utilisateur reste le sien
    assert container.jobs.list_jobs(CAROL) == [] and len(container.jobs.list_rejected_jobs(CAROL)) == 1
    with container.database.session() as session:
        [correction] = CorrectionRepository(session, BOB).list_all()
        # Le verdict contredit est gardé : c'est lui qui dit sur quoi le tri s'est trompé
        assert (correction.kind, correction.reason, correction.matches_skills) == ("restored", None, False)
        # Une page que le journal ne connaît pas n'a pas de version de prompt
        assert correction.prompt_version is None

    # Supprimée ensuite, l'offre ne peut pas être remise une seconde fois : son adresse est déjà connue
    container.jobs.delete_job(BOB, restored.id)
    insert_rejected(container, BOB, "https://r/1")
    with pytest.raises(ConflictError):
        container.jobs.restore_rejected_job(BOB, "https://r/1")
    assert len(container.jobs.list_rejected_jobs(BOB)) == 1


def test_corrections_are_counted_by_prompt_version(container, ready_users):
    container.search.run_search(BOB)
    [kept] = container.jobs.list_jobs(BOB)
    [rejected] = container.jobs.list_rejected_jobs(BOB)

    assert container.search.get_stats(BOB).corrections == []
    container.jobs.restore_rejected_job(BOB, rejected.url)
    container.jobs.delete_job(BOB, kept.id, "not_my_job")
    stats = container.search.get_stats(BOB)

    [version] = stats.corrections
    assert version.prompt_version == prompt_version()
    assert (version.evaluated, version.kept, version.rejected) == (2, 1, 1)
    assert (version.restored, version.wrongly_kept, version.other_deleted) == (1, 1, 0)
    assert (version.restored_rate, version.wrongly_kept_rate) == (1.0, 1.0)
    assert [(reason.label, reason.count) for reason in stats.delete_reasons] == [("Ce n'est pas mon métier", 1)]

    # Une offre qui n'intéresse pas, ou supprimée sans motif, ne reproche rien au tri
    [restored] = container.jobs.list_jobs(BOB)
    container.jobs.delete_job(BOB, restored.id, "not_interested")
    [version] = container.search.get_stats(BOB).corrections
    assert (version.wrongly_kept, version.other_deleted) == (1, 1)
    assert container.search.get_stats(CAROL).corrections == []


def test_search_runs_for_its_user_and_reports_progress(search, graph, ready_users):
    events = []

    summary = search.run_search(BOB, events.append)

    # Le graph reçoit aussi le lancement enregistré, pour y rattacher le journal des pages évaluées
    [run] = search.list_runs(BOB)
    assert graph.inputs == [{"user_id": BOB, "run_id": run.id}]
    assert (run.status, run.found_count, run.new_count, run.kept_count, run.inserted_count) == ("done", 1, 1, None, 1)
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


def test_outcomes_say_what_became_of_the_kept_offers(container, ready_users):
    container.queries.add_query(BOB, "CDI", "autre recherche")
    container.search.run_search(BOB)
    first, second = sorted(container.jobs.list_jobs(BOB), key=lambda job: job.query)
    [rejected, _] = container.jobs.list_rejected_jobs(BOB)
    empty = container.search.get_stats(BOB)
    assert (empty.outcomes.kept, empty.outcomes.pending, empty.outcomes.applied_rate) == (2, 2, 0.0)
    assert (empty.outcomes.interview_rate, empty.cost_per_application_usd) == (None, None)

    # Une candidature menée jusqu'à l'entretien, une offre supprimée, et une page remise par l'utilisateur
    container.jobs.set_status(BOB, first.id, "applied")
    container.jobs.set_status(BOB, first.id, "interview")
    container.jobs.delete_job(BOB, second.id, "not_my_job")
    container.jobs.restore_rejected_job(BOB, rejected.url)
    stats = container.search.get_stats(BOB)

    # La page remise n'a pas été retenue par le tri : elle ne compte pas
    total = stats.outcomes
    assert (total.label, total.kept, total.applied) == ("Toutes les offres", 2, 1)
    assert (total.interviews, total.refused) == (1, 0)
    assert (total.pending, total.deleted, total.applied_rate, total.interview_rate) == (0, 1, 0.5, 1.0)
    assert [(group.label, group.kept, group.applied, group.deleted) for group in stats.outcomes_by_query] == [
        ("autre recherche", 1, 1, 0),
        ("une recherche", 1, 0, 1),
    ]
    assert [(group.label, group.kept, group.applied) for group in stats.outcomes_by_site] == [("x", 2, 1)]
    assert [(group.label, group.kept) for group in stats.outcomes_by_prompt] == [(prompt_version(), 2)]
    assert stats.cost_per_application_usd == stats.cost_usd

    # Un refus de l'employeur reste une candidature, et l'entretien obtenu reste compté
    container.jobs.set_status(BOB, first.id, "rejected")
    refused = container.search.get_stats(BOB).outcomes
    assert (refused.applied, refused.refused, refused.interviews) == (1, 1, 1)
    assert container.search.get_stats(CAROL).outcomes.kept == 0


def test_weeks_follow_the_searches_and_the_applications(container, ready_users):
    # Le propriétaire n'a pas de quota, et autant d'appels au moteur que de recherches par défaut
    owner, calls = DEFAULT_USER_ID, len(DEFAULT_QUERIES)
    container.search.run_search(owner)
    container.search.run_search(owner)
    container.jobs.set_status(owner, container.jobs.list_jobs(owner)[0].id, "applied")

    weeks = container.search.get_stats(owner).weeks

    # Douze semaines, la plus ancienne en premier : celles sans recherche y sont, à zéro
    assert len(weeks) == WEEKS_SHOWN and weeks == sorted(weeks, key=lambda week: week.start)
    assert {(week.runs, week.cost_usd, week.known_rate, week.applications) for week in weeks[:-1]} == {(0, 0, None, 0)}
    current = weeks[-1]
    # La seconde recherche n'a retrouvé que les pages de la première : la moitié des pages était connue
    assert (current.runs, current.failed_runs, current.found, current.evaluated) == (2, 0, 4 * calls, 2 * calls)
    assert (current.known_rate, current.kept, current.kept_rate, current.applications) == (0.5, calls, 0.5, 1)
    # Le faux modèle n'a pas de tarif : pas de coût, plutôt qu'un coût partiel
    assert current.cost_usd is None

    # Trois semaines plus tard, les mêmes chiffres ont reculé d'autant
    later = container.search.get_stats(owner, now=datetime.now(UTC) + timedelta(weeks=3)).weeks
    assert [week.runs for week in later[-4:]] == [2, 0, 0, 0] and later[-4].applications == 1
    # Une recherche échouée compte dans sa semaine, sans fausser la part des pages connues
    broken = SearchService(container.database, BrokenGraph)
    with pytest.raises(RuntimeError):
        broken.run_search(owner)
    failed = container.search.get_stats(owner).weeks[-1]
    assert (failed.runs, failed.failed_runs, failed.found, failed.known_rate) == (3, 1, 4 * calls + 1, 0.5)
    assert container.search.get_stats(CAROL).weeks[-1].runs == 0


def test_week_starts_on_monday_in_paris():
    # Dimanche 22 h 30 en UTC, c'est déjà lundi à Paris
    assert start_of_local_week(datetime(2026, 10, 11, 22, 30, tzinfo=UTC)).isoformat() == "2026-10-12"
    assert start_of_local_week(datetime(2026, 10, 11, 21, 30, tzinfo=UTC)).isoformat() == "2026-10-05"


def test_guest_coming_on_several_days_is_counted_each_day(tmp_path):
    # Une horloge en avance sur la vraie : la création du compte, elle, est datée par la base
    now = [(datetime.now(UTC) + timedelta(days=10)).timestamp()]
    settings = Settings(
        data_dir=tmp_path, google_client_id="id", owner_email="proprietaire@exemple.fr", allowed_emails="*"
    )
    container = build_container(settings, FakeSearchEngine(), FakeEvaluator())
    container.auth.clock = lambda: now[0]

    alice = container.auth.resolve_user_id("alice@exemple.fr", True)
    # Plusieurs requêtes le même jour, puis une le surlendemain
    container.auth.resolve_user_id("alice@exemple.fr", True)
    now[0] += 2 * 24 * 3600
    container.auth.resolve_user_id("alice@exemple.fr", True)
    # L'activité du propriétaire n'est pas datée
    container.auth.resolve_user_id("proprietaire@exemple.fr", True)

    journeys = container.usage.get_journeys(datetime.fromtimestamp(now[0], UTC) + timedelta(days=4))
    [account] = [row for row in journeys.accounts if row.user_id == alice]
    assert (account.active_days, account.returned, account.idle_days) == (2, True, 4)
    [owner] = [row for row in journeys.accounts if row.is_owner]
    assert owner.active_days == 0
    # Les jours partent avec le compte
    container.account.delete_account(alice)
    with container.database.session() as session:
        assert ActivityRepository(session, alice).list_days() == []


def test_guest_seen_on_another_day_has_returned(container):
    with container.database.session() as session:
        users = UserRepository(session)
        alice, bob = (users.get_or_create_user_id(f"{name}@exemple.fr") for name in ("alice", "bob"))
        # Alice est revenue trois jours après la création de son compte, Bob ne l'a jamais rouvert
        long_ago = datetime.now(UTC) - timedelta(days=30)
        users.record_activity(alice, datetime.now(UTC) + timedelta(days=3), datetime.now(UTC) + timedelta(days=1))
        users.record_activity(bob, long_ago, datetime.now(UTC) + timedelta(days=1))

    journeys = container.usage.get_journeys()

    # Le dernier vu en premier
    assert [(account.email, account.returned) for account in journeys.accounts if not account.is_owner] == [
        ("alice@exemple.fr", True),
        ("bob@exemple.fr", False),
    ]
    assert (journeys.guests, journeys.steps[-1].label, journeys.steps[-1].count) == (2, "Revenu un autre jour", 1)
    # Sans invité, aucune part ne se calcule
    container.account.delete_account(alice)
    container.account.delete_account(bob)
    empty = container.usage.get_journeys()
    assert (empty.guests, {step.rate for step in empty.steps}, len(empty.accounts)) == (0, {None}, 1)


def test_budget_projects_the_month_from_the_days_elapsed(container, ready_users):
    container.usage.monthly_budget_usd = 0.02
    container.search.run_search(BOB)
    with container.database.session() as session:
        session.execute(update(SearchRun).values(created_at=datetime(2026, 3, 10, 12, tzinfo=UTC)))

    # Le 16 mars à minuit, heure de Paris : quinze jours écoulés sur trente et un
    budget = container.usage.get_budget(datetime(2026, 3, 15, 23, tzinfo=UTC))

    assert budget.month_start == datetime(2026, 2, 28, 23, tzinfo=UTC)
    assert (budget.day_of_month, budget.days_left) == (16, 16)
    # Un appel au moteur de recherche, et un modèle sans tarif : la dépense est un plancher
    assert (budget.runs, budget.spent_usd, budget.partial, budget.guests_spent_usd) == (1, 0.016, True, None)
    assert (budget.daily_average_usd, budget.projected_usd) == (0.001067, 0.033067)
    assert (budget.spent_rate, budget.projected_rate) == (0.8, 1.6533)
    assert (budget.over_budget, budget.projected_over_budget) == (False, True)

    # Le compte supprimé, sa dépense du mois reste dans le budget
    container.account.delete_account(BOB)
    assert container.usage.get_budget(datetime(2026, 3, 15, 23, tzinfo=UTC)).spent_usd == 0.016
    # Le 1er avril à minuit et demi à Paris, UTC est encore en mars : c'est le mois de Paris qui compte
    april = container.usage.get_budget(datetime(2026, 3, 31, 22, 30, tzinfo=UTC))
    assert (april.month_start, april.runs, april.spent_usd, april.projected_usd) == (
        datetime(2026, 3, 31, 22, tzinfo=UTC),
        0,
        0,
        0,
    )
    # Sans budget, rien n'est jamais dépassé
    container.usage.monthly_budget_usd = 0
    free = container.usage.get_budget(datetime(2026, 3, 15, 23, tzinfo=UTC))
    assert (free.spent_rate, free.projected_rate, free.over_budget, free.projected_over_budget) == (
        None,
        None,
        False,
        False,
    )


def test_budget_sends_an_alert_when_exceeded_or_about_to_be(alerting, notifier, ready_users, monkeypatch):
    alerting.search.run_search(BOB)
    assert notifier.sent == []

    alerting.usage.monthly_budget_usd = 0.02
    alerting.search.run_search(CAROL)
    alerting.search.run_search(BOB)
    assert notifier.sent == [("Budget dépassé", "0.03 $ dépensés ce mois-ci pour un budget de 0.02 $")]

    def budget(day: int) -> BudgetOverview:
        return BudgetOverview(
            month_start=datetime(2026, 4, 1, tzinfo=UTC),
            budget_usd=10,
            runs=4,
            spent_usd=2,
            partial=False,
            guests_spent_usd=0.5,
            day_of_month=day,
            days_left=31 - day,
            daily_average_usd=1,
            projected_usd=30,
            spent_rate=0.2,
            projected_rate=3,
            over_budget=False,
            projected_over_budget=True,
        )

    # En tout début de mois, la projection repose sur trop peu de jours pour prévenir
    monkeypatch.setattr(alerting.usage, "get_budget", lambda: budget(2))
    alerting.search.run_search(DEFAULT_USER_ID)
    assert len(notifier.sent) == 1
    monkeypatch.setattr(alerting.usage, "get_budget", lambda: budget(12))
    alerting.search.run_search(DEFAULT_USER_ID)
    alerting.search.run_search(DEFAULT_USER_ID)
    assert notifier.sent[1:] == [("Budget menacé", "À ce rythme, 30.00 $ en fin de mois pour un budget de 10.00 $")]


def test_engine_calls_say_what_became_of_their_pages():
    def page(search_index: int) -> dict:
        return {"search_index": search_index}

    searches = [
        {"query": "data engineer", "search_text": "offre data engineer", "international": False, "found_count": 5},
        {"query": "data engineer", "search_text": "data engineer remote job", "international": True, "found_count": 4},
    ]
    state = {
        "searches": searches,
        # Deux pages du second appel avaient déjà été rendues par le premier : elles lui reviennent
        "jobs": [page(0)] * 5 + [page(1)] * 2,
        "new_jobs": [page(0)] * 3 + [page(1)],
        "filtered_jobs": [page(0)],
    }

    first, second = describe_engine_calls(state)
    assert (first["unique_count"], first["new_count"], first["kept_count"]) == (5, 3, 1)
    assert (second["search_text"], second["unique_count"], second["new_count"], second["kept_count"]) == (
        "data engineer remote job",
        2,
        1,
        0,
    )
    # Un lancement arrêté avant le tri des doublons ne sait pas ce que ses pages sont devenues
    [stopped] = describe_engine_calls({"searches": searches[:1], "jobs": [page(0)] * 5})
    assert (stopped["unique_count"], stopped["new_count"], stopped["kept_count"]) == (5, None, None)
    assert describe_engine_calls({}) == []

    calls = [EngineCall(**call) for call in (first, second, stopped)]
    worst, best = summarize_engine_calls(calls)
    # Le texte qui n'a rien fait retenir vient en premier
    assert (worst.search_text, worst.international, worst.calls) == ("data engineer remote job", True, 1)
    assert (worst.found, worst.repeated, worst.known, worst.rejected, worst.kept) == (4, 2, 1, 1, 0)
    assert (worst.search_cost_usd, worst.cost_per_kept_usd) == (0.016, None)
    assert (best.calls, best.found, best.repeated, best.known, best.rejected, best.kept) == (2, 10, 0, 2, 2, 1)
    assert (best.search_cost_usd, best.cost_per_kept_usd) == (0.032, 0.032)


def test_failed_search_still_counts(container, ready_users):
    search = SearchService(container.database, BrokenGraph)

    with pytest.raises(RuntimeError):
        search.run_search(BOB)

    assert search.remaining_searches(BOB) == MAX_SEARCHES_PER_DAY - 1
    # Le lancement garde ce qui a été mesuré avant l'échec, et le type de l'erreur sans son message
    [run] = search.list_runs(BOB)
    assert (run.status, run.error, run.found_count, run.new_count) == ("failed", "RuntimeError", 1, None)
    assert (run.search_ms, run.search_calls, run.evaluate_ms, run.duration_ms) == (12, 1, None, 12)
    assert run.finished_at is not None
    # L'appel au moteur fait avant l'échec a été payé : il reste compté, sans suite connue
    [call] = search.get_stats(BOB).by_search
    assert (call.calls, call.found, call.known, call.rejected, call.kept) == (1, 1, 0, 0, 0)


def test_health_counts_what_failed_on_every_account(container, ready_users):
    broken = SearchService(container.database, BrokenGraph)
    for user_id in (BOB, CAROL):
        with pytest.raises(RuntimeError):
            broken.run_search(user_id)
    container.search.run_search(BOB)
    # Un lancement de Carol que le serveur a coupé en redémarrant
    with container.database.session() as session:
        SearchRunRepository(session, CAROL).record_run()

    health = container.health.get_overview()

    assert (health.runs, health.failed_runs, health.interrupted_runs, health.failure_rate) == (4, 2, 1, 0.75)
    assert (health.healthy, health.since, health.last_interrupted_at is not None) == (False, None, True)
    assert (health.incidents, health.interrupted_accounts) == (3, 1)
    [failure] = health.run_failures
    assert (failure.error_type, failure.count, failure.accounts) == ("RuntimeError", 2, 2)

    # Une recherche en cours n'est pas une recherche interrompue
    events = container.search.stream_search(DEFAULT_USER_ID)
    next(events)
    running = container.health.get_overview()
    assert (running.runs, running.interrupted_runs, running.failure_rate) == (5, 1, 0.6)
    list(events)

    # Rien de tout cela n'est dans les trente jours précédant une date lointaine
    later = container.health.get_overview(days=30, now=datetime.now(UTC) + timedelta(days=60))
    assert (later.healthy, later.runs, later.failure_rate, later.run_failures) == (True, 0, None, [])


def test_server_errors_are_kept_for_a_while_then_forgotten(container):
    container.health.record_error(BOB, "PUT", "/api/cv", 422, "InvalidInputError")
    container.health.record_error(None, "GET", None, 500, "KeyError")
    health = container.health.get_overview()
    # Les pannes passent avant les demandes refusées, et seules elles disent que l'instance va mal
    assert [(group.error_type, group.is_failure, group.accounts) for group in health.server_errors] == [
        ("KeyError", True, 0),
        ("InvalidInputError", False, 1),
    ]
    assert (health.failures, health.refusals, health.incidents, health.healthy) == (1, 1, 1, False)

    # Devenues trop anciennes, elles sont effacées à l'erreur suivante
    old = datetime.now(UTC) - timedelta(days=SERVER_ERROR_DAYS + 1)
    with container.database.session() as session:
        session.execute(update(ServerError).values(created_at=old))
    container.health.record_error(CAROL, "GET", "/api/jobs", 404, "NotFoundError")
    health = container.health.get_overview()
    assert [group.error_type for group in health.server_errors] == ["NotFoundError"]
    assert health.healthy

    # Une base qui ne répond plus ne doit pas empêcher la réponse d'erreur de partir
    container.health.database = None
    container.health.record_error(BOB, "GET", "/api/jobs", 500, "OperationalError")


def test_failed_search_sends_an_alert_without_naming_anyone(alerting, notifier, ready_users):
    alerting.search.run_search(BOB)
    assert notifier.sent == []

    alerting.search._get_graph = BrokenGraph
    for user_id in (BOB, CAROL, DEFAULT_USER_ID):
        with pytest.raises(RuntimeError):
            alerting.search.run_search(user_id)

    # La même erreur chez un second compte, dans l'heure, ne sonne pas une seconde fois
    assert notifier.sent == [("Recherche échouée", "RuntimeError pendant une recherche d'un invité")]
    assert alerting.health.get_overview().alerts_enabled


def test_server_failure_sends_an_alert_but_a_refusal_does_not(alerting, notifier):
    alerting.health.record_error(BOB, "PUT", "/api/cv", 422, "InvalidInputError")
    assert notifier.sent == []

    alerting.health.record_error(BOB, "GET", "/api/jobs/{job_id}", 500, "KeyError")
    alerting.health.record_error(CAROL, "GET", "/api/jobs/{job_id}", 500, "KeyError")
    alerting.health.record_error(None, "GET", None, 500, "KeyError")
    # Même si la base ne répond plus : c'est justement une panne
    alerting.health.database = None
    alerting.health.record_error(BOB, "GET", "/api/cv", 500, "OperationalError")

    assert notifier.sent == [
        ("Panne du serveur", "KeyError sur GET /api/jobs/{job_id}"),
        ("Panne du serveur", "KeyError sur une route inconnue"),
        ("Panne du serveur", "OperationalError sur GET /api/cv"),
    ]


def test_unusual_daily_cost_sends_one_alert_a_day(alerting, notifier, ready_users, monkeypatch):
    alerting.search.run_search(BOB)
    assert notifier.sent == []

    # Le faux modèle ne coûte rien ici : il reste le coût du moteur de recherche, 0,016 $ par appel
    monkeypatch.setattr(health_service, "DAILY_COST_ALERT_USD", 0.03)
    alerting.search.run_search(CAROL)
    alerting.search.run_search(BOB)

    assert notifier.sent == [("Coût anormal", "0.03 $ en 24 heures pour 2 recherches, tous comptes réunis")]


def test_unreachable_database_is_reported_once(alerting, notifier):
    assert alerting.health.is_alive() and notifier.sent == []

    alerting.health.database = None

    # La sonde revient toutes les quelques minutes : l'alerte, elle, ne part qu'une fois dans l'heure
    assert not alerting.health.is_alive() and not alerting.health.is_alive()
    assert notifier.sent == [("Base injoignable", "AttributeError à la lecture de la base")]


def test_model_without_a_price_is_reported(settings, valid_pdf):
    notifier = FakeNotifier()
    container = build_container(settings, FakeSearchEngine(), FakeEvaluator(), notifier)
    container.alerts.dispatch = lambda send: send()
    container.cv.save_cv(DEFAULT_USER_ID, valid_pdf)
    assert container.health.get_overview().unpriced_models == []

    container.search.run_search(DEFAULT_USER_ID)
    container.search.run_search(DEFAULT_USER_ID)

    # Une fois par jour : sans tarif, coûts et budget sont faux sans que rien ne le dise
    message = "Aucun tarif pour faux-modèle : coûts et budget ne comptent plus ce modèle"
    assert notifier.sent == [("Tarif manquant", message)]
    health = container.health.get_overview()
    # Un réglage à corriger, pas un incident
    assert (health.unpriced_models, health.healthy) == (["faux-modèle"], True)


def test_priced_model_is_not_reported(alerting, notifier, ready_users):
    alerting.search.run_search(BOB)
    assert notifier.sent == [] and alerting.health.get_overview().unpriced_models == []


def test_errors_of_the_front_are_kept_counted_and_reported(alerting, notifier, monkeypatch):
    crash = ClientErrorReport(error_type="TypeError", route="/offres", source="main-5UFRYBOQ.js:1:23456")
    assert alerting.health.record_client_error(BOB, crash)
    assert alerting.health.record_client_error(CAROL, crash)
    assert alerting.health.record_client_error(BOB, ClientErrorReport(error_type="RangeError"))

    health = alerting.health.get_overview()
    groups = [
        (group.route, group.error_type, group.source, group.count, group.accounts) for group in health.client_errors
    ]
    assert groups == [
        ("/offres", "TypeError", "main-5UFRYBOQ.js:1:23456", 2, 2),
        (None, "RangeError", None, 1, 1),
    ]
    # Une erreur chez un utilisateur est un incident, comme une panne du serveur
    assert (health.client_failures, health.incidents, health.healthy) == (3, 3, False)
    # La même erreur chez un second compte ne sonne pas deux fois dans l'heure
    assert notifier.sent == [
        ("Erreur dans le navigateur", "TypeError sur l'écran /offres"),
        ("Erreur dans le navigateur", "RangeError sur un écran inconnu"),
    ]

    # Une page qui échoue en boucle n'apprend plus rien : au-delà du plafond du jour, on n'enregistre plus
    monkeypatch.setattr(health_service, "CLIENT_ERRORS_PER_DAY", 2)
    assert not alerting.health.record_client_error(BOB, crash)
    assert alerting.health.record_client_error(CAROL, crash)
    assert alerting.health.get_overview().client_failures == 4

    # Elles partent avec le compte, et ne font jamais échouer l'appelant
    alerting.account.delete_account(BOB)
    assert alerting.health.get_overview().client_failures == 2
    alerting.health.database = None
    assert not alerting.health.record_client_error(CAROL, crash)


def test_restart_reports_the_searches_it_has_cut(alerting, notifier, ready_users):
    assert alerting.health.alert_on_interrupted_runs() == 0
    with alerting.database.session() as session:
        SearchRunRepository(session, BOB).record_run()
        SearchRunRepository(session, CAROL).record_run()

    # Une recherche coupée depuis longtemps n'est plus une nouvelle
    assert alerting.health.alert_on_interrupted_runs(datetime.now(UTC) + timedelta(hours=2)) == 0
    assert notifier.sent == []
    assert alerting.health.alert_on_interrupted_runs() == 2
    assert notifier.sent == [("Recherche interrompue", "2 recherche(s) coupée(s) par un redémarrage du serveur")]


def test_alerts_are_not_repeated_and_never_raise():
    notifier = FakeNotifier()
    alerts = AlertService(notifier, dispatch=lambda send: send())
    now = datetime.now(UTC)

    assert alerts.notify("panne", "Titre", "Message", now=now)
    assert not alerts.notify("panne", "Titre", "Message", now=now + timedelta(minutes=59))
    assert alerts.notify("autre", "Titre", "Autre message", now=now)
    assert alerts.notify("panne", "Titre", "Message", now=now + timedelta(minutes=61))
    assert len(notifier.sent) == 3

    def broken_dispatch(send):
        raise RuntimeError("plus de fil disponible")

    assert not AlertService(notifier, dispatch=broken_dispatch).notify("panne", "Titre", "Message")
    # Sans destinataire, rien ne part et rien n'échoue
    silent = AlertService()
    assert (silent.enabled, silent.notify("panne", "Titre", "Message"), silent.send_test()) == (False, False, False)
    assert AlertService(FakeNotifier()).send_test() and not AlertService(FakeNotifier(works=False)).send_test()


def test_ntfy_receives_the_alert_on_its_topic():
    received = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"]))
            received.append((self.path, self.headers["Content-Type"], json.loads(body)))
            self.send_response(200)
            self.end_headers()

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_port}"
    try:
        assert NtfyNotifier(url, "sujet-secret").send("Panne du serveur", "KeyError sur GET /api/jobs")
    finally:
        server.shutdown()
        server.server_close()

    [(path, content_type, body)] = received
    assert (path, content_type) == ("/", "application/json")
    assert (body["topic"], body["title"], body["message"]) == (
        "sujet-secret",
        "Panne du serveur",
        "KeyError sur GET /api/jobs",
    )
    # Le serveur vient d'être arrêté : l'envoi échoue sans lever
    assert not NtfyNotifier(url, "sujet-secret").send("Titre", "Message")


def test_run_left_running_by_a_restart_is_reported_as_interrupted(container, search, ready_users):
    # Un lancement enregistré, puis le serveur redémarre : rien ne vient écrire son bilan
    with container.database.session() as session:
        SearchRunRepository(session, BOB).record_run()
    assert [run.status for run in search.list_runs(BOB)] == ["interrupted"]

    events = search.stream_search(BOB)
    next(events)
    # Seul le dernier lancement tourne vraiment
    assert [run.status for run in search.list_runs(BOB)] == ["running", "interrupted"]
    list(events)
    assert [run.status for run in search.list_runs(BOB)] == ["done", "interrupted"]

    with pytest.raises(NotFoundError):
        search.list_evaluations(CAROL, search.list_runs(BOB)[0].id)


def test_second_search_is_refused_while_the_first_runs_without_using_the_quota(search, graph, ready_users):
    events = search.stream_search(BOB)
    next(events)

    assert search.is_running(BOB)
    with pytest.raises(ConflictError):
        search.stream_search(BOB)
    # Le refus n'a rien coûté, et ne gêne pas un autre utilisateur
    assert search.remaining_searches(BOB) == MAX_SEARCHES_PER_DAY - 1
    assert not search.is_running(CAROL)
    search.run_search(CAROL)

    list(events)
    assert not search.is_running(BOB)
    search.run_search(BOB)
    assert len(graph.inputs) == 3


def test_search_that_fails_or_is_never_read_does_not_block_the_next_one(container, search, ready_users):
    broken = SearchService(container.database, BrokenGraph)
    with pytest.raises(RuntimeError):
        broken.run_search(DEFAULT_USER_ID)
    assert not broken.is_running(DEFAULT_USER_ID)

    # Un déroulement abandonné avant sa première lecture : la connexion s'est fermée trop tôt
    abandoned = search.stream_search(DEFAULT_USER_ID)
    assert search.is_running(DEFAULT_USER_ID)
    del abandoned
    gc.collect()
    assert not search.is_running(DEFAULT_USER_ID)

    # Un quota atteint ne laisse pas non plus de recherche fantôme
    for _ in range(MAX_SEARCHES_PER_DAY):
        search.run_search(BOB)
    with pytest.raises(QuotaExceededError):
        search.stream_search(BOB)
    assert not search.is_running(BOB)


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

    updated = container.jobs.set_status(BOB, ids["https://a/1"], "applied")
    assert (updated.id, updated.status) == (ids["https://a/1"], "applied") and updated.applied_at is not None
    assert container.jobs.set_status(BOB, ids["https://a/1"], "todo").applied_at is None
    container.jobs.set_status(BOB, ids["https://a/1"], "applied")
    with pytest.raises(NotFoundError):
        container.jobs.set_status(CAROL, ids["https://a/1"], "applied")
    assert container.jobs.delete_jobs(CAROL, [ids["https://a/2"]]) == 0
    with pytest.raises(NotFoundError):
        container.jobs.delete_job(CAROL, ids["https://a/2"])
    container.jobs.delete_job(BOB, ids["https://a/2"], "profile")
    with pytest.raises(NotFoundError):
        container.jobs.delete_job(BOB, ids["https://a/2"])
    # La suppression laisse une correction, avec son motif : une seule, celle qui a réussi
    with container.database.session() as session:
        [correction] = CorrectionRepository(session, BOB).list_all()
        assert (correction.kind, correction.url, correction.reason) == ("deleted", "https://a/2", "profile")
        assert CorrectionRepository(session, CAROL).list_all() == []

    [saved] = container.jobs.list_jobs(BOB)
    assert (saved.url, saved.status) == ("https://a/1", "applied")
    assert saved.applied_at.tzinfo is not None and saved.created_at.tzinfo is not None
    assert container.jobs.list_jobs(CAROL) == []


def test_application_goes_through_its_steps_and_each_one_is_dated(container):
    with container.database.session() as session:
        JobRepository(session, BOB).insert_jobs([job("https://a/1")])
    [saved] = container.jobs.list_jobs(BOB)
    monday, tuesday, wednesday = (datetime(2026, 10, day, 9, tzinfo=UTC) for day in (5, 6, 7))
    # L'API dit ce que l'offre peut devenir : le front ne propose rien d'autre
    assert (saved.status, saved.next_statuses) == ("todo", ["applied"])

    applied = container.jobs.set_status(BOB, saved.id, "applied", monday)
    assert (applied.applied_at, applied.next_statuses) == (monday, ["interview", "rejected", "todo"])

    interview = container.jobs.set_status(BOB, saved.id, "interview", tuesday)
    assert (interview.applied_at, interview.interview_at) == (monday, tuesday)
    assert interview.next_statuses == ["rejected", "applied"]

    rejected = container.jobs.set_status(BOB, saved.id, "rejected", wednesday)
    assert (rejected.applied_at, rejected.interview_at, rejected.rejected_at) == (monday, tuesday, wednesday)
    # Le refus se défait vers l'étape où en était la candidature, pas vers le début
    assert rejected.next_statuses == ["interview"]

    reopened = container.jobs.set_status(BOB, saved.id, "interview", wednesday)
    assert (reopened.status, reopened.interview_at, reopened.rejected_at) == ("interview", tuesday, None)
    # Revenir en arrière efface la date de l'étape quittée
    back = container.jobs.set_status(BOB, saved.id, "applied", wednesday)
    assert (back.applied_at, back.interview_at) == (monday, None)
    assert container.jobs.set_status(BOB, saved.id, "todo", wednesday).applied_at is None


def test_refusal_before_any_interview_is_undone_to_applied(container):
    with container.database.session() as session:
        JobRepository(session, BOB).insert_jobs([job("https://a/1")])
    [saved] = container.jobs.list_jobs(BOB)
    container.jobs.set_status(BOB, saved.id, "applied")

    rejected = container.jobs.set_status(BOB, saved.id, "rejected")

    assert (rejected.interview_at, rejected.next_statuses) == (None, ["applied"])


def test_application_cannot_skip_a_step(container):
    with container.database.session() as session:
        JobRepository(session, BOB).insert_jobs([job("https://a/1")])
    [saved] = container.jobs.list_jobs(BOB)

    # Ni entretien ni refus pour une offre à laquelle on n'a pas postulé
    for status in ("interview", "rejected"):
        with pytest.raises(InvalidInputError):
            container.jobs.set_status(BOB, saved.id, status)
    # Redemander l'état en place ne change rien, date comprise
    first = container.jobs.set_status(BOB, saved.id, "applied", datetime(2026, 10, 5, tzinfo=UTC))
    again = container.jobs.set_status(BOB, saved.id, "applied", datetime(2026, 10, 6, tzinfo=UTC))
    assert again.applied_at == first.applied_at


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
    # Une page qui n'est pas une offre porte sa nature, et rien d'autre
    for page_kind, motive in [
        ("liste d'offres", "Liste ou page de résultats"),
        ("article", "Article"),
        ("fiche métier", "Fiche métier"),
        ("page d'accueil", "Page d'accueil"),
        ("offre expirée", "Offre expirée"),
        ("formation", "Contrat non recherché"),
        ("autre", "Pas une offre valable"),
    ]:
        assert motives(is_real_offer=False, page_kind=page_kind, matches_search=False) == (motive, [motive])
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
    container.jobs.delete_job(user_id, container.jobs.list_jobs(user_id)[0].id, "location")
    with container.database.session() as session:
        bob_id = UserRepository(session).get_or_create_user_id("bob@exemple.fr")
    container.queries.add_query(bob_id, "CDI", "data engineer")
    # Une copie d'avant migration, faite alors que les deux comptes existaient
    backup = container.settings.db_path.with_name("jobs.avant-migration-0001.db")
    with closing(sqlite3.connect(container.settings.db_path)) as source, closing(sqlite3.connect(backup)) as target:
        source.backup(target)
    unreadable = container.settings.db_path.with_name("jobs.avant-migration-0002.db")
    unreadable.write_bytes(b"pas une base")

    container.account.delete_account(user_id)

    assert container.jobs.list_jobs(user_id) == [] and container.jobs.list_rejected_jobs(user_id) == []
    with container.database.session() as session:
        assert CorrectionRepository(session, user_id).list_all() == []
        assert EngineCallRepository(session, user_id).list_all() == []
    assert container.queries.list_queries(user_id) == []
    assert container.cv.get_status(user_id).updated_at is None
    assert stored_cv_text(container, user_id) is None
    # Le quota repart de zéro : les lancements sont effacés aussi
    assert container.search.remaining_searches(user_id) == MAX_SEARCHES_PER_DAY
    # Seuls restent des totaux du mois, sans adresse : un compte supprimé, une recherche, deux pages trouvées
    [gone] = container.usage.get_overview().accounts
    assert (gone.deleted, gone.email, gone.plan, gone.runs, gone.found_count) == (True, None, "free", 1, 2)
    with closing(sqlite3.connect(container.settings.db_path)) as connection:
        [(month,)] = connection.execute("SELECT DISTINCT month FROM archived_usage").fetchall()
    assert month == datetime.now(UTC).strftime("%Y-%m")
    # La copie reste, pour revenir en arrière après une migration ratée : seules ses données en sont retirées
    with closing(sqlite3.connect(backup)) as copy:
        for table in ("jobs", "rejected_jobs", "search_queries", "search_runs"):
            assert copy.execute(f"SELECT COUNT(*) FROM {table} WHERE user_id = ?", (user_id,)).fetchone() == (0,)
        assert copy.execute("SELECT email FROM users WHERE id = ?", (user_id,)).fetchone() == (None,)
        assert copy.execute("SELECT COUNT(*) FROM search_queries WHERE user_id = ?", (bob_id,)).fetchone() == (1,)
        assert copy.execute("SELECT email FROM users WHERE id = ?", (bob_id,)).fetchone() == ("bob@exemple.fr",)
    # Une copie illisible ne peut pas être nettoyée : elle est effacée
    assert not unreadable.exists()
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


def test_owner_is_also_removed_from_a_backup_older_than_accounts(container, tmp_path):
    # Avant les comptes, les tables n'avaient pas de colonne user_id : tout y était au propriétaire
    backup = container.settings.db_path.with_name("jobs.avant-migration-0001.db")
    with closing(sqlite3.connect(backup)) as copy:
        copy.execute("CREATE TABLE jobs (url TEXT PRIMARY KEY, title TEXT)")
        copy.execute("INSERT INTO jobs VALUES ('https://a/1', 'Offre')")
        copy.commit()

    assert container.database.purge_user_from_backups(BOB) == 1
    with closing(sqlite3.connect(backup)) as copy:
        assert copy.execute("SELECT COUNT(*) FROM jobs").fetchone() == (1,)

    container.account.delete_account(DEFAULT_USER_ID)
    with closing(sqlite3.connect(backup)) as copy:
        assert copy.execute("SELECT COUNT(*) FROM jobs").fetchone() == (0,)


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


def test_guest_accounts_left_unused_too_long_are_deleted(container, valid_pdf):
    now = datetime(2026, 10, 9, tzinfo=UTC)
    limit = timedelta(days=INACTIVE_ACCOUNT_DAYS)
    last_seen = {
        "alice@exemple.fr": now - limit - timedelta(days=1),
        "bob@exemple.fr": now - limit + timedelta(days=1),
        "carol@exemple.fr": now - limit - timedelta(days=30),
    }
    with container.database.session() as session:
        users = UserRepository(session)
        ids = {email: users.get_or_create_user_id(email) for email in last_seen}
        for email, seen in last_seen.items():
            assert users.record_activity(ids[email], seen, now + timedelta(days=1))
        # Le propriétaire aussi est resté longtemps sans venir : il n'est jamais concerné
        users.record_activity(DEFAULT_USER_ID, now - 3 * limit, now + timedelta(days=1))
        # Carol a déjà supprimé son compte : sa ligne, sans adresse, n'est pas un compte à supprimer
        users.forget_user(ids["carol@exemple.fr"])
    alice, bob = ids["alice@exemple.fr"], ids["bob@exemple.fr"]
    for user_id in (alice, bob):
        container.cv.save_cv(user_id, valid_pdf)
        container.queries.add_query(user_id, "CDI", "data engineer")

    assert container.account.delete_inactive_accounts(now) == 1

    assert container.queries.list_queries(alice) == [] and container.cv.get_status(alice).updated_at is None
    assert len(container.queries.list_queries(bob)) == 1 and container.cv.get_status(bob).updated_at is not None
    assert container.queries.list_queries(DEFAULT_USER_ID)
    with container.database.session() as session:
        emails = {user.id: user.email for user in UserRepository(session).list_users()}
    assert (emails[alice], emails[bob]) == (None, "bob@exemple.fr")
    # Rien de plus à supprimer au passage suivant
    assert container.account.delete_inactive_accounts(now) == 0


def make_inactive_guest(container, email, now):
    with container.database.session() as session:
        users = UserRepository(session)
        user_id = users.get_or_create_user_id(email)
        last_seen = now - timedelta(days=INACTIVE_ACCOUNT_DAYS + 1)
        users.record_activity(user_id, last_seen, datetime.now(UTC) + timedelta(days=1))
    return user_id


def guest_emails(container):
    with container.database.session() as session:
        return {user.email for user in UserRepository(session).list_users()} - {None}


def test_inactive_accounts_are_deleted_at_most_once_a_day(container):
    # Une machine mise en veille ne redémarre pas : la suppression ne peut pas compter sur le démarrage
    now = datetime(2026, 10, 9, 8, tzinfo=UTC)
    make_inactive_guest(container, "alice@exemple.fr", now)

    container.account.delete_inactive_accounts_if_due(now)
    assert guest_emails(container) == set()

    make_inactive_guest(container, "bob@exemple.fr", now)
    container.account.delete_inactive_accounts_if_due(now + timedelta(hours=10))
    assert guest_emails(container) == {"bob@exemple.fr"}

    container.account.delete_inactive_accounts_if_due(now + timedelta(days=1))
    assert guest_emails(container) == set()


def test_failed_deletion_of_inactive_accounts_does_not_reach_the_caller(container, monkeypatch):
    now = datetime(2026, 10, 9, 8, tzinfo=UTC)
    make_inactive_guest(container, "alice@exemple.fr", now)
    with monkeypatch.context() as patch:
        patch.setattr(container.database, "purge_user_from_backups", lambda user_id: 1 / 0)
        # La requête qui a déclenché la suppression n'a pas à échouer avec elle
        container.account.delete_inactive_accounts_if_due(now)

    # Retentée le lendemain
    make_inactive_guest(container, "bob@exemple.fr", now + timedelta(days=1))
    container.account.delete_inactive_accounts_if_due(now + timedelta(days=1))
    assert guest_emails(container) == set()


RAW_CV = "Alice Martin\nalice.martin@exemple.fr - 06 12 34 56 78\n12 rue des Lilas, 75011 Paris\nIngénieure IA, Python"
ANONYMOUS_CV = "[nom] [nom]\n[e-mail] - [téléphone]\n[adresse], 75011 Paris\nIngénieure IA, Python"


def stored_cv_text(container, user_id: int) -> str | None:
    with container.database.session() as session:
        return CvTextRepository(session, user_id).get_content()


def test_saved_cv_is_stored_without_its_contact_details_and_read_from_the_database(container, valid_pdf, monkeypatch):
    monkeypatch.setattr(CvPdfReader, "read_text", lambda self, data: RAW_CV)

    container.cv.save_cv(BOB, valid_pdf, ["Alice Martin"])

    assert stored_cv_text(container, BOB) == ANONYMOUS_CV
    assert stored_cv_text(container, CAROL) is None
    # Le PDF n'a pas été gardé : c'est le texte enregistré qui part au modèle
    monkeypatch.setattr(CvPdfReader, "read_text", lambda self, data: pytest.fail("un PDF a été lu"))
    assert container.cv.read_text(BOB) == ANONYMOUS_CV


def test_new_cv_replaces_the_stored_text(container, valid_pdf, monkeypatch):
    monkeypatch.setattr(CvPdfReader, "read_text", lambda self, data: RAW_CV)
    container.cv.save_cv(BOB, valid_pdf)

    monkeypatch.setattr(CvPdfReader, "read_text", lambda self, data: "Nouveau CV, bob@exemple.fr")
    container.cv.save_cv(BOB, valid_pdf)

    assert container.cv.read_text(BOB) == "Nouveau CV, [e-mail]"


def test_reading_the_cv_of_a_user_who_has_none_is_a_user_error(container):
    with pytest.raises(InvalidInputError):
        container.cv.read_text(BOB)


def test_search_sends_the_anonymized_cv_to_the_model(container, evaluator, valid_pdf, monkeypatch):
    monkeypatch.setattr(CvPdfReader, "read_text", lambda self, data: RAW_CV)
    container.cv.save_cv(BOB, valid_pdf, ["Alice Martin"])
    container.queries.add_query(BOB, "CDI", "data engineer")

    container.search.run_search(BOB)

    assert {cv for cv, _ in evaluator.evaluated} == {ANONYMOUS_CV}
