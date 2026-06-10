from langgraph.graph import StateGraph, END

from app.models.state import ResearchState

from app.agents.planner import planner_node
from app.agents.researcher import researcher_node
from app.agents.fact_checker import fact_checker_node
from app.agents.reporter import reporter_node
from app.agents.claim_extractor import claim_extractor_node
from app.agents.evidence_ranker import evidence_ranker_node


def build_graph():
    graph = StateGraph(ResearchState)

    # Nodes
    graph.add_node("planner", planner_node)
    graph.add_node("researcher", researcher_node)
    graph.add_node("claim_extractor", claim_extractor_node)
    graph.add_node("fact_checker", fact_checker_node)
    graph.add_node("reporter", reporter_node)
    graph.add_node("evidence_ranker", evidence_ranker_node)

    # Flow (linear for v1)
    graph.set_entry_point("planner")

    graph.add_edge("planner", "researcher")
    graph.add_edge("researcher", "evidence_ranker")
    graph.add_edge("evidence_ranker", "claim_extractor")
    graph.add_edge("claim_extractor", "fact_checker")
    graph.add_edge("fact_checker", "reporter")
    graph.add_edge("reporter", END)

    return graph.compile()