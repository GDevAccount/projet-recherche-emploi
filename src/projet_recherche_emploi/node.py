import logging

from dotenv import load_dotenv
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langchain_tavily import TavilySearch
from langgraph.config import get_stream_writer
from pydantic import BaseModel

from projet_recherche_emploi.config import DB_PATH, DEFAULT_USER_ID, FILTER_MODEL, MAX_PAGE_CHARS, cv_path
from projet_recherche_emploi.cv_reader import CV_reader
from projet_recherche_emploi.job_repository import JobRepository
from projet_recherche_emploi.query_repository import QueryRepository
from projet_recherche_emploi.rejected_job_repository import RejectedJobRepository
from projet_recherche_emploi.state import JobSearchState

load_dotenv()

logger = logging.getLogger(__name__)

JOB_SITES = [
    "welcometothejungle.com",
    "free-work.com",
    "malt.fr",
    "linkedin.com",
    "indeed.com",
    "apec.fr",
    "hellowork.com",
    "jobteaser.com",
    "monster.fr",
    "francetravail.fr",
    "jobijoba.com",
    "regionsjob.com",
    "cadremploi.fr",
    "keljob.com",
    "jobintree.com",
    "collective.work",
    "lehibou.com",
    "careerbuilder.com",
    "tekkit.io/offres",
    "fr.talent.com",
    "glassdoor.fr",
    "wellfound.com",
    "foorilla.com",
    "jobs.stationf.co"
]

FILTER_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "Tu évalues des pages web trouvées lors d'une recherche d'emploi, pour un candidat dont voici le CV.\n\n"
            "CV :\n{cv}\n\n"
            "Pour la page fournie, détermine :\n"
            "- is_real_offer : vrai seulement si la page décrit UNE offre d'emploi ou mission précise "
            "(un poste, une entreprise ou un client, des missions). Faux pour une liste ou une page de "
            "résultats de recherche regroupant plusieurs offres, un article, une fiche métier, une "
            "formation, une page d'accueil, une offre expirée ou une offre qui ne se situe pas en région parisienne.\n"
            "- matches_cv : vrai seulement si le poste correspond au profil du candidat "
            "(compétences, niveau d'expérience, domaine).\n"
            "- reason : une phrase qui justifie la décision.",
        ),
        ("human", "Titre : {title}\nURL : {url}\n\nContenu de la page :\n{page}"),
    ]
)


def get_user_id(state: JobSearchState) -> int:
    # Sans utilisateur dans l'état (commande sans interface), la recherche est celle de l'utilisateur par défaut
    return state.get("user_id", DEFAULT_USER_ID)


class JobEvaluation(BaseModel):
    is_real_offer: bool
    matches_cv: bool
    reason: str


def search_jobs(state: JobSearchState) -> dict:
    tavily = TavilySearch(
        max_results=20,
        search_depth="advanced",
        time_range="week",
        include_domains=JOB_SITES,
        include_raw_content=True,
    )

    queries = QueryRepository(DB_PATH, get_user_id(state)).list_queries()
    if not queries:
        logger.warning("Aucune recherche enregistrée en base : rien à chercher")

    write_progress = get_stream_writer()

    jobs_by_url = {}
    for index, (contract_type, query) in enumerate((q["contract_type"], q["query"]) for q in queries):
        write_progress(
            {
                "message": f"Recherche Tavily {index + 1}/{len(queries)} : {query}",
                "done": index,
                "total": len(queries),
            }
        )
        response = tavily.invoke({"query": query})

        # Sans résultat, l'outil Tavily renvoie un message texte au lieu du dict habituel
        if isinstance(response, str):
            logger.warning("Recherche sans résultat (%s) : %s", query, response)
            continue

        if "error" in response:
            raise RuntimeError(f"Tavily search failed: {response['error']}")

        for result in response["results"]:
            jobs_by_url.setdefault(
                result["url"],
                {
                    "title": result["title"],
                    "url": result["url"],
                    "content": result["content"],
                    "raw_content": result.get("raw_content"),
                    "score": result["score"],
                    "contract_type": contract_type,
                    "query": query,
                },
            )

    return {"jobs": list(jobs_by_url.values())}


def filter_duplicates(state: JobSearchState) -> dict:
    # Écarter les pages déjà évaluées avant le filtre évite de payer un appel au modèle pour rien.
    # Les offres supprimées comptent aussi : leur URL reste en base pour qu'elles ne reviennent pas.
    # Les pages rejetées de même : le modèle les rejetterait à nouveau.
    user_id = get_user_id(state)
    known_urls = (
        JobRepository(DB_PATH, user_id).list_known_urls()
        | RejectedJobRepository(DB_PATH, user_id).list_known_urls()
    )
    jobs = state["jobs"]
    new_jobs = [job for job in jobs if job["url"] not in known_urls]
    logger.info("%d page(s) nouvelle(s) sur %d trouvée(s)", len(new_jobs), len(jobs))
    get_stream_writer()({"message": f"{len(new_jobs)} page(s) nouvelle(s) sur {len(jobs)} trouvée(s)"})
    return {"new_jobs": new_jobs}


def filter_jobs(state: JobSearchState) -> dict:
    cv_content = CV_reader(cv_path(get_user_id(state))).get_cv_content()

    evaluator = FILTER_PROMPT | ChatOpenAI(model=FILTER_MODEL).with_structured_output(JobEvaluation)

    jobs = state["new_jobs"]
    write_progress = get_stream_writer()
    if jobs:
        write_progress({"message": f"Évaluation par OpenAI 0/{len(jobs)}", "done": 0, "total": len(jobs)})

    # Les réponses arrivent dans le désordre : l'indice les remet en face de leur offre
    evaluations = [None] * len(jobs)
    completed = evaluator.batch_as_completed(
        [
            {
                "cv": cv_content,
                "title": job["title"],
                "url": job["url"],
                "page": (job.get("raw_content") or job["content"])[:MAX_PAGE_CHARS],
            }
            for job in jobs
        ],
        config={"max_concurrency": 5},
    )
    for done, (index, evaluation) in enumerate(completed, start=1):
        evaluations[index] = evaluation
        write_progress(
            {"message": f"Évaluation par OpenAI {done}/{len(jobs)}", "done": done, "total": len(jobs)}
        )

    filtered_jobs = []
    rejected_jobs = []
    for job, evaluation in zip(jobs, evaluations):
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


def insert_jobs(state: JobSearchState) -> dict:
    user_id = get_user_id(state)
    filtered_jobs = state["filtered_jobs"]
    inserted_count = JobRepository(DB_PATH, user_id).insert_jobs(filtered_jobs)
    logger.info(
        "%d offre(s) insérée(s) sur %d retenue(s) (%d déjà en base)",
        inserted_count,
        len(filtered_jobs),
        len(filtered_jobs) - inserted_count,
    )

    rejected_jobs = state["rejected_jobs"]
    RejectedJobRepository(DB_PATH, user_id).insert_rejected_jobs(rejected_jobs)
    logger.info("%d page(s) rejetée(s) mémorisée(s)", len(rejected_jobs))
    return {"inserted_count": inserted_count}
