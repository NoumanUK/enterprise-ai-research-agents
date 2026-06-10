"""
Evidence Ranker Node — Research Pipeline v2 (fast)
====================================================
Zero LLM calls — pure heuristic scoring.
Keeps quality high while cutting ~25 LLM calls vs the previous version.

State keys read:   state["findings"]
State keys written: state["ranked_evidence"]
"""

import re
from typing import Dict, List
from app.models.state import ResearchState

TOP_K_EVIDENCE = 5
MIN_EVIDENCE_SCORE = 0.15

AUTHORITY_DOMAINS = {".gov", ".edu", "arxiv", "ieee", "acm", "nature.com",
                     "scholar", "pubmed", "reuters", "bloomberg", "ft.com"}


def _heuristic_score(task: str, text: str, url: str) -> float:
    score = 0.0

    # Length — longer docs are usually more substantive
    length = len(text)
    if length > 3000:
        score += 0.30
    elif length > 1500:
        score += 0.20
    elif length > 500:
        score += 0.10

    # Keyword overlap between task and evidence
    task_words = set(re.findall(r"\b[a-z]{4,}\b", task.lower()))
    text_words = set(re.findall(r"\b[a-z]{4,}\b", text.lower()[:2000]))
    overlap = len(task_words & text_words)
    score += min(overlap * 0.05, 0.35)   # up to 0.35 from keyword overlap

    # Source quality signals
    url_lower = url.lower()
    if url_lower.startswith("https://"):
        score += 0.05
    if any(d in url_lower for d in AUTHORITY_DOMAINS):
        score += 0.10

    # Penalise very short or boilerplate text
    if length < 200:
        score -= 0.20

    return round(max(0.0, min(score, 1.0)), 3)


def _rank_finding(finding: Dict) -> Dict:
    task     = finding.get("task", "")
    intent   = finding.get("intent", "")
    raw_text = finding.get("finding", "")
    sources  = finding.get("sources", [])
    evidence = finding.get("evidence", [])

    pairs: List[tuple[str, str]] = []

    if evidence and sources:
        for i, chunk in enumerate(evidence):
            url = sources[i]["url"] if i < len(sources) and isinstance(sources[i], dict) else ""
            pairs.append((chunk, url))
    elif sources:
        for s in sources:
            if isinstance(s, dict):
                body = s.get("text") or s.get("snippet", "")
                url  = s.get("url", "")
            else:
                body, url = "", str(s)
            if body:
                pairs.append((body, url))
    elif raw_text:
        pairs.append((raw_text, ""))

    scored: List[Dict] = []
    for text, url in pairs:
        if not text or len(text) < 40:
            continue
        score = _heuristic_score(task, text, url)
        # Write score back to source dict
        for s in sources:
            if isinstance(s, dict) and s.get("url") == url:
                s["score"] = score
        scored.append({"text": text, "url": url, "score": score})

    scored = [e for e in scored if e["score"] >= MIN_EVIDENCE_SCORE]
    scored.sort(key=lambda x: x["score"], reverse=True)
    top = scored[:TOP_K_EVIDENCE]

    return {
        "task":     task,
        "intent":   intent,
        "finding":  raw_text,
        "evidence": top,
        "sources":  [e["url"] for e in top if e["url"]],
    }


def evidence_ranker_node(state: ResearchState) -> ResearchState:
    state["ranked_evidence"] = [_rank_finding(f) for f in state["findings"]]
    return state