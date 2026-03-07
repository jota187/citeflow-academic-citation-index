from __future__ import annotations
from typing import Dict, Optional, Tuple
from bs4 import BeautifulSoup
from urllib.parse import unquote
import re


def _split_authors_venue(raw: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Separa 'Autores - Revista, Ano' em (autores, venue).
    Trata espaços normais E espaços não separáveis (\\xa0).
    """
    raw = raw.strip()
    # Padrão: espaço (normal ou \\xa0) + traço + espaço (normal ou \\xa0)
    match = re.search(r'[\s\xa0][-–—][\s\xa0]', raw)
    if match:
        idx = match.start()
        authors = raw[:idx].strip()
        venue = raw[match.end():].strip()
        return authors, venue
    return raw, None


def parse_scholar_alert_html(html: str) -> Dict:
    soup = BeautifulSoup(html, "html.parser")

    # 1. Título e URL
    citing_title_tag = soup.find(class_="gse_alrt_title")
    citing_title = citing_title_tag.get_text(strip=True) if citing_title_tag else None

    citing_url = None
    if citing_title_tag:
        link = citing_title_tag.find("a")
        if link:
            href = link.get("href", "")
            url_match = re.search(r"url=([^&]+)", href)
            citing_url = unquote(url_match.group(1)) if url_match else href

    # 2. Autores e venue
    citing_authors = None
    citing_venue = None

    for tag in soup.find_all(True):
        if tag.find(True):
            continue
        text = tag.get_text(strip=True)
        if not text or len(text) < 10 or len(text) > 200:
            continue
        if text == citing_title:
            continue
        if "gse_alrt_sni" in " ".join(tag.get("class", [])):
            continue
        authors, venue = _split_authors_venue(text)
        if authors and venue:
            citing_authors = authors
            citing_venue = venue
            break

    # 3. Snippet
    snippet_tag = soup.find(class_="gse_alrt_sni")
    citing_snippet = snippet_tag.get_text(strip=True) if snippet_tag else None

    # 4. Título do teu artigo citado
    my_work_title = None
    citations_node = soup.find(
        string=re.compile(r"Cita[çc][oõ]es:|Citations:", re.IGNORECASE)
    )
    if citations_node:
        parent = citations_node.find_parent()
        if parent:
            full_text = parent.get_text(" ", strip=True)
            match = re.search(
                r"(?:Cita[çc][oõ]es:|Citations:)\s*(.+)",
                full_text, re.IGNORECASE
            )
            if match:
                my_work_title = match.group(1).strip()

    return {
        "platform": "scholar",
        "my_work_title": my_work_title,
        "citing_title": citing_title,
        "citing_authors": citing_authors,
        "citing_venue": citing_venue,
        "citing_snippet": citing_snippet,
        "citing_url": citing_url,
    }
