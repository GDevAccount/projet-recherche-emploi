from sqlalchemy import Row, case, func, insert, literal, select
from sqlalchemy.orm import Session

from jobgrep.config import DEFAULT_PLAN, TRIAL_PLAN
from jobgrep.data.models import AccountEvent, User

COLUMNS = ["day", "kind", "plan", "detail"]


class AccountEventRepository:
    """Moments du parcours de tous les comptes, sans utilisateur : il ne rend que des nombres par jour.

    Un compte n'y est lu que pour sa formule, à l'écriture. Ne rien y ajouter qui le désigne.
    """

    def __init__(self, session: Session):
        self.session = session

    def record(self, day: str, kind: str, plan: str, detail: str | None = None) -> None:
        """Note un moment du parcours, ce jour-là (« AAAA-MM-JJ »), pour un compte de cette formule."""
        self.session.execute(insert(AccountEvent).values(day=day, kind=kind, plan=plan, detail=detail))

    def record_for(self, user_id: int, day: str, kind: str, detail: str | None = None) -> bool:
        """Note un moment du parcours de ce compte, sous la formule qu'il a, et renvoie faux s'il n'existe pas.

        La formule est lue dans la requête qui écrit : la transaction commence ainsi par une écriture.
        """
        account_plan = case((User.trial_key.is_not(None), TRIAL_PLAN), else_=DEFAULT_PLAN)
        row = select(literal(day), literal(kind), account_plan, literal(detail)).where(User.id == user_id)
        return self.session.execute(insert(AccountEvent).from_select(COLUMNS, row)).rowcount == 1

    def summarize(self, since_day: str) -> list[Row]:
        """Renvoie, depuis ce jour, le nombre de moments par jour, par genre, par formule et par précision."""
        statement = (
            select(
                AccountEvent.day,
                AccountEvent.kind,
                AccountEvent.plan,
                AccountEvent.detail,
                func.count().label("count"),
            )
            .where(AccountEvent.day >= since_day)
            .group_by(AccountEvent.day, AccountEvent.kind, AccountEvent.plan, AccountEvent.detail)
            .order_by(AccountEvent.day)
        )
        return list(self.session.execute(statement))

    def get_first_day(self) -> str | None:
        """Renvoie le premier jour noté, ou None si rien ne l'a encore été."""
        return self.session.scalar(select(func.min(AccountEvent.day)))
