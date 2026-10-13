"""Reconnaître la même annonce publiée sur deux sites, à son texte.

Deux sites ne donnent à une annonce ni la même adresse, ni le même intitulé, ni toujours le même employeur
(un agrégateur cite le site d'où il la reprend) : seul le corps de l'annonce est recopié tel quel. Mesuré le
2026-10-13 sur le texte rendu par Tavily : une annonce reprise partage plus de 400 suites de cinq mots avec
l'originale, deux annonces distinctes de deux sites moins de 30. Sur un même site, l'habillage commun aux pages
pèse plus que l'annonce : deux pages d'un même site ne sont donc pas comparées.
"""

import re
import unicodedata
import zlib
from collections.abc import Iterable
from dataclasses import dataclass
from urllib.parse import urlsplit

from jobgrep.agent.state import FoundPage
from jobgrep.config import (
    AGGREGATOR_SITES,
    DUPLICATE_MIN_SHARED,
    FINGERPRINT_SAMPLING,
    JOB_SITES,
    REMOTE_JOB_SITES,
    SHINGLE_WORDS,
)

WORD = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True)
class SeenOffer:
    """Annonce à laquelle comparer une page : son site et l'empreinte de son texte."""

    site: str
    fingerprint: frozenset[int]


def site_of(url: str) -> str:
    """Renvoie le site d'une page : « fr.linkedin.com » et « www.linkedin.com » sont le même."""
    host = urlsplit(url).hostname or ""
    for site in (*JOB_SITES, *REMOTE_JOB_SITES):
        if host == site or host.endswith(f".{site}"):
            return site
    return host.removeprefix("www.")


def text_fingerprint(text: str) -> list[int]:
    """Renvoie l'empreinte d'un texte : une part, toujours la même, des suites de mots qu'il contient.

    Sans accent, majuscule ni ponctuation, pour qu'un caractère mal recopié ne change que les suites qu'il touche.
    Une suite sur FINGERPRINT_SAMPLING est gardée, choisie par sa valeur : deux textes gardent donc les mêmes.
    """
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    words = WORD.findall("".join(char for char in decomposed if not unicodedata.combining(char)))
    shingles = {" ".join(words[index : index + SHINGLE_WORDS]) for index in range(len(words) - SHINGLE_WORDS + 1)}
    # crc32 et non hash() : l'empreinte est relue par un autre processus
    values = {zlib.crc32(shingle.encode()) for shingle in shingles}
    return sorted(value for value in values if value % FINGERPRINT_SAMPLING == 0)


def split_duplicates(
    pages: Iterable[FoundPage], seen: Iterable[SeenOffer]
) -> tuple[list[FoundPage], list[tuple[FoundPage, str]]]:
    """Sépare les pages à évaluer de celles qui reprennent une annonce d'un autre site.

    Renvoie les premières avec leur empreinte, et les secondes avec le site où l'annonce a déjà été vue :
    parmi les annonces en base (seen), ou parmi les pages elles-mêmes.
    """
    pages = list(pages)
    seen = list(seen)
    fingerprints: dict[str, list[int] | None] = {}
    duplicates: dict[str, str] = {}
    # Les agrégateurs passent en dernier : entre deux pages de la même annonce, c'est l'originale qui reste
    for page in sorted(pages, key=lambda page: site_of(page["url"]) in AGGREGATOR_SITES):
        site = site_of(page["url"])
        # Sans le texte entier de la page, l'extrait est trop court pour comparer
        fingerprint = text_fingerprint(page["raw_content"]) if page.get("raw_content") else []
        fingerprints[page["url"]] = fingerprint or None
        if not fingerprint:
            continue
        values = frozenset(fingerprint)
        original = next(
            (offer for offer in seen if offer.site != site and len(offer.fingerprint & values) >= DUPLICATE_MIN_SHARED),
            None,
        )
        if original is not None:
            duplicates[page["url"]] = original.site
        else:
            seen.append(SeenOffer(site, values))
    kept = [{**page, "text_fingerprint": fingerprints[page["url"]]} for page in pages if page["url"] not in duplicates]
    return kept, [(page, duplicates[page["url"]]) for page in pages if page["url"] in duplicates]
