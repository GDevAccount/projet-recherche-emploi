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

from projet_recherche_emploi.config import INACTIVE_ACCOUNT_DAYS, MAX_SEARCHES_PER_DAY, Settings

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
<meta name="theme-color" content="#f5f4ef" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#0a0b0d" media="(prefers-color-scheme: dark)">
<link rel="icon" href="/favicon.ico">
<style>{style}</style>
<script src="/theme-init.js"></script>
</head>
<body>
<header>
  <a class="brand" href="/">
    <span class="mark">
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <circle cx="11" cy="11" r="6.5"/><path d="m16 16 4.5 4.5"/>
      </svg>
    </span>
    Tamis
  </a>
</header>
<main>
{body}
</main>
<nav>{links}</nav>
</body>
</html>
"""

# Les couleurs sont celles du front (variables --app-* de frontend/src/styles.scss), recopiées : cette page est
# servie même sans le front construit.
DARK_COLORS = """
      color-scheme: dark;
      --bg: #0a0b0d; --surface: #131518; --text: #f2f3f5; --muted: #9aa0a8; --border: rgba(255, 255, 255, 0.09);
      --link: #a3e635;
      --shadow: inset 0 1px 0 rgba(255, 255, 255, 0.04), 0 24px 48px -24px rgba(0, 0, 0, 0.7);
      --glow: radial-gradient(56rem 28rem at 88% -8%, rgba(163, 230, 53, 0.17), transparent 62%),
        radial-gradient(40rem 24rem at -8% 6%, rgba(56, 189, 248, 0.08), transparent 60%);
"""

# Le thème est celui choisi dans l'application : theme-init.js, le script du front, pose « app-dark » ou
# « app-light » sur <html>. Sans JavaScript, ou sans front construit, la page suit le réglage du système.
PAGE_STYLE = (
    """
  :root {
    color-scheme: light;
    --accent: #a3e635; --accent-strong: #84cc16; --accent-ink: #1a2e05;
    --bg: #f5f4ef; --surface: #ffffff; --text: #15171a; --muted: #666a72; --border: rgba(21, 23, 26, 0.1);
    --link: #3f6212;
    --shadow: 0 1px 2px rgba(21, 23, 26, 0.04), 0 16px 40px -18px rgba(21, 23, 26, 0.18);
    --glow: radial-gradient(56rem 28rem at 88% -8%, rgba(163, 230, 53, 0.3), transparent 62%),
      radial-gradient(40rem 24rem at -8% 6%, rgba(56, 189, 248, 0.14), transparent 60%);
  }
  :root.app-dark {"""
    + DARK_COLORS
    + """  }
  @media (prefers-color-scheme: dark) {
    :root:not(.app-light) {"""
    + DARK_COLORS
    + """    }
  }
  * { box-sizing: border-box; }
  html { background: var(--bg); }
  body {
    margin: 0; min-height: 100vh; padding: 0 1rem 3rem;
    font: 1rem/1.65 system-ui, sans-serif; color: var(--text); background: var(--glow) no-repeat;
  }
  header, main, nav { max-width: 46rem; margin: 0 auto; }
  header { padding: 1.5rem 0; }
  .brand {
    display: inline-flex; align-items: center; gap: 0.7rem;
    font-size: 1.35rem; font-weight: 650; letter-spacing: -0.02em; color: inherit; text-decoration: none;
  }
  .mark {
    display: grid; place-items: center; width: 2.1rem; height: 2.1rem;
    border-radius: 10px; background: var(--accent); color: var(--accent-ink);
  }
  .mark svg {
    width: 1.15rem; height: 1.15rem; fill: none; stroke: currentColor; stroke-width: 2.4; stroke-linecap: round;
  }
  main {
    padding: clamp(1.5rem, 5vw, 3rem); border: 1px solid var(--border); border-radius: 20px;
    background: var(--surface); box-shadow: var(--shadow); overflow-wrap: break-word;
  }
  h1, h2 { letter-spacing: -0.025em; line-height: 1.15; }
  h1 { margin: 0 0 1.5rem; font-size: clamp(1.75rem, 5vw, 2.4rem); }
  h2 { margin: 2.25rem 0 0.5rem; font-size: 1.2rem; }
  p, ul { margin: 0.75rem 0; }
  ul { padding-left: 1.25rem; }
  li { margin: 0.35rem 0; }
  li::marker { color: var(--accent-strong); }
  a { color: var(--link); text-underline-offset: 3px; }
  nav { display: flex; flex-wrap: wrap; gap: 0.5rem 1.5rem; padding: 1.5rem 0.25rem 0; font-size: 0.875rem; }
  nav a { color: var(--muted); }
  nav a:hover { color: var(--text); }
  :focus-visible { outline: 2px solid var(--accent-strong); outline-offset: 2px; }
  ::selection { background: var(--accent); color: var(--accent-ink); }
"""
)


def render_legal_page(page: str, contact_email: str = "") -> str:
    """Renvoie la page légale demandée, en HTML complet."""
    contact = contact_email.strip() or "adressez-vous à l'exploitant de l'application"
    text = (LEGAL_DIR / f"{page}.md").read_text(encoding="utf-8")
    text = text.replace("{contact}", contact).replace("{max_searches}", str(MAX_SEARCHES_PER_DAY))
    text = text.replace("{inactive_months}", str(INACTIVE_ACCOUNT_DAYS // 30))
    links = ['<a href="/">Retour à l\'application</a>']
    links += [f'<a href="/{other}">{title}</a>' for other, title in LEGAL_PAGES.items() if other != page]
    return PAGE_TEMPLATE.format(
        title=html.escape(LEGAL_PAGES[page]), style=PAGE_STYLE, body=markdown.markdown(text), links="".join(links)
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
