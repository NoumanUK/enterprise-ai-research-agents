from app.models.state import ResearchState


def researcher_node(state: ResearchState) -> ResearchState:
    """
    CONTRACT

    Input:
        state["tasks"]

    Output:
        state["findings"]

    Responsibility:
        Execute research tasks and gather evidence.
    """

    findings = []

    for task in state["tasks"]:
        findings.append({
            "task": task,
            "finding": f"Research result for: {task}",
            "sources": []
        })

    state["findings"] = findings

    return state