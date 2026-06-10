from typing import TypedDict, List, Dict, Any, Optional


class ResearchState(TypedDict, total=False):
    # ── Input ──────────────────────────────────────────────
    query: str

    # ── planner_node ───────────────────────────────────────
    tasks: List[Dict[str, Any]]       # list of TaskDicts (task, intent, query, priority)
    research_plan: str                # human-readable plan summary

    # ── researcher_node ────────────────────────────────────
    findings: List[Dict[str, Any]]    # per-task synthesis + evidence + sources

    # ── evidence_ranker_node ───────────────────────────────
    ranked_evidence: List[Dict[str, Any]]   # scored, filtered evidence chunks

    # ── claim_extractor_node ───────────────────────────────
    claims: List[Dict[str, Any]]      # atomic verifiable claims per task

    # ── fact_checker_node ──────────────────────────────────
    verified_claims: List[Dict[str, Any]]   # verified claims with status/confidence

    # ── reporter_node ──────────────────────────────────────
    report: str
    report_metadata: Dict[str, Any]

    # ── legacy / optional ──────────────────────────────────
    verified_findings: List[Dict[str, Any]]  # kept for backward compat
    metadata: Optional[Dict[str, Any]]