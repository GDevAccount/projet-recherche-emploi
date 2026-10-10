"""Banc d'évaluation de l'assistant : rejoue des questions de référence sur le graph, et note ce qu'il rend.

Chaque question de evaluation_cases.json dit l'issue attendue, les sections des textes du site qui portent
la réponse, et une réponse de référence. On en tire trois mesures : la recherche a-t-elle ramené la bonne
section, le graph a-t-il pris la bonne issue, et la réponse est-elle juste et fidèle aux passages reçus.
"""

import json
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

from langgraph.graph.state import CompiledStateGraph

from jobgrep.assistant.ports import AnswerJudge, Exchange, ModelUsage, Outcome

CASES_FILE = Path(__file__).parent / "evaluation_cases.json"


@dataclass(frozen=True)
class EvalCase:
    id: str
    question: str
    # Issue attendue du graph
    outcome: Outcome
    # Échanges qui précèdent la question, pour un rebond
    history: tuple[Exchange, ...] = ()
    # Sections des textes du site qui portent la réponse (nom du texte, titre de la section) : l'une d'elles
    # suffit. Vide quand aucune n'est attendue
    sections: tuple[tuple[str, str], ...] = ()
    # Réponse attendue, à laquelle le juge compare celle de l'assistant ; vide s'il n'y a rien à comparer
    reference: str = ""


@dataclass(frozen=True)
class CaseResult:
    id: str
    question: str
    expected_outcome: Outcome
    outcome: Outcome
    answer: str
    # Titres des passages donnés au modèle, le plus proche en premier
    retrieved: list[str]
    # Rang, à partir de 1, de la première section attendue parmi ces passages ; None si aucune n'y est,
    # ou si la question n'en attend pas
    rank: int | None
    # La réponse cite-t-elle une section attendue ; None si la question n'en attend pas
    cited: bool | None
    # Avis du juge ; None quand il n'a pas été consulté
    faithful: bool | None
    correct: bool | None
    judge_reason: str
    input_tokens: int
    output_tokens: int
    embedding_tokens: int
    judge_input_tokens: int
    judge_output_tokens: int

    @property
    def passed(self) -> bool:
        """Vrai si rien n'est à reprocher : la bonne issue, la bonne section retrouvée, une réponse juste et fidèle."""
        found = self.rank is not None or self.cited is None
        judged_well = self.correct is not False and self.faithful is not False
        return self.outcome == self.expected_outcome and found and judged_well


def load_cases(fill: Callable[[str], str] = lambda text: text) -> list[EvalCase]:
    """Renvoie les questions de référence. « fill » remplace leurs champs entre accolades par les valeurs en vigueur."""
    cases = []
    for row in json.loads(CASES_FILE.read_text(encoding="utf-8")):
        history = tuple(Exchange(turn["question"], fill(turn["answer"])) for turn in row.get("history", []))
        sections = tuple((source, section) for source, section in row.get("sections", []))
        cases.append(
            EvalCase(row["id"], row["question"], row["outcome"], history, sections, fill(row.get("reference", "")))
        )
    return cases


def evaluate_case(graph: CompiledStateGraph, judge: AnswerJudge, case: EvalCase) -> CaseResult:
    """Pose une question de référence au graph de l'assistant, et note ce qu'il rend."""
    state = graph.invoke({"question": case.question, "history": list(case.history)})
    passages, usage = state["passages"], state["usage"]

    def expected_among(candidates: Sequence) -> list[int]:
        return [
            position
            for position, passage in enumerate(candidates, start=1)
            if (passage.source, passage.section) in case.sections
        ]

    ranks = expected_among(passages)
    faithful, correct, reason, judge_usage = None, None, "", ModelUsage()
    if case.outcome == "answered" and case.reference:
        if state["outcome"] == "answered":
            verdict, judge_usage = judge.judge(case.question, passages, state["answer"], case.reference)
            faithful, correct, reason = verdict.faithful, verdict.correct, verdict.reason
        else:
            # Un refus ou un renvoi vers l'exploitant ne dit pas ce que la référence attendait
            correct = False

    return CaseResult(
        id=case.id,
        question=case.question,
        expected_outcome=case.outcome,
        outcome=state["outcome"],
        answer=state["answer"],
        retrieved=[passage.heading for passage in passages],
        rank=(ranks[0] if ranks else None) if case.sections else None,
        cited=bool(expected_among(state["cited"])) if case.sections else None,
        faithful=faithful,
        correct=correct,
        judge_reason=reason,
        input_tokens=usage.input_tokens or 0,
        output_tokens=usage.output_tokens or 0,
        embedding_tokens=state.get("embedding_tokens") or 0,
        judge_input_tokens=judge_usage.input_tokens or 0,
        judge_output_tokens=judge_usage.output_tokens or 0,
    )


def summarize(cases: Sequence[EvalCase], results: Sequence[CaseResult]) -> dict[str, float]:
    """Renvoie les compteurs d'une évaluation : pour chaque mesure, les questions concernées et celles qui passent."""
    with_sections = [result for case, result in zip(cases, results, strict=True) if case.sections]
    off_topic = [result for result in results if result.expected_outcome == "off_topic"]
    compared = [result for result in results if result.correct is not None]
    judged = [result for result in results if result.faithful is not None]
    return {
        "cases": len(results),
        "passed": sum(result.passed for result in results),
        "outcome_hits": sum(result.outcome == result.expected_outcome for result in results),
        "retrieval_cases": len(with_sections),
        "retrieval_hits": sum(result.rank is not None for result in with_sections),
        # Somme des inverses des rangs : divisée par le nombre de questions, elle dit si la bonne section
        # arrive en tête (1) ou en fin de liste
        "reciprocal_rank_sum": round(sum(1 / result.rank for result in with_sections if result.rank), 4),
        "cited_hits": sum(bool(result.cited) for result in with_sections),
        "answer_cases": len(compared),
        "correct": sum(bool(result.correct) for result in compared),
        "judged": len(judged),
        "faithful": sum(bool(result.faithful) for result in judged),
        "off_topic_cases": len(off_topic),
        "off_topic_refused": sum(result.outcome == "off_topic" for result in off_topic),
        "input_tokens": sum(result.input_tokens for result in results),
        "output_tokens": sum(result.output_tokens for result in results),
        "embedding_tokens": sum(result.embedding_tokens for result in results),
        "judge_input_tokens": sum(result.judge_input_tokens for result in results),
        "judge_output_tokens": sum(result.judge_output_tokens for result in results),
    }


def describe_results(results: Sequence[CaseResult]) -> list[dict]:
    """Renvoie le détail de chaque question, tel qu'il est enregistré avec l'évaluation."""
    kept = ("id", "question", "expected_outcome", "outcome", "answer", "retrieved", "rank", "cited")
    return [
        {field: asdict(result)[field] for field in (*kept, "faithful", "correct", "judge_reason")}
        | {"passed": result.passed}
        for result in results
    ]
