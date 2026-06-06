from langgraph.graph import StateGraph, END

from app.models.state import ResearchState

from app.agents.planner import planner_node
from app.agents.researcher import researcher_node
from app.agents.fact_checker import fact_checker_node
from app.agents.reporter import reporter_node


def build_graph():
    graph = StateGraph(ResearchState)

    # Nodes
    graph.add_node("planner", planner_node)
    graph.add_node("researcher", researcher_node)
    graph.add_node("fact_checker", fact_checker_node)
    graph.add_node("reporter", reporter_node)

    # Flow (linear for v1)
    graph.set_entry_point("planner")

    graph.add_edge("planner", "researcher")
    graph.add_edge("researcher", "fact_checker")
    graph.add_edge("fact_checker", "reporter")
    graph.add_edge("reporter", END)

    return graph.compile()