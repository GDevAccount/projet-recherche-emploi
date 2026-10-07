import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from projet_recherche_emploi.config import MAX_SEARCHES_PER_DAY
from projet_recherche_emploi.public_pages import build_routes


def client(environment: dict[str, str]) -> TestClient:
    return TestClient(Starlette(routes=build_routes(environment)))


@pytest.mark.parametrize(
    ("path", "title"),
    [("/confidentialite", "Règles de confidentialité"), ("/conditions", "Conditions d'utilisation")],
)
def test_legal_page_is_plain_html_readable_without_javascript(path, title):
    response = client({"CONTACT_EMAIL": "contact@exemple.fr"}).get(path)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert f"<h1>{title}</h1>" in response.text
    assert "contact@exemple.fr" in response.text
    assert "<script" not in response.text
    # Aucun champ de remplacement oublié dans le texte
    assert "{contact}" not in response.text and "{max_searches}" not in response.text


def test_conditions_state_the_real_quota_and_link_to_the_privacy_rules():
    text = client({}).get("/conditions").text

    assert f"limité à {MAX_SEARCHES_PER_DAY} par jour" in text
    assert 'href="/confidentialite"' in text


def test_privacy_rules_name_who_receives_the_data():
    text = client({}).get("/confidentialite").text

    for recipient in ("Google", "OpenAI", "Tavily", "Fly.io"):
        assert recipient in text


def test_verification_file_is_served_only_when_configured():
    assert client({}).get("/google1a2b3c.html").status_code == 404

    response = client({"GOOGLE_SITE_VERIFICATION_FILE": "google1a2b3c.html"}).get("/google1a2b3c.html")

    assert response.status_code == 200
    assert response.text == "google-site-verification: google1a2b3c.html"


@pytest.mark.parametrize("name", ["../secret.html", "google.html", "googleXYZ.html", "google1a.html/x", "autre.html"])
def test_unexpected_verification_file_names_are_ignored(name):
    paths = [route.path for route in build_routes({"GOOGLE_SITE_VERIFICATION_FILE": name})]

    assert paths == ["/confidentialite", "/conditions"]
