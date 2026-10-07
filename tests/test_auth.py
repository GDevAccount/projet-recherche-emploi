import tomllib

import pytest

from projet_recherche_emploi.auth import resolve_user_id
from projet_recherche_emploi.auth_secrets import build_secrets
from projet_recherche_emploi.config import DEFAULT_USER_ID
from projet_recherche_emploi.job_repository import JobRepository
from projet_recherche_emploi.search_run_repository import SearchRunRepository
from projet_recherche_emploi.user_repository import UserRepository

GOOGLE_ENVIRONMENT = {
    "AUTH_REDIRECT_URI": "https://exemple.fly.dev/oauth2callback",
    "AUTH_COOKIE_SECRET": 'secret avec "guillemets" et \\ barre',
    "GOOGLE_CLIENT_ID": "id.apps.googleusercontent.com",
    "GOOGLE_CLIENT_SECRET": "secret",
    "OWNER_EMAIL": "proprietaire@exemple.fr",
}


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    monkeypatch.setenv("OWNER_EMAIL", "Proprietaire@Exemple.fr")
    monkeypatch.setenv("ALLOWED_EMAILS", "alice@exemple.fr, Bob@Exemple.fr ,")
    return tmp_path / "jobs.db"


def test_owner_gets_the_default_user(db_path):
    assert resolve_user_id(db_path, "proprietaire@exemple.fr", True) == DEFAULT_USER_ID
    assert resolve_user_id(db_path, " PROPRIETAIRE@exemple.fr ", True) == DEFAULT_USER_ID


def test_invited_users_get_their_own_stable_account(db_path):
    alice = resolve_user_id(db_path, "alice@exemple.fr", True)
    bob = resolve_user_id(db_path, "bob@exemple.fr", True)

    assert len({DEFAULT_USER_ID, alice, bob}) == 3
    assert resolve_user_id(db_path, "ALICE@exemple.fr", True) == alice
    assert resolve_user_id(db_path, "bob@exemple.fr", True) == bob


def test_first_guest_never_gets_the_owner_account(db_path):
    # Même si l'invité se connecte avant le propriétaire, sur une base toute neuve
    assert resolve_user_id(db_path, "alice@exemple.fr", True) != DEFAULT_USER_ID


def test_guest_does_not_see_the_owner_data(db_path):
    JobRepository(db_path).insert_jobs(
        [{"url": "https://a/1", "title": "t", "content": "c", "score": 1.0,
          "contract_type": "CDI", "query": "q", "match_reason": "r"}]
    )

    alice = resolve_user_id(db_path, "alice@exemple.fr", True)

    assert JobRepository(db_path, alice).list_jobs() == []


@pytest.mark.parametrize(
    ("email", "email_verified"),
    [
        ("inconnu@exemple.fr", True),
        ("alice@exemple.fr", False),
        ("alice@exemple.fr", None),
        ("proprietaire@exemple.fr", False),
        (None, True),
        ("", True),
    ],
)
def test_other_addresses_are_refused_and_create_no_account(db_path, email, email_verified):
    assert resolve_user_id(db_path, email, email_verified) is None
    assert [user["email"] for user in UserRepository(db_path).list_users()] == [None]


def test_removed_guest_is_refused(db_path, monkeypatch):
    assert resolve_user_id(db_path, "alice@exemple.fr", True) is not None

    monkeypatch.setenv("ALLOWED_EMAILS", "bob@exemple.fr")

    assert resolve_user_id(db_path, "alice@exemple.fr", True) is None


def test_missing_owner_is_an_error(db_path, monkeypatch):
    monkeypatch.delenv("OWNER_EMAIL")

    with pytest.raises(ValueError, match="OWNER_EMAIL"):
        resolve_user_id(db_path, "alice@exemple.fr", True)


def test_quota_is_per_user_and_per_day(db_path):
    alice, bob = SearchRunRepository(db_path, 2), SearchRunRepository(db_path, 3)
    today = "2000-01-01 00:00:00"

    assert alice.record_run(today, limit=2) is True
    assert alice.record_run(today, limit=2) is True
    assert alice.record_run(today, limit=2) is False
    assert alice.count_runs_since(today) == 2

    assert bob.count_runs_since(today) == 0
    assert bob.record_run(today, limit=2) is True

    # Les recherches d'avant minuit ne comptent plus le lendemain
    tomorrow = "2999-01-01 00:00:00"
    assert alice.count_runs_since(tomorrow) == 0


def test_run_without_limit_is_always_recorded(db_path):
    owner = SearchRunRepository(db_path)

    assert all(owner.record_run() for _ in range(5))
    assert owner.count_runs_since("2000-01-01 00:00:00") == 5


def test_secrets_are_not_written_without_google_variables():
    assert build_secrets({"OWNER_EMAIL": "proprietaire@exemple.fr", "GOOGLE_CLIENT_ID": "  "}) is None


def test_secrets_hold_the_streamlit_auth_section():
    secrets = tomllib.loads(build_secrets(GOOGLE_ENVIRONMENT))

    assert secrets == {
        "auth": {
            "redirect_uri": GOOGLE_ENVIRONMENT["AUTH_REDIRECT_URI"],
            "cookie_secret": GOOGLE_ENVIRONMENT["AUTH_COOKIE_SECRET"],
            "client_id": GOOGLE_ENVIRONMENT["GOOGLE_CLIENT_ID"],
            "client_secret": GOOGLE_ENVIRONMENT["GOOGLE_CLIENT_SECRET"],
            "server_metadata_url": "https://accounts.google.com/.well-known/openid-configuration",
        }
    }


@pytest.mark.parametrize("missing", list(GOOGLE_ENVIRONMENT))
def test_incomplete_google_configuration_is_an_error(missing):
    environment = {name: value for name, value in GOOGLE_ENVIRONMENT.items() if name != missing}

    with pytest.raises(ValueError, match=missing):
        build_secrets(environment)
