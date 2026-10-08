import json
import time

import pytest
from conftest import FakeEvaluator, FakeSearchEngine
from fastapi.testclient import TestClient
from helpers import blank_pdf, job

from projet_recherche_emploi.api.main import create_app
from projet_recherche_emploi.api.security import Identity
from projet_recherche_emploi.config import (
    DEFAULT_QUERIES,
    DEFAULT_USER_ID,
    MAX_SEARCHES_PER_DAY,
    SESSION_DAYS,
    Settings,
)
from projet_recherche_emploi.container import build_container
from projet_recherche_emploi.data.job_repository import JobRepository

ALICE = {"Authorization": "Bearer jeton-alice"}
BOB = {"Authorization": "Bearer jeton-bob"}
OWNER = {"Authorization": "Bearer jeton-proprietaire"}
PASSWORD = {"Authorization": "Bearer sesame"}
SECRET = "secret-de-test"
FOREIGN_ORIGIN = {"Origin": "https://autre-site.exemple"}
QUERY = {"contract_type": "CDI", "query": "data engineer"}


class FakeIdentityVerifier:
    """Reconnaît les jetons « jeton-<nom> » sans appeler Google."""

    def verify(self, token):
        if not token.startswith("jeton-"):
            return None
        name = token.removeprefix("jeton-")
        return Identity(email=f"{name}@exemple.fr", email_verified=name != "non-verifie")


def make_client(tmp_path, evaluator=None, base_url="http://localhost", **settings) -> TestClient:
    container = build_container(
        Settings(data_dir=tmp_path, **settings), FakeSearchEngine(), evaluator or FakeEvaluator()
    )
    # Adresse locale : le cookie de session n'y est pas réservé à HTTPS, donc le client de test le renvoie
    return TestClient(create_app(container, FakeIdentityVerifier()), base_url=base_url)


@pytest.fixture
def client(tmp_path):
    """API avec la connexion Google : un propriétaire, Alice et Bob invités."""
    return make_client(
        tmp_path,
        google_client_id="id.apps.googleusercontent.com",
        owner_email="proprietaire@exemple.fr",
        allowed_emails="alice@exemple.fr,bob@exemple.fr",
        auth_cookie_secret=SECRET,
    )


def server_sent_events(text: str) -> list[tuple[str, dict]]:
    events = []
    for block in text.strip().split("\n\n"):
        name, data = block.split("\n")
        events.append((name.removeprefix("event: "), json.loads(data.removeprefix("data: "))))
    return events


def test_health_and_legal_pages_are_public(client):
    assert client.get("/api/health").json() == {"status": "ok"}
    assert client.get("/confidentialite").status_code == 200


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/me"),
        ("POST", "/api/session"),
        ("GET", "/api/jobs"),
        ("PATCH", "/api/jobs"),
        ("POST", "/api/jobs/delete"),
        ("GET", "/api/rejected-jobs"),
        ("GET", "/api/queries"),
        ("POST", "/api/queries"),
        ("DELETE", "/api/queries/1"),
        ("GET", "/api/cv"),
        ("PUT", "/api/cv"),
        ("POST", "/api/searches"),
    ],
)
def test_every_data_route_requires_an_identity(client, method, path):
    assert client.request(method, path).status_code == 401
    assert client.request(method, path, headers={"Authorization": "Bearer faux"}).status_code == 401


def test_every_route_is_covered_by_the_identity_test(client):
    # Une route ajoutée sans figurer dans le test ci-dessus ferait échouer celui-ci
    tested = test_every_data_route_requires_an_identity.pytestmark[0].args[1]
    routes = {
        (method.upper(), path.replace("{query_id}", "1"))
        for path, operations in client.app.openapi()["paths"].items()
        if path != "/api/health"
        for method in operations
        # La déconnexion ne lit aucune donnée : elle a son propre test
        if (method, path) != ("delete", "/api/session")
    }

    assert routes == set(tested)


def test_uninvited_or_unverified_address_is_forbidden(client):
    assert client.get("/api/jobs", headers={"Authorization": "Bearer jeton-inconnu"}).status_code == 403
    assert client.get("/api/jobs", headers={"Authorization": "Bearer jeton-non-verifie"}).status_code == 403


def test_account_tells_who_is_calling(client):
    owner = client.get("/api/me", headers=OWNER).json()
    alice = client.get("/api/me", headers=ALICE).json()

    assert owner == {
        "user_id": DEFAULT_USER_ID,
        "is_owner": True,
        "remaining_searches": None,
        "max_searches_per_day": MAX_SEARCHES_PER_DAY,
    }
    assert alice["is_owner"] is False and alice["remaining_searches"] == MAX_SEARCHES_PER_DAY
    assert alice["user_id"] not in (DEFAULT_USER_ID, client.get("/api/me", headers=BOB).json()["user_id"])


def test_queries_are_private_and_validated(client):
    created = client.post("/api/queries", headers=ALICE, json={"contract_type": "CDI", "query": " data engineer "})

    assert created.status_code == 201 and created.json()["query"] == "data engineer"
    assert [query["id"] for query in client.get("/api/queries", headers=ALICE).json()] == [created.json()["id"]]
    assert client.get("/api/queries", headers=BOB).json() == []
    assert len(client.get("/api/queries", headers=OWNER).json()) == len(DEFAULT_QUERIES)

    duplicate = client.post("/api/queries", headers=ALICE, json={"contract_type": "CDI", "query": "data engineer"})
    assert duplicate.status_code == 409 and duplicate.json() == {"detail": "Cette recherche existe déjà."}
    assert client.post("/api/queries", headers=ALICE, json={"contract_type": "CDI", "query": " "}).status_code == 422
    assert client.post("/api/queries", headers=ALICE, json={"contract_type": "?", "query": "x"}).status_code == 422

    query_path = f"/api/queries/{created.json()['id']}"
    assert client.delete(query_path, headers=BOB).status_code == 404
    assert client.delete(query_path, headers=ALICE).status_code == 204
    assert client.get("/api/queries", headers=ALICE).json() == []


def test_jobs_are_private(client):
    alice_id = client.get("/api/me", headers=ALICE).json()["user_id"]
    with client.app.state.container.database.session() as session:
        JobRepository(session, alice_id).insert_jobs([job("https://a/1"), job("https://a/2")])

    assert client.get("/api/jobs", headers=BOB).json() == []
    applied = {"url": "https://a/1", "applied": True}
    assert client.patch("/api/jobs", headers=BOB, json=applied).status_code == 404
    assert client.patch("/api/jobs", headers=ALICE, json=applied).status_code == 204
    deletion = {"urls": ["https://a/2"]}
    assert client.post("/api/jobs/delete", headers=BOB, json=deletion).json() == {"deleted": 0}
    assert client.post("/api/jobs/delete", headers=ALICE, json=deletion).json() == {"deleted": 1}

    [saved] = client.get("/api/jobs", headers=ALICE).json()
    assert (saved["url"], saved["applied"]) == ("https://a/1", True)
    # Les dates sortent avec leur fuseau : le front n'a pas à deviner qu'elles sont en UTC
    assert saved["created_at"].endswith(("Z", "+00:00")) and saved["applied_at"].endswith(("Z", "+00:00"))
    # Ni l'identifiant de l'utilisateur ni la marque de suppression ne sortent de l'API
    assert "user_id" not in saved and "deleted" not in saved


def test_cv_upload(client, valid_pdf):
    assert client.get("/api/cv", headers=ALICE).json() == {"updated_at": None}

    refused = client.put("/api/cv", headers=ALICE, files={"file": ("cv.pdf", blank_pdf(), "application/pdf")})
    assert refused.status_code == 422 and "PDF" in refused.json()["detail"]

    saved = client.put("/api/cv", headers=ALICE, files={"file": ("cv.pdf", valid_pdf, "application/pdf")})
    assert saved.status_code == 200 and saved.json()["updated_at"] is not None
    assert client.get("/api/cv", headers=BOB).json() == {"updated_at": None}


def test_search_is_streamed_then_counted(client, valid_pdf):
    refused = client.post("/api/searches", headers=ALICE)
    assert refused.status_code == 422

    client.put("/api/cv", headers=ALICE, files={"file": ("cv.pdf", valid_pdf, "application/pdf")})
    client.post("/api/queries", headers=ALICE, json={"contract_type": "CDI", "query": "data engineer"})
    response = client.post("/api/searches", headers=ALICE)

    assert response.status_code == 200 and response.headers["content-type"].startswith("text/event-stream")
    *progress, (last_name, summary) = server_sent_events(response.text)
    assert progress and {name for name, _ in progress} == {"progress"}
    assert last_name == "result"
    assert summary == {"found": 2, "new": 2, "kept": 1, "rejected": 1, "inserted": 1}
    assert [saved["url"] for saved in client.get("/api/jobs", headers=ALICE).json()] == ["https://x/data engineer/0"]
    assert len(client.get("/api/rejected-jobs", headers=ALICE).json()) == 1

    # Le refus n'avait pas entamé le quota, la recherche si
    assert client.get("/api/me", headers=ALICE).json()["remaining_searches"] == MAX_SEARCHES_PER_DAY - 1
    client.post("/api/searches", headers=ALICE)
    assert client.post("/api/searches", headers=ALICE).status_code == 429


def test_failed_search_ends_the_stream_with_an_error_without_leaking_its_cause(tmp_path, valid_pdf):
    class BrokenEvaluator:
        def evaluate(self, cv, pages):
            raise RuntimeError("clé sk-secrete refusée")
            yield

    client = make_client(tmp_path, BrokenEvaluator(), app_password="sesame")
    password = {"Authorization": "Bearer sesame"}
    client.put("/api/cv", headers=password, files={"file": ("cv.pdf", valid_pdf, "application/pdf")})

    response = client.post("/api/searches", headers=password)

    *_, last = server_sent_events(response.text)
    assert last == ("error", {"detail": "La recherche a échoué."})
    assert "sk-secrete" not in response.text


def test_without_google_the_password_identifies_the_owner(tmp_path):
    client = make_client(tmp_path, app_password="sesame")

    assert client.get("/api/me", headers={"Authorization": "Bearer sesame"}).json()["user_id"] == DEFAULT_USER_ID
    assert client.get("/api/me", headers={"Authorization": "Bearer autre"}).status_code == 401
    # Un jeton Google ne vaut rien tant que la connexion Google n'est pas réglée
    assert client.get("/api/me", headers=ALICE).status_code == 401
    assert client.get("/api/me").status_code == 401


def test_with_google_the_password_no_longer_opens_the_api(tmp_path):
    client = make_client(
        tmp_path, app_password="jeton-sesame", google_client_id="id", owner_email="proprietaire@exemple.fr"
    )

    assert client.get("/api/me", headers={"Authorization": "Bearer jeton-sesame"}).status_code == 403


def test_unprotected_api_refuses_every_data_route(tmp_path):
    client = make_client(tmp_path)

    assert client.get("/api/jobs").status_code == 503
    assert client.get("/api/jobs", headers={"Authorization": "Bearer "}).status_code == 503
    assert client.get("/api/health").status_code == 200


def test_google_login_without_owner_is_a_configuration_error(tmp_path):
    client = make_client(tmp_path, google_client_id="id")

    assert client.get("/api/jobs", headers=ALICE).status_code == 503


def test_cors_is_closed_unless_origins_are_listed(tmp_path):
    preflight = {"Origin": "http://localhost:4200", "Access-Control-Request-Method": "GET"}
    closed = make_client(tmp_path / "a", app_password="sesame")
    opened = make_client(tmp_path / "b", app_password="sesame", cors_origins="http://localhost:4200")

    assert "access-control-allow-origin" not in closed.options("/api/jobs", headers=preflight).headers
    allowed = opened.options("/api/jobs", headers=preflight).headers
    assert allowed["access-control-allow-origin"] == "http://localhost:4200"


def test_session_cookie_replaces_the_google_token(client):
    opened = client.post("/api/session", headers=ALICE)

    assert opened.status_code == 200 and opened.json() == client.get("/api/me", headers=ALICE).json()
    cookie = opened.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie and "path=/api" in cookie
    # Sans en-tête : le cookie seul désigne Alice, et ses données restent les siennes
    assert client.get("/api/me").json() == opened.json()
    assert client.post("/api/queries", json=QUERY).status_code == 201
    assert len(client.get("/api/queries", headers=ALICE).json()) == 1
    assert client.get("/api/queries", headers=BOB).json() == []

    assert client.delete("/api/session").status_code == 204
    assert client.get("/api/me").status_code == 401


def test_session_cookie_is_https_only_outside_the_developer_machine(tmp_path):
    settings = {"app_password": "sesame", "auth_cookie_secret": SECRET}
    online = make_client(tmp_path / "a", base_url="http://app.exemple.fr", **settings)
    local = make_client(tmp_path / "b", **settings)

    assert "secure" in online.post("/api/session", headers=PASSWORD).headers["set-cookie"].lower()
    assert "secure" not in local.post("/api/session", headers=PASSWORD).headers["set-cookie"].lower()


def test_session_cannot_be_opened_or_renewed_with_a_cookie(client):
    client.post("/api/session", headers=ALICE)

    # Un cookie volé ne doit pas pouvoir se prolonger lui-même
    assert client.post("/api/session").status_code == 401


def test_session_follows_the_guest_list(client):
    client.post("/api/session", headers=ALICE)

    client.app.state.container.settings.allowed_emails = "bob@exemple.fr"

    assert client.get("/api/me").status_code == 403


def test_expired_or_forged_session_is_refused(client):
    auth = client.app.state.container.auth
    token = client.post("/api/session", headers=ALICE).cookies["session"]
    body, signature = token.split(".")
    forged_body = auth.create_session_token("proprietaire@exemple.fr").split(".")[0]
    client.cookies.clear()

    def status_with(session):
        return client.get("/api/me", headers={"Cookie": f"session={session}"}).status_code

    assert status_with(token) == 200
    assert status_with(f"{forged_body}.{signature}") == 401
    assert status_with(f"{body}.") == 401
    assert status_with("sans-signature") == 401

    auth.clock = lambda: time.time() + (SESSION_DAYS + 1) * 24 * 3600
    assert status_with(token) == 401


def test_password_session_identifies_the_owner_until_the_password_changes(tmp_path):
    client = make_client(tmp_path / "a", app_password="sesame", auth_cookie_secret=SECRET)
    token = client.post("/api/session", headers=PASSWORD).cookies["session"]
    cookie = {"Cookie": f"session={token}"}

    assert client.get("/api/me").json()["user_id"] == DEFAULT_USER_ID

    changed = make_client(tmp_path / "b", app_password="nouveau", auth_cookie_secret=SECRET)
    assert changed.get("/api/me", headers=cookie).status_code == 401
    # Une session ouverte par mot de passe ne donne pas les données du propriétaire une fois Google activé
    google = make_client(
        tmp_path / "c",
        app_password="sesame",
        auth_cookie_secret=SECRET,
        google_client_id="id",
        owner_email="proprietaire@exemple.fr",
    )
    assert google.get("/api/me", headers=cookie).status_code == 401


def test_session_needs_a_signing_secret(tmp_path):
    client = make_client(tmp_path, app_password="sesame")

    opened = client.post("/api/session", headers=PASSWORD)

    assert opened.status_code == 503 and "AUTH_COOKIE_SECRET" in opened.json()["detail"]
    assert "set-cookie" not in opened.headers
    assert client.get("/api/me", headers={"Cookie": "session=x.y"}).status_code == 401


def test_cookie_is_refused_on_a_change_requested_by_another_site(tmp_path):
    client = make_client(
        tmp_path, app_password="sesame", auth_cookie_secret=SECRET, cors_origins="http://localhost:4200"
    )
    client.post("/api/session", headers=PASSWORD)

    refused = client.post("/api/queries", json=QUERY, headers=FOREIGN_ORIGIN)

    assert refused.status_code == 403
    assert len(client.get("/api/queries").json()) == len(DEFAULT_QUERIES)
    # Une lecture ne change rien, et le front (même adresse, ou origine listée dans CORS_ORIGINS) reste accepté
    assert client.get("/api/queries", headers=FOREIGN_ORIGIN).status_code == 200
    front = {"Origin": "http://localhost:4200"}
    assert client.post("/api/queries", json=QUERY, headers=front).status_code == 201
    same_host = {"Origin": "http://localhost"}
    assert client.post("/api/queries", json=QUERY | {"query": "autre"}, headers=same_host).status_code == 201
    # Avec l'en-tête Authorization, rien à craindre : un autre site ne peut pas le remplir
    client.cookies.clear()
    by_header = FOREIGN_ORIGIN | PASSWORD
    assert client.post("/api/queries", json=QUERY | {"query": "encore"}, headers=by_header).status_code == 201


def test_cors_lets_the_listed_front_send_the_session_cookie(tmp_path):
    client = make_client(tmp_path, app_password="sesame", cors_origins="http://localhost:4200")

    headers = client.get("/api/health", headers={"Origin": "http://localhost:4200"}).headers

    assert headers["access-control-allow-credentials"] == "true"
    assert headers["access-control-allow-origin"] == "http://localhost:4200"
