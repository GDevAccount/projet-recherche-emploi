"""Pages servies sans connexion, en HTML simple : présentation, textes légaux, et ce que lisent les robots.

Les robots de Google ne lisent pas une page qui n'a de contenu qu'une fois son JavaScript exécuté,
comme celles du front Angular. Ces pages sont donc des routes à part, ajoutées au serveur par api/main.py.
"""

import html
import re
from dataclasses import dataclass

import markdown
from starlette.requests import Request
from starlette.responses import HTMLResponse, PlainTextResponse, Response
from starlette.routing import Route

from jobgrep.config import Settings
from jobgrep.site_texts import read_site_text


@dataclass(frozen=True)
class PublicPage:
    title: str
    # Résumé que les moteurs de recherche affichent sous le titre
    description: str


# Adresse de la page -> page, dans l'ordre des liens du pied de page. Le texte de chacune est dans texts/
PAGES = {
    "fonctionnement": PublicPage(
        "Comment fonctionne JobGrep",
        "JobGrep cherche des offres d'emploi sur les principaux sites, compare chaque annonce à votre CV "
        "et ne garde que celles qui vous correspondent. Son fonctionnement, étape par étape.",
    ),
    "confidentialite": PublicPage(
        "Règles de confidentialité",
        "Les données que JobGrep enregistre, à qui elles sont transmises, combien de temps, et comment les effacer.",
    ),
    "conditions": PublicPage(
        "Conditions d'utilisation",
        "Les conditions d'utilisation de JobGrep : accès, limites du service et responsabilités.",
    ),
}
# Fichiers que les robots demandent d'eux-mêmes, à la racine du site
ROBOTS_PATH = "/robots.txt"
SITEMAP_PATH = "/sitemap.xml"
# Nom du fichier que Search Console demande de publier à la racine du site
VERIFICATION_FILE_PATTERN = re.compile(r"google[0-9a-f]+\.html")

PAGE_TEMPLATE = """<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} · JobGrep</title>
<meta name="description" content="{description}">
{canonical}
<meta name="theme-color" content="#0a0b0d">
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
    JobGrep
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
# Le thème est celui de l'application : sombre, sauf si l'utilisateur y a choisi le clair. theme-init.js, le script
# du front, pose alors « app-light » sur <html>. Sans JavaScript, ou sans front construit, la page reste sombre.
PAGE_STYLE = """
  :root {
    color-scheme: dark;
    --accent: #a3e635; --accent-strong: #84cc16; --accent-ink: #1a2e05;
    --bg: #0a0b0d; --surface: #131518; --text: #f2f3f5; --muted: #9aa0a8; --border: rgba(255, 255, 255, 0.09);
    --link: #a3e635;
    --shadow: inset 0 1px 0 rgba(255, 255, 255, 0.04), 0 24px 48px -24px rgba(0, 0, 0, 0.7);
    --glow: radial-gradient(56rem 28rem at 88% -8%, rgba(163, 230, 53, 0.17), transparent 62%),
      radial-gradient(40rem 24rem at -8% 6%, rgba(56, 189, 248, 0.08), transparent 60%);
  }
  :root.app-light {
    color-scheme: light;
    --bg: #f5f4ef; --surface: #ffffff; --text: #15171a; --muted: #666a72; --border: rgba(21, 23, 26, 0.1);
    --link: #3f6212;
    --shadow: 0 1px 2px rgba(21, 23, 26, 0.04), 0 16px 40px -18px rgba(21, 23, 26, 0.18);
    --glow: radial-gradient(56rem 28rem at 88% -8%, rgba(163, 230, 53, 0.3), transparent 62%),
      radial-gradient(40rem 24rem at -8% 6%, rgba(56, 189, 248, 0.14), transparent 60%);
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


def render_page(path: str, settings: Settings) -> str:
    """Renvoie la page publique demandée, en HTML complet."""
    page = PAGES[path]
    text = read_site_text(path, settings.contact_email)
    links = ['<a href="/">Retour à l\'application</a>']
    links += [f'<a href="/{other}">{html.escape(PAGES[other].title)}</a>' for other in PAGES if other != path]
    # Sans adresse publique réglée, la page ne dit pas où elle se trouve : rien à déclarer aux moteurs
    canonical = f'<link rel="canonical" href="{html.escape(settings.site_url)}/{path}">' if settings.site_url else ""
    return PAGE_TEMPLATE.format(
        title=html.escape(page.title),
        description=html.escape(page.description),
        canonical=canonical,
        style=PAGE_STYLE,
        body=markdown.markdown(text),
        links="".join(links),
    )


def render_robots(site_url: str) -> str:
    """Renvoie robots.txt : tout le site est ouvert aux robots, sauf l'API, qui ne sert que des données."""
    lines = ["User-agent: *", "Allow: /", "Disallow: /api/"]
    if site_url:
        lines += ["", f"Sitemap: {site_url}{SITEMAP_PATH}"]
    return "\n".join(lines) + "\n"


def render_sitemap(site_url: str) -> str:
    """Renvoie le plan du site : l'accueil et les pages publiques, seules adresses lisibles sans connexion."""
    urls = "".join(f"<url><loc>{html.escape(f'{site_url}/{path}')}</loc></url>" for path in ("", *PAGES))
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>'
    )


def build_routes(settings: Settings) -> list[Route]:
    """Renvoie les routes publiques à ajouter au serveur web."""
    routes = [_page_route(path, settings) for path in PAGES]
    routes.append(_text_route(ROBOTS_PATH, render_robots(settings.site_url), "text/plain"))
    # Un plan du site ne porte que des adresses complètes : sans adresse publique, il n'y en a pas
    if settings.site_url:
        routes.append(_text_route(SITEMAP_PATH, render_sitemap(settings.site_url), "application/xml"))

    verification_file = settings.google_site_verification_file
    # Le nom est contrôlé : il devient une adresse du site
    if VERIFICATION_FILE_PATTERN.fullmatch(verification_file):
        routes.append(_verification_route(verification_file))
    return routes


def _page_route(path: str, settings: Settings) -> Route:
    async def public_page(request: Request) -> HTMLResponse:
        return HTMLResponse(render_page(path, settings))

    return Route(f"/{path}", public_page)


def _text_route(path: str, content: str, media_type: str) -> Route:
    async def text_file(request: Request) -> Response:
        return Response(content, media_type=media_type)

    return Route(path, text_file)


def _verification_route(verification_file: str) -> Route:
    async def verification(request: Request) -> PlainTextResponse:
        # Contenu attendu par Search Console pour ce fichier
        return PlainTextResponse(f"google-site-verification: {verification_file}", media_type="text/html")

    return Route(f"/{verification_file}", verification)
