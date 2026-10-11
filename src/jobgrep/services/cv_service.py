from collections.abc import Callable, Iterable, Iterator
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from langgraph.graph.state import CompiledStateGraph

from jobgrep.config import DEFAULT_USER_ID, LOCAL_TIMEZONE, MAX_CV_EXTRACTIONS_PER_DAY
from jobgrep.data.database import Database
from jobgrep.data.repositories.cv_extraction_repository import CvExtractionRepository
from jobgrep.data.repositories.cv_text_repository import CvTextRepository
from jobgrep.data.repositories.query_repository import QueryRepository
from jobgrep.data.repositories.rejected_job_repository import RejectedJobRepository
from jobgrep.errors import InvalidInputError
from jobgrep.schemas import CvDeposit, CvProgress, CvQueriesOutcome, CvStatus

# Un CV pèse quelques centaines de ko : au-delà, ce n'en est pas un, et le fichier est lu en mémoire
MAX_CV_BYTES = 10 * 1024 * 1024

# Ce qui est dit à l'utilisateur de ses postes recherchés, une fois son CV enregistré
MANUAL_ENTRY = "ajoutez vos postes recherchés à la main"
DEPOSIT_MESSAGES: dict[CvQueriesOutcome, str] = {
    "created": "CV enregistré. Vos postes recherchés ont été préparés à partir de lui : vérifiez-les.",
    "kept": "CV enregistré. Vos postes recherchés n'ont pas changé.",
    "limit": (
        "CV enregistré. Vos postes recherchés n'ont pas été préparés : c'est possible "
        f"{MAX_CV_EXTRACTIONS_PER_DAY} fois par jour. D'ici demain, {MANUAL_ENTRY}."
    ),
    "budget": (
        "CV enregistré. Vos postes recherchés n'ont pas été préparés : le budget du jour de l'application est "
        f"atteint. D'ici demain, {MANUAL_ENTRY}."
    ),
    "empty": f"CV enregistré, mais aucun poste n'a pu en être tiré : {MANUAL_ENTRY}.",
    "failed": (
        "CV enregistré, mais vos postes recherchés n'ont pas pu être préparés pour l'instant : "
        f"{MANUAL_ENTRY}, ou déposez de nouveau votre CV plus tard."
    ),
}


def _day_start(now: datetime) -> datetime:
    """Renvoie minuit du jour en cours, à l'heure de Paris : la limite se compte par jour."""
    local = now.astimezone(ZoneInfo(LOCAL_TIMEZONE))
    return local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)


class CvService:
    def __init__(
        self,
        database: Database,
        graph: Callable[[], CompiledStateGraph],
        budget_reached: Callable[[], bool] = lambda: False,
        on_failure: Callable[[int, str], None] = lambda user_id, error_type: None,
    ):
        self.database = database
        # Le graph du dépôt d'un CV, construit à son premier usage
        self.graph = graph
        self.budget_reached = budget_reached
        # Appelé quand le modèle n'a pas pu lire un CV, avec le type de l'erreur : la panne doit laisser une trace
        self.on_failure = on_failure

    def save_cv(self, user_id: int, data: bytes, names: Iterable[str] = (), replace_queries: bool = False) -> CvDeposit:
        """Remplace le CV de l'utilisateur par ce PDF, et dit ce qu'il est advenu de ses postes recherchés.

        C'est stream_deposit, sans le suivi : voir cette méthode.
        """
        *_, deposit = self.stream_deposit(user_id, data, names, replace_queries)
        return deposit

    def stream_deposit(
        self,
        user_id: int,
        data: bytes,
        names: Iterable[str] = (),
        replace_queries: bool = False,
        now: datetime | None = None,
    ) -> Iterator[CvProgress | CvDeposit]:
        """Remplace le CV de l'utilisateur par ce PDF, et rend chaque étape puis le résultat.

        Seul le texte du CV est gardé, sans ses coordonnées : le PDF n'est pas conservé. « names » donne les
        noms connus de l'utilisateur, à retirer aussi. Un modèle tire ensuite du CV les postes à rechercher :
        d'office si l'utilisateur n'en a aucun, à la place des siens seulement s'il l'a demandé
        (« replace_queries »). Une fois la limite du jour ou le budget atteint, ou si le modèle ne répond pas,
        le CV est enregistré quand même et les postes restent à saisir.

        Un fichier trop gros est refusé à l'appel, avant le premier élément ; un PDF illisible l'est à la
        première étape, et laisse le CV en place.
        """
        if len(data) > MAX_CV_BYTES:
            raise InvalidInputError(f"Le CV dépasse {MAX_CV_BYTES // (1024 * 1024)} Mo.")
        skipped = self._reason_to_skip_extraction(user_id, replace_queries, now or datetime.now(UTC))
        return self._deposit(user_id, data, list(names), skipped)

    def _reason_to_skip_extraction(self, user_id: int, replace_queries: bool, now: datetime) -> CvQueriesOutcome | None:
        """Dit pourquoi les postes ne seront pas tirés de ce CV, ou None s'ils le seront."""
        with self.database.session() as session:
            has_queries = bool(QueryRepository(session, user_id).list_queries())
            extractions = CvExtractionRepository(session, user_id).count_since(_day_start(now))
        if has_queries and not replace_queries:
            return "kept"
        # Ni le budget ni la limite ne s'appliquent au propriétaire, qui paie les clés API
        if user_id == DEFAULT_USER_ID:
            return None
        if self.budget_reached():
            return "budget"
        return "limit" if extractions >= MAX_CV_EXTRACTIONS_PER_DAY else None

    def _deposit(
        self, user_id: int, data: bytes, names: list[str], skipped: CvQueriesOutcome | None
    ) -> Iterator[CvProgress | CvDeposit]:
        state = {"user_id": user_id, "data": data, "names": names, "extract": skipped is None}
        final: dict = {}
        for mode, chunk in self.graph().stream(state, stream_mode=["custom", "values"]):
            if mode == "custom":
                yield CvProgress(**chunk)
            else:
                final = chunk
        outcome = final.get("outcome") or skipped or "kept"
        if outcome == "failed":
            self.on_failure(user_id, final.get("error_type", "Exception"))
        yield CvDeposit(
            updated_at=self.get_status(user_id).updated_at,
            queries_outcome=outcome,
            message=DEPOSIT_MESSAGES[outcome],
            queries=list(final.get("queries", [])),
        )

    def store_text(self, user_id: int, content: str) -> None:
        """Enregistre le texte du CV de l'utilisateur, déjà sans coordonnées, à la place du précédent."""
        with self.database.session() as session:
            CvTextRepository(session, user_id).save(content)
            # Les rejets valaient pour l'ancien CV : ces pages peuvent convenir au nouveau
            RejectedJobRepository(session, user_id).clear()

    def read_text(self, user_id: int) -> str:
        """Renvoie le texte du CV de l'utilisateur, coordonnées retirées : celui qui peut être envoyé au modèle."""
        with self.database.session() as session:
            content = CvTextRepository(session, user_id).get_content()
        if content is None:
            raise InvalidInputError("Aucun CV enregistré.")
        return content

    def get_status(self, user_id: int) -> CvStatus:
        """Dit si l'utilisateur a un CV en place, et depuis quand."""
        with self.database.session() as session:
            return CvStatus(updated_at=CvTextRepository(session, user_id).get_updated_at())
