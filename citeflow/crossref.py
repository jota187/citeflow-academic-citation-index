# citeflow/crossref.py
# Simple Crossref DOI lookup by title + author (sync HTTP).

from __future__ import annotations

import os
import time
from typing import Optional

import requests

CROSSREF_WORKS_URL = "https://api.crossref.org/works"
DEFAULT_TIMEOUT_S = 30
def _get_env_float(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


DEFAULT_DELAY_S = _get_env_float("CROSSREF_DELAY_S", 5.0)
_delay_logged = False


def _build_headers() -> dict:
    # Crossref recommends a contact email in User-Agent when possible.
    mailto = os.getenv("CROSSREF_MAILTO", "").strip()
    if mailto:
        return {"User-Agent": f"citeflow-crossref/1.0 (mailto:{mailto})"}
    return {"User-Agent": "citeflow-crossref/1.0"}


def find_doi_by_title_author(title: str, authors: str | None) -> Optional[str]:
    """
    Returns DOI string if found, otherwise None.
    """
    if not title or len(title.strip()) < 5:
        return None

    params = {
        "query.bibliographic": title,
        "rows": 1,
    }
    if authors and authors.strip():
        params["query.author"] = authors

    try:
        resp = requests.get(
            CROSSREF_WORKS_URL,
            params=params,
            timeout=DEFAULT_TIMEOUT_S,
            headers=_build_headers(),
        )
    except Exception as e:
        print(f"    [AVISO] Crossref: network error: {e}")
        return None

    if resp.status_code != 200:
        body = (resp.text or "").strip()
        if len(body) > 300:
            body = body[:300] + "..."
        print(f"    [AVISO] Crossref: HTTP {resp.status_code}: {body}")
        return None

    try:
        payload = resp.json()
    except Exception as e:
        print(f"    [AVISO] Crossref: invalid JSON: {e}")
        return None

    items = payload.get("message", {}).get("items", []) or []
    if not items:
        return None

    doi = (items[0] or {}).get("DOI")
    return doi


def find_doi_with_delay(title: str, authors: str | None, delay: float = DEFAULT_DELAY_S) -> Optional[str]:
    global _delay_logged
    if delay > 0 and not _delay_logged:
        print(f"  (pausa de {DEFAULT_DELAY_S:.1f}s entre chamadas para respeitar limites da API)\n")
        _delay_logged = True
    doi = find_doi_by_title_author(title, authors)
    time.sleep(delay)
    return doi
