import json
from pathlib import Path

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from jobgrep.api.frontend import HASHED_FILE_PATTERN, build_frontend_routes
from jobgrep.config import Settings

FRONTEND = Path(__file__).parent.parent / "frontend"


@pytest.fixture
def client(tmp_path):
    front = tmp_path / "front"
    front.mkdir()
    (front / "index.html").write_text("<app-root></app-root>", encoding="utf-8")
    (front / "main-ABC12345.js").write_text("console.log('front')", encoding="utf-8")
    (front / "chunk-BBrCm5NO.js").write_text("", encoding="utf-8")
    (front / "theme-init.js").write_text("", encoding="utf-8")
    (front / "robots.txt").write_text("User-agent: *", encoding="utf-8")
    return TestClient(Starlette(routes=build_frontend_routes(Settings(frontend_dir=front))))


def test_home_page_describes_the_application_without_javascript():
    # Lu par les robots de Google pour valider l'écran de connexion : ils n'exécutent pas le JavaScript
    page = (FRONTEND / "src" / "index.html").read_text(encoding="utf-8")

    assert "<h1>JobGrep</h1>" in page
    assert '<meta name="description"' in page
    assert "offres d'emploi" in page
    assert 'href="/confidentialite"' in page
    assert 'href="/conditions"' in page
    # Ce qui mène un moteur de recherche à la page de présentation, et lui dit quelle adresse retenir
    assert 'href="/fonctionnement"' in page
    assert '<link rel="canonical" href="https://jobgrep.fr/">' in page
    assert '<meta property="og:image" content="https://jobgrep.fr/social-card.png">' in page
    assert (FRONTEND / "public" / "social-card.png").is_file()


def test_public_files_are_not_taken_for_hashed_files():
    # Un nom qui finit comme une empreinte serait gardé un an par le navigateur, alors que le fichier peut changer
    names = [path.name for path in (FRONTEND / "public").iterdir()]

    assert names
    assert [name for name in names if HASHED_FILE_PATTERN.search(name)] == []


def test_manifest_names_the_application_and_icons_that_exist():
    public = FRONTEND / "public"
    manifest = json.loads((public / "manifest.webmanifest").read_text(encoding="utf-8"))

    assert manifest["short_name"] == "JobGrep"
    assert manifest["start_url"] == "/"
    assert manifest["icons"]
    for icon in manifest["icons"]:
        assert (public / icon["src"]).is_file()
    assert 'href="manifest.webmanifest"' in (FRONTEND / "src" / "index.html").read_text(encoding="utf-8")


def test_front_is_served_at_the_root(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "<app-root>" in response.text
    # La page d'accueil garde son nom d'un build à l'autre : le navigateur doit la redemander
    assert response.headers["cache-control"] == "no-cache"

    script = client.get("/main-ABC12345.js")
    assert script.text == "console.log('front')"
    # Son nom porte son empreinte : il ne change jamais, le navigateur le garde
    assert script.headers["cache-control"] == "public, max-age=31536000, immutable"
    # Un fichier sans empreinte peut changer d'un build à l'autre
    assert "immutable" in client.get("/chunk-BBrCm5NO.js").headers["cache-control"]
    for path in ("/robots.txt", "/theme-init.js"):
        assert "cache-control" not in client.get(path).headers


def test_unknown_address_is_left_to_the_angular_router(client):
    for path in ("/offres", "/profil", "/une/adresse/inconnue"):
        response = client.get(path)
        assert response.status_code == 200
        assert "<app-root>" in response.text
        assert response.headers["cache-control"] == "no-cache"


def test_missing_file_is_not_answered_with_the_home_page(client):
    assert client.get("/main-ANCIEN.js").status_code == 404


def test_unknown_api_address_is_not_answered_with_the_home_page(client):
    for path in ("/api", "/api/", "/api/inconnu"):
        assert client.get(path).status_code == 404
    # Seul le premier segment compte : une page du front peut contenir « api » ailleurs
    assert client.get("/apiculture").status_code == 200
    assert client.get("/offres/api").status_code == 200


def test_former_address_redirects_to_the_root(client):
    # Le front était servi sous /frontend tant que Streamlit occupait la racine
    for former, current in (
        ("/frontend", "/"),
        ("/frontend/", "/"),
        ("/frontend/offres", "/offres"),
        ("/frontend/rejets?motif=lieu", "/rejets?motif=lieu"),
    ):
        response = client.get(former, follow_redirects=False)
        assert response.status_code == 308
        assert response.headers["location"] == current


def test_front_does_not_reach_outside_its_directory(client, tmp_path):
    (tmp_path / "secret.txt").write_text("secret", encoding="utf-8")

    for path in ("/../secret.txt", "/%2e%2e/secret.txt", "/..%2fsecret.txt"):
        assert "secret" not in client.get(path).text


def test_without_a_build_the_front_is_not_served(tmp_path):
    assert build_frontend_routes(Settings(frontend_dir=tmp_path)) == []
