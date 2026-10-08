from projet_recherche_emploi.config import CONTRACT_TYPES
from projet_recherche_emploi.data.database import Database
from projet_recherche_emploi.data.query_repository import QueryRepository
from projet_recherche_emploi.errors import ConflictError, InvalidInputError, NotFoundError
from projet_recherche_emploi.schemas import SearchQueryRead


class QueryService:
    def __init__(self, database: Database):
        self.database = database

    def list_queries(self, user_id: int) -> list[SearchQueryRead]:
        """Renvoie les postes recherchés de l'utilisateur, dans l'ordre de création."""
        with self.database.session() as session:
            queries = QueryRepository(session, user_id).list_queries()
            return [SearchQueryRead.model_validate(query) for query in queries]

    def add_query(self, user_id: int, contract_type: str, query: str) -> SearchQueryRead:
        """Enregistre un poste recherché."""
        query = query.strip()
        if not query:
            raise InvalidInputError("La recherche est vide.")
        if contract_type not in CONTRACT_TYPES:
            raise InvalidInputError(f"Type de contrat inconnu : {contract_type}.")

        with self.database.session() as session:
            created = QueryRepository(session, user_id).add_query(contract_type, query)
            if created is None:
                raise ConflictError("Cette recherche existe déjà.")
            return SearchQueryRead.model_validate(created)

    def delete_query(self, user_id: int, query_id: int) -> None:
        """Supprime un poste recherché."""
        with self.database.session() as session:
            if not QueryRepository(session, user_id).delete_query(query_id):
                raise NotFoundError("Cette recherche n'existe pas.")
