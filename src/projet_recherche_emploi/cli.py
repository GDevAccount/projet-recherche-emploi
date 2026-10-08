"""Commande projet-recherche-emploi.

Sans argument, lance une recherche pour le propriétaire, sans passer par le serveur.
"""

import argparse
import logging

from dotenv import load_dotenv

from projet_recherche_emploi.config import DEFAULT_USER_ID, configure_logging
from projet_recherche_emploi.container import get_container
from projet_recherche_emploi.errors import AppError
from projet_recherche_emploi.schemas import SearchProgress

logger = logging.getLogger(__name__)

PORT = 8000


def run_search() -> None:
    def log_progress(event: SearchProgress) -> None:
        logger.info(event.message)

    # Le propriétaire n'a pas de quota : le lancement est enregistré, jamais refusé
    summary = get_container().search.run_search(DEFAULT_USER_ID, log_progress)
    logger.info(
        "%d page(s) trouvée(s), %d pas encore évaluée(s), %d retenue(s), %d rejetée(s), %d nouvelle(s) en base",
        summary.found,
        summary.new,
        summary.kept,
        summary.rejected,
        summary.inserted,
    )


def draw_graph() -> None:
    # Le rendu passe par le service en ligne mermaid.ink : il n'est fait qu'à la demande
    get_container().graph.get_graph().draw_mermaid_png(output_file_path="graph.png")


def migrate() -> None:
    # Construire le conteneur met déjà la base à jour. L'image Docker passe par ici avant de servir :
    # une connexion à moitié réglée arrête donc le déploiement, comme une migration qui échoue
    get_container().auth.check_configuration()


def purge() -> None:
    deleted = get_container().account.delete_inactive_accounts()
    logger.info("%d compte(s) inactif(s) supprimé(s)", deleted)


def serve_api() -> None:
    import uvicorn

    uvicorn.run("projet_recherche_emploi.api.main:create_app", factory=True, host="127.0.0.1", port=PORT)


def serve() -> None:
    import uvicorn

    # Toutes les interfaces : dans un conteneur, la requête arrive par le réseau de l'hébergeur
    uvicorn.run("projet_recherche_emploi.api.main:create_server_app", factory=True, host="0.0.0.0", port=PORT)


COMMANDS = {
    "search": (run_search, "lance une recherche pour le propriétaire (par défaut)"),
    "graph": (draw_graph, "génère le schéma du graph dans graph.png"),
    "migrate": (migrate, "crée la base ou l'amène à la dernière version du schéma"),
    "purge": (purge, "supprime les comptes d'invités inactifs depuis trop longtemps (fait aussi à chaque démarrage)"),
    "api": (serve_api, "sert l'application en développement, avec la documentation : http://127.0.0.1:8000/docs"),
    "serve": (serve, "sert l'application en ligne sur le port 8000, sans la documentation de l'API"),
}


def main() -> None:
    parser = argparse.ArgumentParser(prog="projet-recherche-emploi", description=__doc__)
    subparsers = parser.add_subparsers(dest="command")
    for name, (_, description) in COMMANDS.items():
        subparsers.add_parser(name, help=description)
    arguments = parser.parse_args()

    load_dotenv()
    configure_logging()
    command, _ = COMMANDS[arguments.command or "search"]
    try:
        command()
    except AppError as error:
        parser.exit(1, f"{error}\n")
