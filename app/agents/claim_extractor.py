"""
Claim Extractor Node — Research Pipeline v2
=============================================
Responsibilities:
  - Extract atomic, verifiable claims from ranked evidence (not raw findings)
  - Cross-finding global deduplication (not just within-finding)
  - Tag each claim with source URL and evidence score for fact_checker_node

State keys read:
  - state["ranked_evidence"]  list[RankedFindingDict]  (from evidence_ranker_node)

State keys written:
  - state["claims"]  list[ClaimGroupDict]

ClaimGroupDict = {
  "task":         str,
  "claims":       list[ClaimDict],
  "source_urls":  list[str],
}

ClaimDict = {
  "claim":      str,
  "source_url": str,
  "evidence_score": float,
}
"""

import re
from typing import List, Dict
from app.models.state import ResearchState
from app.services.llm_service import LLMService

llm = LLMService()

# ------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------
MIN_CLAIM_CHARS          = 20    # discard trivially short extractions
MAX_CLAIMS_PER_TASK      = 12    # cap to keep fact-checker tractable
GLOBAL_SIMILARITY_WINDOW = 6     # words checked for near-duplicate detection

# ------------------------------------------------------------------
# 1. CLAIM PARSER
# ------------------------------------------------------------------

def _parse_claims(raw: str) -> List[str]:
    """
    Accept multiple common LLM output formats:
      CLAIM: ...
      - ...
      • ...
      1. ...
    """
    claims = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        # Strip common prefixes
        for prefix in ("CLAIM:", "claim:", "-", "•", "*"):
            if line.startswith(prefix):
                line = line[len(prefix):].strip()
                break
        # Strip leading numbering like "1." or "2)"
        line = re.sub(r"^\d+[\.\)]\s*", "", line).strip()

        if len(line) >= MIN_CLAIM_CHARS:
            claims.append(line)
    return claims


# ------------------------------------------------------------------
# 2. NEAR-DUPLICATE FILTER
#    Lightweight word-overlap check — no embedding needed
# ------------------------------------------------------------------

def _key_words(text: str) -> frozenset:
    """Extract meaningful words for overlap comparison."""
    stopwords = {"the", "a", "an", "is", "are", "was", "were", "in", "of",
                 "to", "and", "or", "for", "with", "that", "this", "it"}
    words = re.findall(r"\b[a-z]{3,}\b", text.lower())
    return frozenset(w for w in words if w not in stopwords)


def _is_duplicate(claim: str, seen_keys: List[frozenset], threshold: float = 0.6) -> bool:
    """
    Jaccard similarity against already-accepted claims.
    Returns True if too similar to an existing claim.
    """
    keys = _key_words(claim)
    if not keys:
        return False
    for existing in seen_keys:
        union     = keys | existing
        intersect = keys & existing
        if union and len(intersect) / len(union) >= threshold:
            return True
    return False


# ------------------------------------------------------------------
# 3. EXTRACT CLAIMS FROM ONE EVIDENCE CHUNK
# ------------------------------------------------------------------

def _extract_from_chunk(task: str, text: str, source_url: str) -> List[str]:
    prompt = f"""
You are an enterprise claim extraction engine.

Extract atomic, verifiable factual claims from the text below.

STRICT RULES:
- ONE idea per claim — split compound statements
- Preserve exact numbers, percentages, dates, and named entities
- Do NOT interpret, summarise, or add information not present
- Do NOT include opinions, predictions without data, or vague statements
- Do NOT extract claims that merely restate the task question

TASK CONTEXT:
{task}

TEXT:
{text[:2500]}

OUTPUT FORMAT (one per line, no other text):
CLAIM: <atomic factual statement>
CLAIM: <atomic factual statement>
"""
    raw = llm.generate(prompt)
    return _parse_claims(raw)


# ------------------------------------------------------------------
# 4. MAIN NODE
# ------------------------------------------------------------------

def claim_extractor_node(state: ResearchState) -> ResearchState:
    """
    Extracts claims from top-ranked evidence chunks.
    Deduplicates globally across all tasks.
    """
    # Global dedup across all tasks to avoid the reporter repeating facts
    global_seen_keys: List[frozenset] = []

    all_claim_groups = []

    for ranked in state["ranked_evidence"]:
        task        = ranked.get("task", "")
        evidence    = ranked.get("evidence", [])      # list[EvidenceDict]
        source_urls = ranked.get("sources", [])

        task_claims: List[Dict] = []

        for ev in evidence:
            text  = ev.get("text", "")
            url   = ev.get("url", "")
            score = ev.get("score", 0.0)

            if not text or len(text) < MIN_CLAIM_CHARS:
                continue

            raw_claims = _extract_from_chunk(task, text, url)

            for claim in raw_claims:
                if len(task_claims) >= MAX_CLAIMS_PER_TASK:
                    break

                # Deduplicate globally
                if _is_duplicate(claim, global_seen_keys):
                    continue

                keys = _key_words(claim)
                global_seen_keys.append(keys)

                task_claims.append({
                    "claim":          claim,
                    "source_url":     url,
                    "evidence_score": score,
                })

        all_claim_groups.append({
            "task":        task,
            "claims":      task_claims,
            "source_urls": source_urls,
        })

    state["claims"] = all_claim_groups
    return state