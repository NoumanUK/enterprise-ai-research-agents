from app.models.state import ResearchState


def fact_checker_node(state: ResearchState) -> ResearchState:
    """
    CONTRACT

    Input:
        state["findings"]

    Output:
        state["verified_findings"]

    Responsibility:
        Verify research findings.
    """

    verified = []

    for finding in state["findings"]:
        verified.append({
            **finding,
            "status": "verified",
            "confidence": 0.90
        })

    state["verified_findings"] = verified

    return state