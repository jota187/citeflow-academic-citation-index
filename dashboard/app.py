import streamlit as st
import sqlite3
import pandas as pd
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[1] / "data" / "citeflow.db"

@st.cache_data
def load_data():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM citations ORDER BY email_date DESC", conn)
    conn.close()
    return df

st.set_page_config(page_title="CiteFlow", page_icon="📚", layout="wide")
st.title("📚 CiteFlow: Academic Citation Index")
st.caption("Dashboard de citações académicas — Google Scholar + Semantic Scholar")

df = load_data()

if df.empty:
    st.warning("Base de dados vazia. Corre primeiro: python -m citeflow.main")
    st.stop()

# ── Converter datas e extrair ano ─────────────────────────────────────────────
df["email_date"] = pd.to_datetime(df["email_date"], errors="coerce", utc=True)
df["email_date"] = df["email_date"].dt.tz_convert(None)
df["year"] = df["email_date"].dt.year

# ════════════════════════════════════════════════════════════════════════════════
# PAINEL LATERAL
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
        "🔬 Dados Semantic Scholar",
    ],
)

df_filtered = df.copy()

if modo == "🕐 N citações mais recentes":
    st.sidebar.markdown("---")
    n = st.sidebar.number_input("Número de citações:", min_value=1, max_value=len(df), value=min(50, len(df)), step=10)
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
    ano_fim = st.sidebar.selectbox("Até (ano):", sorted(anos, reverse=True), index=0)
    if ano_ini > ano_fim:
        st.sidebar.error("⚠️ O ano inicial não pode ser maior que o ano final.")
        st.stop()
    df_filtered = df[(df["year"] >= ano_ini) & (df["year"] <= ano_fim)]

elif modo == "🏆 Artigos meus mais citados":
    st.sidebar.markdown("---")
    n_top = st.sidebar.number_input("Quantos artigos mostrar?", min_value=1, max_value=df["my_work_title"].nunique(), value=min(10, df["my_work_title"].nunique()), step=1)
    contagem = df["my_work_title"].value_counts().head(int(n_top)).reset_index()
    contagem.columns = ["Artigo", "Citações"]
    st.subheader(f"🏆 Top {int(n_top)} artigos meus mais citados")
    col1, col2 = st.columns(2)
    col1.metric("Total de citações na BD", len(df))
    col2.metric("Artigos meus com citações", df["my_work_title"].nunique())
    st.bar_chart(contagem.set_index("Artigo"))
    st.dataframe(contagem, use_container_width=True)
    st.divider()
    st.caption(f"CiteFlow v1.2 · {len(df)} citações totais · Gmail API + Semantic Scholar")
    st.stop()

elif modo == "🔬 Dados Semantic Scholar":
    st.sidebar.markdown("---")
    st.subheader("🔬 Enriquecimento Semantic Scholar")

    total = len(df)
    enriquecidos = int(df["ss_enriched"].sum()) if "ss_enriched" in df.columns else 0
    pct = round(enriquecidos / total * 100, 1) if total > 0 else 0

    col1, col2, col3 = st.columns(3)
    col1.metric("Total de registos", total)
    col2.metric("Enriquecidos", enriquecidos)
    col3.metric("Cobertura", f"{pct}%")

    st.divider()

    # Registos com DOI
    df_ss = df[df["ss_enriched"] == 1].copy() if "ss_enriched" in df.columns else pd.DataFrame()

    if df_ss.empty:
        st.info("Ainda não há dados da Semantic Scholar. Corre: python -m citeflow.enrich")
    else:
        st.subheader("📋 Citações com dados enriquecidos")

        # Tornar DOI clicável
        if "ss_doi" in df_ss.columns:
            df_ss["DOI"] = df_ss["ss_doi"].apply(
                lambda d: f"https://doi.org/{d}" if pd.notna(d) and d else ""
            )

        colunas_ss = ["citing_title", "ss_venue", "ss_year", "ss_citation_count", "ss_doi", "my_work_title"]
        colunas_ex = [c for c in colunas_ss if c in df_ss.columns]

        st.dataframe(
            df_ss[colunas_ex].rename(columns={
                "citing_title":      "Artigo citante",
                "ss_venue":          "Venue (SS)",
                "ss_year":           "Ano (SS)",
                "ss_citation_count": "Citações do artigo",
                "ss_doi":            "DOI",
                "my_work_title":     "Meu artigo citado",
            }).sort_values("Citações do artigo", ascending=False, na_position="last"),
            use_container_width=True,
        )

        st.divider()
        st.subheader("📊 Distribuição de citações dos artigos citantes")
        if "ss_citation_count" in df_ss.columns:
            contagem_ss = df_ss["ss_citation_count"].dropna()
            if not contagem_ss.empty:
                st.bar_chart(contagem_ss.value_counts().sort_index())

    st.divider()
    st.caption(f"CiteFlow v1.2 · {len(df)} citações totais · Gmail API + Semantic Scholar")
    st.stop()


# ════════════════════════════════════════════════════════════════════════════════
# MÉTRICAS GERAIS
# ════════════════════════════════════════════════════════════════════════════════
st.subheader("📊 Resumo")
col1, col2, col3, col4 = st.columns(4)
col1.metric("Citações encontradas", len(df_filtered))
col2.metric("Artigos meus citados", df_filtered["my_work_title"].nunique())
col3.metric("Artigos que me citam", df_filtered["citing_title"].nunique())
enriquecidos_filtro = int(df_filtered["ss_enriched"].sum()) if "ss_enriched" in df_filtered.columns else 0
col4.metric("Enriquecidos (SS)", enriquecidos_filtro)

st.divider()

# ── Filtro adicional por artigo meu ──────────────────────────────────────────
st.subheader("🔍 Filtro adicional")
artigos = ["(todos)"] + sorted(df_filtered["my_work_title"].dropna().unique().tolist())
artigo_sel = st.selectbox("Filtrar por artigo meu:", artigos)
if artigo_sel != "(todos)":
    df_filtered = df_filtered[df_filtered["my_work_title"] == artigo_sel]

# ── Tabela ────────────────────────────────────────────────────────────────────
st.subheader(f"📋 Citações ({len(df_filtered)} registos)")
colunas_mostrar = ["my_work_title", "citing_title", "citing_authors", "citing_venue", "email_date", "ss_citation_count", "ss_doi"]
colunas_existentes = [c for c in colunas_mostrar if c in df_filtered.columns]
st.dataframe(
    df_filtered[colunas_existentes].sort_values("email_date", ascending=False),
    use_container_width=True,
)

st.divider()

# ── Gráfico por ano ───────────────────────────────────────────────────────────
st.subheader("📅 Citações por ano")
por_ano = df_filtered.groupby("year", dropna=True).size().reset_index(name="Citações").sort_values("year")
por_ano["year"] = por_ano["year"].astype(str)
st.bar_chart(por_ano.set_index("year"))

st.divider()
st.caption(f"CiteFlow v1.2 · {len(df)} citações totais · Gmail API + Semantic Scholar")
