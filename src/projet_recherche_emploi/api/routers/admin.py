from typing import Annotated

from fastapi import APIRouter, Query

from projet_recherche_emploi.api.security import AdminId, Services
from projet_recherche_emploi.schemas import AlertTest, BudgetOverview, HealthOverview, JourneyOverview, UsageOverview

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


@router.get("/admin/health")
def get_health(
    admin_id: AdminId,
    services: Services,
    days: Annotated[int | None, Query(ge=1, le=MAX_USAGE_DAYS)] = None,
) -> HealthOverview:
    """Santé de l'instance : recherches échouées ou interrompues et erreurs de l'API, sur tous les comptes.

    Réservé aux administrateurs. « days » limite le calcul aux derniers jours. Seuls des nombres, des routes
    et des types d'erreur sortent d'ici : ni message d'erreur, ni compte, ni contenu.
    """
    return services.health.get_overview(days)


@router.post("/admin/alerts/test")
def send_test_alert(admin_id: AdminId, services: Services) -> AlertTest:
    """Envoie une alerte d'essai, pour vérifier qu'elles arrivent. « sent » est faux si rien n'est parti.

    Réservé aux administrateurs. Le message ne porte rien de l'appelant.
    """
    return AlertTest(sent=services.health.send_test_alert())


@router.get("/admin/budget")
def get_budget(admin_id: AdminId, services: Services) -> BudgetOverview:
    """Dépense du mois en cours, tous comptes réunis, sa projection en fin de mois et le budget de l'instance.

    Réservé aux administrateurs. Seuls des montants en sortent.
    """
    return services.usage.get_budget()


@router.get("/admin/journeys")
def get_journeys(admin_id: AdminId, services: Services) -> JourneyOverview:
    """Parcours des invités : combien déposent un CV, lancent une recherche, postulent et reviennent.

    Réservé aux administrateurs. Pour chaque compte, son adresse et des nombres : aucun poste, aucune offre.
    """
    return services.usage.get_journeys()
