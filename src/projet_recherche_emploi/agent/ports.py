"""Ce que le graph attend de l'extérieur. Les tests y branchent des faux, sans réseau ni facture."""

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel

from projet_recherche_emploi.agent.state import FoundPage
from projet_recherche_emploi.config import OFFER_PAGE_KIND, ContractType, PageKind, WorkMode


@dataclass(frozen=True)
class SearchCriteria:
    """Ce que l'utilisateur cherche, toutes recherches enregistrées confondues.

    Un verdict est mémorisé par URL, pas par recherche : une page est donc jugée sur l'ensemble.
    """

    # Phrases de recherche saisies : elles disent le métier visé, que le CV ne dit pas
    sought_jobs: tuple[str, ...] = ()
    contract_types: frozenset[str] = frozenset()
    # Zones géographiques acceptées, dans les mots lus par le filtre ; vide s'il n'y en a aucune
    accepted_areas: str = ""
    # Vrai si l'une des recherches accepte le télétravail complet, quel que soit le pays
    accepts_full_remote: bool = False


class CvReader(Protocol):
    def read_text(self, user_id: int) -> str:
        """Renvoie le texte du CV de l'utilisateur, tel qu'il peut être envoyé au modèle : sans ses coordonnées."""
        ...


class JobEvaluation(BaseModel):
    """Ce que le modèle lit sur une page. Les champs sont dans l'ordre où il les écrit : les faits, puis les avis.

    Il ne dit pas si le lieu ou le contrat conviennent au candidat : il les rapporte, et le graph décide.
    """

    # Nature de la page : une offre précise, ou ce qu'elle est d'autre
    page_kind: PageKind
    # Lus sur la page ; None quand elle ne le dit pas
    contract_type: ContractType | None = None
    work_city: str | None = None
    work_country: str | None = None
    work_mode: WorkMode | None = None
    # Le lieu du poste est-il dans l'une des zones géographiques acceptées, télétravail mis à part
    in_accepted_area: bool = True
    # Faux quand la page réserve le poste aux candidats d'un pays ou d'une zone sans la France
    open_to_candidates_in_france: bool = True
    # Le métier du poste est-il l'un de ceux que le candidat recherche, quel que soit son CV
    matches_search: bool
    # Le CV couvre-t-il les compétences principales du poste, et son niveau d'expérience est-il compatible
    matches_skills: bool
    matches_level: bool
    reason: str

    @property
    def is_real_offer(self) -> bool:
        return self.page_kind == OFFER_PAGE_KIND


@dataclass(frozen=True)
class EvaluationUsage:
    """Ce qu'a coûté l'évaluation d'une page. None quand l'évaluateur ne le dit pas."""

    input_tokens: int | None = None
    output_tokens: int | None = None
    duration_ms: int | None = None
    # Parts des jetons d'entrée lues ou écrites en cache, facturées à un autre tarif
    cache_read_tokens: int | None = None
    cache_write_tokens: int | None = None
    # Part des jetons de sortie passée en raisonnement, que la réponse ne montre pas
    reasoning_tokens: int | None = None


def page_text(page: FoundPage) -> str:
    """Renvoie le texte d'une page donné à l'évaluateur, avant troncature : la page entière, sinon son extrait."""
    return page.get("raw_content") or page["content"]


class JobSearchEngine(Protocol):
    def search(self, query: str, international: bool = False) -> list[dict]:
        """Renvoie les pages trouvées pour cette recherche : title, url, content, raw_content, score.

        Une recherche internationale porte aussi sur les sites d'offres en télétravail, hors de France.
        """
        ...


class JobEvaluator(Protocol):
    # Nom du modèle interrogé, enregistré avec chaque lancement
    model_name: str

    def evaluate(
        self, cv: str, criteria: SearchCriteria, pages: Sequence[FoundPage]
    ) -> Iterator[tuple[int, JobEvaluation, EvaluationUsage]]:
        """Évalue chaque page au regard du CV et de ce que l'utilisateur cherche.

        Les verdicts arrivent dans le désordre, chacun avec l'indice de sa page et ce que l'appel a coûté.
        """
        ...
