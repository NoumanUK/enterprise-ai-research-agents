from typing import TypedDict, List, Dict, Any, Optional


class ResearchState(TypedDict):
    # User input
    query: str

    # Step 1 output (planner)
    tasks: List[str]

    # Step 2 output (researcher)
    findings: List[Dict[str, Any]]

    # Step 3 output (fact checker)
    verified_findings: List[Dict[str, Any]]

    # Step 4 output (reporter)
    report: str

    # Optional metadata (important for MCP later)
    metadata: Optional[Dict[str, Any]]