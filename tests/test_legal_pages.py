from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).parents[1] / "src" / "projet_recherche_emploi" / "app.py")


@pytest.mark.parametrize(
    ("page", "title"),
    [("confidentialite", "Règles de confidentialité"), ("conditions", "Conditions d'utilisation")],
)
def test_legal_page_is_public_and_shows_nothing_else(page, title, monkeypatch):
    monkeypatch.setenv("CONTACT_EMAIL", "contact@exemple.fr")
    # Un mot de passe est exigé : la page légale doit s'afficher sans le demander
    monkeypatch.setenv("APP_PASSWORD", "secret")
    at = AppTest.from_file(APP, default_timeout=30)
    at.query_params["page"] = page

    at.run()

    assert not at.exception
    text = at.markdown[0].value
    assert text.startswith(f"# {title}")
    assert "contact@exemple.fr" in text
    assert "{" not in text
    # Aucun champ, bouton ni tableau : rien de l'application n'est accessible depuis cette page
    assert len(at.text_input) == len(at.button) == len(at.dataframe) == len(at.metric) == 0


def test_unknown_page_still_requires_the_password(monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "secret")
    at = AppTest.from_file(APP, default_timeout=30)
    at.query_params["page"] = "autre"

    at.run()

    assert not at.exception
    assert [field.label for field in at.text_input] == ["Mot de passe"]
    assert len(at.button) == len(at.dataframe) == len(at.metric) == 0
