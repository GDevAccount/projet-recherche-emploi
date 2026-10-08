"""Serveur de l'application : l'API sous /api, les pages légales et le front Angular à la racine.

Tout tient dans un seul processus, à une seule adresse : la base est un fichier sur un volume qui n'est pas
partagé entre machines, et le front appelle l'API sans changer d'origine.

Se lance avec : projet-recherche-emploi serve (en ligne), ou projet-recherche-emploi api (développement)
"""

from dotenv import load_dotenv
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from projet_recherche_emploi.api.frontend import build_frontend_routes
from projet_recherche_emploi.api.public_pages import build_routes
from projet_recherche_emploi.api.routers import account, cv, jobs, queries, searches
from projet_recherche_emploi.api.security import GoogleIdentityVerifier, IdentityVerifier
from projet_recherche_emploi.config import configure_logging
from projet_recherche_emploi.container import Container, get_container
from projet_recherche_emploi.errors import (
    AppError,
    ConfigurationError,
    ConflictError,
    InvalidInputError,
    NotFoundError,
    QuotaExceededError,
)

API_PREFIX = "/api"

STATUS_CODES = {
    InvalidInputError: status.HTTP_422_UNPROCESSABLE_CONTENT,
    NotFoundError: status.HTTP_404_NOT_FOUND,
    ConflictError: status.HTTP_409_CONFLICT,
    QuotaExceededError: status.HTTP_429_TOO_MANY_REQUESTS,
    ConfigurationError: status.HTTP_503_SERVICE_UNAVAILABLE,
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
    settings = container.settings

    # La documentation décrit toutes les routes : elle n'est servie qu'en développement
    documentation = {} if docs else {"docs_url": None, "redoc_url": None, "openapi_url": None}
    app = FastAPI(title="Recherche d'emploi", version="0.1.0", **documentation)
    app.state.container = container
    app.state.identity_verifier = identity_verifier or GoogleIdentityVerifier(settings.google_client_id)

    # Le front pèse plusieurs centaines de ko non compressé. Le flux d'une recherche (text/event-stream)
    # n'est pas concerné : le compresser le retiendrait, et son suivi n'arriverait plus en direct
    app.add_middleware(GZipMiddleware, minimum_size=1024)

    if settings.cors_origin_list:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origin_list,
            # Sans cela, le navigateur ne joint pas le cookie de session à une requête venue d'une autre origine
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["Authorization", "Content-Type"],
        )

    @app.exception_handler(AppError)
    def handle_app_error(request: Request, error: AppError) -> JSONResponse:
        status_code = STATUS_CODES.get(type(error), status.HTTP_400_BAD_REQUEST)
        return JSONResponse({"detail": str(error)}, status_code=status_code)

    @app.get(f"{API_PREFIX}/health", tags=["état"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    for router in (account.router, jobs.router, queries.router, cv.router, searches.router):
        app.include_router(router, prefix=API_PREFIX)

    # Pages légales, fichier de validation Google et fichiers du front, servis sans connexion
    app.router.routes.extend(build_routes(settings))
    # En dernier : le front reçoit toute adresse que l'API et les pages publiques n'ont pas prise
    app.router.routes.extend(build_frontend_routes(settings))
    return app


def create_server_app() -> FastAPI:
    """Point d'entrée du serveur en ligne : comme create_app, sans la documentation de l'API."""
    return create_app(docs=False)
