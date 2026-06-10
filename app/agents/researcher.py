"""
Researcher Node — Research Pipeline v2
========================================
Fixes applied:
  1. Source prioritisation — official docs, papers, primary sources ranked first
  2. Fallback search — if <3 results, retries with broader query
  3. Stricter synthesis — statistical claims flagged for verification
  4. Retrieval bias warning — flags blog/aggregator-heavy results
  5. Contradiction detection — surfaces conflicting claims across sources

State keys read:   state["tasks"]
State keys written: state["findings"]
"""

from typing import Dict, List, Tuple
from ddgs import DDGS

from app.models.state import ResearchState
from app.services.llm_service import LLMService
from app.services.document_reader import read_documents

llm = LLMService()

# ------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------
MAX_SEARCH_RESULTS = 6
MIN_SNIPPET_LEN    = 60
MIN_FULL_TEXT_LEN  = 400
MAX_DOCS_FETCHED   = 7
CONTEXT_CHARS      = 3500

# Source quality tiers — higher tier = more trustworthy
PRIMARY_DOMAINS = {
    "anthropic.com", "openai.com", "deepmind.com", "microsoft.com",
    "arxiv.org", "github.com", "docs.github.com",
    "ieee.org", "acm.org", "nature.com", "science.org",
    "nist.gov", "iso.org", "w3.org",
    "wikipedia.org",
}
SECONDARY_DOMAINS = {
    "techcrunch.com", "wired.com", "reuters.com", "bloomberg.com",
    "ft.com", "hbr.org", "mckinsey.com", "gartner.com", "forrester.com",
    "venturebeat.com", "zdnet.com", "infoq.com",
}
BLOG_SIGNALS = {
    "medium.com", "substack.com", "hashnode.dev", "dev.to",
    "wordpress.com", "blogger.com", "blogspot.com",
}

# Statistical claim markers — these get extra scrutiny
STAT_MARKERS = {
    "%", "percent", "million", "billion", "trillion",
    "growth", "market size", "forecast", "cagr", "survey",
    "respondents", "organizations reported", "companies said",
}


# ------------------------------------------------------------------
# 1. SOURCE TIER CLASSIFIER
# ------------------------------------------------------------------

def _source_tier(url: str) -> int:
    """Returns 1 (primary), 2 (secondary), 3 (blog/aggregator), 4 (unknown)."""
    url_lower = url.lower()
    for d in PRIMARY_DOMAINS:
        if d in url_lower:
            return 1
    for d in SECONDARY_DOMAINS:
        if d in url_lower:
            return 2
    for d in BLOG_SIGNALS:
        if d in url_lower:
            return 3
    return 4  # unknown — treat as blog-level


def _retrieval_bias_warning(sources: List[Dict]) -> str:
    """Returns a warning string if retrieval is blog/aggregator-heavy."""
    if not sources:
        return ""
    tiers = [_source_tier(s.get("url", "")) for s in sources]
    primary_count   = tiers.count(1)
    blog_count      = tiers.count(3) + tiers.count(4)
    if primary_count == 0 and blog_count > len(tiers) // 2:
        return (
            "⚠ RETRIEVAL BIAS WARNING: No primary/official sources found. "
            "All findings are based on blogs and aggregators — treat with caution."
        )
    return ""


# ------------------------------------------------------------------
# 2. SUB-QUERY GENERATOR
# ------------------------------------------------------------------

def _generate_sub_queries(task: str, intent: str, seed_query: str) -> List[str]:
    prompt = f"""
You are a search query specialist for enterprise AI research.

Generate 2 search queries that approach the task from different angles.

Rules:
- Query 1: target official documentation, technical specs, or primary sources
- Query 2: target adoption data, case studies, or analyst reports
- Use precise technical terminology — write out acronyms in full
- Do NOT use "overview" or "introduction"
- Return ONE query per line, nothing else

Task:   {task}
Intent: {intent}
Seed:   {seed_query}
"""
    raw     = llm.generate(prompt)
    queries = [q.strip() for q in raw.splitlines() if q.strip() and len(q.strip()) > 8]
    all_q   = [seed_query] + [q for q in queries if q != seed_query]
    return all_q[:3]


# ------------------------------------------------------------------
# 3. WEB SEARCH WITH FALLBACK
# ------------------------------------------------------------------

def _search_web(query: str, max_results: int = MAX_SEARCH_RESULTS) -> List[Dict]:
    results = []
    try:
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                results.append({
                    "title":   r.get("title", ""),
                    "url":     r.get("href", ""),
                    "snippet": r.get("body", ""),
                    "text":    "",
                    "score":   0.0,
                    "tier":    _source_tier(r.get("href", "")),
                })
    except Exception:
        pass
    return results


def _search_with_fallback(sub_queries: List[str], task: str) -> List[Dict]:
    """
    Search all sub-queries. If total unique results < 3, add a
    broader fallback query to avoid empty task findings.
    """
    all_results: List[Dict] = []
    seen_urls: set = set()

    for q in sub_queries:
        for r in _search_web(q):
            url = r.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                all_results.append(r)

    # Fallback: if we got almost nothing, try a simpler query
    if len(all_results) < 3:
        # Strip down to the most important noun phrase
        words      = task.split()
        short_q    = " ".join(words[:6]) if len(words) > 6 else task
        fallback_q = f"{short_q} 2024 2025"
        for r in _search_web(fallback_q, max_results=8):
            url = r.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                all_results.append(r)

    return all_results


# ------------------------------------------------------------------
# 4. FILTER
# ------------------------------------------------------------------

def _filter_results(results: List[Dict]) -> List[Dict]:
    cleaned = []
    seen    = set()
    for r in results:
        url     = r.get("url", "")
        snippet = r.get("snippet", "")
        if not url or not snippet or url in seen:
            continue
        if len(snippet) < MIN_SNIPPET_LEN:
            continue
        seen.add(url)
        cleaned.append(r)

    # Sort: primary sources first, then secondary, then blogs
    cleaned.sort(key=lambda x: x.get("tier", 4))
    return cleaned


# ------------------------------------------------------------------
# 5. DOCUMENT FETCHER
# ------------------------------------------------------------------

def _fetch_documents(results: List[Dict]) -> List[Dict]:
    urls    = [r["url"] for r in results if r.get("url")]
    url_map = {r["url"]: r for r in results}

    try:
        docs = read_documents(urls, max_docs=MAX_DOCS_FETCHED)
    except Exception:
        docs = []

    for doc in docs:
        url  = doc.get("url", "")
        text = doc.get("text", "")
        if url and url in url_map and len(text) >= MIN_FULL_TEXT_LEN:
            url_map[url]["text"]  = text
            url_map[url]["title"] = doc.get("title", url_map[url].get("title", ""))

    enriched = [
        r for r in url_map.values()
        if r.get("text") or len(r.get("snippet", "")) >= MIN_SNIPPET_LEN
    ]
    # Keep tier-sorted order
    enriched.sort(key=lambda x: x.get("tier", 4))
    return enriched


# ------------------------------------------------------------------
# 6. CONTEXT BUILDER
# ------------------------------------------------------------------

def _build_context(sources: List[Dict]) -> Tuple[str, List[str]]:
    """
    Primary sources get full CONTEXT_CHARS.
    Blog/unknown sources get half to reduce their weight.
    """
    ranked = sorted(
        sources,
        key=lambda s: (s.get("tier", 4), -len(s.get("text", s.get("snippet", "")))),
    )[:5]

    blocks   = []
    evidence = []

    for s in ranked:
        body  = s.get("text") or s.get("snippet", "")
        tier  = s.get("tier", 4)
        chars = CONTEXT_CHARS if tier <= 2 else CONTEXT_CHARS // 2
        body  = body[:chars].strip()
        if not body:
            continue

        tier_label = {1: "PRIMARY", 2: "SECONDARY", 3: "BLOG", 4: "UNKNOWN"}.get(tier, "UNKNOWN")
        evidence.append(body)
        blocks.append(
            f"SOURCE [{tier_label}]: {s['url']}\n"
            f"TITLE: {s.get('title', 'N/A')}\n\n"
            f"{body}"
        )

    context_str = "\n\n---\n\n".join(blocks) if blocks else "NO DOCUMENTS RETRIEVED"
    return context_str, evidence


# ------------------------------------------------------------------
# 7. STATISTICAL CLAIM DETECTOR
# ------------------------------------------------------------------

def _has_stat_claims(text: str) -> bool:
    text_lower = text.lower()
    return any(marker in text_lower for marker in STAT_MARKERS)


# ------------------------------------------------------------------
# 8. SYNTHESIS  — strict grounding + contradiction detection
# ------------------------------------------------------------------

def _synthesise(task: str, intent: str, context: str, bias_warning: str) -> str:
    stat_instruction = """
STATISTICAL CLAIMS RULE:
- Any number, percentage, market size, or survey result MUST be attributed
  to a specific named source with its publication date
- If the same statistic appears in a blog but NOT in a primary source,
  flag it as UNVERIFIED STATISTIC
- Do not repeat a statistic that only one low-tier source mentions
""" if _has_stat_claims(context) else ""

    prompt = f"""
You are a senior enterprise research analyst with strict evidence standards.

STRICT RULES:
- Use ONLY the documents provided below — no outside knowledge
- If documents lack evidence for a point, write "INSUFFICIENT DATA" — do not guess
- Cite every claim as (Source: <url>) — no uncited facts
- PRIMARY sources outweigh BLOG sources — note when a claim only has blog support
{stat_instruction}
CONTRADICTION DETECTION:
- If two sources disagree on a fact, write:
  CONFLICT: Source A says X. Source B says Y. Resolution: <which is more credible and why>
- Do not silently pick one version — surface all conflicts

TASK:   {task}
INTENT: {intent}
{bias_warning}

DOCUMENTS:
{context}

Return in this exact structure:

FINDING:
<2–4 sentence factual summary, strictly grounded, primary sources preferred>

INSIGHTS:
- <insight (Source: url) [PRIMARY/BLOG]>
- <insight (Source: url) [PRIMARY/BLOG]>

STATISTICAL CLAIMS:
- <stat> (Source: url, date if available) [VERIFIED/UNVERIFIED STATISTIC]

CONFLICTS:
- <CONFLICT description, or "None detected">

DATA GAPS:
- <what could not be confirmed>

SOURCES:
- <url> [tier]
"""
    return llm.generate(prompt).strip()


# ------------------------------------------------------------------
# 9. MAIN NODE
# ------------------------------------------------------------------

def researcher_node(state: ResearchState) -> ResearchState:
    all_findings = []

    for task_dict in state["tasks"]:
        task       = task_dict["task"]
        intent     = task_dict["intent"]
        seed_query = task_dict["query"]

        # 1. Sub-queries
        sub_queries = _generate_sub_queries(task, intent, seed_query)

        # 2. Search with fallback
        raw_results = _search_with_fallback(sub_queries, task)

        # 3. Filter and tier-sort
        filtered = _filter_results(raw_results)

        # 4. Fetch full text
        sources = _fetch_documents(filtered)

        # 5. Build context (tier-aware)
        context, evidence = _build_context(sources)

        # 6. Retrieval bias check
        bias_warning = _retrieval_bias_warning(sources)

        # 7. Synthesise with contradiction detection
        finding = _synthesise(task, intent, context, bias_warning)

        all_findings.append({
            "task":         task,
            "intent":       intent,
            "queries":      sub_queries,
            "finding":      finding,
            "evidence":     evidence,
            "sources":      sources,
            "bias_warning": bias_warning,   # passed to reporter for transparency
        })

    state["findings"] = all_findings
    return state