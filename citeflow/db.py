from pathlib import Path
import sqlite3

# Caminho para o ficheiro da base de dados: <raiz>/data/citeflow.db
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / "data" / "citeflow.db"


def get_connection():
    """
    Abre uma ligação à base de dados SQLite.
    Garante que a pasta data/ existe.
    """
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    return conn


def init_db():
    """
    Cria a tabela citations se ainda não existir.
    """
    create_table_sql = """
    CREATE TABLE IF NOT EXISTS citations (
        id INTEGER PRIMARY KEY,
        platform TEXT NOT NULL,
        my_work_title TEXT NOT NULL,
        citing_title TEXT NOT NULL,
        citing_authors TEXT,
        citing_year INTEGER,
        citing_venue TEXT,
        doi TEXT,
        semantic_scholar_paper_id TEXT,
        email_message_id TEXT UNIQUE,
        email_date TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        citing_abstract TEXT,
        citing_citation_count INTEGER,
        semantic_scholar_url TEXT,
        pdf_url TEXT,
        match_confidence REAL,
        raw_email_subject TEXT,
        raw_email_snippet TEXT
    );
    """

    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(create_table_sql)
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    # Permite correr: python -m citeflow.db
    init_db()
    print(f"Base de dados inicializada em {DB_PATH}")
