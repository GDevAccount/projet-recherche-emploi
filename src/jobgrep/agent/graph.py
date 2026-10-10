"""Graph de recherche : searchJobs → FilterDuplicates → FilterJobs → InsertJobs."""

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from jobgrep.agent.nodes import SearchNodes
from jobgrep.agent.state import JobSearchState


def build_graph(nodes: SearchNodes) -> CompiledStateGraph:
    builder = StateGraph(JobSearchState)

    builder.add_node("searchJobs", nodes.search_jobs)
    builder.add_node("FilterDuplicates", nodes.filter_duplicates)
    builder.add_node("FilterJobs", nodes.filter_jobs)
    builder.add_node("InsertJobs", nodes.insert_jobs)

    builder.add_edge(START, "searchJobs")
    builder.add_edge("searchJobs", "FilterDuplicates")
    builder.add_edge("FilterDuplicates", "FilterJobs")
    builder.add_edge("FilterJobs", "InsertJobs")
    builder.add_edge("InsertJobs", END)

    return builder.compile()
