import math
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from jobgrep.config import (
    DEFAULT_PLAN,
    DEFAULT_USER_ID,
    LOCAL_TIMEZONE,
    MODEL_PRICES_USD,
    OFFER_PAGE_KIND,
    TRIAL_PLAN,
)
from jobgrep.data.database import Database
from jobgrep.data.models import Correction, Job, PageEvaluation, SearchRun
from jobgrep.data.repositories.correction_repository import CorrectionRepository
from jobgrep.data.repositories.cv_text_repository import CvTextRepository
from jobgrep.data.repositories.health_repository import HealthRepository
from jobgrep.data.repositories.job_repository import JobRepository
from jobgrep.data.repositories.page_evaluation_repository import PageEvaluationRepository
from jobgrep.data.repositories.query_repository import QueryRepository
from jobgrep.data.repositories.search_run_repository import SearchRunRepository
from jobgrep.data.repositories.usage_repository import UsageRepository
from jobgrep.data.repositories.user_repository import UserRepository
from jobgrep.errors import NotFoundError
from jobgrep.schemas import (
    DELETE_REASON_NOT_GIVEN,
    DELETE_REASONS,
    AccountDetail,
    AccountJourney,
    AccountUsage,
    BudgetOverview,
    JourneyEvent,
    JourneyOverview,
    JourneyStep,
    RejectionCount,
    UsageOverview,
)
from jobgrep.services.search_costs import (
    COST_DECIMALS,
    model_cost_usd,
    search_cost_usd,
    sum_costs,
)

FIRST_STEP = "Compte créé"
# Étapes du parcours d'un invité, dans l'ordre, et ce qui dit qu'un compte l'a franchie
JOURNEY_STEPS: dict[str, Callable[[AccountJourney], bool]] = {
    FIRST_STEP: lambda account: True,
    "CV déposé": lambda account: account.has_cv,
    "Poste recherché saisi": lambda account: account.queries > 0,
    "Recherche lancée": lambda account: account.runs > 0,
    "Offre retenue": lambda account: account.kept > 0,
    "Annonce ouverte": lambda account: account.opened > 0,
    "Candidature envoyée": lambda account: account.applied > 0,
    "Revenu un autre jour": lambda account: account.returned,
}
# Raisons qui écartent une page, dans l'ordre où le tri les regarde
REJECTION_LABELS = {
    "page_kind": "Pas une offre",
    "matches_search": "Métier",
    "matches_skills": "Compétences",
    "matches_level": "Niveau",
    "matches_contract": "Contrat",
    "matches_location": "Lieu",
}
# Au-delà, la fiche d'un compte ne montre que les moments les plus récents
MAX_JOURNEY_EVENTS = 200


def _rejection_labels(page: PageEvaluation) -> list[str]:
    """Renvoie les raisons pour lesquelles cette page a été écartée."""
    if page.page_kind is not None and page.page_kind != OFFER_PAGE_KIND:
        return [REJECTION_LABELS["page_kind"]]
    criteria = [name for name in REJECTION_LABELS if name != "page_kind"]
    return [REJECTION_LABELS[name] for name in criteria if getattr(page, name) is False]


def _describe_run(run: SearchRun) -> JourneyEvent:
    if run.status == "failed":
        return JourneyEvent(at=run.created_at, kind="error", label="Recherche échouée", detail=run.error)
    if run.status == "done":
        evaluated, found, kept = run.new_count or 0, run.found_count or 0, run.kept_count or 0
        detail = f"{evaluated} pages évaluées sur {found} trouvées, {kept} retenues"
        return JourneyEvent(at=run.created_at, kind="search", label="Recherche lancée", detail=detail)
    # Sans bilan : une recherche d'avant le suivi, en cours, ou coupée par un redémarrage
    return JourneyEvent(at=run.created_at, kind="search", label="Recherche lancée", detail="Sans bilan")


def _describe_job(job: Job) -> list[JourneyEvent]:
    steps = [
        (job.opened_at, "opened", "Annonce ouverte"),
        (job.applied_at, "applied", "Candidature envoyée"),
        (job.interview_at, "interview", "Entretien obtenu"),
        (job.rejected_at, "refused", "Refus de l'employeur"),
    ]
    return [JourneyEvent(at=at, kind=kind, label=label) for at, kind, label in steps if at is not None]


def _describe_correction(correction: Correction) -> JourneyEvent:
    if correction.kind == "restored":
        label = "Page écartée remise dans les offres"
        return JourneyEvent(at=correction.created_at, kind="restored", label=label)
    reason = DELETE_REASONS.get(correction.reason, DELETE_REASON_NOT_GIVEN)
    return JourneyEvent(at=correction.created_at, kind="deleted", label="Offre supprimée", detail=reason)


class UsageService:
    """Consommation de tous les comptes, pour les administrateurs : le seul service qui ne prend pas d'utilisateur.

    C'est à l'interface de n'y laisser entrer qu'un administrateur (AuthService.is_admin).
    """

    def __init__(self, database: Database, monthly_budget_usd: float = 0, daily_budget_usd: float = 0):
        self.database = database
        self.monthly_budget_usd = monthly_budget_usd
        self.daily_budget_usd = daily_budget_usd

    def get_overview(self, days: int | None = None, now: datetime | None = None) -> UsageOverview:
        """Renvoie ce que chaque compte a consommé et coûté, le plus coûteux en premier.

        Sans nombre de jours, tout l'historique est compté. Un compte supprimé y reste, sans adresse, avec
        ce qu'il avait consommé : ses totaux sont gardés par mois, donc un mois entamé compte en entier.
        """
        since = None if days is None else (now or datetime.now(UTC)) - timedelta(days=days)
        return self._overview(since, since)

    def get_budget(self, now: datetime | None = None) -> BudgetOverview:
        """Renvoie la dépense du mois en cours, à l'heure de Paris, et ce qu'elle sera à ce rythme en fin de mois.

        Tous les comptes y sont, ceux supprimés pendant le mois compris. Sans tarif connu pour un modèle, la
        dépense ne compte que le moteur de recherche (partial) : un plancher vaut mieux qu'aucun chiffre.
        """
        local = (now or datetime.now(UTC)).astimezone(ZoneInfo(LOCAL_TIMEZONE))
        start = local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        # Le 1er du mois suivant : 32 jours mènent toujours dans le mois d'après
        end = (start + timedelta(days=32)).replace(day=1)
        # Les totaux archivés se comparent par mois : c'est le mois de Paris qu'il leur faut, pas celui d'UTC
        overview = self._overview(start.astimezone(UTC), start)

        partial = overview.cost_usd is None
        spent = overview.search_cost_usd if partial else overview.cost_usd
        # Au moins un jour : une recherche à minuit et quart ne se projette pas sur un mois entier
        elapsed_days = max((local - start) / timedelta(days=1), 1.0)
        daily_average = spent / elapsed_days
        projected = round(daily_average * ((end - start) / timedelta(days=1)), COST_DECIMALS)
        budget = self.monthly_budget_usd
        today_spent = self.get_daily_spend(now)
        return BudgetOverview(
            month_start=start.astimezone(UTC),
            budget_usd=budget,
            runs=overview.runs,
            spent_usd=spent,
            partial=partial,
            guests_spent_usd=overview.guests_cost_usd,
            day_of_month=local.day,
            days_left=math.ceil((end - local) / timedelta(days=1)),
            daily_average_usd=round(daily_average, COST_DECIMALS),
            projected_usd=projected,
            spent_rate=round(spent / budget, 4) if budget else None,
            projected_rate=round(projected / budget, 4) if budget else None,
            over_budget=bool(budget) and spent > budget,
            projected_over_budget=bool(budget) and projected > budget,
            daily_budget_usd=self.daily_budget_usd,
            today_spent_usd=today_spent,
            daily_budget_reached=bool(self.daily_budget_usd) and today_spent >= self.daily_budget_usd,
        )

    def get_daily_spend(self, now: datetime | None = None) -> float:
        """Renvoie la dépense du jour en cours, à l'heure de Paris, tous comptes réunis.

        Les questions posées à l'assistant y comptent, comme dans le mois. Comme pour lui, un modèle sans
        tarif ne laisse que le coût du moteur de recherche : un plancher.
        Une recherche en cours n'y est pas encore, ni celles d'un compte supprimé dans la journée, dont il ne
        reste que des totaux par mois.
        """
        local = (now or datetime.now(UTC)).astimezone(ZoneInfo(LOCAL_TIMEZONE))
        start = local.replace(hour=0, minute=0, second=0, microsecond=0)
        with self.database.session() as session:
            rows = _consumption(session, start.astimezone(UTC))
        accounts = [
            _describe_account(user_id, None, DEFAULT_PLAN, deleted=False, rows=rows)
            for user_id, rows in _by_user(rows).items()
        ]
        cost = sum_costs(account.cost_usd for account in accounts)
        if cost is None:
            cost = sum(account.search_cost_usd for account in accounts)
        return round(cost, COST_DECIMALS)

    def daily_budget_reached(self, now: datetime | None = None) -> bool:
        """Dit si le budget du jour est atteint : plus de recherche avant demain, sauf pour le propriétaire."""
        return bool(self.daily_budget_usd) and self.get_daily_spend(now) >= self.daily_budget_usd

    def get_journeys(self, now: datetime | None = None) -> JourneyOverview:
        """Renvoie où en est chaque compte, et combien d'invités ont franchi chaque étape du parcours.

        C'est ce qui dit si l'application sert à d'autres que son propriétaire : un invité qui postule aux
        offres retenues et qui revient. Des nombres seulement : ni poste, ni offre, ni page d'un compte.
        """
        now = now or datetime.now(UTC)
        with self.database.session() as session:
            accounts = self._describe_accounts(session, now)
        accounts.sort(key=lambda account: (account.last_seen_at or account.created_at, account.user_id), reverse=True)

        # Un essai n'engage à rien : compté avec eux, il ferait croire que les utilisateurs abandonnent
        guests = [account for account in accounts if not account.is_owner and not account.is_trial]
        trials = [account for account in accounts if account.is_trial]
        return JourneyOverview(
            guests=len(guests),
            steps=_count_steps(guests),
            trials=len(trials),
            trial_steps=_count_steps(trials),
            accounts=accounts,
        )

    def get_journey(self, user_id: int, now: datetime | None = None) -> AccountDetail:
        """Renvoie la fiche d'un compte : sa chronologie, et les raisons qui écartent ses pages.

        Pour comprendre où un invité bute. Chaque ligne dit ce qu'il a fait et quand, jamais sur quoi : ni
        intitulé, ni lien, ni phrase de recherche ne sortent d'ici.
        """
        now = now or datetime.now(UTC)
        with self.database.session() as session:
            account = next((row for row in self._describe_accounts(session, now) if row.user_id == user_id), None)
            if account is None:
                raise NotFoundError("Ce compte n'existe pas.")
            events = [JourneyEvent(at=account.created_at, kind="account", label="Compte créé")]
            cv_date = CvTextRepository(session, user_id).get_updated_at()
            if cv_date is not None:
                events.append(JourneyEvent(at=cv_date, kind="cv", label="CV déposé"))
            events += [
                JourneyEvent(at=query.created_at, kind="query", label="Poste recherché ajouté")
                for query in QueryRepository(session, user_id).list_queries()
            ]
            events += [_describe_run(run) for run in SearchRunRepository(session, user_id).list_runs()]
            for job in JobRepository(session, user_id).list_all():
                events += _describe_job(job)
            events += [_describe_correction(row) for row in CorrectionRepository(session, user_id).list_all()]
            health = HealthRepository(session)
            events += [
                JourneyEvent(
                    at=error.created_at,
                    kind="error",
                    label="Panne du serveur" if error.status_code >= 500 else "Demande refusée",
                    detail=f"{error.method} {error.route or 'route inconnue'} · {error.error_type}",
                )
                for error in health.list_errors_of(user_id)
            ]
            events += [
                JourneyEvent(
                    at=error.created_at,
                    kind="error",
                    label="Erreur du navigateur",
                    detail=f"{error.error_type} sur l'écran {error.route or 'inconnu'}",
                )
                for error in health.list_client_errors_of(user_id)
            ]
            pages = PageEvaluationRepository(session, user_id).list_all()
            rejected = [page for page in pages if not page.kept]
            counts = dict.fromkeys(REJECTION_LABELS.values(), 0)
            for page in rejected:
                for label in _rejection_labels(page):
                    counts[label] += 1

        # Le plus récent en premier ; à la même seconde, l'ordre du parcours : le compte se crée avant le CV
        ranked = sorted(enumerate(events), key=lambda ranked: (ranked[1].at, ranked[0]), reverse=True)
        events = [event for _, event in ranked]
        rejections = [
            RejectionCount(label=label, count=count, rate=round(count / len(rejected), 4))
            for label, count in sorted(counts.items(), key=lambda item: -item[1])
            if count
        ]
        return AccountDetail(
            account=account,
            evaluated=len(pages),
            rejected=len(rejected),
            rejections=rejections,
            events=events[:MAX_JOURNEY_EVENTS],
        )

    def _describe_accounts(self, session, now: datetime) -> list[AccountJourney]:
        timezone = ZoneInfo(LOCAL_TIMEZONE)
        usage = UsageRepository(session)
        with_cv = usage.list_accounts_with_cv()
        queries = {row.user_id: row.queries for row in usage.count_queries()}
        jobs = {row.user_id: row for row in usage.count_jobs()}
        corrections = {row.user_id: row.corrections for row in usage.count_corrections()}
        active_days = {row.user_id: row.days for row in usage.count_active_days()}
        runs: dict[int, int] = {}
        for row in usage.summarize_runs():
            runs[row.user_id] = runs.get(row.user_id, 0) + row.runs

        accounts = []
        for user in UserRepository(session).list_users():
            # Une ligne sans adresse ni clé d'essai est un compte supprimé, sauf celle du propriétaire
            if user.email is None and user.trial_key is None and user.id != DEFAULT_USER_ID:
                continue
            counted = jobs.get(user.id)
            account = AccountJourney(
                user_id=user.id,
                email=user.email,
                is_owner=user.id == DEFAULT_USER_ID,
                is_trial=user.trial_key is not None,
                created_at=user.created_at,
                last_seen_at=user.last_seen_at,
                has_cv=user.id in with_cv,
                queries=queries.get(user.id, 0),
                runs=runs.get(user.id, 0),
                kept=counted.kept if counted else 0,
                opened=counted.opened if counted else 0,
                applied=counted.applied if counted else 0,
                interviews=counted.interviews if counted else 0,
                corrections=corrections.get(user.id, 0),
                returned=user.last_seen_at is not None
                and user.last_seen_at.astimezone(timezone).date() > user.created_at.astimezone(timezone).date(),
                active_days=active_days.get(user.id, 0),
                step=FIRST_STEP,
                idle_days=None if user.last_seen_at is None else max((now - user.last_seen_at).days, 0),
            )
            # La dernière étape franchie, dans l'ordre du parcours : c'est là que le compte s'est arrêté
            account.step = [label for label, has_reached in JOURNEY_STEPS.items() if has_reached(account)][-1]
            accounts.append(account)
        return accounts

    def list_unpriced_models(self, since: datetime | None = None) -> list[str]:
        """Renvoie les modèles qui ont servi depuis cette date, au tri ou à l'assistant, et dont le tarif manque.

        Leur coût vaut None partout, et le budget ne compte plus qu'eux en moins : c'est à corriger dans
        MODEL_PRICES_USD dès que FILTER_MODEL change.
        """
        with self.database.session() as session:
            rows = _consumption(session, since)
        used = {row.model for row in rows if row.input_tokens is not None}
        return sorted(model or "inconnu" for model in used if model not in MODEL_PRICES_USD)

    def _overview(self, since: datetime | None, archived_since: datetime | None) -> UsageOverview:
        with self.database.session() as session:
            rows = _consumption(session, since)
            archived_rows = UsageRepository(session).summarize_archived(archived_since)
            users = UserRepository(session).list_users()
            emails = {user.id: user.email for user in users}
            trial_ids = {user.id for user in users if user.trial_key is not None}

        accounts = [
            _describe_account(
                user_id,
                emails.get(user_id),
                TRIAL_PLAN if user_id in trial_ids else DEFAULT_PLAN,
                deleted=False,
                rows=rows,
            )
            for user_id, rows in _by_user(rows).items()
        ]
        accounts += [
            _describe_account(user_id, None, rows[0].plan, deleted=True, rows=rows)
            for user_id, rows in _by_user(archived_rows).items()
        ]
        # Un coût inconnu ne se classe pas : il passe après les autres
        accounts.sort(
            key=lambda account: (account.cost_usd is None, -(account.cost_usd or 0), account.user_id, account.deleted)
        )

        guests = [account for account in accounts if not account.is_owner]
        return UsageOverview(
            since=since,
            accounts=accounts,
            runs=sum(account.runs for account in accounts),
            kept_count=sum(account.kept_count for account in accounts),
            search_cost_usd=round(sum(account.search_cost_usd for account in accounts), COST_DECIMALS),
            model_cost_usd=sum_costs(account.model_cost_usd for account in accounts),
            cost_usd=sum_costs(account.cost_usd for account in accounts),
            guests_cost_usd=sum_costs(account.cost_usd for account in guests),
        )


def _consumption(session, since: datetime | None) -> list:
    """Renvoie ce que chaque compte a consommé, par modèle : ses recherches, puis ses questions à l'assistant."""
    usage = UsageRepository(session)
    return usage.summarize_runs(since) + usage.summarize_assistant(since)


def _count_steps(accounts: list[AccountJourney]) -> list[JourneyStep]:
    steps = []
    for label, has_reached in JOURNEY_STEPS.items():
        count = sum(has_reached(account) for account in accounts)
        steps.append(JourneyStep(label=label, count=count, rate=round(count / len(accounts), 4) if accounts else None))
    return steps


def _by_user(rows: list) -> dict[int, list]:
    rows_by_user: dict[int, list] = {}
    for row in rows:
        rows_by_user.setdefault(row.user_id, []).append(row)
    return rows_by_user


def _describe_account(user_id: int, email: str | None, plan: str, deleted: bool, rows: list) -> AccountUsage:
    def total(name: str) -> int:
        return sum(getattr(row, name) or 0 for row in rows)

    search_cost = search_cost_usd(total("search_calls"))
    # Un coût par modèle, puisque chacun a son tarif ; une ligne sans jetons n'a rien coûté au modèle
    model_cost = sum_costs(
        model_cost_usd(row.model, row.input_tokens, row.output_tokens, row.cache_read_tokens, row.cache_write_tokens)
        for row in rows
        if row.input_tokens is not None
    )
    return AccountUsage(
        user_id=user_id,
        email=email,
        is_owner=user_id == DEFAULT_USER_ID,
        deleted=deleted,
        plan=plan,
        runs=total("runs"),
        found_count=total("found_count"),
        kept_count=total("kept_count"),
        search_calls=total("search_calls"),
        input_tokens=total("input_tokens"),
        output_tokens=total("output_tokens"),
        search_cost_usd=search_cost,
        model_cost_usd=model_cost,
        cost_usd=None if model_cost is None else round(search_cost + model_cost, COST_DECIMALS),
        last_search_at=max((row.last_search_at for row in rows if row.last_search_at), default=None),
    )
