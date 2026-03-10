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
    st.warning("Base de dados vazia. Corre primeiro: python -m citeflow.main")
    st.stop()


# ── Converter datas e extrair ano ─────────────────────────────────────────────
df["email_date"] = pd.to_datetime(df["email_date"], errors="coerce", utc=True)
df["email_date"] = df["email_date"].dt.tz_localize(None) if df["email_date"].dt.tz is None else df["email_date"].dt.tz_convert(None)
df["year"] = df["email_date"].dt.year.where(df["email_date"].notna())



# ════════════════════════════════════════════════════════════════════════════════
# PAINEL LATERAL — MODO DE VISUALIZAÇÃO
# ════════════════════════════════════════════════════════════════════════════════
st.sidebar.header("🔎 Modo de visualização")

modo = st.sidebar.radio(
    "O que pretendes ver?",
    [
        "📋 Todas as citações",
        "🕐 N citações mais recentes",
        "📅 Citações de um ano específico",
        "📆 Citações num período de anos",
        "🏆 Artigos meus mais citados",
    ],
)


# ── Aplicar filtro de modo ────────────────────────────────────────────────────
df_filtered = df.copy()

if modo == "🕐 N citações mais recentes":
    st.sidebar.markdown("---")
    n = st.sidebar.number_input(
        "Número de citações a mostrar:",
        min_value=1,
        max_value=len(df),
        value=min(50, len(df)),
        step=10,
    )
    df_filtered = df.sort_values("email_date", ascending=False).head(int(n))

elif modo == "📅 Citações de um ano específico":
    st.sidebar.markdown("---")
    anos = sorted(df["year"].dropna().unique().astype(int), reverse=True)
    ano = st.sidebar.selectbox("Escolhe o ano:", anos)
    df_filtered = df[df["year"] == ano]

elif modo == "📆 Citações num período de anos":
    st.sidebar.markdown("---")
    anos = sorted(df["year"].dropna().unique().astype(int))
    ano_ini = st.sidebar.selectbox("De (ano):", anos, index=0)
    anos_fim = sorted(anos, reverse=True)
    ano_fim = st.sidebar.selectbox("Até (ano):", anos_fim, index=0)
    if ano_ini > ano_fim:
        st.sidebar.error("⚠️ O ano inicial não pode ser maior que o ano final.")
        st.stop()
    df_filtered = df[(df["year"] >= ano_ini) & (df["year"] <= ano_fim)]

elif modo == "🏆 Artigos meus mais citados":
    st.sidebar.markdown("---")
    n_top = st.sidebar.number_input(
        "Quantos artigos mostrar?",
        min_value=1,
        max_value=df["my_work_title"].nunique(),
        value=min(10, df["my_work_title"].nunique()),
        step=1,
    )
    contagem = (
        df["my_work_title"]
        .value_counts()
        .head(int(n_top))
        .reset_index()
    )
    contagem.columns = ["Artigo", "Citações"]

    st.subheader(f"🏆 Top {int(n_top)} artigos meus mais citados")
    col1, col2 = st.columns(2)
    col1.metric("Total de citações na BD", len(df))
    col2.metric("Artigos meus com citações", df["my_work_title"].nunique())

    st.bar_chart(contagem.set_index("Artigo"))
    st.dataframe(contagem, use_container_width=True)
    st.divider()
    st.caption(f"CiteFlow v1.1 · {len(df)} citações totais · Gmail API + SQLite")
    st.stop()


# ════════════════════════════════════════════════════════════════════════════════
# MÉTRICAS (para todos os modos excepto "Artigos mais citados")
# ════════════════════════════════════════════════════════════════════════════════
st.subheader("📊 Resumo")
col1, col2, col3 = st.columns(3)
col1.metric("Citações encontradas", len(df_filtered))
col2.metric("Artigos meus citados", df_filtered["my_work_title"].nunique())
col3.metric("Artigos que me citam", df_filtered["citing_title"].nunique())


st.divider()


# ── Filtro adicional por artigo meu ──────────────────────────────────────────
st.subheader("🔍 Filtro adicional")
artigos = ["(todos)"] + sorted(df_filtered["my_work_title"].dropna().unique().tolist())
artigo_sel = st.selectbox("Filtrar por artigo meu:", artigos)
if artigo_sel != "(todos)":
    df_filtered = df_filtered[df_filtered["my_work_title"] == artigo_sel]


# ── Tabela ────────────────────────────────────────────────────────────────────
st.subheader(f"📋 Citações ({len(df_filtered)} registos)")
colunas_mostrar = [
    "my_work_title",
    "citing_title",
    "citing_authors",
    "citing_venue",
    "email_date",
]
colunas_existentes = [c for c in colunas_mostrar if c in df_filtered.columns]
st.dataframe(
    df_filtered[colunas_existentes].sort_values("email_date", ascending=False),
    use_container_width=True,
)


st.divider()


# ── Gráfico: citações por ano ─────────────────────────────────────────────────
st.subheader("📅 Citações por ano")
por_ano = (
    df_filtered.groupby("year", dropna=True)
    .size()
    .reset_index(name="Citações")
    .sort_values("year")
)
por_ano["year"] = por_ano["year"].astype(str)
st.bar_chart(por_ano.set_index("year"))


st.divider()


# ── Rodapé ────────────────────────────────────────────────────────────────────
st.caption(f"CiteFlow v1.1 · {len(df)} citações totais · Gmail API + SQLite")
