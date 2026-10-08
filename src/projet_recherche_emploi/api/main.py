"""API HTTP, destinée au futur front Angular. Elle expose les mêmes services que l'interface Streamlit.

Se lance avec : projet-recherche-emploi api
"""

from dotenv import load_dotenv
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

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

STATUS_CODES = {
    InvalidInputError: status.HTTP_422_UNPROCESSABLE_CONTENT,
    NotFoundError: status.HTTP_404_NOT_FOUND,
    ConflictError: status.HTTP_409_CONFLICT,
    QuotaExceededError: status.HTTP_429_TOO_MANY_REQUESTS,
    ConfigurationError: status.HTTP_503_SERVICE_UNAVAILABLE,
}


def create_app(container: Container | None = None, identity_verifier: IdentityVerifier | None = None) -> FastAPI:
    """Construit l'API. Sans conteneur, c'est le point d'entrée du serveur : il charge alors .env et règle les logs."""
    if container is None:
        load_dotenv()
        configure_logging()
        container = get_container()
    settings = container.settings

    app = FastAPI(title="Recherche d'emploi", version="0.1.0")
    app.state.container = container
    app.state.identity_verifier = identity_verifier or GoogleIdentityVerifier(settings.google_client_id)

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

    @app.get("/api/health", tags=["état"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    for router in (account.router, jobs.router, queries.router, cv.router, searches.router):
        app.include_router(router, prefix="/api")

    # Pages légales et fichier de validation Google, servis sans connexion
    app.router.routes.extend(build_routes(settings))
    return app
