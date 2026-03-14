# CiteFlow: Academic Citation Index

CiteFlow e uma ferramenta pessoal que le alertas de citacao do Google Scholar no Gmail, usa a API da Semantic Scholar para obter metadados completos dos artigos que citam o teu trabalho, e guarda tudo numa base de dados SQLite para consulta e analise.

## Stack (V1)

- Python 3
- Gmail API (read-only)
- Semantic Scholar API
- SQLite
- Streamlit

## Estado do projeto

- Fase 1 - Motor de recolha (Gmail -> Semantic Scholar -> SQLite)
- Fase 2 - Dashboard Streamlit
- Fase 3 - Polimento (config, logging, testes)

## Executar projeto

ativar ambiente virtual:
```
.venv\Scripts\activate
```

instalar requirements:
```
pip install -r requirements.txt
```

desativar ambiente virtual:
```
deactivate
```

apaga a base de dados:
```
del data\citeflow.db
```

cria base de dados:
```
python -m citeflow.db
```

importa emails novos:
```
python -m citeflow.main
```

enriquecer a BD:
```
python -m citeflow.enrich
```

ver o dashboard:
```
streamlit run dashboard/app.py
```

## Configuracao local (.env)

Cria um ficheiro `.env` na raiz com UMA das opcoes:

Opcao A (JSON no .env) - obrigatoria para token:
```
GOOGLE_CREDENTIALS_JSON={...}
GOOGLE_TOKEN_JSON={...}
```

Opcao B (paths locais) - apenas para credentials:
```
GOOGLE_CREDENTIALS_PATH=credentials.json
GOOGLE_TOKEN_PATH=token.json
```

Podes usar `.env.example` como base.

Variaveis opcionais para ajustar o ritmo de chamadas (em segundos):
- `SEMANTIC_SCHOLAR_DELAY_S` (default: 1.2)
- `CROSSREF_DELAY_S` (default: 5.0)

## GitHub Actions (pipeline agendado)

Este projeto pode correr automaticamente no GitHub Actions. A pipeline:
- cria/atualiza a BD a partir dos emails
- tenta obter DOI via Crossref e, se falhar, via Semantic Scholar
- publica a BD como artefacto

Secrets necessarios (Settings -> Secrets and variables -> Actions):
- `GOOGLE_CREDENTIALS_JSON` (conteudo completo do credentials.json)
- `GOOGLE_TOKEN_JSON` (conteudo completo do token.json com refresh_token)
- `SEMANTIC_SCHOLAR_API_KEY` (opcional, recomendado)
- `CROSSREF_MAILTO` (opcional, recomendado)
- `SEMANTIC_SCHOLAR_DELAY_S` (opcional)
- `CROSSREF_DELAY_S` (opcional)

Nota: o `token.json` deve ser gerado localmente uma vez (OAuth), e depois guardado como secret.
