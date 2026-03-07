from pathlib import Path
import sqlite3

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / "data" / "citeflow.db"


def get_connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    return conn


def init_db():
    create_table_sql = """
    CREATE TABLE IF NOT EXISTS citations (
        id INTEGER PRIMARY KEY,
        platform TEXT,
        my_work_title TEXT,
        citing_title TEXT,
        citing_authors TEXT,
        citing_venue TEXT,
        citing_snippet TEXT,
        citing_url TEXT,
        email_message_id TEXT UNIQUE,
        email_date TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
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
    init_db()
    print(f"Base de dados inicializada em {DB_PATH}")
