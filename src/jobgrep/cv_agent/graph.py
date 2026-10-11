"""Graph du dépôt d'un CV : ReadCv → AnonymizeCv → SaveCv, puis ExtractProfile → SaveQueries pour ses postes."""

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from jobgrep.cv_agent.nodes import CvDepositNodes, route_after_extract, route_after_save
from jobgrep.cv_agent.state import CvDepositState


def build_cv_graph(nodes: CvDepositNodes) -> CompiledStateGraph:
    builder = StateGraph(CvDepositState)

    builder.add_node("ReadCv", nodes.read_cv)
    builder.add_node("AnonymizeCv", nodes.anonymize_cv)
    builder.add_node("SaveCv", nodes.save_cv)
    builder.add_node("ExtractProfile", nodes.extract_profile)
    builder.add_node("SaveQueries", nodes.save_queries)

    builder.add_edge(START, "ReadCv")
    builder.add_edge("ReadCv", "AnonymizeCv")
    builder.add_edge("AnonymizeCv", "SaveCv")
    builder.add_conditional_edges("SaveCv", route_after_save, {"extract": "ExtractProfile", "stop": END})
    builder.add_conditional_edges("ExtractProfile", route_after_extract, {"save": "SaveQueries", "stop": END})
    builder.add_edge("SaveQueries", END)

    return builder.compile()
