import base64
from citeflow.gmail_client import get_gmail_service, search_messages, get_message
from citeflow.scholar_parser import parse_scholar_alert_html
from citeflow.db import init_db, get_connection


def get_html(payload):
    data = payload.get('body', {}).get('data', '')
    if data and payload.get('mimeType') == 'text/html':
        return base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
    for part in payload.get('parts', []):
        result = get_html(part)
        if result:
            return result
    return None

def run():
    init_db()

    max_emails = None
    print("A processar TODOS os emails disponiveis...")

    print("\n=== CiteFlow: Academic Citation Index ===")
    print(f"A iniciar pipeline...")

    service = get_gmail_service()
    msgs = search_messages(
        service,
        query='from:(scholaralerts-noreply@google.com)',
        max_results=max_emails
    )

    if not msgs:
        print("Nenhum email encontrado.")
        return

    # Normalizar: pode ser lista ou dict
    if isinstance(msgs, dict):
        msgs = [msgs]

    print(f"Emails encontrados: {len(msgs)}")

    novos = 0
    ignorados = 0

    conn = get_connection()
    cur = conn.cursor()
    pending_commits = 0
    commit_every = 50

    try:
        for msg_ref in msgs:
            msg_id = msg_ref.get('id') if isinstance(msg_ref, dict) else msg_ref
            msg = get_message(service, msg_id)
            html = get_html(msg.get('payload', {}))
            if not html:
                continue

            result = parse_scholar_alert_html(html)
            if not result or not result.get('citing_title'):
                continue

            email_message_id = msg.get('id', '')
            headers = msg.get('payload', {}).get('headers', [])
            headers_map = {h.get('name'): h.get('value', '') for h in headers}
            subject = headers_map.get('Subject', '')
            date_hdr = headers_map.get('Date', '')

            cur.execute(
                "SELECT id FROM citations WHERE email_message_id = ?",
                (email_message_id,)
            )
            if cur.fetchone():
                ignorados += 1
                continue

            cur.execute("""
                INSERT INTO citations (
                    platform, my_work_title, citing_title,
                    citing_authors, citing_venue, citing_snippet,
                    email_message_id, email_date,
                    raw_email_subject, raw_email_snippet
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                result.get('platform', 'scholar'),
                result.get('my_work_title', ''),
                result.get('citing_title', ''),
                result.get('citing_authors', ''),
                result.get('citing_venue', ''),
                result.get('citing_snippet', ''),
                email_message_id,
                date_hdr,
                subject,
                result.get('citing_snippet', '')[:200],
            ))
            pending_commits += 1
            if pending_commits >= commit_every:
                conn.commit()
                pending_commits = 0

            print(f"  [OK] {result.get('citing_title', '')[:60]}...")
            novos += 1

        if pending_commits:
            conn.commit()
    finally:
        conn.close()

    print(f"\n=== Concluído ===")
    print(f"  Novos registos: {novos}")
    print(f"  Já existentes (ignorados): {ignorados}")
    print(f"  Total processados: {novos + ignorados}")

if __name__ == "__main__":
    run()

