# citeflow/semantic_scholar.py
# Module to enrich records using the Semantic Scholar Graph API (sync HTTP).

from __future__ import annotations

import os
import time
from typing import Optional

import requests

SEMANTIC_SCHOLAR_GRAPH_SEARCH_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
DEFAULT_TIMEOUT_S = 30
DEFAULT_DELAY_S = 5.0
last_rate_limited = False


def _build_headers() -> dict:
    headers = {"User-Agent": "citeflow-enricher/1.0"}
    api_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY", "").strip()
    if api_key:
        headers["x-api-key"] = api_key
    return headers


def enrich_by_title(title: str) -> Optional[dict]:
    """
    Search for a paper by title on Semantic Scholar (Graph API).

    Returns:
      - dict with "ss_*" fields when found
      - {} when not found
      - None when API/network error (so caller can retry later)
    """
    if not title or len(title.strip()) < 5:
        return {}

    params = {
        "query": title,
        "limit": 1,
        "fields": "title,year,venue,externalIds,citationCount,url",
    }

    global last_rate_limited
    last_rate_limited = False
    try:
        resp = requests.get(
            SEMANTIC_SCHOLAR_GRAPH_SEARCH_URL,
            params=params,
            timeout=DEFAULT_TIMEOUT_S,
            headers=_build_headers(),
        )
    except Exception as e:
        print(f"    [AVISO] Semantic Scholar: network error: {e}")
        return None

    if resp.status_code != 200:
        if resp.status_code == 429:
            last_rate_limited = True
        body = (resp.text or "").strip()
        if len(body) > 300:
            body = body[:300] + "..."
        print(f"    [AVISO] Semantic Scholar: HTTP {resp.status_code}: {body}")
        return None

    try:
        payload = resp.json()
    except Exception as e:
        print(f"    [AVISO] Semantic Scholar: invalid JSON: {e}")
        return None

    data = payload.get("data") or []
    if not data:
        return {}

    paper = data[0] or {}
    external_ids = paper.get("externalIds") or {}
    doi = external_ids.get("DOI")

    return {
        "ss_doi": doi,
        "ss_year": paper.get("year"),
        "ss_venue": paper.get("venue"),
        "ss_citation_count": paper.get("citationCount"),
        "ss_url": paper.get("url"),
    }


def enrich_with_delay(title: str, delay: float = DEFAULT_DELAY_S) -> Optional[dict]:
    """Same as enrich_by_title but with a delay between calls."""
    result = enrich_by_title(title)
    time.sleep(delay)
    return result
