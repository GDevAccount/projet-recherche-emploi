"""Commande jobgrep.

Sans argument, lance une recherche pour le propriétaire, sans passer par le serveur.
"""

import argparse
import logging

from dotenv import load_dotenv

from jobgrep.config import DEFAULT_USER_ID, configure_logging
from jobgrep.container import get_container
from jobgrep.errors import AppError
from jobgrep.schemas import SearchProgress

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


def index_texts() -> None:
    # Au déploiement, pour que la première question à l'assistant n'attende pas ce calcul. Un échec ne doit
    # pas empêcher le serveur de démarrer : la première question le refera
    try:
        logger.info("%d passage(s) des textes du site prêts pour l'assistant", get_container().assistant.index_texts())
    except Exception as error:
        logger.warning("Les textes du site n'ont pas pu être préparés pour l'assistant : %s", type(error).__name__)


def purge() -> None:
    account = get_container().account
    logger.info("%d compte(s) inactif(s) supprimé(s)", account.delete_inactive_accounts())
    logger.info("%d ligne(s) effacée(s), leur durée de conservation étant passée", account.forget_expired_records())


def evaluate() -> None:
    # Chaque question de référence appelle les modèles : l'évaluation coûte, et ne se lance qu'à la demande
    result = get_container().evaluation.run()

    def percent(rate: float | None) -> str:
        return "—" if rate is None else f"{rate:.0%}"

    logger.info(
        "Évaluation %d, consignes %s : %d question(s) sur %d sans reproche",
        result.id,
        result.prompt_version,
        result.passed,
        result.cases,
    )
    logger.info(
        "Section retrouvée %s, issue attendue %s, réponse juste %s, fidèle aux passages %s, hors-sujet refusé %s",
        percent(result.retrieval_rate),
        percent(result.outcome_rate),
        percent(result.correct_rate),
        percent(result.faithful_rate),
        percent(result.refusal_rate),
    )
    for case in result.results:
        if not case.passed:
            logger.info("À revoir : %s (%s) %s", case.id, case.outcome, case.judge_reason)


def serve_api() -> None:
    import uvicorn

    uvicorn.run("jobgrep.api.main:create_app", factory=True, host="127.0.0.1", port=PORT)


def serve() -> None:
    import uvicorn

    # Toutes les interfaces : dans un conteneur, la requête arrive par le réseau de l'hébergeur
    uvicorn.run("jobgrep.api.main:create_server_app", factory=True, host="0.0.0.0", port=PORT)


COMMANDS = {
    "search": (run_search, "lance une recherche pour le propriétaire (par défaut)"),
    "graph": (draw_graph, "génère le schéma du graph dans graph.png"),
    "migrate": (migrate, "crée la base ou l'amène à la dernière version du schéma"),
    "index": (index_texts, "prépare les textes du site pour l'assistant, si l'un d'eux a changé (appel à OpenAI)"),
    "evaluate": (evaluate, "pose à l'assistant ses questions de référence et note ses réponses (appels payants)"),
    "purge": (purge, "supprime les comptes d'invités inactifs depuis trop longtemps (fait aussi par le serveur)"),
    "api": (serve_api, "sert l'application en développement, avec la documentation : http://127.0.0.1:8000/docs"),
    "serve": (serve, "sert l'application en ligne sur le port 8000, sans la documentation de l'API"),
}


def main() -> None:
    parser = argparse.ArgumentParser(prog="jobgrep", description=__doc__)
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
