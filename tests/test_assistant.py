from datetime import UTC, datetime, timedelta

import pytest
from conftest import FakeAnswerModel, FakeEmbedder, FakeEvaluator, FakeSearchEngine
from sqlalchemy import func, select

from jobgrep.assistant.graph import build_graph
from jobgrep.assistant.nodes import OFF_TOPIC_ANSWER, AssistantNodes
from jobgrep.assistant.passages import Passage, rank_passages, similarity, split_text
from jobgrep.assistant.prompts import ANSWER_PROMPT, describe_passages, prompt_version
from jobgrep.config import (
    ASSISTANT_HISTORY_MINUTES,
    ASSISTANT_MESSAGE_DAYS,
    ASSISTANT_PASSAGES,
    DEFAULT_USER_ID,
    MAX_ASSISTANT_QUESTIONS_PER_DAY,
    MODEL_PRICES_USD,
    ModelPrice,
    Settings,
)
from jobgrep.container import build_container
from jobgrep.data.models import AssistantMessage, AssistantPassage
from jobgrep.data.repositories.assistant_message_repository import AssistantMessageRepository
from jobgrep.data.repositories.user_repository import UserRepository
from jobgrep.errors import BudgetReachedError, InvalidInputError, QuotaExceededError
from jobgrep.schemas import MAX_QUESTION_CHARS
from jobgrep.site_texts import SITE_TEXTS, read_site_text

BOB = 2
CAROL = 3
NOON = datetime(2026, 10, 10, 10, tzinfo=UTC)
# Ses mots sont ceux d'une seule section du guide : le faux embedding des tests ne compare que des mots
QUESTION = "Puis-je remplacer mon fichier par un autre PDF scanné ?"


@pytest.fixture
def priced(monkeypatch):
    """Donne un tarif aux faux modèles : un dollar le million de jetons lus, deux le million écrits."""
    monkeypatch.setitem(MODEL_PRICES_USD, FakeAnswerModel.model_name, ModelPrice(1, 2, 0, 0))
    monkeypatch.setitem(MODEL_PRICES_USD, FakeEmbedder.model_name, ModelPrice(1, 0, 0, 0))


def count_rows(container, table) -> int:
    with container.database.session() as session:
        return session.scalar(select(func.count()).select_from(table))


def test_text_is_split_by_section_and_long_sections_by_paragraph():
    text = (
        "# Titre\n\nIntroduction avec un [lien](/ailleurs).\n\n"
        "## Première\n\nUn.\n\n- **Deux**\n- Trois\n\n## Seconde\n\nFin."
    )

    passages = split_text("page", text)

    assert [(passage.section, passage.content) for passage in passages] == [
        ("", "Introduction avec un lien."),
        ("Première", "Un.\n- Deux\n- Trois"),
        ("Seconde", "Fin."),
    ]
    assert {passage.page_title for passage in passages} == {"Titre"}
    assert passages[1].heading == "Titre · Première" and passages[0].heading == "Titre"
    # Une section trop longue est coupée entre deux paragraphes, jamais au milieu de l'un
    assert [passage.content for passage in split_text("page", text, max_chars=8)][1:4] == ["Un.", "- Deux", "- Trois"]
    # L'empreinte suit le texte : un mot changé, et le passage est à situer de nouveau
    assert passages[2].content_hash != split_text("page", text.replace("Fin.", "Fin !"))[2].content_hash


def test_closest_passages_come_first():
    near, far = Passage("a", "A", "", "proche"), Passage("b", "B", "", "loin")

    assert rank_passages([1.0, 0.0], [(far, [0.0, 1.0]), (near, [0.9, 0.1])], 1) == [near]
    assert similarity([1.0, 0.0], [2.0, 0.0]) == 1.0
    # Un vecteur nul ne ressemble à rien, sans diviser par zéro
    assert similarity([0.0, 0.0], [1.0, 0.0]) == 0.0


@pytest.mark.parametrize("name", SITE_TEXTS)
def test_site_texts_leave_no_field_unfilled(name):
    text = read_site_text(name, "contact@exemple.fr")

    assert "{" not in text and "}" not in text
    assert all(passage.content for passage in split_text(name, text))


def test_guide_states_the_real_limits_of_the_assistant():
    guide = read_site_text("aide", "contact@exemple.fr")

    assert f"{MAX_ASSISTANT_QUESTIONS_PER_DAY} questions par jour" in guide
    assert f"pendant {ASSISTANT_MESSAGE_DAYS} jours" in guide
    assert "contact@exemple.fr" in guide
    assert f"effacé au bout de {ASSISTANT_MESSAGE_DAYS} jours" in read_site_text("confidentialite")
    assert f"limitées à {MAX_ASSISTANT_QUESTIONS_PER_DAY} par jour" in read_site_text("conditions")


def test_prompt_numbers_the_passages_and_has_a_version():
    passages = [Passage("aide", "Guide", "Thème", "Un bouton."), Passage("aide", "Guide", "", "Intro.")]

    assert describe_passages(passages) == "[1] Guide · Thème\nUn bouton.\n\n[2] Guide\nIntro."
    assert len(prompt_version()) == 12
    # Le prompt se remplit sans champ oublié, avec ou sans échange précédent
    messages = ANSWER_PROMPT.format_messages(passages="p", history=[], question="q")
    assert [message.type for message in messages] == ["system", "human"]


def test_graph_follows_what_the_model_returned(embedder, answer_model):
    passage = Passage("aide", "Guide", "Thème", "Un bouton change de thème.")
    nodes = AssistantNodes(embedder, answer_model, lambda: [(passage, [1.0])], "contact@exemple.fr")
    graph = build_graph(nodes)
    # Le faux embedding rend 256 nombres : ici seul compte le chemin suivi, pas la proximité
    embedder.embed = lambda texts: ([[1.0]], 3)

    answered = graph.invoke({"question": "Comment changer de thème ?", "history": []})
    assert (answered["outcome"], answered["cited"], answered["embedding_tokens"]) == ("answered", [passage], 3)

    answer_model.outcome = "off_topic"
    declined = graph.invoke({"question": "Quelle heure est-il ?"})
    assert (declined["outcome"], declined["answer"], declined["cited"]) == ("off_topic", OFF_TOPIC_ANSWER, [])

    answer_model.outcome = "unknown"
    referred = graph.invoke({"question": "Une application mobile ?"})
    assert referred["outcome"] == "unknown" and referred["answer"].endswith("écrivez à contact@exemple.fr.")
    assert set(graph.get_graph().nodes) >= {"RetrievePassages", "GenerateAnswer", "CiteSources"}


def test_answer_comes_from_the_site_texts_and_names_them(container, embedder, answer_model):
    reply = container.assistant.ask(BOB, "  Puis-je remplacer mon fichier par un autre PDF scanné ?  ", NOON)

    question, passages, history = answer_model.asked[0]
    assert (question, history, len(passages)) == (QUESTION, [], ASSISTANT_PASSAGES)
    # Le passage le plus proche de la question est celui qui en parle
    assert passages[0].section == "Déposer ou remplacer son CV"
    assert reply.message.answer == "Voir « Guide d'utilisation · Déposer ou remplacer son CV »."
    assert reply.message.outcome == "answered"
    [source] = reply.message.sources
    # Le guide n'est pas une page du site : il est cité sans adresse
    assert (source.title, source.section, source.url) == ("Guide d'utilisation", "Déposer ou remplacer son CV", None)
    assert reply.remaining_questions == MAX_ASSISTANT_QUESTIONS_PER_DAY - 1
    # Rien d'un compte n'est envoyé : ni au modèle qui situe, ni à celui qui répond
    assert embedder.embedded[-1] == [QUESTION]

    conversation = container.assistant.get_conversation(BOB, NOON)
    assert conversation.messages == [reply.message]
    assert (conversation.remaining_questions, conversation.max_questions_per_day, conversation.retention_days) == (
        MAX_ASSISTANT_QUESTIONS_PER_DAY - 1,
        MAX_ASSISTANT_QUESTIONS_PER_DAY,
        ASSISTANT_MESSAGE_DAYS,
    )
    # La conversation d'un autre compte reste vide
    assert container.assistant.get_conversation(CAROL, NOON).messages == []


def test_a_public_page_is_cited_with_its_address(container, answer_model):
    reply = container.assistant.ask(BOB, "À qui mes données sont-elles transmises ?", NOON)

    _, passages, _ = answer_model.asked[0]
    assert passages[0].source == "confidentialite"
    assert reply.message.sources[0].url == "/confidentialite"
    assert reply.message.sources[0].title == "Règles de confidentialité"


def test_sources_are_only_the_passages_the_model_really_had(container, answer_model):
    # Deux fois le même passage, et deux numéros qui n'en désignent aucun
    answer_model.cited = [1, 1, 0, 99]

    reply = container.assistant.ask(BOB, QUESTION, NOON)

    assert [source.section for source in reply.message.sources] == ["Déposer ou remplacer son CV"]


def test_passages_are_located_once_and_only_changed_ones_again(tmp_path):
    settings = Settings(data_dir=tmp_path, contact_email="contact@exemple.fr")
    embedders = [FakeEmbedder() for _ in range(3)]

    def start(embedder, settings=settings):
        return build_container(
            settings, FakeSearchEngine(), FakeEvaluator(), embedder=embedder, answer_model=FakeAnswerModel()
        )

    first = start(embedders[0])
    # Construire l'application ne situe rien : cela attend la première question
    assert embedders[0].embedded == [] and count_rows(first, AssistantPassage) == 0
    first.assistant.ask(BOB, "Comment déposer mon CV ?", NOON)
    first.assistant.ask(BOB, "Et le remplacer ?", NOON)
    total = count_rows(first, AssistantPassage)
    # Tous les passages en un appel, puis un appel par question
    assert [len(texts) for texts in embedders[0].embedded] == [total, 1, 1]

    # Après un redémarrage, les vecteurs sont relus de la base
    start(embedders[1]).assistant.ask(BOB, "Comment déposer mon CV ?", NOON)
    assert [len(texts) for texts in embedders[1].embedded] == [1]

    # Un texte qui change ne fait situer que ses passages, et les anciens sont effacés
    changed = start(embedders[2], Settings(data_dir=tmp_path, contact_email="autre@exemple.fr"))
    changed.assistant.ask(BOB, "Comment déposer mon CV ?", NOON)
    located_again = embedders[2].embedded[0]
    assert 0 < len(located_again) < total and all("autre@exemple.fr" in text for text in located_again)
    assert count_rows(changed, AssistantPassage) == total

    # Un autre modèle d'embedding ne place pas les textes au même endroit : tout est à refaire
    other = FakeEmbedder()
    other.model_name = "autre-embedding"
    start(other, Settings(data_dir=tmp_path, contact_email="autre@exemple.fr")).assistant.ask(BOB, "CV ?", NOON)
    assert len(other.embedded[0]) == total and count_rows(changed, AssistantPassage) == total


def test_question_outside_the_application_is_refused_and_still_counted(container, answer_model):
    answer_model.outcome = "off_topic"

    reply = container.assistant.ask(BOB, "Quelle est la capitale de l'Australie ?", NOON)

    assert (reply.message.outcome, reply.message.answer, reply.message.sources) == ("off_topic", OFF_TOPIC_ANSWER, [])
    # Elle a coûté autant qu'une autre
    assert reply.remaining_questions == MAX_ASSISTANT_QUESTIONS_PER_DAY - 1


def test_question_the_texts_do_not_answer_sends_to_the_operator(tmp_path, container, answer_model):
    answer_model.outcome = "unknown"

    reply = container.assistant.ask(BOB, "JobGrep aura-t-il une application mobile ?", NOON)

    assert (reply.message.outcome, reply.message.sources) == ("unknown", [])
    assert reply.message.answer.endswith("adressez-vous à l'exploitant de l'application.")

    with_contact = build_container(
        Settings(data_dir=tmp_path / "contact", contact_email="contact@exemple.fr"),
        FakeSearchEngine(),
        FakeEvaluator(),
        embedder=FakeEmbedder(),
        answer_model=answer_model,
    )
    assert with_contact.assistant.ask(BOB, "Une application mobile ?", NOON).message.answer.endswith(
        "écrivez à contact@exemple.fr."
    )
    # Une réponse vide n'en est pas une
    answer_model.outcome, answer_model.text = "answered", "  "
    assert container.assistant.ask(BOB, "Une application mobile ?", NOON).message.outcome == "unknown"


def test_empty_or_endless_question_is_refused_before_any_call(container, embedder, answer_model):
    for question in ("   ", "x" * (MAX_QUESTION_CHARS + 1)):
        with pytest.raises(InvalidInputError):
            container.assistant.ask(BOB, question, NOON)

    assert embedder.embedded == [] and answer_model.asked == []


def test_questions_are_limited_per_day_except_for_the_owner(container, answer_model):
    for _ in range(MAX_ASSISTANT_QUESTIONS_PER_DAY):
        last = container.assistant.ask(BOB, "Comment déposer mon CV ?", NOON)
    assert last.remaining_questions == 0

    with pytest.raises(QuotaExceededError):
        container.assistant.ask(BOB, "Comment déposer mon CV ?", NOON)
    # La question refusée n'est pas partie
    assert len(answer_model.asked) == MAX_ASSISTANT_QUESTIONS_PER_DAY
    # Le quota est par compte, et repart à minuit, heure de Paris
    assert container.assistant.ask(CAROL, "Comment déposer mon CV ?", NOON).remaining_questions is not None
    midnight_in_paris = datetime(2026, 10, 10, 22, 1, tzinfo=UTC)
    assert container.assistant.ask(BOB, "Comment déposer mon CV ?", midnight_in_paris).remaining_questions == (
        MAX_ASSISTANT_QUESTIONS_PER_DAY - 1
    )

    for _ in range(MAX_ASSISTANT_QUESTIONS_PER_DAY + 1):
        owner = container.assistant.ask(DEFAULT_USER_ID, "Comment déposer mon CV ?", NOON)
    assert owner.remaining_questions is None
    assert container.assistant.get_conversation(DEFAULT_USER_ID, NOON).remaining_questions is None


def test_daily_budget_stops_the_questions_except_the_owner_s(container, answer_model):
    container.assistant.budget_reached = lambda: True

    with pytest.raises(BudgetReachedError):
        container.assistant.ask(BOB, "Comment déposer mon CV ?", NOON)

    assert answer_model.asked == []
    assert container.assistant.ask(DEFAULT_USER_ID, "Comment déposer mon CV ?", NOON).message.outcome == "answered"


def test_a_follow_up_question_is_read_with_the_previous_one(container, embedder, answer_model):
    first = container.assistant.ask(BOB, "Combien de recherches par jour ?", NOON)
    container.assistant.ask(BOB, "Et pour un essai ?", NOON + timedelta(minutes=1))

    _, _, history = answer_model.asked[1]
    assert [(exchange.question, exchange.answer) for exchange in history] == [
        ("Combien de recherches par jour ?", first.message.answer)
    ]
    # Seule, la seconde question ne dit pas de quoi elle parle : elle est située avec la précédente
    assert embedder.embedded[-1] == ["Combien de recherches par jour ?\nEt pour un essai ?"]

    # Passé un moment, c'est une autre conversation ; et celle d'un autre compte n'y entre jamais
    later = NOON + timedelta(minutes=ASSISTANT_HISTORY_MINUTES + 2)
    container.assistant.ask(BOB, "Comment supprimer mon compte ?", later)
    container.assistant.ask(CAROL, "Et pour un essai ?", NOON + timedelta(minutes=1))
    assert answer_model.asked[2][2] == [] and answer_model.asked[3][2] == []


def test_question_texts_are_forgotten_after_a_while_but_not_their_cost(container, priced):
    container.assistant.ask(BOB, "Comment déposer mon CV ?", NOON)
    later = NOON + timedelta(days=ASSISTANT_MESSAGE_DAYS, minutes=1)

    # Le délai passé, le texte n'est plus montré, même si aucune question ne l'a encore effacé
    assert container.assistant.get_conversation(BOB, later).messages == []
    assert container.assistant.get_overview(now=later).entries == []

    container.assistant.ask(CAROL, "Comment supprimer mon compte ?", later)

    with container.database.session() as session:
        [old, recent] = session.scalars(select(AssistantMessage).order_by(AssistantMessage.id))
        assert (old.question, old.answer, old.sources, old.retrieved) == (None, None, None, None)
        assert old.input_tokens == 2000
        assert recent.question == "Comment supprimer mon compte ?"
    overview = container.assistant.get_overview(now=later)
    assert (overview.questions, overview.accounts, len(overview.entries)) == (2, 2, 1)


def test_administrator_reads_the_questions_without_the_accounts(container, answer_model, priced):
    container.assistant.ask(BOB, "Comment déposer mon CV ?", NOON)
    answer_model.outcome = "unknown"
    container.assistant.ask(CAROL, "Une application mobile ?", NOON + timedelta(minutes=1))
    answer_model.outcome = "off_topic"
    container.assistant.ask(CAROL, "Écris-moi une lettre de motivation", NOON + timedelta(minutes=2))

    overview = container.assistant.get_overview(now=NOON + timedelta(hours=1))

    assert (overview.questions, overview.answered, overview.unknown, overview.off_topic) == (3, 1, 1, 1)
    assert overview.accounts == 2
    # La plus récente en premier
    assert [entry.question for entry in overview.entries] == [
        "Écris-moi une lettre de motivation",
        "Une application mobile ?",
        "Comment déposer mon CV ?",
    ]
    assert "user_id" not in overview.model_dump_json() and "email" not in overview.model_dump_json()
    # Chaque question garde les textes où la recherche est allée, le plus proche en premier, même sans réponse :
    # c'est ce qui dit si la recherche ou le modèle s'est trompé
    answered = overview.entries[-1]
    assert answered.sources == answered.retrieved[:1] and 1 < len(answered.retrieved) <= ASSISTANT_PASSAGES
    assert overview.entries[0].sources == [] and overview.entries[0].retrieved
    # Trois réponses à 2 000 jetons lus et 100 écrits, et trois questions situées : 5 mots, 4, puis 9 pour
    # la dernière, située avec la précédente du même compte
    assert overview.cost_usd == pytest.approx(3 * (2000 + 2 * 100) / 1e6 + (5 + 4 + 9) / 1e6)
    # Une période qui ne contient aucune question
    assert container.assistant.get_overview(days=1, now=NOON + timedelta(days=3)).questions == 0


def test_assistant_spending_counts_in_the_budget_and_outlives_the_account(container, priced):
    with container.database.session() as session:
        alice = UserRepository(session).get_or_create_user_id("alice@exemple.fr")
    now = datetime.now(UTC)
    container.assistant.ask(alice, "Comment déposer mon CV ?", now)
    cost = round((2000 + 2 * 100 + 5) / 1e6, 6)

    assert container.usage.get_daily_spend(now) == cost
    [account] = container.usage.get_overview(now=now).accounts
    assert (account.email, account.runs, account.cost_usd, account.input_tokens) == ("alice@exemple.fr", 0, cost, 2005)
    assert container.usage.get_budget(now).spent_usd == cost
    assert container.usage.list_unpriced_models() == []

    container.account.delete_account(alice)

    # Les questions partent avec le compte ; ce qu'elles ont coûté reste, en totaux du mois sans adresse
    assert count_rows(container, AssistantMessage) == 0
    [gone] = container.usage.get_overview(now=now).accounts
    assert (gone.deleted, gone.email, gone.cost_usd) == (True, None, cost)
    assert container.usage.get_budget(now).spent_usd == cost


def test_model_without_price_is_reported_for_the_assistant_too(container):
    container.assistant.ask(BOB, "Comment déposer mon CV ?", datetime.now(UTC))

    assert container.usage.list_unpriced_models() == [FakeAnswerModel.model_name, FakeEmbedder.model_name]


def test_each_user_has_their_own_questions(session):
    bob, carol = AssistantMessageRepository(session, BOB), AssistantMessageRepository(session, CAROL)
    message = {"question": "q", "answer": "r", "outcome": "answered", "created_at": NOON}
    bob.insert_message(message)
    bob.insert_message(message | {"question": "q2"})
    carol.insert_message(message | {"question": "autre"})

    assert [row.question for row in bob.list_recent(10)] == ["q", "q2"]
    assert [row.question for row in bob.list_recent(1)] == ["q2"]
    assert bob.list_recent(10, NOON + timedelta(seconds=1)) == []
    assert (bob.count_since(NOON), carol.count_since(NOON), bob.count_since(NOON + timedelta(seconds=1))) == (2, 1, 0)

    assert bob.delete_all() == 2
    assert bob.list_recent(10) == [] and [row.question for row in carol.list_recent(10)] == ["autre"]
