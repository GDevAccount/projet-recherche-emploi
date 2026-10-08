"""Front Angular, servi à la même adresse que l'API : le cookie de session et le contrôle d'origine valent sans CORS.

Le front est construit à part (npm run build dans frontend/, ou l'image Docker). Tant que Streamlit occupe
la racine du site, il est servi sous /frontend.
"""

from pathlib import PurePosixPath

from starlette.exceptions import HTTPException
from starlette.responses import Response
from starlette.routing import BaseRoute, Mount
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

from projet_recherche_emploi.config import Settings

# Doit rester égal à « baseHref » dans frontend/angular.json
FRONTEND_PATH = "/frontend"
INDEX_FILE = "index.html"


class SinglePageApp(StaticFiles):
    """Fichiers du front. Une adresse inconnue reçoit la page d'accueil : c'est le routeur d'Angular qui la résout."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        try:
            response = await super().get_response(path, scope)
        except HTTPException as error:
            # Un fichier manquant (script, image) reste une erreur 404 : lui répondre du HTML la masquerait
            if error.status_code != 404 or PurePosixPath(path).suffix:
                raise
            path = INDEX_FILE
            response = await super().get_response(path, scope)
        if path in (".", INDEX_FILE):
            # Les autres fichiers changent de nom à chaque build ; la page d'accueil, non
            response.headers["Cache-Control"] = "no-cache"
        return response


def build_frontend_routes(settings: Settings) -> list[BaseRoute]:
    """Renvoie la route du front, ou rien s'il n'a pas été construit (tests, développement avec ng serve)."""
    if not (settings.frontend_dir / INDEX_FILE).is_file():
        return []
    return [Mount(FRONTEND_PATH, app=SinglePageApp(directory=settings.frontend_dir, html=True), name="frontend")]
