from collections.abc import Iterable, Mapping

from sqlalchemy import delete, insert, select
from sqlalchemy.orm import Session

from projet_recherche_emploi.data.models import PageEvaluation

INSERTED_FIELDS = (
    "url",
    "title",
    "query",
    "score",
    "kept",
    "page_kind",
    "contract_type",
    "work_city",
    "work_country",
    "work_mode",
    "in_accepted_area",
    "open_to_candidates_in_france",
    "matches_search",
    "matches_skills",
    "matches_level",
    "matches_contract",
    "matches_location",
    "reason",
    "page_chars",
    "truncated",
    "full_page",
    "input_tokens",
    "output_tokens",
    "duration_ms",
)


class PageEvaluationRepository:
    def __init__(self, session: Session, user_id: int):
        self.session = session
        # Chaque requête se limite aux lignes de cet utilisateur
        self.user_id = user_id

    def insert_evaluations(self, search_run_id: int | None, evaluations: Iterable[Mapping]) -> int:
        """Ajoute au journal les pages évaluées pendant ce lancement, et renvoie leur nombre."""
        rows = [
            {
                "user_id": self.user_id,
                "search_run_id": search_run_id,
                **{field: evaluation.get(field) for field in INSERTED_FIELDS},
            }
            for evaluation in evaluations
        ]
        if rows:
            self.session.execute(insert(PageEvaluation), rows)
        return len(rows)

    def list_for_run(self, search_run_id: int) -> list[PageEvaluation]:
        """Renvoie les pages évaluées pendant ce lancement, dans l'ordre de leur enregistrement."""
        statement = (
            select(PageEvaluation)
            .where(PageEvaluation.user_id == self.user_id, PageEvaluation.search_run_id == search_run_id)
            .order_by(PageEvaluation.id)
        )
        return list(self.session.scalars(statement))

    def delete_all(self) -> int:
        """Efface tout le journal de l'utilisateur, et renvoie le nombre de lignes."""
        return self.session.execute(delete(PageEvaluation).where(PageEvaluation.user_id == self.user_id)).rowcount
