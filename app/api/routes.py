from fastapi import APIRouter
from pydantic import BaseModel

from app.workflows.research_graph import build_graph

router = APIRouter()


class ResearchRequest(BaseModel):
    query: str


@router.post("/research")
def research(request: ResearchRequest):
    graph = build_graph()

    initial_state = {
        "query": request.query,
        "tasks": [],
        "findings": [],
        "claims": [],
        "verified_claims": [],
        "verified_findings": [],
        "ranked_evidence": [],
        "report": "",
        "metadata": {}
    }

    result = graph.invoke(initial_state)

    return {
        "module": "enterprise_ai_research_agents",
        "query": request.query,
        "research_plan": result.get("research_plan", ""),
        "tasks": result.get("tasks", []),
        "findings": result.get("findings", []),
        "claims": result.get("claims", []),
        "verified_claims": result.get("verified_claims", []),
        "report": result.get("report", "")
    }