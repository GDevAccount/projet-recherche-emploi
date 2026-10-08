"""Front Angular, servi à la même adresse que l'API : le cookie de session et le contrôle d'origine valent sans CORS.

Le front est construit à part (npm run build dans frontend/, ou l'image Docker) et occupe la racine du site.
Ses routes s'ajoutent en dernier : elles ne reçoivent que ce que l'API et les pages publiques n'ont pas pris.
"""

from pathlib import PurePosixPath

from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response
from starlette.routing import BaseRoute, Mount, Route
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

from projet_recherche_emploi.config import Settings

INDEX_FILE = "index.html"
# Chemins de l'API : une adresse inconnue y reste une erreur, elle ne revient pas au front
API_PATH = "api"
# Adresse du front tant que Streamlit occupait la racine : les favoris d'alors y pointent encore
FORMER_PATH = "/frontend"


class SinglePageApp(StaticFiles):
    """Fichiers du front. Une adresse inconnue reçoit la page d'accueil : c'est le routeur d'Angular qui la résout."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        try:
            response = await super().get_response(path, scope)
        except HTTPException as error:
            # Un fichier manquant (script, image) reste une erreur 404 : lui répondre du HTML la masquerait
            if error.status_code != 404 or PurePosixPath(path).suffix or _is_api_path(path):
                raise
            path = INDEX_FILE
            response = await super().get_response(path, scope)
        if path in (".", INDEX_FILE):
            # Les autres fichiers changent de nom à chaque build ; la page d'accueil, non
            response.headers["Cache-Control"] = "no-cache"
        return response


def build_frontend_routes(settings: Settings) -> list[BaseRoute]:
    """Renvoie les routes du front, ou rien s'il n'a pas été construit (tests, développement avec ng serve)."""
    if not (settings.frontend_dir / INDEX_FILE).is_file():
        return []
    return [
        Route(FORMER_PATH, _redirect_former_path),
        Route(FORMER_PATH + "/{path:path}", _redirect_former_path),
        Mount("/", app=SinglePageApp(directory=settings.frontend_dir, html=True), name="frontend"),
    ]


def _is_api_path(path: str) -> bool:
    # Le chemin reçu porte les séparateurs du système : des barres obliques inverses sous Windows
    return path.replace("\\", "/").split("/")[0] == API_PATH


async def _redirect_former_path(request: Request) -> RedirectResponse:
    target = "/" + request.path_params.get("path", "")
    if request.url.query:
        target += "?" + request.url.query
    return RedirectResponse(target, status_code=308)
