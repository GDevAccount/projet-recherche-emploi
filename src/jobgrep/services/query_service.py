from collections.abc import Sequence

from jobgrep.config import CONTRACT_TYPES, MAX_SKILL_CHARS, MAX_SKILLS_PER_QUERY, SKILL_SUGGESTIONS
from jobgrep.data.database import Database
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

        with self.database.session() as session:
            # Une compétence du référentiel s'écrit comme lui : « sap » devient « SAP »
            known = {skill.search_name: skill.name for skill in SkillRepository(session).find(map(fold_skill, skills))}
            skills = [known.get(fold_skill(skill), skill) for skill in skills]
            created = QueryRepository(session, user_id).add_query(contract_type, query, location, remote, skills)
            if created is None:
                raise ConflictError("Cette recherche existe déjà.")
            # Une page rejetée pour son métier, son contrat ou son lieu peut convenir à cette nouvelle recherche
            RejectedJobRepository(session, user_id).clear_search_dependent_rejections()
            return SearchQueryRead.model_validate(created)

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
