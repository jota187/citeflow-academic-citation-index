# citeflow/semantic_scholar.py
# Módulo para enriquecer registos com dados da Semantic Scholar API

from semanticscholar import SemanticScholar
import time

sch = SemanticScholar()


def enrich_by_title(title: str) -> dict:
    """
    Pesquisa um artigo pelo título na Semantic Scholar.
    Devolve um dicionário com os campos de enriquecimento,
    ou um dicionário vazio se não encontrar nada.
    """
    if not title or len(title.strip()) < 5:
        return {}

    try:
        results = sch.search_paper(title, limit=1, fields=[
            "title", "year", "venue", "externalIds",
            "citationCount", "url"
        ])

        if not results or len(results) == 0:
            return {}

        paper = results[0]

        doi = None
        if hasattr(paper, "externalIds") and paper.externalIds:
            doi = paper.externalIds.get("DOI")

        return {
            "ss_doi":            doi,
            "ss_year":           getattr(paper, "year", None),
            "ss_venue":          getattr(paper, "venue", None),
            "ss_citation_count": getattr(paper, "citationCount", None),
            "ss_url":            getattr(paper, "url", None),
        }

    except Exception as e:
        print(f"    [AVISO] Semantic Scholar: {e}")
        return {}


def enrich_with_delay(title: str, delay: float = 1.5) -> dict:
    """
    Igual a enrich_by_title mas com pausa entre chamadas
    para não exceder os limites da API.
    """
    result = enrich_by_title(title)
    time.sleep(delay)
    return result
