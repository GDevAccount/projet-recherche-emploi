"""Serveur des tests de bout en bout du front (frontend/e2e/), lancé par Playwright.

C'est l'application entière, front construit compris, sur une base neuve dans un dossier temporaire, avec les
faux Tavily et OpenAI des tests : une recherche lancée depuis le navigateur ne coûte rien.

Se lance avec : uv run python tests/e2e_server.py <port>
"""

import sys
import tempfile
from pathlib import Path

import uvicorn
from conftest import FakeEvaluator, FakeSearchEngine

from projet_recherche_emploi.api.main import create_app
from projet_recherche_emploi.config import Settings, configure_logging
from projet_recherche_emploi.container import build_container

FRONTEND_DIR = Path(__file__).parents[1] / "frontend" / "dist" / "frontend" / "browser"
# Le même que dans frontend/e2e/ : sans connexion Google, il ouvre le compte du propriétaire
PASSWORD = "mot-de-passe-e2e"


def main() -> None:
    if not (FRONTEND_DIR / "index.html").is_file():
        sys.exit("Le front n'est pas construit : lancer « npm run build » dans frontend/.")
    configure_logging()
    with tempfile.TemporaryDirectory() as data_dir:
        # Les réglages sont passés ici, pour que ceux de la machine ne changent pas le mode de connexion
        settings = Settings(
            data_dir=Path(data_dir),
            frontend_dir=FRONTEND_DIR,
            app_password=PASSWORD,
            auth_cookie_secret="secret-des-tests-de-bout-en-bout",
            google_client_id="",
            # Le parcours se termine par un essai sans compte
            max_trials_per_day=5,
        )
        container = build_container(settings, FakeSearchEngine(), FakeEvaluator())
        uvicorn.run(create_app(container, docs=False), host="127.0.0.1", port=int(sys.argv[1]))


if __name__ == "__main__":
    main()
