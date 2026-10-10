"""Graph de l'assistant : RetrievePassages → GenerateAnswer, puis une suite selon ce que le modèle a rendu.

S'il demande à connaître le compte de la personne, ConsultAccount exécute ses outils et lui rend la main.
Sinon, une réponse garde ses sources (CiteSources), une question hors sujet est refusée (DeclineQuestion),
et une question sur l'application restée sans réponse est renvoyée vers l'exploitant (ReferToOperator).
"""

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode

from jobgrep.assistant.nodes import CONSULT, AssistantNodes
from jobgrep.assistant.state import AssistantState


def build_graph(nodes: AssistantNodes) -> CompiledStateGraph:
    builder = StateGraph(AssistantState)

    builder.add_node("RetrievePassages", nodes.retrieve_passages)
    builder.add_node("GenerateAnswer", nodes.generate_answer)
    builder.add_node("CiteSources", nodes.cite_sources)
    builder.add_node("DeclineQuestion", nodes.decline_question)
    builder.add_node("ReferToOperator", nodes.refer_to_operator)

    builder.add_edge(START, "RetrievePassages")
    builder.add_edge("RetrievePassages", "GenerateAnswer")
    routes = {"answered": "CiteSources", "off_topic": "DeclineQuestion", "unknown": "ReferToOperator"}
    if nodes.tools:
        # Le nœud d'outils de LangGraph : il met dans chaque appel le compte de l'appelant, pris dans l'état
        builder.add_node("ConsultAccount", ToolNode(nodes.tools, messages_key="transcript"))
        builder.add_edge("ConsultAccount", "GenerateAnswer")
        routes[CONSULT] = "ConsultAccount"
    builder.add_conditional_edges("GenerateAnswer", nodes.route_after_answer, routes)
    for last in ("CiteSources", "DeclineQuestion", "ReferToOperator"):
        builder.add_edge(last, END)

    return builder.compile()
