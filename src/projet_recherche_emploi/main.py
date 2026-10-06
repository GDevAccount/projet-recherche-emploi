
import logging
from pathlib import Path

from langgraph.graph import END, START, StateGraph

from projet_recherche_emploi.node import filter_jobs, insert_jobs, search_jobs
from projet_recherche_emploi.state import JobSearchState

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")


def build_graph():
    builder = StateGraph(JobSearchState)

    builder.add_node("searchJobs", search_jobs)
    builder.add_node("FilterJobs", filter_jobs)
    builder.add_node("InsertJobs", insert_jobs)

    builder.add_edge(START, "searchJobs")
    builder.add_edge("searchJobs", "FilterJobs")
    builder.add_edge("FilterJobs", "InsertJobs")
    builder.add_edge("InsertJobs", END)

    return builder.compile()


app = build_graph()
app.get_graph().draw_mermaid_png(output_file_path="graph.png")