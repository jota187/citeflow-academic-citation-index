from __future__ import annotations

from pathlib import Path
from typing import List, Dict, Any

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

# Escopo: só leitura do Gmail
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CREDENTIALS_PATH = PROJECT_ROOT / "credentials.json"
TOKEN_PATH = PROJECT_ROOT / "token.json"


def get_gmail_service():
    """
    Cria (ou reutiliza) uma ligação autenticada à Gmail API.

    Na primeira vez:
      - abre o browser para autorizar o acesso
      - grava token.json com o token de acesso/refresh.
    Nas vezes seguintes:
      - reutiliza e, se preciso, renova esse token.
    """
    creds = None

    # 1) Se já existe token.json, tenta reutilizar
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

    # 2) Se não há credenciais válidas, faz o fluxo OAuth
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            # Renova automaticamente
            creds.refresh(Request())
        else:
            # Fluxo de autorização no browser
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CREDENTIALS_PATH), SCOPES
            )
            creds = flow.run_local_server(port=0)

        # Guarda o token para reutilizar depois
        TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")

    # 3) Constroi o cliente da Gmail API
    service = build("gmail", "v1", credentials=creds)
    return service


def search_messages(service, query: str, max_results: int = 50) -> List[Dict[str, Any]]:
    """
    Procura mensagens no Gmail usando a mesma sintaxe da caixa de pesquisa do Gmail.

    Exemplo de query:
      - 'from:(scholaralerts-noreply@google.com)'
      - 'label:citeflow-citations is:unread'

    Devolve uma lista de dicionários simples com 'id' e 'threadId'.
    """
    response = service.users().messages().list(
        userId="me", q=query, maxResults=max_results
    ).execute()

    messages = response.get("messages", [])
    return messages


def get_message(service, message_id: str) -> Dict[str, Any]:
    """
    Vai buscar o conteúdo completo de uma mensagem pelo ID.
    """
    message = service.users().messages().get(
        userId="me", id=message_id, format="full"
    ).execute()
    return message


if __name__ == "__main__":
    # Pequeno teste manual: listar alguns emails que correspondam à query
    service = get_gmail_service()
    query = "from:(scholaralerts-noreply@google.com)"
    msgs = search_messages(service, query=query, max_results=5)
    print(f"Encontradas {len(msgs)} mensagens para a query: {query}")
    for msg in msgs:
        print("-", msg.get("id"))
