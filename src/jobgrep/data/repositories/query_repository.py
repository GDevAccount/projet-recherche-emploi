from sqlalchemy import delete, select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from jobgrep.data.models import SearchQuery


class QueryRepository:
    def __init__(self, session: Session, user_id: int):
        self.session = session
        # Chaque requête se limite aux lignes de cet utilisateur
        self.user_id = user_id

    def list_queries(self) -> list[SearchQuery]:
        """Renvoie les recherches enregistrées, dans l'ordre de création."""
        statement = select(SearchQuery).where(SearchQuery.user_id == self.user_id).order_by(SearchQuery.id)
        return list(self.session.scalars(statement))

    def add_query(self, contract_type: str, query: str, location: str = "", remote: bool = False) -> SearchQuery | None:
        """Enregistre une recherche et la renvoie, ou None si elle existe déjà."""
        # Utilisateur + query + lieu + télétravail est unique : une recherche déjà enregistrée est ignorée
        statement = (
            insert(SearchQuery)
            .values(user_id=self.user_id, contract_type=contract_type, query=query, location=location, remote=remote)
            .on_conflict_do_nothing()
        )
        if self.session.execute(statement).rowcount == 0:
            return None
        return self.session.scalars(
            select(SearchQuery).where(
                SearchQuery.user_id == self.user_id,
                SearchQuery.query == query,
                SearchQuery.location == location,
                SearchQuery.remote == remote,
            )
        ).one()

    def delete_query(self, query_id: int) -> bool:
        """Supprime une recherche, et renvoie faux si l'identifiant est inconnu ou appartient à un autre utilisateur."""
        statement = delete(SearchQuery).where(SearchQuery.user_id == self.user_id, SearchQuery.id == query_id)
        return self.session.execute(statement).rowcount == 1

    def delete_all(self) -> int:
        """Efface toutes les recherches enregistrées de l'utilisateur, et renvoie leur nombre."""
        return self.session.execute(delete(SearchQuery).where(SearchQuery.user_id == self.user_id)).rowcount
