# citeflow/enrich.py
# Script que enriquece os registos da BD com dados da Semantic Scholar (por titulo).

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone

from .db import get_connection, init_db
from .semantic_scholar import DEFAULT_DELAY_S, enrich_with_delay
from .crossref import DEFAULT_DELAY_S as CROSSREF_DELAY_S, find_doi_with_delay


def run(limit: int | None = None) -> None:
    """
    Percorre os registos da BD que ainda nao foram enriquecidos (ss_enriched = 0)
    e tenta obter DOI via Semantic Scholar (titulo).

    limit: numero maximo de registos a processar (None = todos)
    """
    init_db()
    conn = get_connection()
    cur = conn.cursor()
    run_id = datetime.now(timezone.utc).isoformat(timespec="seconds")

    if limit:
        cur.execute(
            """
            SELECT id, citing_title, citing_authors FROM citations
            WHERE ss_enriched = 0 AND citing_title IS NOT NULL
            LIMIT ?
            """,
            (limit,),
        )
    else:
        cur.execute(
            """
            SELECT id, citing_title, citing_authors FROM citations
            WHERE ss_enriched = 0 AND citing_title IS NOT NULL
            """
        )

    records = cur.fetchall()
    total = len(records)
    if total == 0:
        print("Todos os registos ja foram enriquecidos.")
        conn.close()
        return

    print("\n=== Enriquecimento Semantic Scholar ===")
    print(f"  Registos por processar: {total}")
    print(f"  (pausa de {DEFAULT_DELAY_S:.1f}s entre chamadas para respeitar limites da API - SS)\n")

    enriched = 0
    enriched_with_doi = 0
    enriched_with_cr = 0
    not_found = 0
    errors = 0
    ss_attempted = 0
    ss_completed = 0

    try:
        print("  Fase unica: Semantic Scholar (DOI + metadados)")
        print(f"  (pausa de {CROSSREF_DELAY_S:.1f}s entre chamadas para respeitar limites da API Crossref)\n")
        for i, (record_id, citing_title, citing_authors) in enumerate(records, 1):
            title_preview = (citing_title or "")[:60]
            print(f"  [SS {i}/{total}] {title_preview}...")

            ss_attempted += 1
            data = enrich_with_delay(citing_title or "")

            if data:
                ss_completed += 1
                has_doi = bool(data.get("ss_doi"))
                if not has_doi:
                    doi_cr = find_doi_with_delay(citing_title or "", citing_authors)
                    if doi_cr:
                        data["ss_doi"] = doi_cr
                        has_doi = True
                        enriched_with_cr += 1
                cur.execute(
                    """
                    UPDATE citations
                    SET ss_doi            = ?,
                        ss_year           = ?,
                        ss_venue          = ?,
                        ss_citation_count = ?,
                        ss_url            = ?,
                        ss_enriched       = 1,
                        ss_enriched_at    = ?,
                        ss_enriched_run_id = ?
                    WHERE id = ?
                    """,
                    (
                        data.get("ss_doi"),
                        data.get("ss_year"),
                        data.get("ss_venue"),
                        data.get("ss_citation_count"),
                        data.get("ss_url"),
                        run_id,
                        run_id,
                        record_id,
                    ),
                )
                enriched += 1
                if has_doi:
                    enriched_with_doi += 1
                print(
                    f"         OK DOI: {data.get('ss_doi')} | Citacoes: {data.get('ss_citation_count')}"
                )
            elif data == {}:
                ss_completed += 1
                doi_cr = find_doi_with_delay(citing_title or "", citing_authors)
                if doi_cr:
                    enriched_with_cr += 1
                    enriched_with_doi += 1
                    enriched += 1
                    cur.execute(
                        """
                        UPDATE citations
                        SET ss_doi            = ?,
                            ss_enriched       = 1,
                            ss_enriched_at    = ?,
                            ss_enriched_run_id = ?
                        WHERE id = ?
                        """,
                        (doi_cr, run_id, run_id, record_id),
                    )
                    print(f"         OK DOI (Crossref): {doi_cr}")
                else:
                    # Consulta OK, mas nao encontrou resultados.
                    cur.execute("UPDATE citations SET ss_enriched = 1 WHERE id = ?", (record_id,))
                    not_found += 1
                    print("         - Nao encontrado")
            else:
                # Erro de API/rede no Semantic Scholar: tentar Crossref e seguir.
                doi_cr = find_doi_with_delay(citing_title or "", citing_authors)
                if doi_cr:
                    enriched_with_cr += 1
                    enriched_with_doi += 1
                    enriched += 1
                    cur.execute(
                        """
                        UPDATE citations
                        SET ss_doi            = ?,
                            ss_enriched       = 1,
                            ss_enriched_at    = ?,
                            ss_enriched_run_id = ?
                        WHERE id = ?
                        """,
                        (doi_cr, run_id, run_id, record_id),
                    )
                    print(f"         OK DOI (Crossref): {doi_cr}")
                else:
                    errors += 1
                    print("         ! Erro na chamada a Semantic Scholar (vai tentar novamente mais tarde)")
                    from .semantic_scholar import last_rate_limited
                    if last_rate_limited:
                        print("         ! Define SEMANTIC_SCHOLAR_API_KEY para limites mais altos.")
                        print("         ! Rate limit atingido; a continuar com outras citacoes.")

            conn.commit()
    finally:
        conn.close()

    total_enriched = enriched_with_doi
    total_not_enriched = not_found + errors

    print("\n=== Concluido ===")
    print(f"  Enriquecidos com SS:    {enriched_with_doi - enriched_with_cr}")
    print(f"  Enriquecidos com CR:    {enriched_with_cr}")
    print(f"  Total de enriquecidos:  {total_enriched}")
    print(f"  Total de nao enriquecidos: {total_not_enriched}")
    print(f"  Nao encontrados:        {not_found}")
    print(f"  Erros de API/rede:      {errors}")
    print(f"  Total processados DOI API: {ss_completed}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Enrich citations via Crossref then Semantic Scholar.")
    parser.add_argument("--limit", type=int, default=None, help="Max number of records to process.")
    args = parser.parse_args()

    if args.limit is not None:
        run(limit=args.limit)
    else:
        # Avoid interactive prompt in non-interactive environments (e.g., CI).
        if not sys.stdin.isatty():
            run(limit=None)
        else:
            resp = input("Quantos registos processar? (Enter = todos): ").strip()
            limit = int(resp) if resp.isdigit() else None
            run(limit=limit)
