"""Graph de l'assistant : RetrievePassages → GenerateAnswer, puis une suite selon ce que le modèle a rendu.

Une réponse garde ses sources (CiteSources), une question hors sujet est refusée (DeclineQuestion), et une
question sur l'application restée sans réponse est renvoyée vers l'exploitant (ReferToOperator).
"""

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from jobgrep.assistant.nodes import AssistantNodes
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
    builder.add_conditional_edges(
        "GenerateAnswer",
        nodes.route_by_outcome,
        {"answered": "CiteSources", "off_topic": "DeclineQuestion", "unknown": "ReferToOperator"},
    )
    for last in ("CiteSources", "DeclineQuestion", "ReferToOperator"):
        builder.add_edge(last, END)

    return builder.compile()
