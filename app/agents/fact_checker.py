"""
Fact Checker Node — Research Pipeline v2
==========================================
- 1 LLM call per task (batched)
- Verifies against real article text
- Statistical claims get stricter scrutiny
- Conflicts from researcher are explicitly adjudicated
- Honest confidence: PARTIAL is default when thin

State keys read:   state["claims"], state["ranked_evidence"]
State keys written: state["verified_claims"]
"""

from typing import Dict, List
from app.models.state import ResearchState
from app.services.llm_service import LLMService

llm = LLMService()

VALID_STATUSES = {"SUPPORTED", "PARTIAL", "NOT_FOUND", "CONTRADICTED"}
STATUS_WEIGHTS = {"SUPPORTED": 1.0, "PARTIAL": 0.6, "NOT_FOUND": 0.2, "CONTRADICTED": 0.0}
EVIDENCE_CHARS     = 1800
MAX_SOURCES_PER_TASK = 4

# Statistical markers — claims with these get lower default confidence
STAT_MARKERS = {"%", "percent", "million", "billion", "growth", "market", "forecast",
                "survey", "respondents", "cagr", "downloads", "organizations reported"}


def _is_stat_claim(claim: str) -> bool:
    return any(m in claim.lower() for m in STAT_MARKERS)


def _build_evidence_index(ranked_evidence: List[Dict]) -> Dict[str, str]:
    index = {}
    for item in ranked_evidence:
        for ev in item.get("evidence", []):
            url  = ev.get("url", "")
            text = ev.get("text", "")
            if url and text and url not in index:
                index[url] = text
    return index


def _build_evidence_block(source_urls: List[str], evidence_index: Dict[str, str]) -> tuple[str, List[str]]:
    chunks         = []
    available_urls = []
    for url in source_urls[:MAX_SOURCES_PER_TASK]:
        text = evidence_index.get(url, "")
        if not text:
            continue
        chunks.append(f"SOURCE [{len(available_urls)+1}]: {url}\n{text[:EVIDENCE_CHARS]}")
        available_urls.append(url)

    if not chunks:
        return "NO ARTICLE TEXT AVAILABLE", []
    return "\n\n---\n\n".join(chunks), available_urls


def _parse_batch_response(response: str, claims: List[Dict], available_urls: List[str]) -> List[Dict]:
    lines_by_key = {}
    for line in response.splitlines():
        line = line.strip()
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        lines_by_key[key.strip().upper()] = val.strip()

    verified = []
    for i, claim in enumerate(claims, start=1):
        prefix = f"CLAIM_{i}_"

        raw_status = lines_by_key.get(f"{prefix}STATUS", "NOT_FOUND").upper()
        status     = raw_status if raw_status in VALID_STATUSES else "NOT_FOUND"

        # Statistical claims default to lower confidence
        default_conf = "0.25" if _is_stat_claim(claim["claim"]) else "0.40"
        try:
            confidence = float(lines_by_key.get(f"{prefix}CONFIDENCE", default_conf))
            confidence = max(0.0, min(confidence, 1.0))
        except ValueError:
            confidence = float(default_conf)

        risk   = lines_by_key.get(f"{prefix}RISK", "medium").lower()
        risk   = risk if risk in {"low", "medium", "high"} else "medium"
        reason = lines_by_key.get(f"{prefix}REASON", "")

        try:
            src_idx    = int(lines_by_key.get(f"{prefix}SOURCE_INDEX", "0")) - 1
            source_url = available_urls[src_idx] if 0 <= src_idx < len(available_urls) else claim.get("source_url", "")
        except (ValueError, IndexError):
            source_url = claim.get("source_url", "")

        verified.append({
            "claim":      claim["claim"],
            "status":     status,
            "confidence": confidence,
            "risk":       risk,
            "reason":     reason,
            "source_url": source_url,
            "is_stat":    _is_stat_claim(claim["claim"]),
        })

    return verified


def _verify_claims_batch(
    task: str,
    claims: List[Dict],
    evidence_block: str,
    available_urls: List[str],
) -> List[Dict]:
    if not claims:
        return []

    claim_lines = "\n".join(
        f"CLAIM_{i}: {c['claim']}"
        + (" [STATISTICAL — requires named source + date]" if _is_stat_claim(c["claim"]) else "")
        for i, c in enumerate(claims, start=1)
    )

    output_lines = []
    for i in range(1, len(claims) + 1):
        output_lines.append(
            f"CLAIM_{i}_STATUS: SUPPORTED | PARTIAL | NOT_FOUND | CONTRADICTED\n"
            f"CLAIM_{i}_CONFIDENCE: <float 0.0-1.0>\n"
            f"CLAIM_{i}_RISK: low | medium | high\n"
            f"CLAIM_{i}_REASON: <cite specific text from source>\n"
            f"CLAIM_{i}_SOURCE_INDEX: <1-{max(len(available_urls),1)} or 0 if none>"
        )

    prompt = f"""You are a strict enterprise fact-verification engine.

VERIFICATION RULES:
- SUPPORTED     = source article explicitly and clearly confirms the claim
- PARTIAL       = source hints at it but does not fully confirm — USE THIS as default when unsure
- NOT_FOUND     = source articles do not mention this topic at all
- CONTRADICTED  = source explicitly says the opposite

CONFIDENCE RULES:
- 0.9-1.0 = exact wording found in a primary source (official docs, paper)
- 0.7-0.8 = clearly stated in a secondary source (major news, analyst firm)
- 0.4-0.6 = implied or mentioned briefly in any source
- 0.1-0.3 = only found in a blog with no primary source backing
- For STATISTICAL claims flagged [STATISTICAL]: cap confidence at 0.6 unless
  the source names the original research organisation AND publication date

TASK: {task}

SOURCE ARTICLES:
{evidence_block}

CLAIMS TO VERIFY:
{claim_lines}

Return ONLY this format, no extra text:
{"".join(output_lines)}
"""

    response = llm.generate(prompt)
    return _parse_batch_response(response, claims, available_urls)


def _aggregate_score(verified_claims: List[Dict]) -> float:
    if not verified_claims:
        return 0.0
    total = sum(
        STATUS_WEIGHTS.get(c["status"], 0.2) * c["confidence"]
        for c in verified_claims
    )
    return round(total / len(verified_claims), 3)


def fact_checker_node(state: ResearchState) -> ResearchState:
    evidence_index   = _build_evidence_index(state.get("ranked_evidence", []))
    verified_results = []

    for claim_group in state["claims"]:
        task        = claim_group.get("task", "")
        claims      = claim_group.get("claims", [])
        source_urls = claim_group.get("source_urls", [])

        evidence_block, available_urls = _build_evidence_block(source_urls, evidence_index)
        verified_claims = _verify_claims_batch(task, claims, evidence_block, available_urls)

        verified_results.append({
            "task":                   task,
            "sources":                source_urls,
            "available_urls":         available_urls,
            "claims":                 verified_claims,
            "task_reliability_score": _aggregate_score(verified_claims),
        })

    state["verified_claims"] = verified_results
    return state