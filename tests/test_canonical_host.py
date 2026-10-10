from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from jobgrep.api.canonical_host import CanonicalHostMiddleware

SITE = "https://jobgrep.exemple"
OTHER = "http://instance.hebergeur.exemple"


async def answer(request):
    return PlainTextResponse("servi")


def client(base_url: str) -> TestClient:
    routes = [Route("/{path:path}", answer, methods=["GET", "POST"])]
    middleware = [Middleware(CanonicalHostMiddleware, site_url=SITE)]
    return TestClient(Starlette(routes=routes, middleware=middleware), base_url=base_url, follow_redirects=False)


def test_page_asked_at_another_address_is_sent_to_the_site():
    for path in ("/", "/fonctionnement", "/offres?etat=todo", "/robots.txt", "/un%20chemin"):
        response = client(OTHER).get(path)

        assert response.status_code == 301
        assert response.headers["location"] == SITE + path


def test_site_address_is_served():
    response = client(SITE).get("/fonctionnement")

    assert response.status_code == 200
    assert response.text == "servi"


def test_api_is_served_at_any_address():
    # La sonde de disponibilité l'appelle à l'adresse de l'hébergeur
    for path in ("/api", "/api/health"):
        assert client(OTHER).get(path).status_code == 200
    # Seul le premier segment compte
    assert client(OTHER).get("/apiculture").status_code == 301


def test_request_that_changes_data_is_not_redirected():
    assert client(OTHER).post("/formulaire").status_code == 200


def test_redirection_never_leaves_the_site():
    response = client(OTHER).get("//ailleurs.exemple/page")

    assert response.headers["location"].startswith(SITE + "/")
