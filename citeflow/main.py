from __future__ import annotations
import base64
import sqlite3
from datetime import datetime
from pathlib import Path

from citeflow.gmail_client import get_gmail_service, search_messages, get_message
from citeflow.scholar_parser import parse_scholar_alert_html
from citeflow.db import get_connection, init_db


def get_html_from_message(msg: dict) -> str | None:
    """Extrai o HTML do corpo de um email da Gmail API."""
    def _extract(payload):
        data = payload.get("body", {}).get("data", "")
        if data and payload.get("mimeType") == "text/html":
            return base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
        for part in payload.get("parts", []):
            result = _extract(part)
            if result:
                return result
        return None
    return _extract(msg.get("payload", {}))


def is_already_processed(conn: sqlite3.Connection, email_message_id: str) -> bool:
    """Verifica se este email já foi processado antes."""
    cur = conn.cursor()
    cur.execute(
        "SELECT id FROM citations WHERE email_message_id = ?",
        (email_message_id,)
    )
    return cur.fetchone() is not None


def save_citation(conn: sqlite3.Connection, data: dict, email_message_id: str, email_date: str):
    """Guarda uma citação na base de dados."""
    cur = conn.cursor()
    cur.execute("""
        INSERT OR IGNORE INTO citations (
            platform,
            my_work_title,
            citing_title,
            citing_authors,
            citing_venue,
            citing_snippet,
            citing_url,
            email_message_id,
            email_date,
            created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        data.get("platform"),
        data.get("my_work_title"),
        data.get("citing_title"),
        data.get("citing_authors"),
        data.get("citing_venue"),
        data.get("citing_snippet"),
        data.get("citing_url"),
        email_message_id,
        email_date,
        datetime.now().isoformat(),
    ))
    conn.commit()


def run(max_emails: int = 50):
    """
    Pipeline principal do CiteFlow:
    Gmail → Parser → SQLite
    """
    print("=== CiteFlow: Academic Citation Index ===")
    print(f"A iniciar pipeline... (max {max_emails} emails)")

    # 1. Inicializar base de dados
    init_db()
    conn = get_connection()

    # 2. Ligar ao Gmail
    service = get_gmail_service()
    query = "from:(scholaralerts-noreply@google.com)"
    messages = search_messages(service, query=query, max_results=max_emails)
    print(f"Emails encontrados: {len(messages)}")

    # 3. Processar cada email
    novos = 0
    ignorados = 0

    for msg_ref in messages:
        email_id = msg_ref["id"]

        # Verificar se já foi processado
        if is_already_processed(conn, email_id):
            ignorados += 1
            continue

        # Ir buscar o email completo
        msg = get_message(service, email_id)
        email_date = str(msg.get("internalDate", ""))

        # Extrair HTML
        html = get_html_from_message(msg)
        if not html:
            print(f"  [AVISO] Email {email_id} sem HTML — ignorado.")
            continue

        # Fazer parsing
        data = parse_scholar_alert_html(html)

        # Guardar na base de dados
        save_citation(conn, data, email_id, email_date)
        novos += 1
        print(f"  [OK] {data.get('citing_title', 'sem título')[:60]}...")

    conn.close()

    print()
    print(f"=== Concluído ===")
    print(f"  Novos registos: {novos}")
    print(f"  Já existentes (ignorados): {ignorados}")
    print(f"  Total processados: {novos + ignorados}")


if __name__ == "__main__":
    run()
