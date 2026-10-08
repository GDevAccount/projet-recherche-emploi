import logging

from langgraph.config import get_stream_writer

from projet_recherche_emploi.agent.ports import JobEvaluation, JobEvaluator, JobSearchEngine
from projet_recherche_emploi.agent.state import JobSearchState
from projet_recherche_emploi.config import DEFAULT_USER_ID
from projet_recherche_emploi.data.cv_storage import CvStorage
from projet_recherche_emploi.data.database import Database
from projet_recherche_emploi.data.job_repository import JobRepository
from projet_recherche_emploi.data.query_repository import QueryRepository
from projet_recherche_emploi.data.rejected_job_repository import RejectedJobRepository

logger = logging.getLogger(__name__)


def get_user_id(state: JobSearchState) -> int:
    # Sans utilisateur dans l'état, la recherche est celle de l'utilisateur par défaut
    return state.get("user_id", DEFAULT_USER_ID)


def build_search_text(contract_type: str, query: str) -> str:
    """Renvoie le texte envoyé au moteur de recherche : la recherche, avec son type de contrat s'il n'y est pas."""
    if contract_type.casefold() in query.casefold():
        return query
    return f"{query} {contract_type}"


class SearchNodes:
    """Les quatre étapes du graph. Chacune ouvre sa propre session : une recherche dure plusieurs minutes."""

    def __init__(
        self,
        database: Database,
        cv_storage: CvStorage,
        search_engine: JobSearchEngine,
        evaluator: JobEvaluator,
    ):
        self.database = database
        self.cv_storage = cv_storage
        self.search_engine = search_engine
        self.evaluator = evaluator

    def search_jobs(self, state: JobSearchState) -> dict:
        with self.database.session() as session:
            queries = [
                (query.contract_type, query.query)
                for query in QueryRepository(session, get_user_id(state)).list_queries()
            ]
        if not queries:
            logger.warning("Aucune recherche enregistrée en base : rien à chercher")

        write_progress = get_stream_writer()

        jobs_by_url = {}
        for index, (contract_type, query) in enumerate(queries):
            search_text = build_search_text(contract_type, query)
            write_progress(
                {
                    "message": f"Recherche Tavily {index + 1}/{len(queries)} : {search_text}",
                    "done": index,
                    "total": len(queries),
                }
            )
            for result in self.search_engine.search(search_text):
                jobs_by_url.setdefault(
                    result["url"],
                    {
                        "title": result["title"],
                        "url": result["url"],
                        "content": result["content"],
                        "raw_content": result.get("raw_content"),
                        "score": result["score"],
                        "query": query,
                    },
                )

        return {"jobs": list(jobs_by_url.values())}

    def filter_duplicates(self, state: JobSearchState) -> dict:
        # Écarter les pages déjà évaluées avant le filtre évite de payer un appel au modèle pour rien.
        # Les offres supprimées comptent aussi : leur URL reste en base pour qu'elles ne reviennent pas.
        # Les pages rejetées de même : le modèle les rejetterait à nouveau.
        user_id = get_user_id(state)
        with self.database.session() as session:
            known_urls = (
                JobRepository(session, user_id).list_known_urls()
                | RejectedJobRepository(session, user_id).list_known_urls()
            )
        jobs = state["jobs"]
        new_jobs = [job for job in jobs if job["url"] not in known_urls]
        logger.info("%d page(s) nouvelle(s) sur %d trouvée(s)", len(new_jobs), len(jobs))
        get_stream_writer()({"message": f"{len(new_jobs)} page(s) nouvelle(s) sur {len(jobs)} trouvée(s)"})
        return {"new_jobs": new_jobs}

    def filter_jobs(self, state: JobSearchState) -> dict:
        jobs = state["new_jobs"]
        if not jobs:
            return {"filtered_jobs": [], "rejected_jobs": []}

        cv_content = self.cv_storage.read_text(get_user_id(state))

        write_progress = get_stream_writer()
        write_progress({"message": f"Évaluation par OpenAI 0/{len(jobs)}", "done": 0, "total": len(jobs)})

        # Les réponses arrivent dans le désordre : l'indice les remet en face de leur offre
        evaluations: list[JobEvaluation | None] = [None] * len(jobs)
        for done, (index, evaluation) in enumerate(self.evaluator.evaluate(cv_content, jobs), start=1):
            evaluations[index] = evaluation
            write_progress(
                {"message": f"Évaluation par OpenAI {done}/{len(jobs)}", "done": done, "total": len(jobs)}
            )

        filtered_jobs = []
        rejected_jobs = []
        for job, evaluation in zip(jobs, evaluations, strict=True):
            # Le contrat enregistré est celui de la page : une recherche de CDI ramène aussi des missions
            job = {**job, "contract_type": evaluation.contract_type}
            if evaluation.is_real_offer and evaluation.matches_cv:
                filtered_jobs.append({**job, "match_reason": evaluation.reason})
            else:
                rejected_jobs.append(
                    {
                        **job,
                        "is_real_offer": evaluation.is_real_offer,
                        "matches_cv": evaluation.matches_cv,
                        "reject_reason": evaluation.reason,
                    }
                )
        return {"filtered_jobs": filtered_jobs, "rejected_jobs": rejected_jobs}

    def insert_jobs(self, state: JobSearchState) -> dict:
        user_id = get_user_id(state)
        filtered_jobs = state["filtered_jobs"]
        rejected_jobs = state["rejected_jobs"]
        # Une seule transaction : une page évaluée finit dans l'une des deux tables, ou dans aucune
        with self.database.session() as session:
            inserted_count = JobRepository(session, user_id).insert_jobs(filtered_jobs)
            RejectedJobRepository(session, user_id).insert_rejected_jobs(rejected_jobs)
        logger.info(
            "%d offre(s) insérée(s) sur %d retenue(s) (%d déjà en base)",
            inserted_count,
            len(filtered_jobs),
            len(filtered_jobs) - inserted_count,
        )
        logger.info("%d page(s) rejetée(s) mémorisée(s)", len(rejected_jobs))
        return {"inserted_count": inserted_count}
