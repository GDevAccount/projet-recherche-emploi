from collections.abc import Sequence

from jobgrep.config import (
    CONTRACT_TYPES,
    MAX_DRAFTED_TITLE_CHARS,
    MAX_PROFILE_JOBS,
    MAX_SKILL_CHARS,
    MAX_SKILLS_PER_QUERY,
    SKILL_SUGGESTIONS,
)
from jobgrep.cv_agent.ports import Extraction
from jobgrep.data.database import Database
from jobgrep.data.repositories.cv_extraction_repository import CvExtractionRepository
from jobgrep.data.repositories.query_repository import QueryRepository
from jobgrep.data.repositories.rejected_job_repository import RejectedJobRepository
from jobgrep.data.repositories.skill_repository import SkillRepository
from jobgrep.data.skills_catalog import fold_skill
from jobgrep.errors import ConflictError, InvalidInputError, NotFoundError
from jobgrep.schemas import SearchQueryRead

# Le lieu est recopié dans le prompt du filtre : une ville ou une région, pas un texte libre
MAX_LOCATION_CHARS = 100


def clean_skills(skills: Sequence[str]) -> list[str]:
    """Renvoie les compétences saisies sans espaces superflus, sans vide ni doublon, dans l'ordre de saisie."""
    cleaned: dict[str, str] = {}
    for skill in skills:
        skill = " ".join(skill.split())
        if skill:
            cleaned.setdefault(fold_skill(skill), skill)
    return list(cleaned.values())


def _spell_like_catalog(session, skills: Sequence[str]) -> list[str]:
    """Renvoie ces compétences écrites comme le référentiel quand elles y sont : « sap » devient « SAP »."""
    known = {skill.search_name: skill.name for skill in SkillRepository(session).find(map(fold_skill, skills))}
    return [known.get(fold_skill(skill), skill) for skill in skills]


def _capitalize(text: str) -> str:
    """Met une majuscule au début de ce qu'un modèle a écrit, qui en met une fois sur deux ; le reste ne change pas."""
    return text[:1].upper() + text[1:]


def _check_job(
    contract_type: str, query: str, location: str, remote: bool, skills: Sequence[str]
) -> tuple[str, str, list[str]]:
    """Renvoie le métier, le lieu et les compétences d'un poste saisi, nettoyés, ou refuse ce qui ne se cherche pas."""
    query = query.strip()
    skills = clean_skills(skills)
    # En télétravail complet, le lieu ne compte pas
    location = "" if remote else location.strip()
    if not query:
        raise InvalidInputError("La recherche est vide.")
    if contract_type not in CONTRACT_TYPES:
        raise InvalidInputError(f"Type de contrat inconnu : {contract_type}.")
    if len(location) > MAX_LOCATION_CHARS:
        raise InvalidInputError(f"Le lieu dépasse {MAX_LOCATION_CHARS} caractères.")
    if len(skills) > MAX_SKILLS_PER_QUERY:
        raise InvalidInputError(f"Un poste accepte au plus {MAX_SKILLS_PER_QUERY} compétences.")
    if any(len(skill) > MAX_SKILL_CHARS for skill in skills):
        raise InvalidInputError(f"Une compétence dépasse {MAX_SKILL_CHARS} caractères.")
    return query, location, skills


class QueryService:
    def __init__(self, database: Database):
        self.database = database

    def list_queries(self, user_id: int) -> list[SearchQueryRead]:
        """Renvoie les postes recherchés de l'utilisateur, dans l'ordre de création."""
        with self.database.session() as session:
            queries = QueryRepository(session, user_id).list_queries()
            return [SearchQueryRead.model_validate(query) for query in queries]

    def add_query(
        self,
        user_id: int,
        contract_type: str,
        query: str,
        location: str = "",
        remote: bool = False,
        skills: Sequence[str] = (),
    ) -> SearchQueryRead:
        """Enregistre un poste recherché, pour un lieu, pour le télétravail complet ou pour toute la France."""
        query, location, skills = _check_job(contract_type, query, location, remote, skills)

        with self.database.session() as session:
            skills = _spell_like_catalog(session, skills)
            created = QueryRepository(session, user_id).add_query(contract_type, query, location, remote, skills)
            if created is None:
                raise ConflictError("Cette recherche existe déjà.")
            # Une page rejetée pour son métier, son contrat ou son lieu peut convenir à cette nouvelle recherche
            RejectedJobRepository(session, user_id).clear_search_dependent_rejections()
            return SearchQueryRead.model_validate(created)

    def update_query(
        self,
        user_id: int,
        query_id: int,
        contract_type: str,
        query: str,
        location: str = "",
        remote: bool = False,
        skills: Sequence[str] = (),
    ) -> SearchQueryRead:
        """Modifie un poste recherché, selon les mêmes règles qu'à son ajout, et le renvoie."""
        query, location, skills = _check_job(contract_type, query, location, remote, skills)

        with self.database.session() as session:
            queries = QueryRepository(session, user_id)
            saved = queries.get_query(query_id)
            if saved is None:
                raise NotFoundError("Cette recherche n'existe pas.")
            before = (saved.contract_type, saved.query, saved.location, saved.remote)
            skills = _spell_like_catalog(session, skills)
            if not queries.update_query(query_id, contract_type, query, location, remote, skills):
                raise ConflictError("Cette recherche existe déjà.")
            # Les compétences ne trient pas : elles seules changées, aucun rejet n'est à revoir, ni à repayer
            if before != (contract_type, query, location, remote):
                RejectedJobRepository(session, user_id).clear_search_dependent_rejections()
            session.refresh(saved)
            return SearchQueryRead.model_validate(saved)

    def apply_profile(self, user_id: int, extraction: Extraction) -> list[SearchQueryRead]:
        """Remplace les postes recherchés de l'utilisateur par ceux qu'un modèle a tirés de son CV, et les renvoie.

        La lecture du CV est enregistrée dans tous les cas : elle a été payée, et compte dans la limite du jour.
        Ce que le modèle propose est tenu aux mêmes règles qu'une saisie ; un poste qui ne les suit pas est
        écarté. S'il n'en reste aucun, les postes en place ne sont pas touchés.
        """
        profile, usage = extraction.profile, extraction.usage
        location = "" if profile.remote else " ".join(profile.location.split())
        # Un lieu trop long n'est pas un département ni une région : mieux vaut toute la France
        location = location if len(location) <= MAX_LOCATION_CHARS else ""
        with self.database.session() as session:
            # L'écriture d'abord : une transaction qui lit avant d'écrire est refusée pendant une recherche
            extractions = CvExtractionRepository(session, user_id)
            extraction_id = extractions.insert_extraction(
                {
                    "model": extraction.model,
                    "prompt_version": extraction.prompt_version,
                    "input_tokens": usage.input_tokens,
                    "output_tokens": usage.output_tokens,
                    "cache_read_tokens": usage.cache_read_tokens,
                    "cache_write_tokens": usage.cache_write_tokens,
                    "duration_ms": usage.duration_ms,
                }
            )
            drafts = []
            for job in profile.jobs:
                title = _capitalize(" ".join(job.title.split()))
                if title and len(title) <= MAX_DRAFTED_TITLE_CHARS and job.contract_type in CONTRACT_TYPES:
                    skills = [skill for skill in clean_skills(job.skills) if len(skill) <= MAX_SKILL_CHARS]
                    skills = [_capitalize(skill) for skill in skills]
                    skills = _spell_like_catalog(session, skills[:MAX_SKILLS_PER_QUERY])
                    drafts.append((job.contract_type, title, location, profile.remote, skills))
            if not drafts:
                return []
            queries = QueryRepository(session, user_id)
            queries.delete_all()
            # Deux fois le même métier ne donne qu'un poste
            created = [query for draft in drafts[:MAX_PROFILE_JOBS] if (query := queries.add_query(*draft))]
            extractions.set_queries_count(extraction_id, len(created))
            # Une page rejetée pour son métier, son contrat ou son lieu peut convenir à ces nouveaux postes
            RejectedJobRepository(session, user_id).clear_search_dependent_rejections()
            return [SearchQueryRead.model_validate(query) for query in created]

    def suggest_skills(self, user_id: int, text: str) -> list[str]:
        """Renvoie les compétences du référentiel qui contiennent ce texte, les plus proches d'abord.

        Le référentiel est le même pour tous : une compétence saisie hors de lui reste sur le poste de son auteur.
        """
        folded = fold_skill(text)
        if not folded:
            return []
        with self.database.session() as session:
            return [skill.name for skill in SkillRepository(session).search(folded, SKILL_SUGGESTIONS)]

    def delete_query(self, user_id: int, query_id: int) -> None:
        """Supprime un poste recherché."""
        with self.database.session() as session:
            if not QueryRepository(session, user_id).delete_query(query_id):
                raise NotFoundError("Cette recherche n'existe pas.")
