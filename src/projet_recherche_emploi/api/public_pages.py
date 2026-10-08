"""Pages servies sans connexion, en HTML simple : textes légaux et preuve de propriété du site.

Les robots de Google ne lisent pas une page qui n'a de contenu qu'une fois son JavaScript exécuté,
comme celles du front Angular. Ces pages sont donc des routes à part, ajoutées au serveur par api/main.py.
"""

import html
import re
from pathlib import Path

import markdown
from starlette.requests import Request
from starlette.responses import HTMLResponse, PlainTextResponse
from starlette.routing import Route

from projet_recherche_emploi.config import MAX_SEARCHES_PER_DAY, Settings

LEGAL_DIR = Path(__file__).parent / "legal"
# Adresse de la page -> titre
LEGAL_PAGES = {"confidentialite": "Règles de confidentialité", "conditions": "Conditions d'utilisation"}
# Nom du fichier que Search Console demande de publier à la racine du site
VERIFICATION_FILE_PATTERN = re.compile(r"google[0-9a-f]+\.html")

PAGE_TEMPLATE = """<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} · Tamis</title>
<style>
  body {{ max-width: 46rem; margin: 2rem auto; padding: 0 1rem; font: 1rem/1.6 system-ui, sans-serif; color: #222; }}
  h1 {{ font-size: 1.8rem; }}
  h2 {{ font-size: 1.2rem; margin-top: 2rem; }}
  nav {{ margin-top: 3rem; padding-top: 1rem; border-top: 1px solid #ddd; }}
</style>
</head>
<body>
{body}
<nav>{links}</nav>
</body>
</html>
"""


def render_legal_page(page: str, contact_email: str = "") -> str:
    """Renvoie la page légale demandée, en HTML complet."""
    contact = contact_email.strip() or "adressez-vous à l'exploitant de l'application"
    text = (LEGAL_DIR / f"{page}.md").read_text(encoding="utf-8")
    text = text.replace("{contact}", contact).replace("{max_searches}", str(MAX_SEARCHES_PER_DAY))
    links = ['<a href="/">Retour à l\'application</a>']
    links += [f'<a href="/{other}">{title}</a>' for other, title in LEGAL_PAGES.items() if other != page]
    return PAGE_TEMPLATE.format(
        title=html.escape(LEGAL_PAGES[page]), body=markdown.markdown(text), links=" · ".join(links)
    )


def build_routes(settings: Settings) -> list[Route]:
    """Renvoie les routes publiques à ajouter au serveur web."""
    routes = [_legal_route(page, settings.contact_email) for page in LEGAL_PAGES]

    verification_file = settings.google_site_verification_file
    # Le nom est contrôlé : il devient une adresse du site
    if VERIFICATION_FILE_PATTERN.fullmatch(verification_file):
        routes.append(_verification_route(verification_file))
    return routes


def _legal_route(page: str, contact_email: str) -> Route:
    async def legal_page(request: Request) -> HTMLResponse:
        return HTMLResponse(render_legal_page(page, contact_email))

    return Route(f"/{page}", legal_page)


def _verification_route(verification_file: str) -> Route:
    async def verification(request: Request) -> PlainTextResponse:
        # Contenu attendu par Search Console pour ce fichier
        return PlainTextResponse(f"google-site-verification: {verification_file}", media_type="text/html")

    return Route(f"/{verification_file}", verification)
