# citeflow/db.py
from pathlib import Path
import sqlite3


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / "data" / "citeflow.db"


def init_db():
    """Cria a base de dados e a tabela citations (se não existirem)."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS citations (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            platform          TEXT,
            my_work_title     TEXT,
            citing_title      TEXT,
            citing_authors    TEXT,
            citing_venue      TEXT,
            citing_snippet    TEXT,
            citing_url        TEXT,
            email_date        TEXT,
            raw_email_subject TEXT,
            email_message_id  TEXT,
            raw_email_snippet TEXT,

            -- Campos enriquecidos pela Semantic Scholar
            ss_doi            TEXT,
            ss_year           INTEGER,
            ss_venue          TEXT,
            ss_citation_count INTEGER,
            ss_url            TEXT,
            ss_enriched       INTEGER DEFAULT 0
        )
    """)

    # Adicionar colunas novas se a BD já existia sem elas
    existing = {row[1] for row in c.execute("PRAGMA table_info(citations)")}
    new_columns = {
        "email_message_id":  "TEXT",
        "raw_email_snippet": "TEXT",
        "ss_doi":            "TEXT",
        "ss_year":           "INTEGER",
        "ss_venue":          "TEXT",
        "ss_citation_count": "INTEGER",
        "ss_url":            "TEXT",
        "ss_enriched":       "INTEGER DEFAULT 0",
        "ss_enriched_at":    "TEXT",
        "ss_enriched_run_id": "TEXT",
        "ss_doi_source":     "TEXT",
    }
    for col, col_type in new_columns.items():
        if col not in existing:
            c.execute(f"ALTER TABLE citations ADD COLUMN {col} {col_type}")
            print(f"  [DB] Coluna adicionada: {col}")

    conn.commit()
    conn.close()


def get_connection():
    """Devolve uma ligação à base de dados."""
    return sqlite3.connect(DB_PATH)


if __name__ == "__main__":
    init_db()
    print(f"Base de dados inicializada em {DB_PATH}")
