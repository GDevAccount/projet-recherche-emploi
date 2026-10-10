from typing import Annotated

from fastapi import APIRouter, Query

from jobgrep.api.security import AdminId, Services
from jobgrep.schemas import (
    AccountDetail,
    AlertTest,
    AssistantOverview,
    BudgetOverview,
    HealthOverview,
    JourneyOverview,
    UsageOverview,
)

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


@router.get("/admin/journeys/{user_id}")
def get_journey(user_id: int, admin_id: AdminId, services: Services) -> AccountDetail:
    """Fiche d'un compte : la chronologie de ce qu'il a fait, et les raisons qui écartent ses pages.

    Réservé aux administrateurs. Des dates, des nombres et des motifs : ni intitulé, ni lien, ni recherche.
    """
    return services.usage.get_journey(user_id)


@router.get("/admin/assistant")
def get_assistant_overview(
    admin_id: AdminId,
    services: Services,
    days: Annotated[int | None, Query(ge=1, le=MAX_USAGE_DAYS)] = None,
) -> AssistantOverview:
    """Usage de l'assistant sur tous les comptes, et les dernières questions qui lui ont été posées.

    Réservé aux administrateurs. Le texte des questions et des réponses en sort, jamais le compte qui les a posées.
    """
    return services.assistant.get_overview(days)
