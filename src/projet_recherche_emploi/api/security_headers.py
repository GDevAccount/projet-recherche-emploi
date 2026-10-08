"""En-têtes de sécurité, posés sur toutes les réponses du serveur.

Ils limitent ce que le navigateur accepte de la page : d'où viennent ses scripts, qui peut l'inclure dans
un cadre, ce qu'elle dit d'elle aux sites vers lesquels elle renvoie.
"""

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

# Seule origine extérieure du front : le bouton « Se connecter avec Google » (Google Identity Services)
GOOGLE_IDENTITY = "https://accounts.google.com/gsi/"

CONTENT_SECURITY_POLICY = "; ".join(
    [
        "default-src 'self'",
        f"script-src 'self' {GOOGLE_IDENTITY}client",
        # PrimeNG et les pages légales écrivent leurs styles dans la page
        f"style-src 'self' 'unsafe-inline' {GOOGLE_IDENTITY}style",
        f"frame-src {GOOGLE_IDENTITY}",
        f"connect-src 'self' {GOOGLE_IDENTITY}",
        "img-src 'self' data:",
        "font-src 'self' data:",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "frame-ancestors 'none'",
    ]
)

SECURITY_HEADERS = {
    "Content-Security-Policy": CONTENT_SECURITY_POLICY,
    # Sans effet en HTTP, donc sur la machine du développeur : le navigateur ne le retient qu'en HTTPS
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}


class SecurityHeadersMiddleware:
    """Ajoute les en-têtes sans toucher au corps : le flux d'une recherche passe tel quel.

    Les pages de documentation de l'API, servies en développement seulement, chargent leurs scripts
    d'un autre site : elles ne reçoivent pas la politique de contenu.
    """

    def __init__(self, app: ASGIApp, unrestricted_paths: frozenset[str] = frozenset()):
        self.app = app
        self.unrestricted_paths = unrestricted_paths

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        unrestricted = scope["path"] in self.unrestricted_paths

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in SECURITY_HEADERS.items():
                    if not (unrestricted and name == "Content-Security-Policy"):
                        headers[name] = value
            await send(message)

        await self.app(scope, receive, send_with_headers)
