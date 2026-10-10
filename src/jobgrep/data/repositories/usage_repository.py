from datetime import datetime

from sqlalchemy import Row, func, insert, literal, null, select
from sqlalchemy.orm import Session

from jobgrep.data.models import (
    ActivityDay,
    ArchivedUsage,
    AssistantMessage,
    Correction,
    CvText,
    Job,
    SearchQuery,
    SearchRun,
    UtcDateTime,
)

# Compteurs d'un lancement additionnés par compte
SUMMED_COLUMNS = (
    "found_count",
    "kept_count",
    "search_calls",
    "input_tokens",
    "output_tokens",
    "cache_read_tokens",
    "cache_write_tokens",
)
# Jetons d'une question posée à l'assistant, parmi les compteurs ci-dessus
ASSISTANT_TOKEN_COLUMNS = ("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens")
# Format du mois d'une ligne archivée : il se compare comme du texte
MONTH_FORMAT = "%Y-%m"


class UsageRepository:
    """Consommation de tous les comptes, pour les administrateurs : sans utilisateur, comme UserRepository.

    Il ne rend que des nombres additionnés par compte, jamais une ligne d'un utilisateur : ni page, ni titre,
    ni lien. Ne rien y ajouter qui en sorte.
    """

    def __init__(self, session: Session):
        self.session = session

    def summarize_runs(self, since: datetime | None = None) -> list[Row]:
        """Renvoie, par compte et par modèle, le nombre de lancements suivis et la somme de leurs compteurs.

        Le modèle sépare les lignes parce que le tarif en dépend. Sans date, tout l'historique est compté.
        """
        sums = [func.sum(getattr(SearchRun, column)).label(column) for column in SUMMED_COLUMNS]
        statement = (
            select(
                SearchRun.user_id,
                SearchRun.model,
                func.count().label("runs"),
                func.max(SearchRun.created_at).label("last_search_at"),
                *sums,
            )
            # Un lancement d'avant le suivi n'a que sa date
            .where(SearchRun.status.is_not(None))
            .group_by(SearchRun.user_id, SearchRun.model)
            .order_by(SearchRun.user_id)
        )
        if since is not None:
            statement = statement.where(SearchRun.created_at >= since)
        return list(self.session.execute(statement))

    def archive_account(self, user_id: int, plan: str, deleted_at: datetime) -> int:
        """Additionne par mois ce qu'ont consommé les lancements d'un compte, avant leur effacement.

        Renvoie le nombre de lignes écrites. Rien n'y désigne une personne : ni adresse, ni date de recherche.
        """
        month = func.strftime(MONTH_FORMAT, SearchRun.created_at)
        sums = [func.sum(getattr(SearchRun, column)) for column in SUMMED_COLUMNS]
        deletion = literal(deleted_at, UtcDateTime())
        totals = (
            select(literal(user_id), literal(plan), month, SearchRun.model, func.count(), *sums, deletion)
            .where(SearchRun.user_id == user_id, SearchRun.status.is_not(None))
            .group_by(month, SearchRun.model)
        )
        columns = ["account_id", "plan", "month", "model", "runs", *SUMMED_COLUMNS, "deleted_at"]
        return self.session.execute(insert(ArchivedUsage).from_select(columns, totals)).rowcount

    def summarize_assistant(self, since: datetime | None = None) -> list[Row]:
        """Renvoie, par compte et par modèle, ce qu'ont consommé les questions posées à l'assistant.

        Les lignes ont la forme de celles de summarize_runs, sans lancement : celles du modèle qui répond,
        puis celles du modèle qui situe la question, chacun ayant son tarif.
        """
        answers = self._assistant_totals(
            AssistantMessage.model,
            {column: func.sum(getattr(AssistantMessage, column)) for column in ASSISTANT_TOKEN_COLUMNS},
            since,
        )
        embeddings = self._assistant_totals(
            AssistantMessage.embedding_model, {"input_tokens": func.sum(AssistantMessage.embedding_tokens)}, since
        )
        return answers + embeddings

    def _assistant_totals(self, model, token_sums: dict, since: datetime | None) -> list[Row]:
        counters = [token_sums.get(column, literal(0)).label(column) for column in SUMMED_COLUMNS]
        statement = (
            select(
                AssistantMessage.user_id,
                model.label("model"),
                literal(0).label("runs"),
                null().label("last_search_at"),
                *counters,
            )
            .where(model.is_not(None))
            .group_by(AssistantMessage.user_id, model)
            .order_by(AssistantMessage.user_id)
        )
        if since is not None:
            statement = statement.where(AssistantMessage.created_at >= since)
        return list(self.session.execute(statement))

    def archive_assistant(self, user_id: int, plan: str, deleted_at: datetime) -> int:
        """Additionne par mois ce qu'ont consommé les questions d'un compte à l'assistant, avant leur effacement.

        Renvoie le nombre de lignes écrites : des jetons par modèle, sans lancement, ni texte, ni date de question.
        """
        totals: dict[tuple[str, str], dict[str, int]] = {}

        def add(month: str, model: str | None, tokens: dict[str, int | None]) -> None:
            if model is None or tokens["input_tokens"] is None:
                return
            total = totals.setdefault((month, model), dict.fromkeys(ASSISTANT_TOKEN_COLUMNS, 0))
            for column, value in tokens.items():
                total[column] += value or 0

        for message in self.session.scalars(select(AssistantMessage).where(AssistantMessage.user_id == user_id)):
            month = message.created_at.strftime(MONTH_FORMAT)
            add(month, message.model, {column: getattr(message, column) for column in ASSISTANT_TOKEN_COLUMNS})
            add(month, message.embedding_model, {"input_tokens": message.embedding_tokens})

        counters = dict.fromkeys(("runs", "found_count", "kept_count", "search_calls"), 0)
        rows = [
            {"account_id": user_id, "plan": plan, "month": month, "model": model, "deleted_at": deleted_at}
            | counters
            | tokens
            for (month, model), tokens in totals.items()
        ]
        if rows:
            self.session.execute(insert(ArchivedUsage), rows)
        return len(rows)

    def summarize_archived(self, since: datetime | None = None) -> list[Row]:
        """Renvoie, par compte supprimé et par modèle, ce qui a été gardé de sa consommation.

        Les lignes ont la forme de celles de summarize_runs. Un mois entamé à la date donnée est compté en entier.
        """
        sums = [func.sum(getattr(ArchivedUsage, column)).label(column) for column in ("runs", *SUMMED_COLUMNS)]
        statement = (
            select(
                ArchivedUsage.account_id.label("user_id"),
                ArchivedUsage.model,
                func.max(ArchivedUsage.plan).label("plan"),
                null().label("last_search_at"),
                *sums,
            )
            .group_by(ArchivedUsage.account_id, ArchivedUsage.model)
            .order_by(ArchivedUsage.account_id)
        )
        if since is not None:
            statement = statement.where(ArchivedUsage.month >= since.strftime(MONTH_FORMAT))
        return list(self.session.execute(statement))

    def list_accounts_with_cv(self) -> set[int]:
        """Renvoie les comptes qui ont un CV en place."""
        return set(self.session.scalars(select(CvText.user_id)))

    def count_queries(self) -> list[Row]:
        """Renvoie, par compte, le nombre de postes recherchés enregistrés."""
        statement = select(SearchQuery.user_id, func.count().label("queries")).group_by(SearchQuery.user_id)
        return list(self.session.execute(statement))

    def count_jobs(self) -> list[Row]:
        """Renvoie, par compte, le nombre d'offres retenues, supprimées comprises, de candidatures et d'entretiens."""
        statement = select(
            Job.user_id,
            func.count().label("kept"),
            # count ne compte que les dates renseignées
            func.count(Job.opened_at).label("opened"),
            func.count(Job.applied_at).label("applied"),
            func.count(Job.interview_at).label("interviews"),
        ).group_by(Job.user_id)
        return list(self.session.execute(statement))

    def count_corrections(self) -> list[Row]:
        """Renvoie, par compte, le nombre de corrections du tri."""
        statement = select(Correction.user_id, func.count().label("corrections")).group_by(Correction.user_id)
        return list(self.session.execute(statement))

    def count_active_days(self) -> list[Row]:
        """Renvoie, par compte, le nombre de jours où il s'est servi de l'application."""
        statement = select(ActivityDay.user_id, func.count().label("days")).group_by(ActivityDay.user_id)
        return list(self.session.execute(statement))
