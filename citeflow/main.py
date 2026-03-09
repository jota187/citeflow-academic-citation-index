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

    # ── Perguntar quantos emails processar ───────────────────────────────
    resposta = input(
        "\nQuantos emails de citações quer processar? "
        "(número, ex: 100) ou Enter para TODOS: "
    ).strip()

    if resposta == "":
        max_emails = None
        print("→ A processar TODOS os emails disponíveis...")
    elif resposta.isdigit() and int(resposta) > 0:
        max_emails = int(resposta)
        print(f"→ A processar os {max_emails} emails mais recentes...")
    else:
        print("Valor inválido. A usar 100 por defeito.")
        max_emails = 100

    print("\n=== CiteFlow: Academic Citation Index ===")
    print(f"A iniciar pipeline...")

    service = get_gmail_service()
    msgs = search_messages(
        service,
        query='from:(scholaralerts-noreply@google.com)',
        max_results=max_emails if max_emails else 500
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
        subject = msg.get('payload', {}).get('headers', [])
        subject = next((h['value'] for h in subject if h['name'] == 'Subject'), '')
        date_hdr = msg.get('payload', {}).get('headers', [])
        date_hdr = next((h['value'] for h in date_hdr if h['name'] == 'Date'), '')

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
        conn.commit()
        print(f"  [OK] {result.get('citing_title', '')[:60]}...")
        novos += 1


    conn.close()

    print(f"\n=== Concluído ===")
    print(f"  Novos registos: {novos}")
    print(f"  Já existentes (ignorados): {ignorados}")
    print(f"  Total processados: {novos + ignorados}")

if __name__ == "__main__":
    run()
