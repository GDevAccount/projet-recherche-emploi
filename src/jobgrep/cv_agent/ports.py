"""Ce que le graph du dépôt d'un CV attend de l'extérieur : de quoi lire un PDF, en retirer les coordonnées,
un modèle qui en tire des postes à rechercher, et de quoi enregistrer le CV et ces postes.

Les versions réelles sont dans adapters.py (OpenAI), dans data/cv_ingestion/ et dans les services ; les tests
branchent les leurs.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from jobgrep.config import MAX_PROFILE_JOBS, ContractType

# Ce qu'il advient des postes recherchés au dépôt d'un CV : créés à partir de lui ; laissés tels quels (« kept ») ;
# non proposés parce que la limite du jour ou le budget est atteint ; rien à tirer du CV ; modèle en panne
QueriesOutcome = Literal["created", "kept", "limit", "budget", "empty", "failed"]


class DraftedJob(BaseModel):
    """Un poste que le CV permet de viser, tel que le modèle le propose."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(description="Intitulé du métier, court, sans contrat ni lieu ni niveau.")
    contract_type: ContractType = Field(description="Contrat que le parcours du CV rend le plus probable.")
    skills: list[str] = Field(description="Compétences écrites dans le CV qui servent ce métier, cinq au plus.")


class DraftedProfile(BaseModel):
    """Ce que le modèle tire d'un CV : les postes à rechercher, et où."""

    model_config = ConfigDict(extra="forbid")

    jobs: list[DraftedJob] = Field(description=f"De un à {MAX_PROFILE_JOBS} postes, le plus évident d'abord.")
    location: str = Field(description="Département ou région où chercher ; vide si le CV ne le dit pas.")
    remote: bool = Field(description="Vrai seulement si le CV dit ne chercher que du télétravail complet.")


@dataclass(frozen=True)
class ExtractionUsage:
    """Ce qu'a coûté la lecture d'un CV par le modèle. None quand il ne le dit pas."""

    input_tokens: int | None = None
    output_tokens: int | None = None
    cache_read_tokens: int | None = None
    cache_write_tokens: int | None = None
    duration_ms: int | None = None


@dataclass(frozen=True)
class Extraction:
    """Une lecture de CV par le modèle : ce qu'il propose, et de quoi la compter."""

    profile: DraftedProfile
    usage: ExtractionUsage
    model: str
    prompt_version: str


class PdfReader(Protocol):
    def read_text(self, data: bytes) -> str:
        """Renvoie le texte d'un PDF, ou lève InvalidInputError s'il est illisible ou sans texte."""
        ...


class Anonymizer(Protocol):
    def anonymize(self, text: str, names: Iterable[str] = ()) -> str:
        """Renvoie le texte sans les coordonnées de la personne, ni les noms donnés."""
        ...


class ProfileExtractor(Protocol):
    model_name: str

    def extract(self, cv: str) -> tuple[DraftedProfile, ExtractionUsage]:
        """Tire d'un CV sans coordonnées les postes qu'il permet de viser, et la zone où les chercher."""
        ...


class CvStore(Protocol):
    def store_text(self, user_id: int, content: str) -> None:
        """Enregistre le texte du CV de l'utilisateur, à la place du précédent."""
        ...


class ProfileStore(Protocol):
    def apply_profile(self, user_id: int, extraction: Extraction) -> Sequence:
        """Enregistre l'extraction, remplace les postes recherchés par ceux qu'elle propose, et les renvoie."""
        ...
