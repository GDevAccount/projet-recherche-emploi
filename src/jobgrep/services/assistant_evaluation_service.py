"""Évaluation de l'assistant : rejoue les questions de référence sur le vrai graph, et garde ce qu'elles mesurent.

Une évaluation appelle les modèles pour chaque question : elle coûte, et ne se lance qu'à la demande, par la
commande « jobgrep evaluate ». Ses résultats se lisent dans la rubrique Suivi, par version des consignes.
"""

import json
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

from langgraph.graph.state import CompiledStateGraph

from jobgrep.assistant.evaluation import describe_results, evaluate_case, load_cases, summarize
from jobgrep.assistant.ports import AnswerJudge
from jobgrep.assistant.prompts import prompt_version
from jobgrep.config import EVALUATION_CONCURRENCY
from jobgrep.data.database import Database
from jobgrep.data.models import AssistantEvaluation
from jobgrep.data.repositories.assistant_evaluation_repository import AssistantEvaluationRepository
from jobgrep.errors import NotFoundError
from jobgrep.schemas import AssistantEvaluationCase, AssistantEvaluationDetail, AssistantEvaluationRead
from jobgrep.services.search_costs import model_cost_usd, sum_costs
from jobgrep.site_texts import fill_fields

# Dernières évaluations montrées dans la rubrique Suivi
MAX_EVALUATIONS_SHOWN = 30


def _rate(hits: int, total: int) -> float | None:
    """Renvoie une part entre 0 et 1, ou None quand il n'y a rien à mesurer."""
    return round(hits / total, 4) if total else None


def _read(row: AssistantEvaluation) -> dict:
    costs = [
        model_cost_usd(row.model, row.input_tokens, row.output_tokens),
        model_cost_usd(row.embedding_model, row.embedding_tokens, 0),
        model_cost_usd(row.judge_model, row.judge_input_tokens, row.judge_output_tokens),
    ]
    return {
        "id": row.id,
        "created_at": row.created_at,
        "model": row.model,
        "embedding_model": row.embedding_model,
        "judge_model": row.judge_model,
        "prompt_version": row.prompt_version,
        "cases": row.cases,
        "passed": row.passed,
        "pass_rate": _rate(row.passed, row.cases),
        "outcome_rate": _rate(row.outcome_hits, row.cases),
        "retrieval_rate": _rate(row.retrieval_hits, row.retrieval_cases),
        "mean_reciprocal_rank": _rate(row.reciprocal_rank_sum, row.retrieval_cases),
        "citation_rate": _rate(row.cited_hits, row.retrieval_cases),
        "correct_rate": _rate(row.correct, row.answer_cases),
        "faithful_rate": _rate(row.faithful, row.judged),
        "refusal_rate": _rate(row.off_topic_refused, row.off_topic_cases),
        "duration_ms": row.duration_ms,
        "cost_usd": sum_costs(costs),
    }


class AssistantEvaluationService:
    """Sans utilisateur : une évaluation ne touche à aucun compte. Ses routes sont réservées aux administrateurs."""

    def __init__(
        self,
        database: Database,
        get_graph: Callable[[], CompiledStateGraph],
        judge: AnswerJudge,
        answer_model_name: str,
        embedding_model_name: str,
        contact_email: str = "",
    ):
        self.database = database
        # Le graph de l'assistant lui-même : c'est lui qui est mesuré, pas une copie
        self._get_graph = get_graph
        self.judge = judge
        self.answer_model_name = answer_model_name
        self.embedding_model_name = embedding_model_name
        self.contact_email = contact_email

    def run(self, now: datetime | None = None) -> AssistantEvaluationDetail:
        """Pose chaque question de référence à l'assistant, note ses réponses, et enregistre le tout.

        Rien n'est écrit dans le journal des questions ni compté dans un quota : aucun compte ne les pose.
        Ce que l'évaluation coûte n'entre pas dans le budget de l'instance ; il se lit avec ses résultats.
        """
        now = (now or datetime.now(UTC)).replace(microsecond=0)
        cases = load_cases(lambda text: fill_fields(text, self.contact_email))
        graph = self._get_graph()

        started = time.perf_counter()
        # Les passages sont situés par la première question : les autres attendent qu'elle ait fini
        first = evaluate_case(graph, self.judge, cases[0])
        with ThreadPoolExecutor(max_workers=EVALUATION_CONCURRENCY) as pool:
            others = list(pool.map(lambda case: evaluate_case(graph, self.judge, case), cases[1:]))
        results = [first, *others]
        duration_ms = round((time.perf_counter() - started) * 1000)

        with self.database.session() as session:
            evaluation_id = AssistantEvaluationRepository(session).insert_evaluation(
                summarize(cases, results)
                | {
                    "created_at": now,
                    "model": self.answer_model_name,
                    "embedding_model": self.embedding_model_name,
                    "judge_model": self.judge.model_name,
                    "prompt_version": prompt_version(),
                    "duration_ms": duration_ms,
                    "details": json.dumps(describe_results(results), ensure_ascii=False),
                }
            )
        return self.get_evaluation(evaluation_id)

    def list_evaluations(self) -> list[AssistantEvaluationRead]:
        """Renvoie les dernières évaluations, la plus récente en premier, avec leurs mesures."""
        with self.database.session() as session:
            rows = AssistantEvaluationRepository(session).list_evaluations(MAX_EVALUATIONS_SHOWN)
            return [AssistantEvaluationRead(**_read(row)) for row in rows]

    def get_evaluation(self, evaluation_id: int) -> AssistantEvaluationDetail:
        """Renvoie une évaluation avec le détail de chaque question, celles qui échouent en premier."""
        with self.database.session() as session:
            row = AssistantEvaluationRepository(session).get_evaluation(evaluation_id)
            if row is None:
                raise NotFoundError("Cette évaluation n'existe pas.")
            results = [AssistantEvaluationCase(**case) for case in json.loads(row.details)]
            # Le tri est stable : dans chaque groupe, les questions gardent l'ordre du fichier
            results.sort(key=lambda case: case.passed)
            return AssistantEvaluationDetail(**_read(row), results=results)
