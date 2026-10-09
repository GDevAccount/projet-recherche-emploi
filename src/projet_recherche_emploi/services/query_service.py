from projet_recherche_emploi.config import CONTRACT_TYPES
from projet_recherche_emploi.data.database import Database
from projet_recherche_emploi.data.repositories.query_repository import QueryRepository
from projet_recherche_emploi.data.repositories.rejected_job_repository import RejectedJobRepository
from projet_recherche_emploi.errors import ConflictError, InvalidInputError, NotFoundError
from projet_recherche_emploi.schemas import SearchQueryRead

# Le lieu est recopié dans le prompt du filtre : une ville ou une région, pas un texte libre
MAX_LOCATION_CHARS = 100


class QueryService:
    def __init__(self, database: Database):
        self.database = database

    def list_queries(self, user_id: int) -> list[SearchQueryRead]:
        """Renvoie les postes recherchés de l'utilisateur, dans l'ordre de création."""
        with self.database.session() as session:
            queries = QueryRepository(session, user_id).list_queries()
            return [SearchQueryRead.model_validate(query) for query in queries]

    def add_query(
        self, user_id: int, contract_type: str, query: str, location: str = "", remote: bool = False
    ) -> SearchQueryRead:
        """Enregistre un poste recherché, pour un lieu, pour le télétravail complet ou pour toute la France."""
        query = query.strip()
        # En télétravail complet, le lieu ne compte pas
        location = "" if remote else location.strip()
        if not query:
            raise InvalidInputError("La recherche est vide.")
        if contract_type not in CONTRACT_TYPES:
            raise InvalidInputError(f"Type de contrat inconnu : {contract_type}.")
        if len(location) > MAX_LOCATION_CHARS:
            raise InvalidInputError(f"Le lieu dépasse {MAX_LOCATION_CHARS} caractères.")

        with self.database.session() as session:
            created = QueryRepository(session, user_id).add_query(contract_type, query, location, remote)
            if created is None:
                raise ConflictError("Cette recherche existe déjà.")
            # Une page rejetée pour son métier, son contrat ou son lieu peut convenir à cette nouvelle recherche
            RejectedJobRepository(session, user_id).clear_search_dependent_rejections()
            return SearchQueryRead.model_validate(created)

    def delete_query(self, user_id: int, query_id: int) -> None:
        """Supprime un poste recherché."""
        with self.database.session() as session:
            if not QueryRepository(session, user_id).delete_query(query_id):
                raise NotFoundError("Cette recherche n'existe pas.")
