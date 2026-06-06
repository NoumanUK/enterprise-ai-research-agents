from app.models.state import ResearchState


def planner_node(state: ResearchState) -> ResearchState:
    """
    CONTRACT

    Input:
        state["query"]

    Output:
        state["tasks"]

    Responsibility:
        Convert user research request into
        actionable research tasks.
    """

    query = state["query"]

    tasks = [
        "Define MCP",
        "Find companies using MCP",
        "Find enterprise adoption examples",
        "Find criticisms",
        "Find future trends"
    ]

    state["tasks"] = tasks

    return state