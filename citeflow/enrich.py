# citeflow/enrich.py
# Script que enriquece os registos da BD com dados da Semantic Scholar (por titulo).

from __future__ import annotations

import argparse
import sys

from .db import get_connection
from .crossref import find_doi_with_delay
from .semantic_scholar import enrich_with_delay


def run(limit: int | None = None) -> None:
    """
    Percorre os registos da BD que ainda nao foram enriquecidos (ss_enriched = 0)
    e tenta obter DOI via Crossref (titulo + autores). Se falhar, usa Semantic Scholar.

    limit: numero maximo de registos a processar (None = todos)
    """
    conn = get_connection()
    cur = conn.cursor()

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

    print("\n=== Enriquecimento Crossref + Semantic Scholar ===")
    print(f"  Registos por processar: {total}")
    print("  (pausa de 5.0s entre chamadas para respeitar limites da API)\n")

    enriched = 0
    not_found = 0
    errors = 0
    sent_to_crossref = 0
    sent_to_semantic = 0
    pending_ss: list[tuple[int, str]] = []

    try:
        print("  Fase 1/2: Crossref (DOI) para todos os titulos")
        for i, (record_id, citing_title, citing_authors) in enumerate(records, 1):
            title_preview = (citing_title or "")[:60]
            print(f"  [CR {i}/{total}] {title_preview}...")

            sent_to_crossref += 1
            doi = find_doi_with_delay(citing_title, citing_authors)
            if doi:
                cur.execute(
                    """
                    UPDATE citations
                    SET ss_doi      = ?,
                        ss_enriched = 1
                    WHERE id = ?
                    """,
                    (doi, record_id),
                )
                enriched += 1
                print(f"         OK DOI (Crossref): {doi}")
                conn.commit()
            else:
                pending_ss.append((record_id, citing_title or ""))

        pct_sem_doi = round(len(pending_ss) / total * 100, 1) if total > 0 else 0
        print(f"\n  Sem DOI apos Crossref: {len(pending_ss)} ({pct_sem_doi}%)")
        if pending_ss:
            print("\n  Fase 2/2: Semantic Scholar (so titulos sem DOI)")
        for i, (record_id, citing_title) in enumerate(pending_ss, 1):
            title_preview = (citing_title or "")[:60]
            print(f"  [SS {i}/{len(pending_ss)}] {title_preview}...")

            sent_to_semantic += 1
            data = enrich_with_delay(citing_title)

            if data:
                cur.execute(
                    """
                    UPDATE citations
                    SET ss_doi            = ?,
                        ss_year           = ?,
                        ss_venue          = ?,
                        ss_citation_count = ?,
                        ss_url            = ?,
                        ss_enriched       = 1
                    WHERE id = ?
                    """,
                    (
                        data.get("ss_doi"),
                        data.get("ss_year"),
                        data.get("ss_venue"),
                        data.get("ss_citation_count"),
                        data.get("ss_url"),
                        record_id,
                    ),
                )
                enriched += 1
                print(
                    f"         OK DOI: {data.get('ss_doi')} | Citacoes: {data.get('ss_citation_count')}"
                )
            elif data == {}:
                # Consulta OK, mas nao encontrou resultados.
                cur.execute("UPDATE citations SET ss_enriched = 1 WHERE id = ?", (record_id,))
                not_found += 1
                print("         - Nao encontrado")
            else:
                # Erro de API/rede: nao marcar como tentado, para permitir retry.
                errors += 1
                print("         ! Erro na chamada a Semantic Scholar (vai tentar novamente mais tarde)")
                # Se for rate limit, parar cedo para nao gastar chamadas.
                from .semantic_scholar import last_rate_limited
                if last_rate_limited:
                    print("         ! Define SEMANTIC_SCHOLAR_API_KEY para limites mais altos.")
                    print("         ! Rate limit atingido; a parar o processamento restante.")
                    break

            conn.commit()
    finally:
        conn.close()

    print("\n=== Concluido ===")
    print(f"  Enviados para Crossref: {sent_to_crossref}")
    print(f"  Enviados para Semantic: {sent_to_semantic}")
    print(f"  Enriquecidos com dados: {enriched}")
    print(f"  Nao encontrados:        {not_found}")
    print(f"  Erros de API/rede:      {errors}")
    print(f"  Total processados:      {total}")


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
