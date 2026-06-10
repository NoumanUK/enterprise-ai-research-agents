"""
Planner Node — Research Pipeline v2
====================================
Responsibilities:
  - Disambiguate acronyms and technical terms BEFORE generating tasks
  - Decompose user query into 4–6 focused research tasks
  - Assign each task: intent, priority, and a search-ready query
  - Produce a shared research_plan written to state for downstream traceability

State keys written:
  - state["tasks"]          list[TaskDict]
  - state["research_plan"]  str  (human-readable summary of plan)
"""

import json
import re
from typing import List

from app.models.state import ResearchState
from app.services.llm_service import LLMService

llm = LLMService()

VALID_INTENTS = {
    "definition",
    "comparison",
    "case_study",
    "trend_analysis",
    "technical_deep_dive",
}


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _sanitize_intent(raw: str) -> str:
    raw = raw.strip().lower().replace(" ", "_")
    return raw if raw in VALID_INTENTS else "definition"


def _build_fallback(query: str) -> List[dict]:
    return [{
        "task":     query,
        "intent":   "definition",
        "query":    query,
        "priority": 1,
    }]


def _parse_tasks(response: str, query: str) -> List[dict]:
    """
    Robust JSON extraction:
      1. Try direct parse
      2. Extract first {...} block (model sometimes adds prose around JSON)
      3. Fall back to single-task plan
    """
    clean = re.sub(r"```(?:json)?|```", "", response).strip()

    candidates = [clean]
    match = re.search(r"\{[\s\S]*\}", clean)
    if match:
        candidates.append(match.group(0))

    for candidate in candidates:
        try:
            data      = json.loads(candidate)
            raw_tasks = data.get("tasks", [])
            if not raw_tasks:
                continue

            tasks = []
            for t in raw_tasks:
                task_str = str(t.get("task",  query)).strip()
                intent   = _sanitize_intent(str(t.get("intent", "definition")))
                q        = str(t.get("query", task_str)).strip()
                priority = int(t.get("priority", 3))

                if not task_str or not q:
                    continue

                tasks.append({
                    "task":     task_str,
                    "intent":   intent,
                    "query":    q,
                    "priority": max(1, min(priority, 5)),
                })

            if tasks:
                tasks.sort(key=lambda x: x["priority"])
                return tasks[:6]

        except (json.JSONDecodeError, KeyError, TypeError):
            continue

    return _build_fallback(query)


# ------------------------------------------------------------------
# Main Node
# ------------------------------------------------------------------

def planner_node(state: ResearchState) -> ResearchState:
    """
    Disambiguates the query, then decomposes it into a structured research plan.
    All downstream agents consume state["tasks"] as-is — no re-derivation needed.
    """
    query = state["query"]

    prompt = f"""
You are an enterprise research planning engine.

STEP 1 — DISAMBIGUATION (do this silently before planning):
Resolve any ambiguous acronyms or terms in the user query using these rules:

- MCP  → Model Context Protocol (Anthropic, 2024) — an open standard for connecting
         AI assistants to external tools and data sources. NOT Multicloud Platform,
         NOT Microsoft Cloud Platform, NOT any other expansion unless explicitly stated.
- LLM  → Large Language Model (AI context)
- RAG  → Retrieval-Augmented Generation (AI context)
- AGI  → Artificial General Intelligence
- If a term has both a tech/AI meaning and a non-tech meaning, always prefer the
  AI/enterprise-software meaning unless the query explicitly says otherwise.

STEP 2 — TASK DECOMPOSITION:
Decompose the (now disambiguated) query into 4–6 focused, non-overlapping research tasks.

Each task must have:
- "task":     a specific research goal (1 sentence), using the FULL expanded term
- "intent":   one of — definition | comparison | case_study | trend_analysis | technical_deep_dive
- "query":    an optimized, search-engine-ready query using the FULL expanded term
- "priority": integer 1–5 (1 = highest business value)

Rules:
- Always write out the full term in queries (e.g. "Model Context Protocol" not "MCP")
- Cover different angles: background, market, technical, risks, adoption, trends
- No two tasks should overlap
- Queries must use precise industry/technical terminology
- Avoid vague terms like "overview" or "information about"
- Return ONLY valid JSON — no prose, no markdown fences, no explanation

Return format:
{{
  "tasks": [
    {{
      "task":     "...",
      "intent":   "...",
      "query":    "...",
      "priority": 1
    }}
  ]
}}

User Query:
{query}
"""

    response = llm.generate(prompt)
    tasks    = _parse_tasks(response, query)

    # Human-readable plan summary for traceability and reporter context
    plan_lines = [f"Research Plan for: {query}", "=" * 60]
    for i, t in enumerate(tasks, 1):
        plan_lines.append(
            f"{i}. [{t['intent'].upper()}] (P{t['priority']}) {t['task']}\n"
            f"   Query: {t['query']}"
        )
    research_plan = "\n".join(plan_lines)

    state["tasks"]         = tasks
    state["research_plan"] = research_plan

    return state