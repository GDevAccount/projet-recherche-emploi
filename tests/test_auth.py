import pytest
from helpers import job

from projet_recherche_emploi.config import DEFAULT_USER_ID, Settings
from projet_recherche_emploi.data.job_repository import JobRepository
from projet_recherche_emploi.data.user_repository import UserRepository
from projet_recherche_emploi.errors import ConfigurationError
from projet_recherche_emploi.services.auth_service import AuthService


def auth_service(database, **settings) -> AuthService:
    defaults = {"owner_email": "Proprietaire@Exemple.fr", "allowed_emails": "alice@exemple.fr, Bob@Exemple.fr ,"}
    return AuthService(Settings(**defaults | settings), database)


@pytest.fixture
def auth(database):
    return auth_service(database)


def test_owner_gets_the_default_user(auth):
    assert auth.resolve_user_id("proprietaire@exemple.fr", True) == DEFAULT_USER_ID
    assert auth.resolve_user_id(" PROPRIETAIRE@exemple.fr ", True) == DEFAULT_USER_ID


def test_invited_users_get_their_own_stable_account(auth):
    alice = auth.resolve_user_id("alice@exemple.fr", True)
    bob = auth.resolve_user_id("bob@exemple.fr", True)

    assert len({DEFAULT_USER_ID, alice, bob}) == 3
    assert auth.resolve_user_id("ALICE@exemple.fr", True) == alice
    assert auth.resolve_user_id("bob@exemple.fr", True) == bob


def test_first_guest_never_gets_the_owner_account(auth):
    # Même si l'invité se connecte avant le propriétaire, sur une base toute neuve
    assert auth.resolve_user_id("alice@exemple.fr", True) != DEFAULT_USER_ID


def test_guest_does_not_see_the_owner_data(auth, database):
    with database.session() as session:
        JobRepository(session, DEFAULT_USER_ID).insert_jobs([job("https://a/1")])

    alice = auth.resolve_user_id("alice@exemple.fr", True)

    with database.session() as session:
        assert JobRepository(session, alice).list_jobs() == []


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
def test_other_addresses_are_refused_and_create_no_account(auth, database, email, email_verified):
    assert auth.resolve_user_id(email, email_verified) is None
    with database.session() as session:
        assert [user.email for user in UserRepository(session).list_users()] == [None]


def test_star_opens_the_application_to_any_verified_google_account(database):
    auth = auth_service(database, allowed_emails="*")

    stranger = auth.resolve_user_id("inconnu@exemple.fr", True)

    assert stranger not in (None, DEFAULT_USER_ID)
    assert auth.resolve_user_id("inconnu@exemple.fr", True) == stranger
    assert auth.resolve_user_id("proprietaire@exemple.fr", True) == DEFAULT_USER_ID
    # Une adresse que Google n'a pas vérifiée reste refusée
    assert auth.resolve_user_id("autre@exemple.fr", False) is None


def test_removed_guest_is_refused(database):
    assert auth_service(database).resolve_user_id("alice@exemple.fr", True) is not None

    auth = auth_service(database, allowed_emails="bob@exemple.fr")

    assert auth.resolve_user_id("alice@exemple.fr", True) is None


def test_missing_owner_is_an_error(database):
    auth = auth_service(database, owner_email="")

    with pytest.raises(ConfigurationError, match="OWNER_EMAIL"):
        auth.resolve_user_id("alice@exemple.fr", True)


def test_password_is_only_required_when_set(database):
    open_instance = auth_service(database)
    protected_instance = auth_service(database, app_password="sésame")

    assert open_instance.password_required is False
    # Sans mot de passe défini, aucune saisie ne « correspond », pas même la chaîne vide
    assert open_instance.password_matches("") is False
    assert protected_instance.password_required is True
    assert protected_instance.password_matches("sésame") is True
    assert protected_instance.password_matches("sesame") is False


def test_settings_are_read_from_the_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("OWNER_EMAIL", "  proprietaire@exemple.fr ")

    settings = Settings()

    assert settings.db_path == tmp_path / "jobs.db"
    assert settings.owner_email == "proprietaire@exemple.fr"
    # Un secret ne doit pas apparaître dans un log qui afficherait les réglages
    assert "sésame" not in repr(Settings(app_password="sésame"))


def test_complete_configurations_are_accepted(database):
    for settings in (
        # Instance locale sans protection : l'API refuse alors tout d'elle-même
        {"owner_email": ""},
        {"app_password": "sesame", "auth_cookie_secret": "secret"},
        {"google_client_id": "id.apps.googleusercontent.com", "auth_cookie_secret": "secret"},
    ):
        auth_service(database, **settings).check_configuration()


@pytest.mark.parametrize(
    ("settings", "missing"),
    [
        ({"google_client_id": "id", "auth_cookie_secret": "secret", "owner_email": " "}, "OWNER_EMAIL"),
        ({"google_client_id": "id"}, "AUTH_COOKIE_SECRET"),
        # Sans secret, aucune session ne s'ouvrirait : le mot de passe serait refusé à tout le monde
        ({"app_password": "sesame"}, "AUTH_COOKIE_SECRET"),
    ],
)
def test_half_configured_login_stops_the_server(database, settings, missing):
    # Le message nomme la variable d'environnement à définir
    with pytest.raises(ConfigurationError, match=missing):
        auth_service(database, **settings).check_configuration()
