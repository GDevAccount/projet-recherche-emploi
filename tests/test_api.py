import json

import pytest
from conftest import FakeEvaluator, FakeSearchEngine
from fastapi.testclient import TestClient
from helpers import blank_pdf, job

from projet_recherche_emploi.api.main import create_app
from projet_recherche_emploi.api.security import Identity
from projet_recherche_emploi.config import DEFAULT_QUERIES, DEFAULT_USER_ID, MAX_SEARCHES_PER_DAY, Settings
from projet_recherche_emploi.container import build_container
from projet_recherche_emploi.data.job_repository import JobRepository

ALICE = {"Authorization": "Bearer jeton-alice"}
BOB = {"Authorization": "Bearer jeton-bob"}
OWNER = {"Authorization": "Bearer jeton-proprietaire"}


class FakeIdentityVerifier:
    """Reconnaît les jetons « jeton-<nom> » sans appeler Google."""

    def verify(self, token):
        if not token.startswith("jeton-"):
            return None
        name = token.removeprefix("jeton-")
        return Identity(email=f"{name}@exemple.fr", email_verified=name != "non-verifie")


def make_client(tmp_path, evaluator=None, **settings) -> TestClient:
    container = build_container(
        Settings(data_dir=tmp_path, **settings), FakeSearchEngine(), evaluator or FakeEvaluator()
    )
    return TestClient(create_app(container, FakeIdentityVerifier()))


@pytest.fixture
def client(tmp_path):
    """API avec la connexion Google : un propriétaire, Alice et Bob invités."""
    return make_client(
        tmp_path,
        google_client_id="id.apps.googleusercontent.com",
        owner_email="proprietaire@exemple.fr",
        allowed_emails="alice@exemple.fr,bob@exemple.fr",
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
