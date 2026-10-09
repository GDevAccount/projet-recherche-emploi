from collections.abc import Iterable
from datetime import UTC, datetime

from projet_recherche_emploi.data.database import Database
from projet_recherche_emploi.data.models import Job
from projet_recherche_emploi.data.repositories.correction_repository import CorrectionRepository
from projet_recherche_emploi.data.repositories.job_repository import JobRepository
from projet_recherche_emploi.data.repositories.page_evaluation_repository import PageEvaluationRepository
from projet_recherche_emploi.data.repositories.rejected_job_repository import RejectedJobRepository
from projet_recherche_emploi.data.repositories.search_run_repository import SearchRunRepository
from projet_recherche_emploi.errors import ConflictError, InvalidInputError, NotFoundError
from projet_recherche_emploi.schemas import DeleteReason, JobRead, JobStatus, RejectedJobRead

# Ce qu'une offre remise par l'utilisateur affiche à la place de la justification du modèle
RESTORED_MATCH_REASON = "Vous avez remis cette page dans vos offres : le tri l'avait écartée."
CORRECTION_RESTORED = "restored"
CORRECTION_DELETED = "deleted"
# Critères du verdict d'une page écartée, recopiés dans la correction qui le contredit
VERDICT_FIELDS = (
    "page_kind",
    "matches_search",
    "matches_contract",
    "matches_skills",
    "matches_level",
    "matches_location",
)


def next_statuses(status: str, had_interview: bool) -> list[JobStatus]:
    """Renvoie les états qu'une candidature peut prendre depuis celui-ci, l'étape suivante en premier.

    Une candidature avance d'une étape, ou revient à la précédente pour corriger une erreur. Un refus se
    déclare une fois la candidature envoyée ; le défaire la rend à l'étape où elle en était.
    """
    if status == "todo":
        return ["applied"]
    if status == "applied":
        return ["interview", "rejected", "todo"]
    if status == "interview":
        return ["rejected", "applied"]
    return ["interview"] if had_interview else ["applied"]


def _read(job: Job) -> JobRead:
    read = JobRead.model_validate(job)
    read.next_statuses = next_statuses(job.status, job.interview_at is not None)
    return read


class JobService:
    def __init__(self, database: Database):
        self.database = database

    def list_jobs(self, user_id: int) -> list[JobRead]:
        """Renvoie les offres retenues de l'utilisateur, les plus récentes en premier."""
        with self.database.session() as session:
            return [_read(job) for job in JobRepository(session, user_id).list_jobs()]

    def mark_opened(self, user_id: int, job_id: int, now: datetime | None = None) -> None:
        """Note que l'utilisateur a ouvert l'annonce, la première fois seulement. Une offre inconnue est ignorée.

        Entre « retenue » et « candidature », c'est le seul signe que l'offre a donné envie d'aller voir.
        """
        with self.database.session() as session:
            JobRepository(session, user_id).mark_opened(job_id, now or datetime.now(UTC))

    def set_status(self, user_id: int, job_id: int, status: JobStatus, now: datetime | None = None) -> JobRead:
        """Fait passer la candidature à cet état, et renvoie l'offre à jour, dates comprises.

        Chaque étape est datée quand elle est franchie, et sa date effacée quand on revient en arrière.
        Refuse un état que l'offre ne peut pas prendre depuis le sien.
        """
        now = now or datetime.now(UTC)
        with self.database.session() as session:
            jobs = JobRepository(session, user_id)
            job = jobs.get_job(job_id)
            if job is None:
                raise NotFoundError("Cette offre n'existe pas.")
            if status != job.status:
                if status not in next_statuses(job.status, job.interview_at is not None):
                    raise InvalidInputError("Cette offre ne peut pas passer à cet état depuis le sien.")
                reached_interview = status == "interview" or (status == "rejected" and job.interview_at is not None)
                jobs.set_tracking(
                    job_id,
                    status,
                    applied_at=None if status == "todo" else job.applied_at or now,
                    interview_at=(job.interview_at or now) if reached_interview else None,
                    rejected_at=now if status == "rejected" else None,
                )
            return _read(jobs.get_job(job_id))

    def delete_job(self, user_id: int, job_id: int, reason: DeleteReason | None = None) -> None:
        """Supprime l'offre, et garde la trace de cette suppression avec le motif donné."""
        with self.database.session() as session:
            jobs = JobRepository(session, user_id)
            job = jobs.get_job(job_id)
            if job is None:
                raise NotFoundError("Cette offre n'existe pas.")
            jobs.delete_jobs([job_id])
            correction = {
                "kind": CORRECTION_DELETED,
                "url": job.url,
                "title": job.title,
                "query": job.query,
                "reason": reason,
                "model_reason": job.match_reason,
            }
            self._record_correction(session, user_id, correction)

    def restore_rejected_job(self, user_id: int, url: str) -> JobRead:
        """Remet une page écartée dans les offres de l'utilisateur, à traiter, et renvoie l'offre créée.

        Le rejet est oublié, et la correction enregistrée avec le verdict qu'elle contredit.
        """
        with self.database.session() as session:
            rejected_jobs = RejectedJobRepository(session, user_id)
            rejected = rejected_jobs.get_rejected_job(url)
            if rejected is None:
                raise NotFoundError("Cette page n'est plus parmi vos pages écartées.")
            jobs = JobRepository(session, user_id)
            offer = {
                "url": rejected.url,
                "title": rejected.title,
                "contract_type": rejected.contract_type,
                "work_location": rejected.work_location,
                "query": rejected.query,
                "match_reason": RESTORED_MATCH_REASON,
            }
            # Aucune ligne ajoutée : l'adresse est celle d'une offre déjà en base, peut-être supprimée
            if jobs.insert_jobs([offer]) == 0:
                raise ConflictError("Cette page est déjà passée par vos offres.")
            correction = {
                "kind": CORRECTION_RESTORED,
                "url": rejected.url,
                "title": rejected.title,
                "query": rejected.query,
                "model_reason": rejected.reject_reason,
                **{field: getattr(rejected, field) for field in VERDICT_FIELDS},
            }
            self._record_correction(session, user_id, correction)
            rejected_jobs.delete_rejected_job(url)
            return _read(jobs.get_job_by_url(url))

    def _record_correction(self, session, user_id: int, correction: dict) -> None:
        # Le journal dit quel lancement avait jugé la page, donc avec quel modèle et quel prompt
        evaluation = PageEvaluationRepository(session, user_id).get_last_for_url(correction["url"])
        run = None
        if evaluation is not None and evaluation.search_run_id is not None:
            run = SearchRunRepository(session, user_id).get_run(evaluation.search_run_id)
        if run is not None:
            judged_by = {"search_run_id": run.id, "model": run.model, "prompt_version": run.prompt_version}
            correction = {**correction, **judged_by}
        CorrectionRepository(session, user_id).insert_correction(correction)

    def delete_jobs(self, user_id: int, job_ids: Iterable[int]) -> int:
        """Supprime les offres de la liste, et renvoie le nombre réellement supprimé."""
        with self.database.session() as session:
            return JobRepository(session, user_id).delete_jobs(job_ids)

    def list_rejected_jobs(self, user_id: int) -> list[RejectedJobRead]:
        """Renvoie les pages rejetées par le modèle pour cet utilisateur, les plus récentes en premier."""
        with self.database.session() as session:
            rejected_jobs = RejectedJobRepository(session, user_id).list_rejected_jobs()
            return [RejectedJobRead.model_validate(job) for job in rejected_jobs]
