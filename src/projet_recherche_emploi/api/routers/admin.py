from typing import Annotated

from fastapi import APIRouter, Query

from projet_recherche_emploi.api.security import AdminId, Services
from projet_recherche_emploi.schemas import UsageOverview

router = APIRouter(tags=["administration"])

# Au-delà, autant tout compter : aucune donnée n'est aussi ancienne
MAX_USAGE_DAYS = 3650


@router.get("/admin/usage")
def get_usage(
    admin_id: AdminId,
    services: Services,
    days: Annotated[int | None, Query(ge=1, le=MAX_USAGE_DAYS)] = None,
) -> UsageOverview:
    """Consommation et coût de chaque compte, le plus coûteux en premier. Réservé aux administrateurs.

    « days » limite le calcul aux derniers jours ; sans lui, tout l'historique est compté. Seuls des nombres
    sortent d'ici : aucune page ni recherche d'un autre compte.
    """
    return services.usage.get_overview(days)
