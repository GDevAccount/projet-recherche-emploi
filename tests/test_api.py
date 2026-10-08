import json
import time

import pytest
from conftest import FakeEvaluator, FakeSearchEngine
from fastapi.testclient import TestClient
from helpers import blank_pdf, job

from projet_recherche_emploi.api.main import create_app
from projet_recherche_emploi.api.security import Identity
from projet_recherche_emploi.config import (
    CONTRACT_TYPES,
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
        return Identity(
            email=f"{name}@exemple.fr",
            email_verified=name != "non-verifie",
            name=name.capitalize(),
            picture=f"https://lh3.googleusercontent.com/{name}",
        )


def make_client(tmp_path, evaluator=None, base_url="http://localhost", **settings) -> TestClient:
    # Sans front construit, sauf si le test en fournit un : celui de la machine ne doit pas répondre à sa place
    settings.setdefault("frontend_dir", tmp_path / "pas-de-front")
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


def test_config_tells_the_front_how_to_log_in(client, tmp_path):
    # Sans identité : le front la lit pour afficher son écran de connexion
    assert client.get("/api/config").json() == {
        "login_mode": "google",
        "google_client_id": "id.apps.googleusercontent.com",
        "contract_types": CONTRACT_TYPES,
    }

    with_password = make_client(tmp_path / "mot-de-passe", app_password="sesame").get("/api/config").json()
    assert with_password["login_mode"] == "password" and with_password["google_client_id"] is None

    unprotected = make_client(tmp_path / "ouverte").get("/api/config").json()
    assert unprotected["login_mode"] is None


def test_config_leaks_no_secret(tmp_path):
    client = make_client(
        tmp_path,
        app_password="sesame",
        google_client_id="id.apps.googleusercontent.com",
        auth_cookie_secret=SECRET,
        owner_email="proprietaire@exemple.fr",
        allowed_emails="alice@exemple.fr",
    )

    text = client.get("/api/config").text

    for secret in ("sesame", SECRET, "proprietaire@exemple.fr", "alice@exemple.fr"):
        assert secret not in text


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/me"),
        ("DELETE", "/api/me"),
        ("POST", "/api/session"),
        ("GET", "/api/jobs"),
        ("PATCH", "/api/jobs/1"),
        ("DELETE", "/api/jobs/1"),
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
        (method.upper(), path.replace("{query_id}", "1").replace("{job_id}", "1"))
        for path, operations in client.app.openapi()["paths"].items()
        # Routes publiques : elles ne lisent aucune donnée d'utilisateur, et ont leurs propres tests
        if path not in ("/api/health", "/api/config")
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
        "email": "proprietaire@exemple.fr",
        "name": "Proprietaire",
        "picture": "https://lh3.googleusercontent.com/proprietaire",
        # Le propriétaire a les recherches par défaut, mais pas encore de CV
        "can_search": False,
        "search_running": False,
        "remaining_searches": None,
        "max_searches_per_day": MAX_SEARCHES_PER_DAY,
    }
    assert alice["is_owner"] is False and alice["remaining_searches"] == MAX_SEARCHES_PER_DAY
    assert alice["user_id"] not in (DEFAULT_USER_ID, client.get("/api/me", headers=BOB).json()["user_id"])


def test_queries_are_private_and_validated(client):
    created = client.post("/api/queries", headers=ALICE, json={"contract_type": "CDI", "query": " data engineer "})

    assert created.status_code == 201 and created.json()["query"] == "data engineer"
    # Sans lieu ni télétravail, la recherche vaut pour toute la France
    assert (created.json()["location"], created.json()["remote"]) == ("", False)
    assert [query["id"] for query in client.get("/api/queries", headers=ALICE).json()] == [created.json()["id"]]
    assert client.get("/api/queries", headers=BOB).json() == []
    assert len(client.get("/api/queries", headers=OWNER).json()) == len(DEFAULT_QUERIES)

    duplicate = client.post("/api/queries", headers=ALICE, json={"contract_type": "CDI", "query": "data engineer"})
    assert duplicate.status_code == 409 and duplicate.json() == {"detail": "Cette recherche existe déjà."}
    assert client.post("/api/queries", headers=ALICE, json={"contract_type": "CDI", "query": " "}).status_code == 422
    assert client.post("/api/queries", headers=ALICE, json={"contract_type": "?", "query": "x"}).status_code == 422

    # La même phrase s'enregistre pour un autre lieu
    elsewhere = client.post("/api/queries", headers=ALICE, json={**QUERY, "location": " Lyon "})
    assert elsewhere.status_code == 201 and elsewhere.json()["location"] == "Lyon"
    assert client.delete(f"/api/queries/{elsewhere.json()['id']}", headers=ALICE).status_code == 204

    query_path = f"/api/queries/{created.json()['id']}"
    assert client.delete(query_path, headers=BOB).status_code == 404
    assert client.delete(query_path, headers=ALICE).status_code == 204
    assert client.get("/api/queries", headers=ALICE).json() == []


def test_jobs_are_private(client):
    alice_id = client.get("/api/me", headers=ALICE).json()["user_id"]
    with client.app.state.container.database.session() as session:
        JobRepository(session, alice_id).insert_jobs([job("https://a/1"), job("https://a/2")])

    assert client.get("/api/jobs", headers=BOB).json() == []
    paths = {saved["url"]: f"/api/jobs/{saved['id']}" for saved in client.get("/api/jobs", headers=ALICE).json()}
    applied = {"applied": True}
    assert client.patch(paths["https://a/1"], headers=BOB, json=applied).status_code == 404
    assert client.patch(paths["https://a/1"], headers=ALICE, json=applied).status_code == 204
    assert client.delete(paths["https://a/2"], headers=BOB).status_code == 404
    assert client.delete(paths["https://a/2"], headers=ALICE).status_code == 204
    assert client.delete(paths["https://a/2"], headers=ALICE).status_code == 404

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
    assert client.get("/api/me", headers=ALICE).json()["can_search"] is False
    client.post("/api/queries", headers=ALICE, json={"contract_type": "CDI", "query": "data engineer"})
    assert client.get("/api/me", headers=ALICE).json()["can_search"] is True
    response = client.post("/api/searches", headers=ALICE)

    assert response.status_code == 200 and response.headers["content-type"].startswith("text/event-stream")
    *progress, (last_name, summary) = server_sent_events(response.text)
    assert progress and {name for name, _ in progress} == {"progress"}
    assert last_name == "result"
    assert summary == {"found": 2, "new": 2, "kept": 1, "rejected": 1, "inserted": 1}
    saved_urls = [saved["url"] for saved in client.get("/api/jobs", headers=ALICE).json()]
    assert saved_urls == ["https://x/offre d'emploi data engineer CDI/0"]
    [rejected] = client.get("/api/rejected-jobs", headers=ALICE).json()
    # Le motif du rejet sort de l'API : le front n'a pas à le recalculer
    assert (rejected["motive"], rejected["failed_criteria"]) == (
        "Compétences insuffisantes",
        ["Compétences insuffisantes"],
    )

    # Le refus n'avait pas entamé le quota, la recherche si
    assert client.get("/api/me", headers=ALICE).json()["remaining_searches"] == MAX_SEARCHES_PER_DAY - 1
    client.post("/api/searches", headers=ALICE)
    assert client.post("/api/searches", headers=ALICE).status_code == 429


def test_failed_search_ends_the_stream_with_an_error_without_leaking_its_cause(tmp_path, valid_pdf):
    class BrokenEvaluator:
        def evaluate(self, cv, criteria, pages):
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


def test_documentation_is_served_in_development_only(tmp_path):
    settings = Settings(data_dir=tmp_path, frontend_dir=tmp_path / "pas-de-front")
    container = build_container(settings, FakeSearchEngine(), FakeEvaluator())

    development = TestClient(create_app(container, FakeIdentityVerifier()))
    assert development.get("/docs").status_code == 200
    assert development.get("/openapi.json").status_code == 200

    # En ligne, rien ne décrit les routes à qui n'est pas connecté
    online = TestClient(create_app(container, FakeIdentityVerifier(), docs=False))
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert online.get(path).status_code == 404
    assert online.get("/api/health").json() == {"status": "ok"}


def test_front_is_served_beside_the_api_without_hiding_it(tmp_path):
    front = tmp_path / "front"
    front.mkdir()
    (front / "index.html").write_text("<app-root></app-root>", encoding="utf-8")
    client = make_client(tmp_path, frontend_dir=front, app_password="sesame", auth_cookie_secret=SECRET)

    assert "<app-root>" in client.get("/").text
    assert "<app-root>" in client.get("/offres").text
    assert client.get("/api/health").json() == {"status": "ok"}
    assert client.get("/api/me").status_code == 401
    assert client.get("/confidentialite").status_code == 200 and "<app-root>" not in client.get("/confidentialite").text
    # Une adresse inconnue de l'API reste une erreur : elle ne reçoit pas la page d'accueil du front
    for path in ("/api", "/api/inconnu", "/api/jobs/1/inconnu"):
        response = client.get(path)
        assert response.status_code == 404 and "<app-root>" not in response.text


def test_front_is_compressed_but_a_search_stream_is_not(tmp_path, valid_pdf):
    front = tmp_path / "front"
    front.mkdir()
    (front / "index.html").write_text("<app-root></app-root>", encoding="utf-8")
    (front / "main-ABC123.js").write_text("console.log('front');" * 200, encoding="utf-8")
    client = make_client(tmp_path, frontend_dir=front, app_password="sesame", auth_cookie_secret=SECRET)

    assert client.get("/main-ABC123.js").headers["content-encoding"] == "gzip"

    client.put("/api/cv", headers=PASSWORD, files={"file": ("cv.pdf", valid_pdf, "application/pdf")})
    stream = client.post("/api/searches", headers=PASSWORD)
    # Compressé, le flux serait retenu jusqu'à la fin : le suivi de la recherche n'arriverait plus en direct
    assert stream.headers["content-type"].startswith("text/event-stream")
    assert "content-encoding" not in stream.headers


def test_every_response_carries_the_security_headers(tmp_path):
    front = tmp_path / "front"
    front.mkdir()
    (front / "index.html").write_text("<app-root></app-root>", encoding="utf-8")
    client = make_client(tmp_path, frontend_dir=front, app_password="sesame", auth_cookie_secret=SECRET)

    # Le front, une page légale, une route de l'API et un refus
    for path in ("/", "/confidentialite", "/api/health", "/api/me"):
        headers = client.get(path).headers
        policy = headers["content-security-policy"]
        assert "default-src 'self'" in policy and "frame-ancestors 'none'" in policy
        # Aucun script écrit dans la page n'est accepté : c'est ce qui arrête un script injecté
        assert "'unsafe-inline'" not in policy.split("script-src")[1].split(";")[0]
        assert headers["x-content-type-options"] == "nosniff"
        assert headers["x-frame-options"] == "DENY"
        assert headers["referrer-policy"] == "strict-origin-when-cross-origin"
        assert headers["strict-transport-security"].startswith("max-age=")

    # Le bouton de connexion Google reste chargeable
    assert "https://accounts.google.com/gsi/client" in policy
    # La documentation, servie en développement, charge ses scripts d'un autre site
    assert "content-security-policy" not in client.get("/docs").headers
    assert client.get("/docs").headers["x-content-type-options"] == "nosniff"


def test_session_keeps_the_google_profile_for_display(client):
    client.post("/api/session", headers=ALICE)

    # Sans en-tête : c'est le cookie qui porte le nom et la photo, rien n'est enregistré en base
    account = client.get("/api/me").json()

    assert (account["email"], account["name"]) == ("alice@exemple.fr", "Alice")
    assert account["picture"] == "https://lh3.googleusercontent.com/alice"


def test_password_account_has_no_profile(tmp_path):
    client = make_client(tmp_path, app_password="sesame", auth_cookie_secret=SECRET)

    account = client.get("/api/me", headers=PASSWORD).json()

    assert (account["email"], account["name"], account["picture"]) == (None, None, None)


def test_deleting_an_account_erases_it_and_closes_the_session(client, valid_pdf):
    for headers in (ALICE, BOB):
        client.put("/api/cv", headers=headers, files={"file": ("cv.pdf", valid_pdf, "application/pdf")})
        client.post("/api/queries", headers=headers, json={"contract_type": "CDI", "query": "data engineer"})
    client.post("/api/searches", headers=ALICE)
    alice_id = client.get("/api/me", headers=ALICE).json()["user_id"]
    client.post("/api/session", headers=ALICE)

    response = client.delete("/api/me")

    assert response.status_code == 204
    # Le cookie est retiré : la session ne survit pas au compte
    assert client.get("/api/me").status_code == 401
    # Encore invitée, Alice retrouve un compte neuf, sous un autre identifiant
    again = client.get("/api/me", headers=ALICE).json()
    assert again["user_id"] != alice_id and again["can_search"] is False
    assert client.get("/api/jobs", headers=ALICE).json() == []
    assert client.get("/api/rejected-jobs", headers=ALICE).json() == []
    assert client.get("/api/queries", headers=ALICE).json() == []
    assert client.get("/api/cv", headers=ALICE).json() == {"updated_at": None}
    # Bob n'a rien perdu
    assert client.get("/api/me", headers=BOB).json()["can_search"] is True
    assert len(client.get("/api/queries", headers=BOB).json()) == 1


def test_account_cannot_be_deleted_from_another_site(tmp_path):
    client = make_client(tmp_path, app_password="sesame", auth_cookie_secret=SECRET)
    client.post("/api/session", headers=PASSWORD)

    assert client.delete("/api/me", headers={"Origin": "https://ailleurs.exemple"}).status_code == 403
    assert client.get("/api/me").status_code == 200
