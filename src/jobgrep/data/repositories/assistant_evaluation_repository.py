from collections.abc import Mapping

from sqlalchemy import insert, select
from sqlalchemy.orm import Session, defer

from jobgrep.data.models import AssistantEvaluation


class AssistantEvaluationRepository:
    """Évaluations de l'assistant : sans utilisateur, puisqu'elles ne rejouent que des questions de référence."""

    def __init__(self, session: Session):
        self.session = session

    def insert_evaluation(self, evaluation: Mapping) -> int:
        """Enregistre une évaluation avec le détail de ses questions, et renvoie son identifiant."""
        result = self.session.execute(insert(AssistantEvaluation).values(**evaluation))
        return result.inserted_primary_key[0]

    def list_evaluations(self, limit: int) -> list[AssistantEvaluation]:
        """Renvoie les dernières évaluations, la plus récente en premier, sans le détail de leurs questions."""
        statement = (
            select(AssistantEvaluation)
            .options(defer(AssistantEvaluation.details))
            .order_by(AssistantEvaluation.id.desc())
            .limit(limit)
        )
        return list(self.session.scalars(statement))

    def get_evaluation(self, evaluation_id: int) -> AssistantEvaluation | None:
        """Renvoie une évaluation avec le détail de ses questions, ou None si elle n'existe pas."""
        return self.session.get(AssistantEvaluation, evaluation_id)
