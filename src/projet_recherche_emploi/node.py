import logging

from dotenv import load_dotenv
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langchain_tavily import TavilySearch
from pydantic import BaseModel

from projet_recherche_emploi.config import CV_PATH, DB_PATH, FILTER_MODEL, MAX_PAGE_CHARS
from projet_recherche_emploi.cv_reader import CV_reader
from projet_recherche_emploi.job_repository import JobRepository
from projet_recherche_emploi.query_repository import QueryRepository
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
    "jobintree.com"
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

    queries = QueryRepository(DB_PATH).list_queries()
    if not queries:
        logger.warning("Aucune recherche enregistrée en base : rien à chercher")

    jobs_by_url = {}
    for contract_type, query in ((q["contract_type"], q["query"]) for q in queries):
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
    # Écarter les offres déjà en base avant le filtre évite de payer un appel au modèle pour rien.
    # Les offres supprimées comptent aussi : leur URL reste en base pour qu'elles ne reviennent pas.
    known_urls = JobRepository(DB_PATH).list_known_urls()
    jobs = state["jobs"]
    new_jobs = [job for job in jobs if job["url"] not in known_urls]
    logger.info("%d page(s) nouvelle(s) sur %d trouvée(s)", len(new_jobs), len(jobs))
    return {"new_jobs": new_jobs}


def filter_jobs(state: JobSearchState) -> dict:
    cv_content = CV_reader(CV_PATH).get_cv_content()

    evaluator = FILTER_PROMPT | ChatOpenAI(model=FILTER_MODEL).with_structured_output(JobEvaluation)

    jobs = state["new_jobs"]
    evaluations = evaluator.batch(
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

    filtered_jobs = [
        {**job, "match_reason": evaluation.reason}
        for job, evaluation in zip(jobs, evaluations)
        if evaluation.is_real_offer and evaluation.matches_cv
    ]
    return {"filtered_jobs": filtered_jobs}


def insert_jobs(state: JobSearchState) -> dict:
    filtered_jobs = state["filtered_jobs"]
    inserted_count = JobRepository(DB_PATH).insert_jobs(filtered_jobs)
    logger.info(
        "%d offre(s) insérée(s) sur %d retenue(s) (%d déjà en base)",
        inserted_count,
        len(filtered_jobs),
        len(filtered_jobs) - inserted_count,
    )
    return {"inserted_count": inserted_count}
