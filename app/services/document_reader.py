from typing import Dict, Any, List, Optional
import trafilatura
import requests
from urllib.parse import urlparse


# ---------------------------------------------------------
# HTTP Fetcher (safe + simple)
# ---------------------------------------------------------
def fetch_html(url: str, timeout: int = 10) -> Optional[str]:
    """
    Fetch raw HTML from a URL.
    """
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Enterprise Research Bot 1.0)"
        }

        response = requests.get(url, headers=headers, timeout=timeout)
        if response.status_code != 200:
            return None

        return response.text

    except Exception:
        return None


# ---------------------------------------------------------
# Extract clean article text
# ---------------------------------------------------------
def extract_text(html: str, url: str) -> str:
    """
    Uses trafilatura to extract main readable content.
    """
    try:
        text = trafilatura.extract(
            html,
            url=url,
            include_comments=False,
            include_tables=True,
            favor_recall=True
        )

        return text if text else ""

    except Exception:
        return ""


# ---------------------------------------------------------
# Main Document Reader
# ---------------------------------------------------------
def read_document(url: str) -> Dict[str, Any]:
    """
    URL → Clean structured document
    """

    html = fetch_html(url)

    if not html:
        return {
            "url": url,
            "title": "",
            "text": "",
            "status": "failed_fetch"
        }

    text = extract_text(html, url)

    return {
        "url": url,
        "title": urlparse(url).netloc,
        "text": text,
        "status": "ok" if text else "empty"
    }


# ---------------------------------------------------------
# Batch reader (important for researcher integration)
# ---------------------------------------------------------
def read_documents(urls: List[str], max_docs: int = 5) -> List[Dict[str, Any]]:
    """
    Reads multiple URLs safely.
    """
    docs = []

    for url in urls[:max_docs]:
        doc = read_document(url)

        # filter useless pages
        if doc["status"] == "ok" and len(doc["text"]) > 200:
            docs.append(doc)

    return docs