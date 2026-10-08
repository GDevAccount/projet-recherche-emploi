import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from projet_recherche_emploi.api.frontend import build_frontend_routes
from projet_recherche_emploi.config import Settings


@pytest.fixture
def client(tmp_path):
    (tmp_path / "index.html").write_text("<app-root></app-root>", encoding="utf-8")
    (tmp_path / "main-ABC123.js").write_text("console.log('front')", encoding="utf-8")
    return TestClient(Starlette(routes=build_frontend_routes(Settings(frontend_dir=tmp_path))))


def test_front_is_served_under_its_path(client):
    for path in ("/frontend", "/frontend/"):
        response = client.get(path)
        assert response.status_code == 200
        assert "<app-root>" in response.text
        # La page d'accueil garde son nom d'un build à l'autre : le navigateur doit la redemander
        assert response.headers["cache-control"] == "no-cache"

    script = client.get("/frontend/main-ABC123.js")
    assert script.text == "console.log('front')"
    assert "cache-control" not in script.headers


def test_unknown_address_is_left_to_the_angular_router(client):
    response = client.get("/frontend/offres/12")

    assert response.status_code == 200
    assert "<app-root>" in response.text


def test_missing_file_is_not_answered_with_the_home_page(client):
    assert client.get("/frontend/main-ANCIEN.js").status_code == 404


def test_front_does_not_reach_outside_its_directory(client, tmp_path):
    (tmp_path.parent / "secret.txt").write_text("secret", encoding="utf-8")

    assert client.get("/frontend/../secret.txt").status_code == 404
    assert client.get("/frontend/%2e%2e/secret.txt").status_code == 404
    assert client.get("/").status_code == 404


def test_without_a_build_the_front_is_not_served(tmp_path):
    assert build_frontend_routes(Settings(frontend_dir=tmp_path)) == []
