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




executar projeto:

.venv\Scripts\activate --------------> ativar ambiente virtual
pip install -r requirements.txt -----> instalar requirnments
deactivate --------------------------> desativar ambiente virtual

-------------------------------------> qd o projeto estiver concluido não é necessário executar
del data\citeflow.db ----------------> apaga base de dados
python -m citeflow.db ---------------> cria base de dados


python -m citeflow.main -------------------->  importar emails novos
python -m citeflow.enrich ------------------> enriquecer (opcional, é lento)
streamlit run dashboard/app.py -> ---------->ver o dashboard