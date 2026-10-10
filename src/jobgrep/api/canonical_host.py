"""Une seule adresse pour le site : les pages demandées à une autre y sont renvoyées.

L'instance répond aussi à l'adresse que lui donne l'hébergeur. Un moteur de recherche y verrait un second site,
copie du premier, et partagerait entre les deux ce qu'il accorde à chacun.
"""

from urllib.parse import quote, urlsplit

from starlette.datastructures import Headers
from starlette.responses import RedirectResponse
from starlette.types import ASGIApp, Receive, Scope, Send

API_PATH = "/api"


class CanonicalHostMiddleware:
    """Renvoie vers l'adresse publique du site toute page demandée sous un autre nom d'hôte.

    L'API n'est pas concernée : la sonde de disponibilité l'appelle à l'adresse de l'hébergeur, et une
    redirection ferait perdre son corps à une requête qui modifie des données.
    """

    def __init__(self, app: ASGIApp, site_url: str):
        self.app = app
        self.site_url = site_url.rstrip("/")
        self.host = urlsplit(site_url).netloc.lower()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and self._is_served_elsewhere(scope):
            target = self.site_url + quote(scope["path"])
            if scope["query_string"]:
                target += "?" + scope["query_string"].decode("latin-1")
            await RedirectResponse(target, status_code=301)(scope, receive, send)
            return
        await self.app(scope, receive, send)

    def _is_served_elsewhere(self, scope: Scope) -> bool:
        if scope["method"] not in ("GET", "HEAD"):
            return False
        path = scope["path"]
        if path == API_PATH or path.startswith(API_PATH + "/"):
            return False
        host = Headers(scope=scope).get("host", "").lower()
        return bool(host) and host != self.host
