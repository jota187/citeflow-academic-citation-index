from __future__ import annotations

import json
import os
from pathlib import Path
from typing import List, Dict, Any, Optional

from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

# Escopo: so leitura do Gmail
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")

CREDENTIALS_PATH = Path(os.getenv("GOOGLE_CREDENTIALS_PATH", PROJECT_ROOT / "credentials.json"))
TOKEN_PATH = Path(os.getenv("GOOGLE_TOKEN_PATH", PROJECT_ROOT / "token.json"))


def _load_json_env(var_name: str) -> Optional[dict]:
    raw = os.getenv(var_name, "").strip()
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        print(f"[AVISO] {var_name} nao contem JSON valido.")
        return None


def _write_json_if_missing(path: Path, data: dict) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def get_gmail_service():
    """
    Cria (ou reutiliza) uma ligacao autenticada a Gmail API.

    Na primeira vez:
      - abre o browser para autorizar o acesso
      - grava token.json com o token de acesso/refresh.
    Nas vezes seguintes:
      - reutiliza e, se preciso, renova esse token.
    """
    creds = None

    # 1) Token deve vir do .env
    token_info = _load_json_env("GOOGLE_TOKEN_JSON")
    if not token_info:
        raise RuntimeError("GOOGLE_TOKEN_JSON em .env e obrigatorio.")
    _write_json_if_missing(TOKEN_PATH, token_info)
    creds = Credentials.from_authorized_user_info(token_info, SCOPES)

    # 2) Se nao ha credenciais validas, faz o fluxo OAuth
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            # Renova automaticamente
            creds.refresh(Request())
        else:
            # Fluxo de autorizacao no browser
            creds_info = _load_json_env("GOOGLE_CREDENTIALS_JSON")
            if creds_info:
                _write_json_if_missing(CREDENTIALS_PATH, creds_info)
                flow = InstalledAppFlow.from_client_config(creds_info, SCOPES)
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(CREDENTIALS_PATH), SCOPES
                )
            creds = flow.run_local_server(port=0)

        # Guarda o token para reutilizar depois
        TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")

    # 3) Constroi o cliente da Gmail API
    service = build("gmail", "v1", credentials=creds)
    return service


def search_messages(
    service,
    query: str,
    max_results: Optional[int] = None
) -> List[Dict[str, Any]]:
    """
    Procura mensagens no Gmail usando a mesma sintaxe da caixa de pesquisa do Gmail.

    Exemplo de query:
      - 'from:(scholaralerts-noreply@google.com)'
      - 'label:citeflow-citations is:unread'

    Devolve uma lista de dicionarios simples com 'id' e 'threadId'.
    """
    messages: List[Dict[str, Any]] = []
    page_token = None
    remaining = max_results

    while True:
        page_size = 500 if remaining is None else min(500, remaining)
        if page_size <= 0:
            break

        response = service.users().messages().list(
            userId="me",
            q=query,
            maxResults=page_size,
            pageToken=page_token
        ).execute()

        batch = response.get("messages", [])
        messages.extend(batch)

        if remaining is not None:
            remaining -= len(batch)
            if remaining <= 0:
                break

        page_token = response.get("nextPageToken")
        if not page_token:
            break

    return messages


def get_message(service, message_id: str) -> Dict[str, Any]:
    """
    Vai buscar o conteudo completo de uma mensagem pelo ID.
    """
    message = service.users().messages().get(
        userId="me", id=message_id, format="full"
    ).execute()
    return message


if __name__ == "__main__":
    # Pequeno teste manual: listar alguns emails que correspondam a query
    service = get_gmail_service()
    query = "from:(scholaralerts-noreply@google.com)"
    msgs = search_messages(service, query=query, max_results=5)
    print(f"Encontradas {len(msgs)} mensagens para a query: {query}")
    for msg in msgs:
        print("-", msg.get("id"))
