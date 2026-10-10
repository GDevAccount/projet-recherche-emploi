"""Outils que le modèle peut appeler pour répondre : ce qu'il sait de la personne qui lui écrit.

Chaque outil lit le compte de l'appelant, et lui seul : l'identifiant du compte vient de l'état du graph,
où le serveur l'a mis. Le modèle ne le voit pas dans la description de l'outil, et ne peut pas en donner un autre.
"""

from typing import Annotated

from langchain_core.tools import BaseTool, tool
from langgraph.prebuilt import InjectedState

from jobgrep.assistant.ports import AccountReader

ACCOUNT_STATUS_TOOL = "etat_du_compte"
OFFERS_TOOL = "mes_offres"
REJECTIONS_TOOL = "mes_pages_ecartees"
QUERIES_TOOL = "mes_postes_recherches"
CV_TOOL = "mon_cv"

UserId = Annotated[int, InjectedState("user_id")]


def build_account_tools(account: AccountReader) -> list[BaseTool]:
    """Renvoie les outils qui lisent le compte de l'appelant, branchés sur ce lecteur."""

    @tool(ACCOUNT_STATUS_TOOL)
    def account_status(user_id: UserId) -> str:
        """Rend la situation du compte de la personne qui écrit, en nombres et en dates : si son CV est
        déposé, combien de postes elle recherche, si elle peut lancer une recherche et combien il lui en
        reste, si une recherche est en cours, ce qu'a donné la dernière, combien d'offres elle a à chaque
        étape et combien de pages ont été écartées pour chaque raison.
        """
        return account.describe(user_id)

    @tool(OFFERS_TOOL)
    def offers(user_id: UserId) -> str:
        """Rend les offres retenues pour la personne qui écrit, les plus récentes en premier : l'intitulé
        de chacune, le site où elle a été trouvée, son contrat, son lieu, l'étape de la candidature avec
        ses dates, et la raison pour laquelle elle a été retenue. À appeler quand la question porte sur
        une ou plusieurs de ses offres : lesquelles, où elles en sont, pourquoi elles ont été retenues.
        """
        return account.describe_offers(user_id)

    @tool(REJECTIONS_TOOL)
    def rejections(user_id: UserId) -> str:
        """Rend les pages écartées pour la personne qui écrit, les plus récentes en premier : l'intitulé
        de chacune, le site où elle a été trouvée, le motif du rejet et son explication. À appeler quand
        la question porte sur une ou plusieurs pages écartées : lesquelles, et pourquoi.
        """
        return account.describe_rejections(user_id)

    @tool(QUERIES_TOOL)
    def queries(user_id: UserId) -> str:
        """Rend les postes que recherche la personne qui écrit : pour chacun, le métier et les spécialités
        qu'elle a saisis, le contrat et le lieu. À appeler quand la question porte sur ses postes
        recherchés, ou pour lui dire quoi y changer quand trop de pages sont écartées.
        """
        return account.describe_queries(user_id)

    @tool(CV_TOOL)
    def cv(user_id: UserId) -> str:
        """Rend le texte du CV de la personne qui écrit, sans ses coordonnées. À appeler seulement quand
        la réponse a besoin de ce que dit le CV : pour expliquer pourquoi des pages sont écartées pour
        leurs compétences ou leur niveau, ou pour dire ce que le CV contient. Jamais pour une autre question.
        """
        return account.describe_cv(user_id)

    return [account_status, offers, rejections, queries, cv]
