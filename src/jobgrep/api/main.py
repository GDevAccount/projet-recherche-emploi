"""Serveur de l'application : l'API sous /api, les pages légales et le front Angular à la racine.

Tout tient dans un seul processus, à une seule adresse : la base est un fichier sur un volume qui n'est pas
partagé entre machines, et le front appelle l'API sans changer d'origine.

Se lance avec : jobgrep serve (en ligne), ou jobgrep api (développement)
"""

from dotenv import load_dotenv
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from jobgrep.api.canonical_host import CanonicalHostMiddleware
from jobgrep.api.frontend import build_frontend_routes
from jobgrep.api.public_pages import build_routes
from jobgrep.api.routers import account, admin, assistant, cv, jobs, queries, searches
from jobgrep.api.security import GoogleIdentityVerifier, IdentityVerifier
from jobgrep.api.security_headers import SecurityHeadersMiddleware
from jobgrep.config import configure_logging
from jobgrep.container import Container, get_container
from jobgrep.errors import (
    AppError,
    AssistantUnavailableError,
    BudgetReachedError,
    ConfigurationError,
    ConflictError,
    InvalidInputError,
    NotFoundError,
    QuotaExceededError,
)

API_PREFIX = "/api"
INTERNAL_ERROR_MESSAGE = "Le serveur a rencontré une erreur. Réessayez dans un instant."

STATUS_CODES = {
    InvalidInputError: status.HTTP_422_UNPROCESSABLE_CONTENT,
    NotFoundError: status.HTTP_404_NOT_FOUND,
    ConflictError: status.HTTP_409_CONFLICT,
    QuotaExceededError: status.HTTP_429_TOO_MANY_REQUESTS,
    BudgetReachedError: status.HTTP_429_TOO_MANY_REQUESTS,
    ConfigurationError: status.HTTP_503_SERVICE_UNAVAILABLE,
    AssistantUnavailableError: status.HTTP_503_SERVICE_UNAVAILABLE,
}


def create_app(
    container: Container | None = None, identity_verifier: IdentityVerifier | None = None, docs: bool = True
) -> FastAPI:
    """Construit le serveur. Sans conteneur, c'est son point d'entrée : il charge alors .env et règle les logs."""
    if container is None:
        load_dotenv()
        configure_logging()
        container = get_container()
        # Une connexion à moitié réglée arrête le serveur au lieu de refuser tout le monde une fois en ligne
        container.auth.check_configuration()
        container.account.delete_inactive_accounts_if_due()
        # Aucune recherche ne tourne encore : celles restées « en cours » viennent d'être coupées
        container.health.alert_on_interrupted_runs()
    settings = container.settings

    # La documentation décrit toutes les routes : elle n'est servie qu'en développement
    documentation = {} if docs else {"docs_url": None, "redoc_url": None, "openapi_url": None}
    app = FastAPI(title="JobGrep", version="0.1.0", **documentation)
    app.state.container = container
    app.state.identity_verifier = identity_verifier or GoogleIdentityVerifier(settings.google_client_id)

    # Le front pèse plusieurs centaines de ko non compressé. Le flux d'une recherche (text/event-stream)
    # n'est pas concerné : le compresser le retiendrait, et son suivi n'arriverait plus en direct
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    if settings.site_url:
        app.add_middleware(CanonicalHostMiddleware, site_url=settings.site_url)
    documentation_paths = frozenset(path for path in (app.docs_url, app.redoc_url) if path)
    app.add_middleware(SecurityHeadersMiddleware, unrestricted_paths=documentation_paths)

    if settings.cors_origin_list:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origin_list,
            # Sans cela, le navigateur ne joint pas le cookie de session à une requête venue d'une autre origine
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["Authorization", "Content-Type"],
        )

    def record_error(request: Request, error: Exception, status_code: int) -> None:
        # Le type de l'erreur, jamais son message : il peut contenir ce que l'utilisateur a envoyé
        user_id = getattr(request.state, "user_id", None)
        route = route_template(request)
        container.health.record_error(user_id, request.method, route, status_code, type(error).__name__)

    @app.exception_handler(AppError)
    def handle_app_error(request: Request, error: AppError) -> JSONResponse:
        # Par famille : une erreur plus précise qu'une de ces classes garde le code de celle-ci
        codes = (code for kind, code in STATUS_CODES.items() if isinstance(error, kind))
        status_code = next(codes, status.HTTP_400_BAD_REQUEST)
        record_error(request, error, status_code)
        return JSONResponse({"detail": str(error)}, status_code=status_code)

    @app.exception_handler(Exception)
    def handle_unexpected_error(request: Request, error: Exception) -> JSONResponse:
        # Les logs de l'hébergeur ne sont pas conservés : sans cette trace, la panne ne se verrait pas
        record_error(request, error, status.HTTP_500_INTERNAL_SERVER_ERROR)
        return JSONResponse({"detail": INTERNAL_ERROR_MESSAGE}, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

    # HEAD aussi : c'est la méthode des sondes de disponibilité, et FastAPI ne l'accepte pas de lui-même
    @app.head(f"{API_PREFIX}/health", include_in_schema=False)
    @app.get(f"{API_PREFIX}/health", tags=["état"])
    def health() -> JSONResponse:
        """État du serveur et de sa base, pour une sonde extérieure : 200 si tout répond, 503 sinon."""
        if container.health.is_alive():
            return JSONResponse({"status": "ok"})
        return JSONResponse({"status": "error"}, status_code=status.HTTP_503_SERVICE_UNAVAILABLE)

    routers = (account, jobs, queries, cv, searches, assistant, admin)
    for router in (module.router for module in routers):
        app.include_router(router, prefix=API_PREFIX)

    # Pages publiques, fichiers lus par les robots et fichiers du front, servis sans connexion
    app.router.routes.extend(build_routes(settings))
    # En dernier : le front reçoit toute adresse que l'API et les pages publiques n'ont pas prise
    app.router.routes.extend(build_frontend_routes(settings))
    return app


def route_template(request: Request) -> str | None:
    """Renvoie le modèle de la route appelée (« /api/jobs/{job_id} »), ou None si aucune n'a été trouvée.

    Jamais l'adresse elle-même, qui porte des identifiants.
    """
    route = request.scope.get("route")
    if route is None:
        return None
    template = route.path.strip("/").split("/")
    called = request.url.path.strip("/").split("/")
    # Le modèle d'une route incluse ne porte pas le préfixe de son routeur : il se lit en tête de l'adresse
    return "/" + "/".join(called[: len(called) - len(template)] + template)


def create_server_app() -> FastAPI:
    """Point d'entrée du serveur en ligne : comme create_app, sans la documentation de l'API."""
    return create_app(docs=False)
