"""Le guide que lit l'assistant recopie des libellés de l'application : chacun doit y exister encore."""

import re
from pathlib import Path

import pytest

from jobgrep.site_texts import read_site_text

ROOT = Path(__file__).parents[1]
FRONT = ROOT / "frontend" / "src"
# Où un libellé peut être écrit : les écrans du front, et les motifs que l'API rédige
SOURCES = [*FRONT.rglob("*.html"), *FRONT.rglob("*.ts"), ROOT / "src" / "jobgrep" / "schemas.py"]
# Citations du guide qui ne sont pas des libellés : un exemple de saisie
NOT_LABELS = {"comptable fournisseurs"}

QUOTED = sorted(set(re.findall(r"« ([^»]+) »", read_site_text("aide"))) - NOT_LABELS)


def normalize(text: str) -> str:
    # Un gabarit coupe ses phrases en lignes, et un script écrit ses apostrophes avec une barre oblique
    return re.sub(r"\s+", " ", text.replace("\\'", "'"))


@pytest.fixture(scope="module")
def application_text() -> str:
    screens = [path for path in SOURCES if not path.name.endswith(".spec.ts")]
    return normalize(" ".join(path.read_text(encoding="utf-8") for path in screens))


def test_guide_quotes_labels():
    assert len(QUOTED) > 15


@pytest.mark.parametrize("label", QUOTED)
def test_label_quoted_by_the_guide_exists_in_the_application(label, application_text):
    # Un bouton renommé sans reprendre le guide, et l'assistant donnerait une consigne fausse
    assert label in application_text, f"« {label} » n'est plus dans l'application : reprendre texts/aide.md"
