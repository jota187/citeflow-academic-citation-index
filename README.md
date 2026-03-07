# CiteFlow: Academic Citation Index

CiteFlow é uma ferramenta pessoal que lê alertas de citação do Google Scholar no Gmail, usa a API da Semantic Scholar para obter metadados completos dos artigos que citam o teu trabalho, e guarda tudo numa base de dados SQLite para consulta e análise.

## Stack (V1)

- Python 3
- Gmail API (read-only)
- Semantic Scholar API
- SQLite
- Streamlit

## Estado do projeto

- [ ] Fase 1 – Motor de recolha (Gmail → Semantic Scholar → SQLite)
- [ ] Fase 2 – Dashboard Streamlit
- [ ] Fase 3 – Polimento (config, logging, testes)




executar projeto: python -m citeflow.db

del data\citeflow.db
python -m citeflow.db
python -m citeflow.main

instalamos: pip install beautifulsoup4