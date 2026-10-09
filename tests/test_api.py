import json
import re
import time
from datetime import UTC, datetime, timedelta

import pytest
from conftest import FakeEvaluator, FakeNotifier, FakeSearchEngine
from fastapi.testclient import TestClient
from helpers import blank_pdf, job

from projet_recherche_emploi.api.main import create_app
from projet_recherche_emploi.api.security import Identity
from projet_recherche_emploi.config import (
    CONTRACT_TYPES,
    DEFAULT_QUERIES,
    DEFAULT_USER_ID,
    FILTER_MODEL,
    INACTIVE_ACCOUNT_DAYS,
    MAX_SEARCHES_PER_DAY,
    SESSION_DAYS,
    Settings,
)
from projet_recherche_emploi.container import build_container
from projet_recherche_emploi.data.cv_ingestion.pdf_reader import CvPdfReader
from projet_recherche_emploi.data.repositories.job_repository import JobRepository
from projet_recherche_emploi.data.repositories.user_repository import UserRepository
from projet_recherche_emploi.schemas import DELETE_REASONS

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


def test_health_answers_an_uptime_probe_and_fails_with_the_database(client):
    # Les sondes de disponibilité appellent en HEAD, sans corps
    probe = client.head("/api/health")
    assert (probe.status_code, probe.content) == (200, b"")

    # Un serveur qui répond sans sa base ne sert à personne : la sonde doit le voir
    client.app.state.container.health.database = None
    broken = client.get("/api/health")
    assert (broken.status_code, broken.json()) == (503, {"status": "error"})
    assert client.head("/api/health").status_code == 503


def test_config_tells_the_front_how_to_log_in(client, tmp_path):
    # Sans identité : le front la lit pour afficher son écran de connexion
    assert client.get("/api/config").json() == {
        "login_mode": "google",
        "google_client_id": "id.apps.googleusercontent.com",
        "contract_types": CONTRACT_TYPES,
        "delete_reasons": [{"code": code, "label": label} for code, label in DELETE_REASONS.items()],
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
        ("POST", "/api/rejected-jobs/restore"),
        ("GET", "/api/queries"),
        ("POST", "/api/queries"),
        ("DELETE", "/api/queries/1"),
        ("GET", "/api/cv"),
        ("PUT", "/api/cv"),
        ("POST", "/api/searches"),
        ("GET", "/api/searches"),
        ("GET", "/api/searches/stats"),
        ("GET", "/api/searches/1/evaluations"),
        ("GET", "/api/admin/usage"),
        ("GET", "/api/admin/health"),
        ("POST", "/api/admin/alerts/test"),
        ("GET", "/api/admin/budget"),
        ("POST", "/api/client-errors"),
        ("GET", "/api/admin/journeys"),
        ("GET", "/api/admin/journeys/1"),
        ("POST", "/api/jobs/1/open"),
    ],
)
def test_every_data_route_requires_an_identity(client, method, path):
    assert client.request(method, path).status_code == 401
    assert client.request(method, path, headers={"Authorization": "Bearer faux"}).status_code == 401


def test_every_route_is_covered_by_the_identity_test(client):
    # Une route ajoutée sans figurer dans le test ci-dessus ferait échouer celui-ci
    tested = test_every_data_route_requires_an_identity.pytestmark[0].args[1]
    routes = {
        (method.upper(), re.sub(r"\{\w+\}", "1", path))
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
        "is_admin": True,
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
    assert alice["is_admin"] is False
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
    applied = {"status": "applied"}
    assert client.patch(paths["https://a/1"], headers=BOB, json=applied).status_code == 404
    updated = client.patch(paths["https://a/1"], headers=ALICE, json=applied)
    # L'offre revient telle qu'elle est maintenant, avec la date que le serveur vient de lui donner
    assert updated.status_code == 200
    assert (updated.json()["url"], updated.json()["status"]) == ("https://a/1", "applied")
    assert updated.json()["applied_at"].endswith(("Z", "+00:00"))
    assert updated.json()["next_statuses"] == ["interview", "rejected", "todo"]
    assert client.patch(paths["https://a/1"], headers=ALICE, json={"status": "todo"}).json()["applied_at"] is None
    # Un état inconnu, ou que l'offre ne peut pas prendre, est refusé
    assert client.patch(paths["https://a/1"], headers=ALICE, json={"status": "embauche"}).status_code == 422
    assert client.patch(paths["https://a/1"], headers=ALICE, json={"status": "interview"}).status_code == 422
    client.patch(paths["https://a/1"], headers=ALICE, json=applied)
    assert client.delete(paths["https://a/2"], headers=BOB).status_code == 404
    assert client.delete(paths["https://a/2"], headers=ALICE).status_code == 204
    assert client.delete(paths["https://a/2"], headers=ALICE).status_code == 404

    [saved] = client.get("/api/jobs", headers=ALICE).json()
    assert (saved["url"], saved["status"]) == ("https://a/1", "applied")
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

    # L'utilisateur corrige le tri : la page écartée devient une offre à traiter, et l'offre retenue est supprimée
    restoration = {"url": rejected["url"]}
    assert client.post("/api/rejected-jobs/restore", headers=BOB, json=restoration).status_code == 404
    restored = client.post("/api/rejected-jobs/restore", headers=ALICE, json=restoration)
    assert restored.status_code == 200 and (restored.json()["url"], restored.json()["status"]) == (
        rejected["url"],
        "todo",
    )
    assert client.get("/api/rejected-jobs", headers=ALICE).json() == []
    assert client.post("/api/rejected-jobs/restore", headers=ALICE, json=restoration).status_code == 404
    [kept_id] = [saved["id"] for saved in client.get("/api/jobs", headers=ALICE).json() if saved["url"] in saved_urls]
    assert client.delete(f"/api/jobs/{kept_id}?reason=inconnu", headers=ALICE).status_code == 422
    assert client.delete(f"/api/jobs/{kept_id}?reason=not_my_job", headers=ALICE).status_code == 204

    # Le refus n'avait pas entamé le quota, la recherche si
    assert client.get("/api/me", headers=ALICE).json()["remaining_searches"] == MAX_SEARCHES_PER_DAY - 1
    client.post("/api/searches", headers=ALICE)
    assert client.post("/api/searches", headers=ALICE).status_code == 429


def test_search_tracking_is_for_administrators_only(client, valid_pdf):
    for headers in (OWNER, ALICE):
        client.put("/api/cv", headers=headers, files={"file": ("cv.pdf", valid_pdf, "application/pdf")})
    client.post("/api/queries", headers=ALICE, json=QUERY)
    client.post("/api/searches", headers=OWNER)
    client.post("/api/searches", headers=ALICE)

    # Le propriétaire relit le bilan de ses recherches, le journal de leurs pages et leur synthèse
    [run] = client.get("/api/searches", headers=OWNER).json()
    calls = len(DEFAULT_QUERIES)
    assert (run["status"], run["search_calls"], run["found_count"]) == ("done", calls, 2 * calls)
    assert (run["input_tokens"], run["output_tokens"]) == (2000 * calls, 100 * calls)
    evaluations = client.get(f"/api/searches/{run['id']}/evaluations", headers=OWNER).json()
    assert len(evaluations) == 2 * calls and {page["kept"] for page in evaluations} == {True, False}
    stats = client.get("/api/searches/stats", headers=OWNER).json()
    # Le faux modèle n'a pas de tarif : pas de coût total, plutôt qu'un total partiel
    assert (stats["runs"], stats["search_cost_usd"], stats["cost_usd"]) == (1, round(0.016 * calls, 6), None)

    # Un invité n'y a pas accès, pas même pour ses propres recherches
    paths = ("/api/searches", "/api/searches/stats", f"/api/searches/{run['id']}/evaluations", "/api/admin/usage")
    for path in (*paths, "/api/admin/health", "/api/admin/budget", "/api/admin/journeys"):
        response = client.get(path, headers=ALICE)
        assert response.status_code == 403 and "sk-" not in response.text
    # Il lance toujours les siennes
    assert client.get("/api/me", headers=ALICE).json()["remaining_searches"] == MAX_SEARCHES_PER_DAY - 1


def test_administrator_sees_what_each_account_spends_and_nothing_else_of_them(tmp_path, valid_pdf):
    evaluator = FakeEvaluator()
    evaluator.model_name = FILTER_MODEL
    # Bob est administrateur sans figurer parmi les invités : ADMIN_EMAILS suffit à le laisser entrer
    client = make_client(
        tmp_path,
        evaluator,
        google_client_id="id.apps.googleusercontent.com",
        owner_email="proprietaire@exemple.fr",
        allowed_emails="alice@exemple.fr",
        admin_emails="Bob@exemple.fr",
        auth_cookie_secret=SECRET,
    )
    bob = client.get("/api/me", headers=BOB).json()
    assert (bob["is_admin"], bob["is_owner"], bob["remaining_searches"]) == (True, False, MAX_SEARCHES_PER_DAY)
    for headers in (OWNER, ALICE):
        client.put("/api/cv", headers=headers, files={"file": ("cv.pdf", valid_pdf, "application/pdf")})
    client.post("/api/queries", headers=ALICE, json=QUERY)
    client.post("/api/searches", headers=OWNER)
    for _ in range(2):
        client.post("/api/searches", headers=ALICE)

    assert client.get("/api/admin/usage", headers=ALICE).status_code == 403
    usage = client.get("/api/admin/usage", headers=BOB).json()

    calls = len(DEFAULT_QUERIES)
    owner, alice = usage["accounts"]
    # Le plus coûteux en premier : le propriétaire a trois recherches enregistrées, Alice une seule lancée deux fois
    assert (owner["is_owner"], owner["email"], owner["runs"], owner["search_calls"]) == (True, None, 1, calls)
    assert (alice["is_owner"], alice["email"], alice["runs"], alice["search_calls"]) == (
        False,
        "alice@exemple.fr",
        2,
        2,
    )
    # La seconde recherche d'Alice n'a retrouvé que des pages déjà vues : rien à payer au modèle
    assert (alice["input_tokens"], alice["output_tokens"], alice["kept_count"]) == (2000, 100, 1)
    assert (alice["search_cost_usd"], alice["model_cost_usd"], alice["cost_usd"]) == (0.032, 0.00025, 0.03225)
    assert usage["guests_cost_usd"] == alice["cost_usd"]
    assert usage["cost_usd"] == round(owner["cost_usd"] + alice["cost_usd"], 6)
    assert (usage["runs"], usage["since"]) == (3, None)
    # Des nombres et une adresse, rien de ce qu'Alice cherche ni des pages trouvées pour elle
    assert "data engineer" not in json.dumps(usage) and "https://x/" not in json.dumps(usage)
    # Bob voit le suivi de ses propres recherches, pas celui d'un autre
    assert client.get("/api/searches", headers=BOB).json() == []

    assert client.get("/api/admin/usage?days=30", headers=BOB).json()["runs"] == 3
    assert client.get("/api/admin/usage?days=0", headers=BOB).status_code == 422
    assert (alice["deleted"], alice["plan"]) == (False, "free")

    # Alice supprime son compte : ce qu'elle a coûté reste, sans son adresse ni la date de ses recherches
    assert client.delete("/api/me", headers=ALICE).status_code == 204
    after = client.get("/api/admin/usage?days=30", headers=BOB).json()
    _, gone = after["accounts"]
    kept = ("runs", "search_calls", "input_tokens", "output_tokens", "kept_count", "cost_usd", "plan", "is_owner")
    assert {name: gone[name] for name in kept} == {name: alice[name] for name in kept}
    assert (gone["deleted"], gone["email"], gone["last_search_at"]) == (True, None, None)
    assert (after["cost_usd"], after["guests_cost_usd"]) == (usage["cost_usd"], usage["guests_cost_usd"])
    assert "alice" not in json.dumps(after)
    # Revenue avec la même adresse, elle a un compte neuf, que rien ne relie à l'ancien
    client.get("/api/me", headers=ALICE)
    assert len(client.get("/api/admin/usage", headers=BOB).json()["accounts"]) == 2


def test_health_reports_the_errors_of_every_account_without_their_content(tmp_path):
    client = make_client(
        tmp_path,
        google_client_id="id.apps.googleusercontent.com",
        owner_email="proprietaire@exemple.fr",
        allowed_emails="alice@exemple.fr",
        admin_emails="bob@exemple.fr",
        auth_cookie_secret=SECRET,
    )
    empty = client.get("/api/admin/health", headers=BOB).json()
    assert (empty["healthy"], empty["runs"], empty["failure_rate"], empty["server_errors"]) == (True, 0, None, [])

    # Deux demandes refusées à Alice, une au propriétaire, puis une panne chez Alice
    for headers in (ALICE, ALICE, OWNER):
        assert client.post("/api/searches", headers=headers).status_code == 422

    def broken_list(user_id):
        raise RuntimeError("contenu-de-la-panne")

    client.app.state.container.jobs.list_jobs = broken_list
    # Le client de test relance d'ordinaire l'erreur du serveur au lieu de rendre sa réponse
    fragile = TestClient(client.app, base_url="http://localhost", raise_server_exceptions=False)
    assert fragile.get("/api/jobs", headers=ALICE).status_code == 500
    assert client.patch("/api/jobs/41", headers=OWNER, json={"status": "applied"}).status_code == 404
    crashed = fragile.get("/api/jobs", headers=ALICE)
    assert crashed.status_code == 500 and "contenu-de-la-panne" not in crashed.text
    assert crashed.json()["detail"].startswith("Le serveur a rencontré une erreur")
    # Un appel sans identité ou sans droit n'est pas une erreur du serveur : il n'est pas compté
    assert client.get("/api/jobs").status_code == 401
    assert client.get("/api/admin/health", headers=ALICE).status_code == 403

    health = client.get("/api/admin/health?days=30", headers=BOB).json()
    assert (health["healthy"], health["failures"], health["refusals"]) == (False, 2, 4)
    failure, refusal, missing = health["server_errors"]
    # Le modèle de la route, pas l'adresse appelée
    assert (missing["method"], missing["route"]) == ("PATCH", "/api/jobs/{job_id}")
    assert failure | {"last_at": None} == {
        "method": "GET",
        "route": "/api/jobs",
        "status_code": 500,
        "error_type": "RuntimeError",
        "is_failure": True,
        "count": 2,
        "accounts": 1,
        "last_at": None,
    }
    assert (refusal["method"], refusal["route"], refusal["status_code"]) == ("POST", "/api/searches", 422)
    assert (refusal["error_type"], refusal["is_failure"], refusal["count"]) == ("InvalidInputError", False, 3)
    assert refusal["accounts"] == 2 and refusal["last_at"] is not None
    # Ni le message de l'erreur, ni le compte qui l'a rencontrée
    assert "contenu-de-la-panne" not in json.dumps(health) and "alice" not in json.dumps(health)
    assert client.get("/api/admin/health?days=0", headers=BOB).status_code == 422

    # Alice supprime son compte : les erreurs qu'elle a rencontrées partent avec lui
    assert client.delete("/api/me", headers=ALICE).status_code == 204
    after = client.get("/api/admin/health", headers=BOB).json()
    assert (after["healthy"], after["failures"], after["refusals"]) == (True, 0, 2)


def test_administrator_can_check_that_alerts_arrive(client, tmp_path):
    # Sans sujet ntfy, rien ne part, et la santé le dit
    assert client.post("/api/admin/alerts/test", headers=ALICE).status_code == 403
    assert client.post("/api/admin/alerts/test", headers=OWNER).json() == {"sent": False}
    assert client.get("/api/admin/health", headers=OWNER).json()["alerts_enabled"] is False

    notifier = FakeNotifier()
    container = build_container(
        Settings(data_dir=tmp_path / "alertes", app_password="sesame", auth_cookie_secret=SECRET),
        FakeSearchEngine(),
        FakeEvaluator(),
        notifier,
    )
    alerting = TestClient(create_app(container, FakeIdentityVerifier()), base_url="http://localhost")

    assert alerting.post("/api/admin/alerts/test", headers=PASSWORD).json() == {"sent": True}
    assert notifier.sent == [("Alerte d'essai", "Les alertes de Tamis arrivent bien ici.")]
    assert alerting.get("/api/admin/health", headers=PASSWORD).json()["alerts_enabled"] is True
    # Le sujet se lit comme un secret : rien de public ne le donne
    assert "ntfy" not in alerting.get("/api/config").text


def test_front_reports_its_errors_without_their_message(client):
    crash = {"error_type": "TypeError", "route": "/offres", "source": "main-5UFRYBOQ.js:1:23456"}
    assert client.post("/api/client-errors", headers=ALICE, json=crash).status_code == 204
    assert client.post("/api/client-errors", headers=ALICE, json={"error_type": "Error"}).status_code == 204

    # Rien qui ressemble à un message, à une adresse ou à un contenu n'est accepté
    for refused in (
        {"error_type": "Cannot read properties of undefined (reading 'title')"},
        {"error_type": "TypeError", "route": "/offres?q=ingénieur IA"},
        {"error_type": "TypeError", "route": "https://exemple.fr/offres"},
        {"error_type": "TypeError", "source": "https://exemple.fr/main.js:1:2"},
        {"error_type": "TypeError", "source": "at JobCard (alice@exemple.fr)"},
        {"error_type": "T" * 81},
        {"route": "/offres"},
    ):
        assert client.post("/api/client-errors", headers=ALICE, json=refused).status_code == 422

    health = client.get("/api/admin/health", headers=OWNER).json()
    assert (health["client_failures"], health["incidents"], health["healthy"]) == (2, 2, False)
    first = health["client_errors"][0]
    assert (first["count"], first["accounts"]) == (1, 1) and "alice" not in json.dumps(health)
    assert {(group["route"], group["error_type"], group["source"]) for group in health["client_errors"]} == {
        ("/offres", "TypeError", "main-5UFRYBOQ.js:1:23456"),
        (None, "Error", None),
    }


def test_administrator_follows_how_far_each_guest_goes(tmp_path, valid_pdf):
    client = make_client(
        tmp_path,
        google_client_id="id.apps.googleusercontent.com",
        owner_email="proprietaire@exemple.fr",
        allowed_emails="alice@exemple.fr,bob@exemple.fr,carol@exemple.fr",
        auth_cookie_secret=SECRET,
    )
    carol = {"Authorization": "Bearer jeton-carol"}
    # Alice va jusqu'à la candidature, Bob s'arrête au CV, Carol ne fait que se connecter
    for headers in (ALICE, BOB):
        client.put("/api/cv", headers=headers, files={"file": ("cv.pdf", valid_pdf, "application/pdf")})
    client.get("/api/me", headers=carol)
    client.post("/api/queries", headers=ALICE, json=QUERY)
    client.post("/api/searches", headers=ALICE)
    [job] = client.get("/api/jobs", headers=ALICE).json()
    # Elle ouvre l'annonce deux fois : seule la première est datée ; celle d'un autre compte ne la concerne pas
    for _ in range(2):
        assert client.post(f"/api/jobs/{job['id']}/open", headers=ALICE).status_code == 204
    assert client.post(f"/api/jobs/{job['id']}/open", headers=BOB).status_code == 204
    client.patch(f"/api/jobs/{job['id']}", headers=ALICE, json={"status": "applied"})
    # Un poste déjà enregistré, refusé : l'erreur fera partie de son parcours
    assert client.post("/api/queries", headers=ALICE, json=QUERY).status_code == 409

    journeys = client.get("/api/admin/journeys", headers=OWNER).json()

    assert journeys["guests"] == 3
    assert [(step["label"], step["count"], step["rate"]) for step in journeys["steps"]] == [
        ("Compte créé", 3, 1.0),
        ("CV déposé", 2, 0.6667),
        ("Poste recherché saisi", 1, 0.3333),
        ("Recherche lancée", 1, 0.3333),
        ("Offre retenue", 1, 0.3333),
        ("Annonce ouverte", 1, 0.3333),
        ("Candidature envoyée", 1, 0.3333),
        ("Revenu un autre jour", 0, 0.0),
    ]
    accounts = {account["email"]: account for account in journeys["accounts"]}
    alice = accounts["alice@exemple.fr"]
    assert (alice["has_cv"], alice["queries"], alice["runs"], alice["kept"], alice["applied"]) == (True, 1, 1, 1, 1)
    assert (alice["interviews"], alice["corrections"], alice["returned"], alice["is_owner"]) == (0, 0, False, False)
    assert (accounts["bob@exemple.fr"]["has_cv"], accounts["bob@exemple.fr"]["runs"]) == (True, 0)
    assert (accounts["carol@exemple.fr"]["has_cv"], accounts["carol@exemple.fr"]["queries"]) == (False, 0)
    # Le propriétaire a sa ligne, sans compter parmi les invités ; ses postes par défaut y sont
    assert (accounts[None]["is_owner"], accounts[None]["queries"]) == (True, len(DEFAULT_QUERIES))
    # Des nombres et une adresse : rien de ce qu'Alice cherche ni des pages trouvées pour elle
    assert "data engineer" not in json.dumps(journeys) and "https://x/" not in json.dumps(journeys)

    # Chacun s'est arrêté à une étape, et n'est venu qu'un jour
    assert (alice["step"], alice["opened"]) == ("Candidature envoyée", 1)
    assert (alice["active_days"], alice["idle_days"]) == (1, 0)
    assert accounts["bob@exemple.fr"]["step"] == "CV déposé"
    assert accounts["carol@exemple.fr"]["step"] == "Compte créé"

    # La fiche d'Alice : ce qu'elle a fait, dans l'ordre, et ce qui écarte ses pages
    assert client.get(f"/api/admin/journeys/{alice['user_id']}", headers=ALICE).status_code == 403
    detail = client.get(f"/api/admin/journeys/{alice['user_id']}", headers=OWNER).json()
    assert detail["account"] == alice
    labels = [event["label"] for event in reversed(detail["events"])]
    assert labels[0] == "Compte créé" and sorted(labels) == sorted(
        [
            "Compte créé",
            "CV déposé",
            "Poste recherché ajouté",
            "Recherche lancée",
            "Annonce ouverte",
            "Candidature envoyée",
            "Demande refusée",
        ]
    )
    by_label = {event["label"]: event for event in detail["events"]}
    assert by_label["Recherche lancée"]["detail"] == "2 pages évaluées sur 2 trouvées, 1 retenues"
    assert by_label["Demande refusée"]["detail"] == "POST /api/queries · ConflictError"
    # La page écartée l'a été pour ses compétences, seul critère que le faux modèle refuse
    assert (detail["evaluated"], detail["rejected"]) == (2, 1)
    assert detail["rejections"] == [{"label": "Compétences", "count": 1, "rate": 1.0}]
    # Ni intitulé, ni lien, ni phrase de recherche
    assert "data engineer" not in json.dumps(detail) and "https://x/" not in json.dumps(detail)
    assert client.get("/api/admin/journeys/9999", headers=OWNER).status_code == 404

    # Un compte supprimé quitte le parcours, et n'a plus de fiche
    bob_id = accounts["bob@exemple.fr"]["user_id"]
    assert client.delete("/api/me", headers=BOB).status_code == 204
    assert client.get(f"/api/admin/journeys/{bob_id}", headers=OWNER).status_code == 404
    after = client.get("/api/admin/journeys", headers=OWNER).json()
    assert after["guests"] == 2 and "bob" not in json.dumps(after)


def test_administrator_reads_the_budget_of_the_month(tmp_path, valid_pdf):
    client = make_client(tmp_path, app_password="sesame", auth_cookie_secret=SECRET, monthly_budget_usd=5)
    client.put("/api/cv", headers=PASSWORD, files={"file": ("cv.pdf", valid_pdf, "application/pdf")})
    client.post("/api/searches", headers=PASSWORD)

    budget = client.get("/api/admin/budget", headers=PASSWORD).json()

    spent = round(0.016 * len(DEFAULT_QUERIES), 6)
    assert (budget["budget_usd"], budget["runs"], budget["spent_usd"], budget["partial"]) == (5, 1, spent, True)
    assert budget["projected_usd"] >= spent and budget["spent_rate"] == round(spent / 5, 4)
    assert (budget["over_budget"], budget["projected_over_budget"]) == (False, False)
    assert len(client.get("/api/searches/stats", headers=PASSWORD).json()["weeks"]) == 12


def test_usage_can_be_limited_to_the_last_days(tmp_path, valid_pdf):
    client = make_client(tmp_path, app_password="sesame")
    client.put("/api/cv", headers=PASSWORD, files={"file": ("cv.pdf", valid_pdf, "application/pdf")})
    client.post("/api/searches", headers=PASSWORD)
    usage = client.app.state.container.usage

    assert usage.get_overview(days=30).runs == 1
    # Vue d'un mois plus tard, la recherche est sortie de la période
    later = datetime.now(UTC) + timedelta(days=31)
    overview = usage.get_overview(days=30, now=later)
    assert (overview.runs, overview.accounts, overview.cost_usd, overview.guests_cost_usd) == (0, [], 0, 0)


def test_failed_search_ends_the_stream_with_an_error_without_leaking_its_cause(tmp_path, valid_pdf):
    class BrokenEvaluator:
        model_name = "faux-modèle"

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


def test_a_visit_deletes_the_guest_accounts_left_unused_too_long(client):
    # Pas seulement au démarrage : une machine mise en veille reprend sans redémarrer
    container = client.app.state.container
    long_ago = datetime.now(UTC) - timedelta(days=INACTIVE_ACCOUNT_DAYS + 1)
    with container.database.session() as session:
        users = UserRepository(session)
        alice_id = users.get_or_create_user_id("alice@exemple.fr")
        users.record_activity(alice_id, long_ago, datetime.now(UTC) + timedelta(days=1))

    assert client.get("/api/me", headers=BOB).status_code == 200

    with container.database.session() as session:
        emails = {user.id: user.email for user in UserRepository(session).list_users()}
    assert emails[alice_id] is None


def test_a_guest_coming_back_after_a_long_time_keeps_the_account(client):
    container = client.app.state.container
    long_ago = datetime.now(UTC) - timedelta(days=INACTIVE_ACCOUNT_DAYS + 1)
    with container.database.session() as session:
        users = UserRepository(session)
        alice_id = users.get_or_create_user_id("alice@exemple.fr")
        users.record_activity(alice_id, long_ago, datetime.now(UTC) + timedelta(days=1))

    # Sa visite date son activité avant que la suppression ne passe
    assert client.get("/api/me", headers=ALICE).json()["user_id"] == alice_id


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


def test_uploaded_cv_loses_the_name_of_the_google_account(client, valid_pdf, monkeypatch):
    monkeypatch.setattr(CvPdfReader, "read_text", lambda self, data: "Alice Durand, alice@exemple.fr, Python")

    response = client.put("/api/cv", headers=ALICE, files={"file": ("cv.pdf", valid_pdf, "application/pdf")})

    assert response.status_code == 200
    user_id = client.get("/api/me", headers=ALICE).json()["user_id"]
    # Le faux Google de ces tests donne « Alice » pour nom de compte
    assert client.app.state.container.cv.read_text(user_id) == "[nom] Durand, [e-mail], Python"
