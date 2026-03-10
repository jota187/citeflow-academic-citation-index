# citeflow/enrich.py
# Script que enriquece os registos da BD com dados da Semantic Scholar

import sqlite3
from .db import get_connection, DB_PATH
from .semantic_scholar import enrich_with_delay


def run(limit: int = None):
    """
    Percorre os registos da BD que ainda não foram enriquecidos
    (ss_enriched = 0) e tenta obter dados da Semantic Scholar
    pelo título do artigo citante (citing_title).

    limit: número máximo de registos a processar (None = todos)
    """
    conn = get_connection()
    c = conn.cursor()

    # Buscar registos por enriquecer
    if limit:
        c.execute("""
            SELECT id, citing_title FROM citations
            WHERE ss_enriched = 0 AND citing_title IS NOT NULL
            LIMIT ?
        """, (limit,))
    else:
        c.execute("""
            SELECT id, citing_title FROM citations
            WHERE ss_enriched = 0 AND citing_title IS NOT NULL
        """)

    registos = c.fetchall()
    total = len(registos)

    if total == 0:
        print("Todos os registos já foram enriquecidos.")
        conn.close()
        return

    print(f"\n=== Enriquecimento Semantic Scholar ===")
    print(f"  Registos por processar: {total}")
    print(f"  (pausa de 1.5s entre chamadas para respeitar limites da API)\n")

    encontrados = 0
    nao_encontrados = 0

    for i, (record_id, citing_title) in enumerate(registos, 1):
        print(f"  [{i}/{total}] {citing_title[:60]}...")
        dados = enrich_with_delay(citing_title)

        if dados:
            c.execute("""
                UPDATE citations
                SET ss_doi            = ?,
                    ss_year           = ?,
                    ss_venue          = ?,
                    ss_citation_count = ?,
                    ss_url            = ?,
                    ss_enriched       = 1
                WHERE id = ?
            """, (
                dados.get("ss_doi"),
                dados.get("ss_year"),
                dados.get("ss_venue"),
                dados.get("ss_citation_count"),
                dados.get("ss_url"),
                record_id
            ))
            encontrados += 1
            print(f"         ✓ DOI: {dados.get('ss_doi')} | Citações: {dados.get('ss_citation_count')}")
        else:
            # Marca como tentado para não repetir
            c.execute("UPDATE citations SET ss_enriched = 1 WHERE id = ?", (record_id,))
            nao_encontrados += 1
            print(f"         — Não encontrado")

        conn.commit()

    conn.close()
    print(f"\n=== Concluído ===")
    print(f"  Enriquecidos com dados: {encontrados}")
    print(f"  Não encontrados:        {nao_encontrados}")
    print(f"  Total processados:      {total}")


if __name__ == "__main__":
    resposta = input("Quantos registos processar? (Enter = todos): ").strip()
    limite = int(resposta) if resposta.isdigit() else None
    run(limit=limite)
