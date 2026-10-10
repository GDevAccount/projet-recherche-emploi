"""Situation d'un compte, telle que l'assistant peut la lire : des nombres et des dates, aucun contenu.

C'est ce que rend l'outil « etat_du_compte » au modèle, donc ce qui part chez OpenAI quand une question
porte sur le compte : ni CV, ni phrase de recherche, ni intitulé ou lien d'une offre. Ne rien y ajouter de
tel sans reprendre les règles de confidentialité.
"""

from collections import Counter
from datetime import datetime
from zoneinfo import ZoneInfo

from jobgrep.config import DEFAULT_USER_ID, LOCAL_TIMEZONE, MAX_SEARCHES_PER_DAY, MAX_TRIAL_SEARCHES
from jobgrep.data.database import Database
from jobgrep.data.repositories.user_repository import UserRepository
from jobgrep.schemas import SearchRunRead
from jobgrep.services.cv_service import CvService
from jobgrep.services.job_service import JobService
from jobgrep.services.query_service import QueryService
from jobgrep.services.search_service import SearchService

# Étapes d'une candidature, dans l'ordre, telles que l'application les nomme
STATUS_LABELS = {
    "todo": "à traiter",
    "applied": "candidature envoyée",
    "interview": "entretien obtenu",
    "rejected": "refusée par l'employeur",
}
RUN_LABELS = {
    "done": "terminée",
    "failed": "échouée",
    "interrupted": "interrompue par une mise à jour de l'application",
    "running": "en cours",
}


def _date(moment: datetime) -> str:
    return moment.astimezone(ZoneInfo(LOCAL_TIMEZONE)).strftime("%d/%m/%Y à %H:%M")


def _describe_run(run: SearchRunRead) -> str:
    state = RUN_LABELS.get(run.status or "", "sans bilan")
    counts = ""
    if run.status == "done":
        counts = (
            f" : {run.found_count or 0} pages trouvées, {run.new_count or 0} nouvelles lues, "
            f"{run.kept_count or 0} offres retenues"
        )
    return f"le {_date(run.created_at)}, {state}{counts}"


class AccountStatusReader:
    """Lit la situation d'un compte par les services, comme un écran le ferait : il ne décide rien."""

    def __init__(
        self, database: Database, search: SearchService, cv: CvService, queries: QueryService, jobs: JobService
    ):
        self.database = database
        self.search = search
        self.cv = cv
        self.queries = queries
        self.jobs = jobs

    def describe(self, user_id: int) -> str:
        """Renvoie la situation du compte, en phrases courtes que le modèle peut citer telles quelles."""
        with self.database.session() as session:
            is_trial = UserRepository(session).is_trial(user_id)
        cv_date = self.cv.get_status(user_id).updated_at
        queries = len(self.queries.list_queries(user_id))
        remaining = self.search.remaining_searches(user_id)
        runs = self.search.list_runs(user_id)
        jobs = self.jobs.list_jobs(user_id)
        rejected = self.jobs.list_rejected_jobs(user_id)

        lines = ["Type de compte : " + ("essai sans compte" if is_trial else "compte connecté") + "."]
        lines.append(f"CV : déposé le {_date(cv_date)}." if cv_date else "CV : aucun CV déposé.")
        lines.append(f"Postes recherchés enregistrés : {queries}.")
        if self.search.can_search(user_id):
            lines.append("Profil complet : une recherche peut être lancée.")
        else:
            missing = [name for name, present in (("le CV", cv_date), ("un poste recherché", queries)) if not present]
            lines.append(f"Profil incomplet, aucune recherche ne peut être lancée : il manque {' et '.join(missing)}.")
        if user_id == DEFAULT_USER_ID or remaining is None:
            lines.append("Recherches restantes : sans limite.")
        elif is_trial:
            lines.append(f"Recherches restantes pour cet essai : {remaining} sur {MAX_TRIAL_SEARCHES} en tout.")
        else:
            lines.append(f"Recherches restantes aujourd'hui : {remaining} sur {MAX_SEARCHES_PER_DAY}.")
        lines.append("Recherche en cours : " + ("oui." if self.search.is_running(user_id) else "non."))
        lines.append(f"Dernière recherche : {_describe_run(runs[0])}." if runs else "Dernière recherche : aucune.")

        lines.append(f"Offres retenues : {len(jobs)}.")
        by_status = Counter(job.status for job in jobs)
        lines += [f"- {label} : {by_status[status]}" for status, label in STATUS_LABELS.items() if by_status[status]]
        lines.append(f"Pages écartées : {len(rejected)}.")
        by_motive = Counter(page.motive for page in rejected)
        lines += [f"- {motive} : {count}" for motive, count in by_motive.most_common()]
        return "\n".join(lines)
