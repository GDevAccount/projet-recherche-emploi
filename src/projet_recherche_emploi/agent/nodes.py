import logging
import unicodedata
from collections.abc import Iterable

from langgraph.config import get_stream_writer

from projet_recherche_emploi.agent.ports import (
    CvReader,
    JobEvaluation,
    JobEvaluator,
    JobSearchEngine,
    SearchCriteria,
)
from projet_recherche_emploi.agent.state import JobSearchState
from projet_recherche_emploi.config import DEFAULT_USER_ID, FULL_REMOTE_MODE, TRAINING_CONTRACTS
from projet_recherche_emploi.data.database import Database
from projet_recherche_emploi.data.models import SearchQuery
from projet_recherche_emploi.data.repositories.job_repository import JobRepository
from projet_recherche_emploi.data.repositories.query_repository import QueryRepository
from projet_recherche_emploi.data.repositories.rejected_job_repository import RejectedJobRepository

logger = logging.getLogger(__name__)


def get_user_id(state: JobSearchState) -> int:
    # Sans utilisateur dans l'état, la recherche est celle de l'utilisateur par défaut
    return state.get("user_id", DEFAULT_USER_ID)


# Sans ces mots, une phrase courte ramène des listes d'offres au lieu d'annonces
OFFER_SEARCH_WORDS = "offre d'emploi"
# Une recherche qui contient l'un de ces mots vise déjà des annonces
OFFER_MARKERS = ("offre", "emploi", "mission", "job")
REMOTE_SEARCH_WORDS = "télétravail complet"
# Une recherche qui contient l'un de ces mots parle déjà de télétravail
REMOTE_MARKERS = ("remote", "télétravail")
ANYWHERE_IN_FRANCE = "toute la France"
REMOTE_LABEL = "Remote"
LOCATION_REJECT_REASON = "Lieu de travail hors des lieux recherchés"
UNKNOWN_PLACE = "lieu non précisé"
CONTRACT_REJECT_REASON = "Contrat non recherché"
RESTRICTED_REMOTE_REASON = "Télétravail réservé aux candidats d'un pays ou d'une zone sans la France"


def _fold(text: str) -> str:
    # « Ile-de-France » et « Île-de-France » sont le même lieu
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(char for char in decomposed if not unicodedata.combining(char)).casefold()


def build_search_text(contract_type: str, query: str, location: str = "", remote: bool = False) -> str:
    """Renvoie le texte envoyé au moteur de recherche pour les sites français.

    C'est la recherche, précédée de « offre d'emploi » et suivie de son type de contrat et de son lieu
    (ou du télétravail), s'ils n'y sont pas déjà.
    """
    folded_query = _fold(query)
    parts = [query]
    if not any(marker in folded_query for marker in OFFER_MARKERS):
        parts.insert(0, OFFER_SEARCH_WORDS)
    if _fold(contract_type) not in folded_query:
        parts.append(contract_type)
    if remote:
        if not any(_fold(marker) in folded_query for marker in REMOTE_MARKERS):
            parts.append(REMOTE_SEARCH_WORDS)
    elif location and _fold(location) not in folded_query:
        parts.append(location)
    return " ".join(parts)


def build_international_search_text(contract_type: str, query: str) -> str:
    """Renvoie la variante en anglais d'une recherche en télétravail complet, pour les annonces hors de France.

    Ni « offre d'emploi » ni « CDI » : une annonce étrangère ne contient pas ces mots.
    """
    folded_query = _fold(query)
    parts = [query]
    if "remote" not in folded_query:
        parts.append("remote")
    ending = "freelance" if contract_type == "freelance" else "job"
    if ending not in folded_query:
        parts.append(ending)
    return " ".join(parts)


def build_searches(queries: Iterable[SearchQuery]) -> list[tuple[str, str, bool]]:
    """Renvoie les recherches à lancer : la phrase saisie, le texte envoyé, et s'il vise les sites internationaux.

    Une recherche en télétravail complet en donne deux, l'une en français et l'autre en anglais.
    """
    searches = []
    for query in queries:
        text = build_search_text(query.contract_type, query.query, query.location, query.remote)
        searches.append((query.query, text, False))
        if query.remote:
            searches.append((query.query, build_international_search_text(query.contract_type, query.query), True))
    return searches


def describe_accepted_areas(queries: Iterable[SearchQuery]) -> str:
    """Renvoie les zones géographiques acceptées par l'ensemble des recherches, ou un texte vide s'il n'y en a pas.

    Un verdict est mémorisé par URL, pas par recherche : une page est donc jugée sur toutes les zones à la fois.
    Les recherches en télétravail complet n'en donnent aucune : voir accepts_full_remote.
    """
    areas = []
    for query in queries:
        if query.remote:
            continue
        if not query.location:
            # Une seule recherche sans lieu couvre les villes de toutes les autres
            return ANYWHERE_IN_FRANCE
        if query.location not in areas:
            areas.append(query.location)
    return " ; ".join(areas)


def accepts_full_remote(queries: Iterable[SearchQuery]) -> bool:
    """Dit si l'une des recherches accepte le télétravail complet, sans condition de pays."""
    return any(query.remote for query in queries)


def build_criteria(queries: Iterable[SearchQuery]) -> SearchCriteria:
    """Réunit ce que cherchent toutes les recherches enregistrées : métiers, contrats et lieux."""
    queries = list(queries)
    return SearchCriteria(
        sought_jobs=tuple(query.query for query in queries),
        contract_types=frozenset(query.contract_type for query in queries),
        accepted_areas=describe_accepted_areas(queries),
        accepts_full_remote=accepts_full_remote(queries),
    )


def contract_is_accepted(contract_type: str | None, searched_contract_types: Iterable[str]) -> bool:
    """Écarte un stage ou une alternance que personne n'a demandé. Tout autre contrat passe.

    Une recherche de CDI ramène aussi des missions, et l'inverse : seuls les contrats de formation sont tranchés.
    """
    return contract_type not in TRAINING_CONTRACTS or contract_type in searched_contract_types


def judge(evaluation: JobEvaluation, criteria: SearchCriteria) -> dict[str, bool]:
    """Renvoie le verdict critère par critère : l'offre est retenue si tous sont vrais.

    Le modèle donne son avis sur le métier, les compétences et le niveau ; le contrat et le lieu sont des règles.
    """
    return {
        "is_real_offer": evaluation.is_real_offer,
        "matches_search": evaluation.matches_search,
        "matches_contract": contract_is_accepted(evaluation.contract_type, criteria.contract_types),
        "matches_skills": evaluation.matches_skills,
        "matches_level": evaluation.matches_level,
        "matches_location": location_is_accepted(evaluation, criteria.accepted_areas, criteria.accepts_full_remote),
    }


def describe_rejection(evaluation: JobEvaluation, verdict: dict[str, bool], criteria: SearchCriteria) -> str:
    """Renvoie la raison du rejet : celle du modèle, précédée des règles du graph qui écartent l'offre."""
    reasons = []
    if evaluation.is_real_offer and not verdict["matches_contract"]:
        reasons.append(f"{CONTRACT_REJECT_REASON} ({evaluation.contract_type})")
    if evaluation.is_real_offer and not verdict["matches_location"]:
        reasons.append(describe_location_rejection(evaluation, criteria.accepts_full_remote))
    return ". ".join([*reasons, evaluation.reason])


def location_is_accepted(evaluation: JobEvaluation, accepted_areas: str, accepts_remote: bool) -> bool:
    """Applique les règles de lieu aux faits lus sur la page : le modèle les rapporte, il ne décide pas."""
    if accepts_remote and is_open_remote(evaluation):
        # Le télétravail complet n'a pas de frontière : l'employeur peut être à l'étranger
        return True
    # Sans recherche en télétravail, un poste à distance reste accepté si l'employeur est dans une zone.
    # Sans zone acceptée, l'avis du modèle sur la géographie ne vaut rien.
    return bool(accepted_areas) and evaluation.in_accepted_area


def is_open_remote(evaluation: JobEvaluation) -> bool:
    """Dit si le poste est en télétravail complet et ouvert à un candidat qui vit en France."""
    return evaluation.work_mode == FULL_REMOTE_MODE and evaluation.open_to_candidates_in_france


def describe_location_rejection(evaluation: JobEvaluation, accepts_remote: bool) -> str:
    """Renvoie la raison affichée quand c'est le lieu qui écarte une offre."""
    restricted = evaluation.work_mode == FULL_REMOTE_MODE and not evaluation.open_to_candidates_in_france
    if accepts_remote and restricted:
        return RESTRICTED_REMOTE_REASON
    return f"{LOCATION_REJECT_REASON} ({format_work_location(evaluation) or UNKNOWN_PLACE})"


def format_work_location(evaluation: JobEvaluation) -> str | None:
    """Renvoie le lieu affiché pour une offre : sa ville, ou « Remote » pour un poste en télétravail complet."""
    place = [evaluation.work_city] if evaluation.work_city else []
    if evaluation.work_country and _fold(evaluation.work_country) != "france":
        place.append(evaluation.work_country)
    place_text = ", ".join(place)
    if evaluation.work_mode == FULL_REMOTE_MODE:
        return f"{REMOTE_LABEL} ({place_text})" if place_text else REMOTE_LABEL
    return place_text or None


class SearchNodes:
    """Les quatre étapes du graph. Chacune ouvre sa propre session : une recherche dure plusieurs minutes."""

    def __init__(
        self,
        database: Database,
        cv_reader: CvReader,
        search_engine: JobSearchEngine,
        evaluator: JobEvaluator,
    ):
        self.database = database
        self.cv_reader = cv_reader
        self.search_engine = search_engine
        self.evaluator = evaluator

    def search_jobs(self, state: JobSearchState) -> dict:
        with self.database.session() as session:
            saved_queries = QueryRepository(session, get_user_id(state)).list_queries()
            criteria = build_criteria(saved_queries)
            queries = build_searches(saved_queries)
        if not queries:
            logger.warning("Aucune recherche enregistrée en base : rien à chercher")

        write_progress = get_stream_writer()

        jobs_by_url = {}
        for index, (query, search_text, international) in enumerate(queries):
            write_progress(
                {
                    "message": f"Recherche Tavily {index + 1}/{len(queries)} : {search_text}",
                    "step": "search",
                    "done": index,
                    "total": len(queries),
                    "found": len(jobs_by_url),
                }
            )
            for result in self.search_engine.search(search_text, international):
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

        return {"jobs": list(jobs_by_url.values()), "criteria": criteria}

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
        get_stream_writer()(
            {
                "message": f"{len(new_jobs)} page(s) nouvelle(s) sur {len(jobs)} trouvée(s)",
                "step": "dedupe",
                "found": len(jobs),
                "new": len(new_jobs),
            }
        )
        return {"new_jobs": new_jobs}

    def filter_jobs(self, state: JobSearchState) -> dict:
        jobs = state["new_jobs"]
        if not jobs:
            return {"filtered_jobs": [], "rejected_jobs": []}

        cv_content = self.cv_reader.read_text(get_user_id(state))

        write_progress = get_stream_writer()
        write_progress(
            {"message": f"Évaluation par OpenAI 0/{len(jobs)}", "step": "evaluate", "done": 0, "total": len(jobs)}
        )

        # Les réponses arrivent dans le désordre : l'indice les remet en face de leur offre
        evaluations: list[JobEvaluation | None] = [None] * len(jobs)
        verdicts: list[dict[str, bool] | None] = [None] * len(jobs)
        criteria = state["criteria"]
        for done, (index, evaluation) in enumerate(self.evaluator.evaluate(cv_content, criteria, jobs), start=1):
            evaluations[index] = evaluation
            # Jugée dès sa réponse, pour que l'avancement donne le verdict page par page
            verdicts[index] = judge(evaluation, criteria)
            write_progress(
                {
                    "message": f"Évaluation par OpenAI {done}/{len(jobs)}",
                    "step": "evaluate",
                    "done": done,
                    "total": len(jobs),
                    "title": jobs[index]["title"],
                    "kept": all(verdicts[index].values()),
                }
            )

        filtered_jobs = []
        rejected_jobs = []
        for job, evaluation, verdict in zip(jobs, evaluations, verdicts, strict=True):
            # Le contrat et le lieu enregistrés sont ceux de la page : une recherche de CDI ramène aussi des missions
            work_location = format_work_location(evaluation)
            job = {**job, "contract_type": evaluation.contract_type, "work_location": work_location}
            if all(verdict.values()):
                filtered_jobs.append({**job, "match_reason": evaluation.reason})
                continue
            rejected_jobs.append(
                {
                    **job,
                    **verdict,
                    "page_kind": evaluation.page_kind,
                    "matches_cv": verdict["matches_skills"] and verdict["matches_level"],
                    "reject_reason": describe_rejection(evaluation, verdict, criteria),
                }
            )
        return {"filtered_jobs": filtered_jobs, "rejected_jobs": rejected_jobs}

    def insert_jobs(self, state: JobSearchState) -> dict:
        user_id = get_user_id(state)
        filtered_jobs = state["filtered_jobs"]
        rejected_jobs = state["rejected_jobs"]
        message = f"Enregistrement de {len(filtered_jobs)} offre(s) et de {len(rejected_jobs)} page(s) rejetée(s)"
        get_stream_writer()({"message": message, "step": "save"})
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
