"""La même annonce publiée sur deux sites n'est gardée qu'une fois."""

import pytest

from jobgrep.agent.duplicates import SeenOffer, site_of, split_duplicates, text_fingerprint
from jobgrep.config import DUPLICATE_MIN_SHARED
from jobgrep.data.repositories.correction_repository import CorrectionRepository
from jobgrep.data.repositories.cv_text_repository import CvTextRepository
from jobgrep.data.repositories.query_repository import QueryRepository
from jobgrep.schemas import REJECT_DUPLICATE

BOB = 2
# Le corps d'une annonce, et celui d'une autre : assez longs pour que leur empreinte se compare
AD = " ".join(f"mission{index}" for index in range(400))
OTHER_AD = " ".join(f"poste{index}" for index in range(400))
ORIGINAL = "https://www.free-work.com/fr/job/0"
COPY = "https://www.jobijoba.com/fr/annonce/0"


def page(url: str, raw_content: str | None) -> dict:
    return {"title": f"Page {url}", "url": url, "content": "c", "raw_content": raw_content, "score": 1.0}


@pytest.fixture
def graph(container):
    with container.database.session() as session:
        CvTextRepository(session, BOB).save("CV de Bob")
        QueryRepository(session, BOB).add_query("CDI", "développeur python")
    return container.graph


def serve(search_engine, *pages: dict) -> None:
    search_engine.search = lambda query, international=False: list(pages)


@pytest.mark.parametrize(
    ("url", "site"),
    [
        ("https://fr.linkedin.com/jobs/view/1", "linkedin.com"),
        ("https://www.linkedin.com/jobs/view/1", "linkedin.com"),
        ("https://www.free-work.com/fr/job/1", "free-work.com"),
        ("https://www.exemple.org/offre", "exemple.org"),
    ],
)
def test_two_addresses_of_a_job_board_are_the_same_site(url, site):
    assert site_of(url) == site


def test_fingerprint_ignores_case_accents_and_punctuation():
    text = "Mettre en œuvre des solutions d'intelligence artificielle générative, pour les équipes métiers. " * 3
    altered = text.upper().replace("É", "E").replace(",", " -")

    assert text_fingerprint(text) == text_fingerprint(altered) != []


def test_a_copied_offer_is_recognized_despite_what_surrounds_it():
    copy = f"Free-Work est une plateforme. {AD} Offres similaires : développeur, ingénieur."
    seen = [SeenOffer("free-work.com", frozenset(text_fingerprint(AD)))]

    kept, copies = split_duplicates([page(COPY, copy), page("https://www.apec.fr/1", OTHER_AD)], seen)

    assert [(found["url"], site) for found, site in copies] == [(COPY, "free-work.com")]
    assert [found["url"] for found in kept] == ["https://www.apec.fr/1"]
    assert len(kept[0]["text_fingerprint"]) >= DUPLICATE_MIN_SHARED


def test_two_pages_of_the_same_site_are_never_compared():
    # Leur habillage commun pèserait plus que l'annonce
    pages = [page(ORIGINAL, AD), page("https://www.free-work.com/fr/job/1", AD)]

    kept, copies = split_duplicates(pages, [])

    assert len(kept) == 2 and copies == []


def test_a_page_without_its_full_text_is_left_to_the_model():
    kept, copies = split_duplicates([page(ORIGINAL, AD), page(COPY, None)], [])

    assert [found["text_fingerprint"] is None for found in kept] == [False, True]
    assert copies == []


def test_the_same_offer_on_another_site_is_not_evaluated(graph, container, search_engine, evaluator):
    serve(search_engine, page(ORIGINAL, AD))
    graph.invoke({"user_id": BOB})
    assert [url for _, url in evaluator.evaluated] == [ORIGINAL]

    serve(search_engine, page(COPY, f"Repris de Free-Work. {AD}"), page("https://www.apec.fr/0", OTHER_AD))
    result = graph.invoke({"user_id": BOB})

    # La copie n'a pas coûté d'appel au modèle ; l'autre annonce est évaluée comme avant
    assert [url for _, url in evaluator.evaluated] == [ORIGINAL, "https://www.apec.fr/0"]
    assert [found["url"] for found in result["new_jobs"]] == ["https://www.apec.fr/0"]
    assert {job.url for job in container.jobs.list_jobs(BOB)} == {ORIGINAL, "https://www.apec.fr/0"}
    [rejected] = container.jobs.list_rejected_jobs(BOB)
    assert (rejected.url, rejected.motive) == (COPY, REJECT_DUPLICATE)
    assert rejected.reject_reason.endswith("free-work.com")
    assert "duplicate" not in rejected.model_dump()

    # Son adresse est mémorisée : elle n'est plus comparée ni évaluée
    result = graph.invoke({"user_id": BOB})
    assert result["new_jobs"] == [] and result["duplicates"] == []


def test_the_copy_of_a_deleted_offer_does_not_come_back(graph, container, search_engine, evaluator):
    serve(search_engine, page(ORIGINAL, AD))
    graph.invoke({"user_id": BOB})
    container.jobs.delete_jobs(BOB, [job.id for job in container.jobs.list_jobs(BOB)])

    serve(search_engine, page(COPY, AD))
    graph.invoke({"user_id": BOB})

    assert container.jobs.list_jobs(BOB) == []
    assert [url for _, url in evaluator.evaluated] == [ORIGINAL]


def test_between_two_pages_of_one_search_the_original_is_kept(graph, container, search_engine, evaluator):
    # L'agrégateur arrive le premier : c'est quand même le site d'origine qui est évalué
    serve(search_engine, page(COPY, AD), page(ORIGINAL, AD))

    progress = list(graph.stream({"user_id": BOB}, stream_mode="custom"))

    assert [url for _, url in evaluator.evaluated] == [ORIGINAL]
    assert [job.url for job in container.jobs.list_jobs(BOB)] == [ORIGINAL]
    [dedupe] = [event for event in progress if event["step"] == "dedupe"]
    assert (dedupe["found"], dedupe["new"]) == (2, 1)
    assert dedupe["message"] == "1 page(s) nouvelle(s) sur 2 trouvée(s), 1 déjà vue(s) sur un autre site"


def test_a_copy_put_back_by_the_user_is_not_a_correction_of_the_sorting(graph, container, search_engine):
    serve(search_engine, page(COPY, AD), page(ORIGINAL, AD))
    graph.invoke({"user_id": BOB})

    restored = container.jobs.restore_rejected_job(BOB, COPY)

    assert restored.url == COPY
    assert container.jobs.list_rejected_jobs(BOB) == []
    # Le tri n'avait pas jugé cette page : rien ne lui est reproché
    with container.database.session() as session:
        assert CorrectionRepository(session, BOB).list_all() == []
