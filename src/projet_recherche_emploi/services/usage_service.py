import math
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from projet_recherche_emploi.config import DEFAULT_PLAN, DEFAULT_USER_ID, LOCAL_TIMEZONE, MODEL_PRICES_USD
from projet_recherche_emploi.data.database import Database
from projet_recherche_emploi.data.repositories.usage_repository import UsageRepository
from projet_recherche_emploi.data.repositories.user_repository import UserRepository
from projet_recherche_emploi.schemas import AccountUsage, BudgetOverview, UsageOverview
from projet_recherche_emploi.services.search_costs import (
    COST_DECIMALS,
    model_cost_usd,
    search_cost_usd,
    sum_costs,
)


class UsageService:
    """Consommation de tous les comptes, pour les administrateurs : le seul service qui ne prend pas d'utilisateur.

    C'est à l'interface de n'y laisser entrer qu'un administrateur (AuthService.is_admin).
    """

    def __init__(self, database: Database, monthly_budget_usd: float = 0):
        self.database = database
        self.monthly_budget_usd = monthly_budget_usd

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
        )

    def list_unpriced_models(self, since: datetime | None = None) -> list[str]:
        """Renvoie les modèles qui ont évalué des pages depuis cette date et dont le tarif manque.

        Leur coût vaut None partout, et le budget ne compte plus qu'eux en moins : c'est à corriger dans
        MODEL_PRICES_USD dès que FILTER_MODEL change.
        """
        with self.database.session() as session:
            rows = UsageRepository(session).summarize_runs(since)
        used = {row.model for row in rows if row.input_tokens is not None}
        return sorted(model or "inconnu" for model in used if model not in MODEL_PRICES_USD)

    def _overview(self, since: datetime | None, archived_since: datetime | None) -> UsageOverview:
        with self.database.session() as session:
            rows = UsageRepository(session).summarize_runs(since)
            archived_rows = UsageRepository(session).summarize_archived(archived_since)
            emails = {user.id: user.email for user in UserRepository(session).list_users()}

        accounts = [
            _describe_account(user_id, emails.get(user_id), DEFAULT_PLAN, deleted=False, rows=rows)
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
