"""Vérifie que l'interface Streamlit se charge et reste fermée sans mot de passe : pas ses écrans en détail."""

from pathlib import Path

import pytest
from helpers import job, rejected_job
from streamlit.testing.v1 import AppTest

import projet_recherche_emploi
from projet_recherche_emploi import container as container_module
from projet_recherche_emploi.config import DEFAULT_USER_ID
from projet_recherche_emploi.data.job_repository import JobRepository
from projet_recherche_emploi.data.rejected_job_repository import RejectedJobRepository

APP_PATH = Path(projet_recherche_emploi.__file__).parent / "ui" / "app.py"


@pytest.fixture
def app(tmp_path, monkeypatch, container):
    # Le dossier courant est vide : le .streamlit/secrets.toml de la machine n'est pas lu
    monkeypatch.chdir(tmp_path)
    # load_dotenv cherche .env à partir du fichier appelant, donc trouverait celui du projet
    monkeypatch.setattr("dotenv.load_dotenv", lambda: False)
    monkeypatch.setattr(container_module, "_container", container)
    return AppTest.from_file(str(APP_PATH), default_timeout=30)


def test_application_shows_the_offers_of_the_owner(app, container, valid_pdf):
    container.cv.save_cv(DEFAULT_USER_ID, valid_pdf)
    with container.database.session() as session:
        JobRepository(session, DEFAULT_USER_ID).insert_jobs([job("https://a/1"), job("https://a/2")])
        RejectedJobRepository(session, DEFAULT_USER_ID).insert_rejected_jobs([rejected_job("https://r/1")])
    first_job = container.jobs.list_jobs(DEFAULT_USER_ID)[0]
    container.jobs.set_applied(DEFAULT_USER_ID, first_job.id, True)

    app.run()

    assert not app.exception
    assert {metric.label: metric.value for metric in app.metric[:3]} == {
        "Offres": "2",
        "Postulées": "1",
        "À traiter": "1",
    }
    [search_button] = [button for button in app.button if button.label == "Lancer une recherche"]
    assert search_button.disabled is False


def test_search_button_is_disabled_without_cv(app):
    app.run()

    assert not app.exception
    [search_button] = [button for button in app.button if button.label == "Lancer une recherche"]
    assert search_button.disabled is True


def test_nothing_is_shown_before_the_password(app, container):
    container.settings.app_password = "sésame"
    with container.database.session() as session:
        JobRepository(session, DEFAULT_USER_ID).insert_jobs([job("https://a/1")])

    app.run()

    assert not app.exception
    assert [field.label for field in app.text_input] == ["Mot de passe"]
    assert len(app.metric) == 0 and len(app.button) == 0 and len(app.sidebar) == 0

    app.text_input[0].set_value("mauvais").run()
    assert [error.value for error in app.error] == ["Mot de passe incorrect"]
    assert len(app.metric) == 0

    app.text_input[0].set_value("sésame").run()
    assert not app.exception
    assert app.metric[0].value == "1"
