import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from jobgrep.api.public_pages import PAGES, build_routes
from jobgrep.assistant.passages import split_text
from jobgrep.config import (
    INACTIVE_ACCOUNT_DAYS,
    JOB_SITES,
    MAX_SEARCHES_PER_DAY,
    MAX_TRIAL_SEARCHES,
    SERVER_ERROR_DAYS,
    TRIAL_ACCOUNT_DAYS,
    TRIAL_START_DAYS,
    Settings,
)
from jobgrep.site_texts import read_site_text, section_anchor


def client(**settings: str) -> TestClient:
    return TestClient(Starlette(routes=build_routes(Settings(**settings))))


@pytest.mark.parametrize(
    ("path", "title"),
    [
        ("/fonctionnement", "Comment fonctionne JobGrep"),
        ("/confidentialite", "Règles de confidentialité"),
        ("/conditions", "Conditions d'utilisation"),
    ],
)
def test_public_page_is_plain_html_readable_without_javascript(path, title):
    response = client(contact_email="contact@exemple.fr").get(path)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    # Chaque titre porte une ancre : l'assistant renvoie à la section d'où vient sa réponse
    assert f'<h1 id="{section_anchor(title)}">{title}</h1>' in response.text
    assert '<meta name="description" content="' in response.text
    # Un seul script, celui du thème, servi par le site : la politique de contenu refuse tout script écrit ici
    assert response.text.count("<script") == 1 and '<script src="/theme-init.js"></script>' in response.text
    # Sombre comme l'application, y compris sans JavaScript ; le clair ne vient que du choix fait dans le site
    assert "color-scheme: dark" in response.text.split(":root.app-light")[0]
    assert "prefers-color-scheme" not in response.text
    assert 'class="brand" href="/"' in response.text
    # Aucun champ de remplacement oublié dans le texte
    assert "{contact}" not in response.text and "{max_searches}" not in response.text
    assert "{inactive_months}" not in response.text
    assert "{trial_" not in response.text and "{job_sites}" not in response.text


def test_legal_pages_give_the_contact_address():
    for path in ("/confidentialite", "/conditions"):
        assert "contact@exemple.fr" in client(contact_email="contact@exemple.fr").get(path).text


def test_presentation_page_states_the_real_limits_and_sites():
    text = client().get("/fonctionnement").text

    assert f"dispose de {MAX_SEARCHES_PER_DAY} recherches par jour" in text
    assert f"donne droit à {MAX_TRIAL_SEARCHES} recherche" in text
    assert f"supprimé au bout de {TRIAL_ACCOUNT_DAYS} jours" in text
    for site in JOB_SITES:
        assert site in text
    assert 'href="/confidentialite"' in text and 'href="/conditions"' in text


def test_public_pages_link_to_each_other():
    for path in PAGES:
        text = client().get(f"/{path}").text
        for other in PAGES:
            assert other == path or f'href="/{other}"' in text


def test_robots_file_opens_the_site_but_not_the_api():
    response = client().get("/robots.txt")

    assert response.headers["content-type"].startswith("text/plain")
    assert response.text.splitlines()[:3] == ["User-agent: *", "Allow: /", "Disallow: /api/"]
    # Sans adresse publique, il n'y a pas de plan du site à annoncer
    assert "Sitemap" not in response.text
    assert client().get("/sitemap.xml").status_code == 404


def test_site_address_is_declared_to_search_engines():
    site = client(site_url="https://jobgrep.exemple/")

    assert "Sitemap: https://jobgrep.exemple/sitemap.xml" in site.get("/robots.txt").text
    sitemap = site.get("/sitemap.xml")
    assert sitemap.headers["content-type"].startswith("application/xml")
    for path in ("", "fonctionnement", "confidentialite", "conditions"):
        assert f"<loc>https://jobgrep.exemple/{path}</loc>" in sitemap.text
    assert "/api" not in sitemap.text
    page = site.get("/fonctionnement").text
    assert '<link rel="canonical" href="https://jobgrep.exemple/fonctionnement">' in page
    assert "canonical" not in client().get("/fonctionnement").text


def test_site_address_must_be_complete():
    with pytest.raises(ValueError, match="SITE_URL"):
        Settings(site_url="jobgrep.exemple")


def test_conditions_state_the_real_quota_and_link_to_the_privacy_rules():
    text = client().get("/conditions").text

    assert f"limité à {MAX_SEARCHES_PER_DAY} par jour" in text
    assert 'href="/confidentialite"' in text


def test_privacy_rules_state_the_real_retention_period():
    text = client().get("/confidentialite").text

    assert f"Un compte resté {INACTIVE_ACCOUNT_DAYS // 30} mois sans utilisation est supprimé automatiquement" in text
    assert f"elles sont effacées au bout de {SERVER_ERROR_DAYS} jours" in text


def test_legal_pages_state_the_real_limits_of_a_trial_without_account():
    conditions, privacy = client().get("/conditions").text, client().get("/confidentialite").text

    assert f"à {MAX_TRIAL_SEARCHES} en tout pour un essai sans compte" in conditions
    assert f"supprimé au bout de {TRIAL_ACCOUNT_DAYS} jours" in conditions
    assert f"{TRIAL_ACCOUNT_DAYS} jours après son ouverture" in privacy
    # Ce qui est gardé de l'adresse IP, pourquoi, et combien de temps
    assert f"effacée au bout de {TRIAL_START_DAYS * 24} heures" in privacy and "article 6.1.f" in privacy


def test_privacy_rules_name_who_receives_the_data():
    text = client().get("/confidentialite").text

    for recipient in ("Google", "OpenAI", "Tavily", "Fly.io"):
        assert recipient in text


def test_verification_file_is_served_only_when_configured():
    assert client().get("/google1a2b3c.html").status_code == 404

    response = client(google_site_verification_file="google1a2b3c.html").get("/google1a2b3c.html")

    assert response.status_code == 200
    assert response.text == "google-site-verification: google1a2b3c.html"


@pytest.mark.parametrize("name", ["../secret.html", "google.html", "googleXYZ.html", "google1a.html/x", "autre.html"])
def test_unexpected_verification_file_names_are_ignored(name):
    paths = [route.path for route in build_routes(Settings(google_site_verification_file=name))]

    assert paths == ["/fonctionnement", "/confidentialite", "/conditions", "/robots.txt"]


@pytest.mark.parametrize("path", PAGES)
def test_every_section_of_a_public_page_can_be_linked_to(path):
    page = client().get(f"/{path}").text

    sections = {passage.section for passage in split_text(path, read_site_text(path)) if passage.section}
    assert sections
    for section in sections:
        # L'assistant cite « /page#ancre » : l'ancre doit être celle que la page donne à son titre
        assert f'id="{section_anchor(section)}"' in page, section
