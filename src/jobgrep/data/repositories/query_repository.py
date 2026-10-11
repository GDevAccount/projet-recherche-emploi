from collections.abc import Sequence

from sqlalchemy import delete, exists, select, update
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session, aliased

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

    def add_query(
        self,
        contract_type: str,
        query: str,
        location: str = "",
        remote: bool = False,
        skills: Sequence[str] = (),
    ) -> SearchQuery | None:
        """Enregistre une recherche et la renvoie, ou None si elle existe déjà."""
        # Utilisateur + query + lieu + télétravail est unique : une recherche déjà enregistrée est ignorée
        statement = (
            insert(SearchQuery)
            .values(
                user_id=self.user_id,
                contract_type=contract_type,
                query=query,
                skills=list(skills),
                location=location,
                remote=remote,
            )
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

    def get_query(self, query_id: int) -> SearchQuery | None:
        """Renvoie une recherche, ou None si l'identifiant est inconnu ou appartient à un autre utilisateur."""
        statement = select(SearchQuery).where(SearchQuery.user_id == self.user_id, SearchQuery.id == query_id)
        return self.session.scalars(statement).one_or_none()

    def update_query(
        self,
        query_id: int,
        contract_type: str,
        query: str,
        location: str = "",
        remote: bool = False,
        skills: Sequence[str] = (),
    ) -> bool:
        """Modifie une recherche, et renvoie faux si elle est inconnue, ou si une autre est déjà celle-là."""
        twin = aliased(SearchQuery)
        # La même contrainte d'unicité qu'à l'ajout, vérifiée ici pour ne pas en faire une erreur de la base
        taken = exists().where(
            twin.user_id == self.user_id,
            twin.id != query_id,
            twin.query == query,
            twin.location == location,
            twin.remote == remote,
        )
        statement = (
            update(SearchQuery)
            .where(SearchQuery.user_id == self.user_id, SearchQuery.id == query_id, ~taken)
            .values(contract_type=contract_type, query=query, skills=list(skills), location=location, remote=remote)
            .execution_options(synchronize_session="fetch")
        )
        return self.session.execute(statement).rowcount == 1

    def delete_query(self, query_id: int) -> bool:
        """Supprime une recherche, et renvoie faux si l'identifiant est inconnu ou appartient à un autre utilisateur."""
        statement = delete(SearchQuery).where(SearchQuery.user_id == self.user_id, SearchQuery.id == query_id)
        return self.session.execute(statement).rowcount == 1

    def delete_all(self) -> int:
        """Efface toutes les recherches enregistrées de l'utilisateur, et renvoie leur nombre."""
        return self.session.execute(delete(SearchQuery).where(SearchQuery.user_id == self.user_id)).rowcount
