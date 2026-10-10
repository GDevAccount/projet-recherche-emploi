from datetime import UTC, datetime

import pytest
from conftest import FakeAnswerModel, FakeEmbedder, FakeJudge
from sqlalchemy import func, select

from jobgrep.assistant.evaluation import CaseAccounts, EvalCase, evaluate_case, load_cases, summarize
from jobgrep.assistant.graph import build_graph
from jobgrep.assistant.nodes import AssistantNodes
from jobgrep.assistant.passages import Passage, split_text
from jobgrep.assistant.prompts import JUDGE_PROMPT, prompt_version
from jobgrep.assistant.tools import build_account_tools
from jobgrep.config import MODEL_PRICES_USD, ModelPrice
from jobgrep.data.models import AssistantMessage
from jobgrep.errors import NotFoundError
from jobgrep.site_texts import SITE_TEXTS, fill_fields, read_site_text

NOW = datetime(2026, 10, 10, 10, tzinfo=UTC)
TOOLS = {"etat_du_compte", "mes_offres", "mes_pages_ecartees", "mes_postes_recherches", "mon_cv"}
THEME = Passage("aide", "Guide", "Changer de thème", "Un bouton change de thème.")
ACCOUNT = Passage("aide", "Guide", "Supprimer son compte", "Un bouton supprime le compte.")


def tiny_graph(embedder, answer_model):
    """Graph de l'assistant sur deux passages, le thème toujours en tête."""
    embedder.embed = lambda texts: ([[1.0, 0.0]], 3)
    index = [(ACCOUNT, [0.0, 1.0]), (THEME, [1.0, 0.0])]
    return build_graph(AssistantNodes(embedder, answer_model, lambda: index))


def test_reference_questions_point_to_sections_that_exist():
    cases = load_cases(fill_fields)
    sections = {(name, passage.section) for name in SITE_TEXTS for passage in split_text(name, read_site_text(name))}

    assert len({case.id for case in cases}) == len(cases) >= 40
    for case in cases:
        # Une section renommée dans un texte doit l'être ici : sinon la question échouerait sans raison
        assert set(case.sections) <= sections, case.id
        assert "{" not in case.reference + case.account + "".join(turn.answer for turn in case.history), case.id
        # Seule une réponse se compare à une référence, et il faut savoir d'où elle devait venir : d'une
        # section des textes, ou du compte
        if case.reference:
            assert case.outcome == "answered" and (case.sections or case.account or case.tools), case.id
        # Une question dont la réponse est dans le compte doit le consulter
        if case.account or case.tools:
            assert case.consults is True, case.id
        # Un outil attendu existe, et le compte fictif a de quoi lui répondre
        assert set(case.tools) <= TOOLS, case.id
        assert "mes_offres" not in case.tools or case.offers, case.id
        assert "mes_pages_ecartees" not in case.tools or case.rejections, case.id
        assert "mes_postes_recherches" not in case.tools or case.queries, case.id
        assert "mon_cv" not in case.tools or case.cv, case.id
    assert {case.outcome for case in cases} == {"answered", "unknown", "off_topic"}
    assert any(case.history for case in cases)


def test_judge_prompt_takes_what_it_is_given():
    messages = JUDGE_PROMPT.format_messages(question="q", passages="p", reference="r", answer="a", account="c")

    assert "Réponse de référence : r" in messages[1].content and "Réponse de l'assistant : a" in messages[1].content


def test_a_good_answer_is_found_cited_and_judged(embedder, answer_model, judge):
    sections = (("aide", "Changer de thème"),)
    case = EvalCase("theme", "Comment changer de thème ?", "answered", (), sections, "Un bouton.")

    result = evaluate_case(tiny_graph(embedder, answer_model), judge, case)

    assert (result.outcome, result.rank, result.cited) == ("answered", 1, True)
    assert (result.faithful, result.correct, result.passed) == (True, True, True)
    assert result.retrieved == ["Guide · Changer de thème", "Guide · Supprimer son compte"]
    assert judge.judged == [("Comment changer de thème ?", result.answer, "Un bouton.")]
    assert (result.input_tokens, result.embedding_tokens, result.judge_input_tokens) == (2000, 3, 1500)


def test_what_goes_wrong_is_told_apart(embedder, answer_model, judge):
    graph = tiny_graph(embedder, answer_model)
    second = EvalCase("compte", "Supprimer ?", "answered", (), (("aide", "Supprimer son compte"),), "Un bouton.")
    missing = EvalCase("absent", "Autre ?", "answered", (), (("conditions", "Accès"),), "Une réponse.")

    # La bonne section est retrouvée, mais en second, et la réponse cite l'autre
    late = evaluate_case(graph, judge, second)
    assert (late.rank, late.cited, late.passed) == (2, False, True)
    # La recherche n'a pas ramené la section : la question échoue, quoi qu'en dise le juge
    lost = evaluate_case(graph, judge, missing)
    assert (lost.rank, lost.cited, lost.correct, lost.passed) == (None, False, True, False)
    # Le juge trouve la réponse inventée
    judge.faithful = False
    assert evaluate_case(graph, judge, second).passed is False

    # Un refus là où une réponse était attendue : il n'y a rien à faire noter
    judge.judged.clear()
    answer_model.outcome = "off_topic"
    refused = evaluate_case(graph, judge, second)
    assert (refused.outcome, refused.correct, refused.faithful, refused.passed) == ("off_topic", False, None, False)
    assert judge.judged == []
    # Le même refus est ce qu'on attend d'une question hors sujet, qui ne vise aucune section
    off_topic = evaluate_case(graph, judge, EvalCase("hors-sujet", "La capitale ?", "off_topic"))
    assert (off_topic.rank, off_topic.cited, off_topic.correct, off_topic.passed) == (None, None, None, True)

    counts = summarize([second, missing, EvalCase("hors-sujet", "La capitale ?", "off_topic")], [late, lost, off_topic])
    assert (counts["cases"], counts["passed"], counts["outcome_hits"]) == (3, 2, 3)
    assert (counts["retrieval_cases"], counts["retrieval_hits"], counts["reciprocal_rank_sum"]) == (2, 1, 0.5)
    assert (counts["answer_cases"], counts["correct"], counts["judged"], counts["faithful"]) == (2, 2, 2, 2)
    assert (counts["off_topic_cases"], counts["off_topic_refused"], counts["cited_hits"]) == (1, 1, 0)


def test_evaluation_replays_every_reference_question_and_keeps_the_measures(container, judge, monkeypatch):
    for model, price in (
        (FakeAnswerModel.model_name, ModelPrice(1, 2, 0, 0)),
        (FakeEmbedder.model_name, ModelPrice(1, 0, 0, 0)),
        (FakeJudge.model_name, ModelPrice(1, 2, 0, 0)),
    ):
        monkeypatch.setitem(MODEL_PRICES_USD, model, price)
    cases = load_cases()
    answered = [case for case in cases if case.outcome == "answered"]

    evaluation = container.evaluation.run(NOW)

    assert (evaluation.created_at, evaluation.cases, evaluation.prompt_version) == (NOW, len(cases), prompt_version())
    assert (evaluation.model, evaluation.embedding_model, evaluation.judge_model) == (
        FakeAnswerModel.model_name,
        FakeEmbedder.model_name,
        FakeJudge.model_name,
    )
    # Le faux modèle répond à tout : seules les questions qui attendaient une réponse ont la bonne issue,
    # et aucune question hors sujet n'est refusée
    assert evaluation.outcome_rate == round(len(answered) / len(cases), 4)
    assert (evaluation.refusal_rate, evaluation.correct_rate, evaluation.faithful_rate) == (0, 1, 1)
    assert len(judge.judged) == len([case for case in answered if case.reference])
    assert 0 < evaluation.retrieval_rate <= 1 and 0 < evaluation.mean_reciprocal_rank <= evaluation.retrieval_rate
    assert evaluation.passed == sum(case.passed for case in evaluation.results) < len(cases)
    # Les questions à revoir viennent en premier
    assert [case.passed for case in evaluation.results] == sorted(case.passed for case in evaluation.results)
    assert evaluation.results[0].retrieved and {case.id for case in evaluation.results} == {case.id for case in cases}
    # Chaque question a payé sa réponse ; chaque réponse notée, son juge
    answers = len(cases) * (2000 + 2 * 100) / 1e6
    judging = len(judge.judged) * (1500 + 2 * 40) / 1e6
    assert answers + judging < evaluation.cost_usd < answers + judging + 0.001

    # Aucun compte n'a posé ces questions : ni journal, ni quota
    with container.database.session() as session:
        assert session.scalar(select(func.count()).select_from(AssistantMessage)) == 0
    [listed] = container.evaluation.list_evaluations()
    assert listed.model_dump() == evaluation.model_dump(exclude={"results"})
    assert container.evaluation.get_evaluation(evaluation.id) == evaluation
    with pytest.raises(NotFoundError):
        container.evaluation.get_evaluation(evaluation.id + 1)


def test_evaluation_without_a_price_has_no_cost(container):
    assert container.evaluation.run(NOW).cost_usd is None
    assert container.evaluation.list_evaluations()[0].pass_rate is not None


def test_a_question_about_the_account_must_consult_it(embedder, answer_model, judge):
    status = "CV : aucun CV déposé."
    asks = EvalCase("compte", "Pourquoi ?", "answered", reference="Il manque le CV.", account=status, consults=True)
    sections = (("aide", "Changer de thème"),)
    general = EvalCase("guide", "Comment changer de thème ?", "answered", (), sections, "Un bouton.")
    forbidden = EvalCase("salut", "Bonjour !", "answered", consults=False)
    cases = [asks, general, forbidden]
    embedder.embed = lambda texts: ([[1.0, 0.0]], 3)
    tools = build_account_tools(CaseAccounts(cases))
    graph = build_graph(AssistantNodes(embedder, answer_model, lambda: [(THEME, [1.0, 0.0])], tools=tools))

    # Le modèle consulte : le compte fictif de la question lui est rendu, et le juge lit ce qu'il a lu
    answer_model.consults = True
    consulted = evaluate_case(graph, judge, asks, 0)
    assert (consulted.consulted, consulted.consult_expected, consulted.passed) == (True, True, True)
    assert consulted.answer == status and judge.accounts == ["etat_du_compte :\n" + status]
    assert (consulted.tools, consulted.consulted_well) == (["etat_du_compte"], True)
    # Deux appels au modèle pour cette question
    assert consulted.input_tokens == 4000
    # Consulter le compte pour une salutation est une faute ; pour une question du guide, ce n'est pas jugé
    wasted = evaluate_case(graph, judge, forbidden, 2)
    assert (wasted.consulted, wasted.passed) == (True, False)
    assert evaluate_case(graph, judge, general, 1).passed is True

    # Le modèle ne consulte pas : la question sur le compte échoue, quoi qu'en dise le juge
    answer_model.consults = False
    skipped = evaluate_case(graph, judge, asks, 0)
    assert (skipped.consulted, skipped.correct, skipped.passed) == (False, True, False)
    assert judge.accounts[-1] == ""

    # Le compte est consulté, mais pas par l'outil que la question demandait
    listing = EvalCase(
        "offres", "Lesquelles ?", "answered", offers="Offres retenues : 1.", consults=True, tools=("mes_offres",)
    )
    answer_model.consults = True
    wrong_tool = evaluate_case(
        build_graph(
            AssistantNodes(
                embedder,
                answer_model,
                lambda: [(THEME, [1.0, 0.0])],
                tools=build_account_tools(CaseAccounts([listing])),
            )
        ),
        judge,
        listing,
        0,
    )
    assert (wrong_tool.consulted, wrong_tool.tools, wrong_tool.consulted_well, wrong_tool.passed) == (
        True,
        ["etat_du_compte"],
        False,
        False,
    )
    answer_model.tool = "mes_offres"
    right_tool = evaluate_case(
        build_graph(
            AssistantNodes(
                embedder,
                answer_model,
                lambda: [(THEME, [1.0, 0.0])],
                tools=build_account_tools(CaseAccounts([listing])),
            )
        ),
        judge,
        listing,
        0,
    )
    assert (right_tool.answer, right_tool.consulted_well, right_tool.passed) == ("Offres retenues : 1.", True, True)

    counts = summarize([asks, forbidden, general], [consulted, wasted, evaluate_case(graph, judge, general, 1)])
    assert (counts["consult_cases"], counts["consult_hits"], counts["passed"]) == (2, 1, 2)
