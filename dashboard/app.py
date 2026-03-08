import streamlit as st
import sqlite3
import pandas as pd
from pathlib import Path

# ── Caminho para a base de dados ──────────────────────────────────────────────
DB_PATH = Path(__file__).resolve().parents[1] / "data" / "citeflow.db"

# ── Carregar dados ────────────────────────────────────────────────────────────
@st.cache_data
def load_data():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM citations ORDER BY email_date DESC", conn)
    conn.close()
    return df

# ── Configuração da página ────────────────────────────────────────────────────
st.set_page_config(
    page_title="CiteFlow",
    page_icon="📚",
    layout="wide"
)

st.title("📚 CiteFlow: Academic Citation Index")
st.caption("Dashboard de citações académicas — Google Scholar")

# ── Carregar dados ────────────────────────────────────────────────────────────
df = load_data()

if df.empty:
    st.warning("Base de dados vazia. Corre primeiro o pipeline: python -m citeflow.main")
    st.stop()

# ── Métricas ──────────────────────────────────────────────────────────────────
col1, col2, col3 = st.columns(3)
col1.metric("Total de citações", len(df))
col2.metric("Artigos meus citados", df["my_work_title"].nunique())
col3.metric("Artigos que me citam", df["citing_title"].nunique())

st.divider()

# ── Filtros ───────────────────────────────────────────────────────────────────
st.subheader("🔍 Filtrar citações")

all_works = ["Todos"] + sorted(df["my_work_title"].dropna().unique().tolist())
selected_work = st.selectbox("Filtrar por artigo meu:", all_works)

if selected_work != "Todos":
    df_filtered = df[df["my_work_title"] == selected_work]
else:
    df_filtered = df

# ── Tabela ────────────────────────────────────────────────────────────────────
st.subheader(f"📋 Citações ({len(df_filtered)} registos)")

colunas_mostrar = [
    "my_work_title",
    "citing_title",
    "citing_authors",
    "citing_venue",
    "email_date",
]
# Mostrar só colunas que existem
colunas_existentes = [c for c in colunas_mostrar if c in df_filtered.columns]
st.dataframe(df_filtered[colunas_existentes], use_container_width=True)

st.divider()

# ── Gráfico: citações por artigo meu ─────────────────────────────────────────
st.subheader("📊 Citações por artigo meu")
contagem = df["my_work_title"].value_counts().reset_index()
contagem.columns = ["Artigo", "Citações"]
st.bar_chart(contagem.set_index("Artigo"))

st.divider()

# ── Rodapé ────────────────────────────────────────────────────────────────────
st.caption("CiteFlow v1.0 · Dados actualizados via Gmail API + SQLite")
