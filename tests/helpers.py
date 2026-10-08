from io import BytesIO

from pypdf import PdfWriter


def job(url: str) -> dict:
    return {
        "url": url,
        "title": f"Offre {url}",
        "content": "c",
        "score": 1.0,
        "contract_type": "CDI",
        "work_location": "Paris",
        "query": "q",
        "match_reason": "r",
    }


def rejected_job(url: str) -> dict:
    return {
        "url": url,
        "title": f"Page {url}",
        "contract_type": "CDI",
        "query": "q",
        "is_real_offer": True,
        "matches_cv": False,
        "matches_location": True,
        "reject_reason": "Hors profil",
    }


def blank_pdf() -> bytes:
    """Renvoie un PDF valide mais sans texte, comme un document scanné."""
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    content = BytesIO()
    writer.write(content)
    return content.getvalue()
