from app.models.state import ResearchState


def reporter_node(state: ResearchState) -> ResearchState:
    """
    CONTRACT

    Input:
        state["verified_findings"]

    Output:
        state["report"]

    Responsibility:
        Generate final report.
    """

    report = "# Research Report\n\n"

    for finding in state["verified_findings"]:
        report += f"- {finding['finding']}\n"

    state["report"] = report

    return state