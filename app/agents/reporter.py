"""
Reporter Node — Research Pipeline v2
======================================
Fixes:
  1. Source diversity enforcement — no URL used more than twice
  2. One section per task — no collapsing or dropping tasks
  3. NOT_FOUND claims explicitly surfaced in Risks section
  4. Honest reliability labelling (not "100% verified")

State keys read:
  - state["verified_claims"]   (from fact_checker_node)
  - state["research_plan"]     (from planner_node)
  - state["query"]

State keys written:
  - state["report"]
  - state["report_metadata"]
"""

from typing import Dict, List
from app.models.state import ResearchState
from app.services.llm_service import LLMService

llm = LLMService()

MIN_RELIABILITY_SCORE = 0.20
MIN_CLAIM_CONFIDENCE  = 0.25
INCLUDE_STATUSES      = {"SUPPORTED", "PARTIAL"}
MAX_USES_PER_SOURCE   = 2     # a single URL may not dominate the report


# ------------------------------------------------------------------
# 1. PARTITION CLAIMS
# ------------------------------------------------------------------

def _partition_claims(group: Dict):
    strong, weak = [], []
    for c in group.get("claims", []):
        if c["status"] in INCLUDE_STATUSES and c["confidence"] >= MIN_CLAIM_CONFIDENCE:
            strong.append(c)
        else:
            weak.append(c)
    return strong, weak


# ------------------------------------------------------------------
# 2. BUILD PER-TASK CONTEXT BLOCK
#    Includes: verified claims with source, weak/not-found claims,
#    and which URLs had real article text vs just snippets
# ------------------------------------------------------------------

def _format_claims_with_sources(claims: List[Dict], source_usage: Dict[str, int]) -> str:
    """
    Format claims and track how many times each source is used.
    Flags over-used sources so the LLM knows to diversify.
    """
    lines = []
    for c in claims:
        url    = c.get("source_url", "")
        conf   = int(c["confidence"] * 100)
        status = c["status"]
        usage  = source_usage.get(url, 0)

        overused_flag = " [OVERUSED — find alternative citation]" if usage >= MAX_USES_PER_SOURCE else ""
        source_usage[url] = usage + 1

        tag = "✓" if status == "SUPPORTED" else "~"
        lines.append(
            f"  {tag} [{conf}% confidence] {c['claim']}\n"
            f"      Source: {url}{overused_flag}\n"
            f"      Reason: {c.get('reason', '')}"
        )
    return "\n".join(lines) if lines else "  None."


def _build_report_context(reliable: List[Dict], unreliable: List[Dict]) -> tuple[str, str, Dict]:
    """
    Returns:
      task_blocks   — one block per reliable task for Key Findings section
      gaps_block    — all NOT_FOUND/weak claims across all tasks for Risks section
      source_usage  — final url → count for metadata
    """
    source_usage: Dict[str, int] = {}
    task_blocks  = []
    gap_lines    = []

    all_groups = reliable + unreliable  # include unreliable in gaps

    for group in all_groups:
        task         = group["task"]
        score        = group["task_reliability_score"]
        avail_urls   = group.get("available_urls", [])
        strong, weak = _partition_claims(group)

        # Collect NOT_FOUND and low-confidence claims for the Risks section
        for c in weak:
            if c["status"] == "NOT_FOUND":
                gap_lines.append(f"  - [{task}] Could not verify: {c['claim']}")
            elif c["status"] == "CONTRADICTED":
                gap_lines.append(f"  - [{task}] CONTRADICTED: {c['claim']} (source: {c.get('source_url','')})")

        if group not in reliable:
            continue  # don't add unreliable tasks to Key Findings

        # Article text availability note
        text_note = (
            f"Evidence text available from: {', '.join(avail_urls)}"
            if avail_urls else
            "No full article text retrieved — claims based on snippets only"
        )

        block = (
            f"TASK: {task}\n"
            f"RELIABILITY: {score} | {text_note}\n\n"
            f"VERIFIED CLAIMS:\n{_format_claims_with_sources(strong, source_usage)}\n\n"
            f"UNVERIFIED:\n{_format_claims_with_sources(weak, source_usage)}"
        )
        task_blocks.append(block)

    separator  = "\n\n" + ("─" * 60) + "\n\n"
    tasks_text = separator.join(task_blocks) if task_blocks else "No reliable tasks."
    gaps_text  = "\n".join(gap_lines) if gap_lines else "  None identified."

    return tasks_text, gaps_text, source_usage


# ------------------------------------------------------------------
# 3. BUILD METADATA
# ------------------------------------------------------------------

def _build_metadata(verified_claims: List[Dict], report: str) -> Dict:
    total      = sum(len(g.get("claims", [])) for g in verified_claims)
    supported  = sum(1 for g in verified_claims for c in g.get("claims", []) if c["status"] == "SUPPORTED")
    partial    = sum(1 for g in verified_claims for c in g.get("claims", []) if c["status"] == "PARTIAL")
    not_found  = sum(1 for g in verified_claims for c in g.get("claims", []) if c["status"] == "NOT_FOUND")
    contradict = sum(1 for g in verified_claims for c in g.get("claims", []) if c["status"] == "CONTRADICTED")

    avg_rel = (
        sum(g["task_reliability_score"] for g in verified_claims) / len(verified_claims)
        if verified_claims else 0.0
    )

    all_sources = list({
        c.get("source_url", "")
        for g in verified_claims
        for c in g.get("claims", [])
        if c.get("source_url")
    })

    return {
        "total_tasks":       len(verified_claims),
        "total_claims":      total,
        "supported":         supported,
        "partial":           partial,
        "not_found":         not_found,
        "contradicted":      contradict,
        "avg_reliability":   round(avg_rel, 3),
        "sources_consulted": len(all_sources),
        "source_urls":       all_sources,
        "report_length":     len(report),
    }


# ------------------------------------------------------------------
# 4. MAIN NODE
# ------------------------------------------------------------------

def reporter_node(state: ResearchState) -> ResearchState:
    verified_claims = state.get("verified_claims", [])
    original_query  = state.get("query", "Research Report")

    reliable = [g for g in verified_claims if g.get("task_reliability_score", 0) >= MIN_RELIABILITY_SCORE]
    unreliable = [g for g in verified_claims if g.get("task_reliability_score", 0) < MIN_RELIABILITY_SCORE]

    # Edge case: nothing passed threshold
    if not reliable:
        report = (
            "# Research Report\n\n## Insufficient Evidence\n\n"
            "All retrieved claims scored below the reliability threshold. "
            "Try a more specific query.\n\n### Low-Confidence Findings\n"
        )
        for g in unreliable:
            report += f"\n**{g['task']}** (score: {g['task_reliability_score']})\n"
            for c in g.get("claims", [])[:3]:
                report += f"- {c['claim']} [{c['status']}]\n"
        state["report"]          = report
        state["report_metadata"] = _build_metadata(verified_claims, report)
        return state

    task_blocks, gaps_block, source_usage = _build_report_context(reliable, unreliable)

    # Collect conflicts and bias warnings from researcher findings
    findings = state.get("findings", [])
    conflict_lines = []
    bias_lines     = []
    for f in findings:
        raw = f.get("finding", "")
        for line in raw.splitlines():
            if line.strip().startswith("CONFLICT:"):
                conflict_lines.append(f"  - {line.strip()}")
        bw = f.get("bias_warning", "")
        if bw:
            bias_lines.append(f"  - [{f.get('task','')[:50]}] {bw}")

    conflicts_block = "\n".join(conflict_lines) if conflict_lines else "  None detected."
    bias_block      = "\n".join(bias_lines)     if bias_lines     else "  None."

    overused = [url for url, count in source_usage.items() if count >= MAX_USES_PER_SOURCE]
    overused_warning = (
        f"\nOVERUSED SOURCES (do NOT cite these more than once more):\n"
        + "\n".join(f"  - {u}" for u in overused)
        if overused else ""
    )

    prompt = f"""You are a senior enterprise research analyst writing a final report.

STRICT RULES:
- Use ONLY the verified claims and sources in TASK DATA below
- Do NOT invent facts not present in the data
- Write EXACTLY ONE ### section per TASK — do not merge or skip any
- Cite source URLs inline as (Source: url)
- Do NOT cite the same URL more than {MAX_USES_PER_SOURCE} times total
- Where multiple sources confirm a claim, cite ALL of them
- Confidence below 60%: write "preliminary evidence suggests..." not a firm statement
- Statistical claims without a named organisation and date: flag as "unverified statistic"
- Risks section MUST include every item from KNOWLEDGE GAPS, CONFLICTS, and BIAS WARNINGS
- Do NOT write template placeholders like "[Repeat for each major topic]"
{overused_warning}

ORIGINAL QUERY: {original_query}

TASK DATA:
{task_blocks}

KNOWLEDGE GAPS:
{gaps_block}

SOURCE CONFLICTS (include in Risks and Source Conflicts section):
{conflicts_block}

RETRIEVAL BIAS WARNINGS (include in Risks):
{bias_block}

Write the report with this exact structure:

# Research Report: {original_query}

## Executive Summary
<3-5 sentences. Synthesise highest-confidence findings. Be honest about evidence quality
and whether findings rely on primary sources or blogs.>

## Key Findings

### <Task name>
<2-4 sentences with inline citations. Flag unverified statistics explicitly.
If multiple sources agree, cite all of them.>

## Source Conflicts
<For each conflict: what Source A says vs Source B says, and which is more credible.
If none: write "No conflicts detected.">

## Evidence Quality
| Task | Reliability | Evidence Tier | Source Domains |
|------|-------------|---------------|----------------|
<One row per task. Tier = Primary / Secondary / Blog / Mixed.>

## Risks & Limitations
<Every item from KNOWLEDGE GAPS, CONFLICTS, and BIAS WARNINGS must appear here.>

## Conclusion
<2-3 sentences answering the original query with an honest confidence statement.>

## Sources
<Every cited URL. Mark each [PRIMARY], [SECONDARY], or [BLOG].>
"""

    report = llm.generate(prompt).strip()

    meta   = _build_metadata(verified_claims, report)
    footer = (
        f"\n\n---\n"
        f"*Pipeline: {meta['supported']} supported · {meta['partial']} partial · "
        f"{meta['not_found']} not found · {meta['contradicted']} contradicted · "
        f"Avg reliability: {meta['avg_reliability']:.0%} · "
        f"{meta['sources_consulted']} sources consulted*"
    )

    state["report"]          = report + footer
    state["report_metadata"] = meta
    return state