import io
import os
import sqlite3
import tempfile
import time
import zipfile
from pathlib import Path

import pandas as pd
import requests
import streamlit as st


DB_PATH = Path(__file__).resolve().parents[1] / "data" / "citeflow.db"
REFRESH_INTERVAL_S = 24 * 60 * 60


def _get_secret(key: str) -> str:
    value = os.getenv(key, "")
    if value:
        return value
    try:
        return str(st.secrets.get(key, ""))
    except Exception:
        return ""


def _is_db_stale(path: Path, max_age_s: int) -> bool:
    if not path.exists():
        return True
    age_s = time.time() - path.stat().st_mtime
    return age_s > max_age_s


def _download_db_from_github() -> bool:
    repo = _get_secret("GITHUB_REPO")
    token = _get_secret("GITHUB_TOKEN")
    artifact_name = _get_secret("GITHUB_ARTIFACT_NAME") or "citeflow-db"

    if not repo or not token:
        return False

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "citeflow-streamlit/1.0",
    }

    url = f"https://api.github.com/repos/{repo}/actions/artifacts?per_page=100"
    resp = requests.get(url, headers=headers, timeout=30)
    if resp.status_code != 200:
        st.warning("Nao foi possivel listar artifacts no GitHub.")
        return False

    data = resp.json()
    artifacts = data.get("artifacts", []) or []
    candidates = [a for a in artifacts if a.get("name") == artifact_name and not a.get("expired")]
    if not candidates:
        st.warning("Nao foi encontrado artifact da BD.")
        return False

    candidates.sort(key=lambda a: a.get("created_at", ""), reverse=True)
    archive_url = candidates[0].get("archive_download_url")
    if not archive_url:
        return False

    resp = requests.get(archive_url, headers=headers, timeout=60)
    if resp.status_code != 200:
        st.warning("Falha ao descarregar o artifact da BD.")
        return False

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmpdir:
        zip_path = Path(tmpdir) / "db.zip"
        zip_path.write_bytes(resp.content)
        with zipfile.ZipFile(zip_path, "r") as zf:
            target = None
            for name in zf.namelist():
                if name.endswith("data/citeflow.db"):
                    target = name
                    break
            if not target:
                st.warning("Artifact nao contem data/citeflow.db.")
                return False
            zf.extract(target, tmpdir)
            extracted = Path(tmpdir) / target
            DB_PATH.write_bytes(extracted.read_bytes())

    return True


@st.cache_data
def load_data():
    if _is_db_stale(DB_PATH, REFRESH_INTERVAL_S):
        _download_db_from_github()
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM citations ORDER BY email_date DESC", conn)
    conn.close()
    return df


def make_doi_clickable(df_in):
    if "ss_doi" in df_in.columns:
        df_in = df_in.copy()
        df_in["ss_doi"] = df_in["ss_doi"].apply(
            lambda d: f"https://doi.org/{d}" if pd.notna(d) and str(d).strip() != "" else None
        )
    return df_in


def export_buttons(df_export: pd.DataFrame, filename_base: str):
    col_csv, col_xlsx, _ = st.columns([1, 1, 4])
    csv_data = df_export.to_csv(index=False).encode("utf-8")
    col_csv.download_button(
        label="⬇️ CSV",
        data=csv_data,
        file_name=f"{filename_base}.csv",
        mime="text/csv",
        help="Descarregar em formato CSV",
    )
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df_export.to_excel(writer, index=False, sheet_name="CiteFlow")
    excel_data = buffer.getvalue()
    col_xlsx.download_button(
        label="⬇️ Excel",
        data=excel_data,
        file_name=f"{filename_base}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        help="Descarregar em formato Excel (.xlsx)",
    )


def calcular_hindex(df: pd.DataFrame):
    contagem = (
        df.groupby("my_work_title")
        .size()
        .reset_index(name="citacoes")
        .sort_values("citacoes", ascending=False)
        .reset_index(drop=True)
    )
    contagem.index += 1
    h = 0
    for rank, row in contagem.iterrows():
        if row["citacoes"] >= rank:
            h = rank
        else:
            break
    return h, contagem


st.set_page_config(page_title="CiteFlow", page_icon="📚", layout="wide")
st.title("📚 CiteFlow: Academic Citation Index")
st.caption("Dashboard de citacoes academicas — Google Scholar + Semantic Scholar")

df = load_data()

if df.empty:
    st.warning("Base de dados vazia. Corre primeiro: python -m citeflow.main")
    st.stop()

df["email_date"] = pd.to_datetime(df["email_date"], errors="coerce", utc=True)
df["email_date"] = df["email_date"].dt.tz_convert(None)
df["year"] = df["email_date"].dt.year

hindex_global, tabela_hindex = calcular_hindex(df)

st.sidebar.header("🔎 Modo de visualizacao")

modo = st.sidebar.radio(
    "O que pretendes ver?",
    [
        "📋 Todas as citacoes",
        "🕐 N citacoes mais recentes",
        "📌 Citacoes de um ano especifico",
        "📆 Citacoes num periodo de anos",
        "🏆 Artigos meus mais citados",
        "📐 H-Index",
        "🔬 Dados Semantic Scholar",
    ],
)

df_filtered = df.copy()

if modo == "🕐 N citacoes mais recentes":
    st.sidebar.markdown("---")
    n = st.sidebar.number_input("Numero de citacoes:", min_value=1, max_value=len(df), value=min(50, len(df)), step=10)
    df_filtered = df.sort_values("email_date", ascending=False).head(int(n))

elif modo == "📌 Citacoes de um ano especifico":
    st.sidebar.markdown("---")
    anos = sorted(df["year"].dropna().unique().astype(int), reverse=True)
    ano = st.sidebar.selectbox("Escolhe o ano:", anos)
    df_filtered = df[df["year"] == ano]

elif modo == "📆 Citacoes num periodo de anos":
    st.sidebar.markdown("---")
    anos = sorted(df["year"].dropna().unique().astype(int))
    ano_ini = st.sidebar.selectbox("De (ano):", anos, index=0)
    ano_fim = st.sidebar.selectbox("Ate (ano):", sorted(anos, reverse=True), index=0)
    if ano_ini > ano_fim:
        st.sidebar.error("O ano inicial nao pode ser maior que o ano final.")
        st.stop()
    df_filtered = df[(df["year"] >= ano_ini) & (df["year"] <= ano_fim)]

elif modo == "🏆 Artigos meus mais citados":
    st.sidebar.markdown("---")
    n_top = st.sidebar.number_input("Quantos artigos mostrar?", min_value=1, max_value=df["my_work_title"].nunique(), value=min(10, df["my_work_title"].nunique()), step=1)
    contagem = df["my_work_title"].value_counts().head(int(n_top)).reset_index()
    contagem.columns = ["Artigo", "Citacoes"]
    st.subheader(f"🏆 Top {int(n_top)} artigos meus mais citados")
    col1, col2 = st.columns(2)
    col1.metric("Total de citacoes na BD", len(df))
    col2.metric("Artigos meus com citacoes", df["my_work_title"].nunique())
    st.bar_chart(contagem.set_index("Artigo"))
    st.dataframe(contagem, use_container_width=True)
    export_buttons(contagem, filename_base="citeflow_top_artigos")
    st.divider()
    st.caption(f"CiteFlow v1.3 · {len(df)} citacoes totais · Gmail API + Semantic Scholar")
    st.stop()

elif modo == "📐 H-Index":
    st.subheader("📐 H-Index aproximado")

    col1, col2, col3 = st.columns(3)
    col1.metric("H-Index (aproximado)", hindex_global,
                help="Baseado nas citacoes registadas nesta base de dados")
    col2.metric("Total de citacoes", len(df))
    col3.metric("Artigos com citacoes", df["my_work_title"].nunique())

    st.info(
        f"**Como interpretar:** tens **h-index ≈ {hindex_global}**, "
        f"o que significa que tens pelo menos **{hindex_global} artigos** "
        f"com pelo menos **{hindex_global} citacoes** cada. "
        "Valor aproximado — baseado apenas nas citacoes registadas nesta BD."
    )

    st.divider()

    st.subheader("📋 Citacoes por artigo")
    tabela_display = tabela_hindex.copy()
    tabela_display.index.name = "Rank"
    tabela_display.columns = ["Artigo", "Citacoes na BD"]
    tabela_display["Conta para h-index?"] = tabela_display.apply(
        lambda row: "✅ Sim" if row["Citacoes na BD"] >= row.name else "❌ Nao",
        axis=1,
    )
    st.dataframe(tabela_display, use_container_width=True)
    export_buttons(tabela_display.reset_index(), filename_base="citeflow_hindex")

    st.divider()

    st.subheader("📊 Grafico do H-Index")
    grafico = tabela_hindex.copy()
    grafico.columns = ["Artigo", "Citacoes"]
    grafico["Rank"] = grafico.index
    grafico["H-Index (linha)"] = hindex_global
    st.line_chart(grafico.set_index("Rank")[["Citacoes", "H-Index (linha)"]])
    st.caption(
        "Linha azul = citacoes por artigo (ordem decrescente). "
        "Linha laranja = valor do h-index. "
        "O cruzamento define o h-index."
    )

    st.divider()

    st.subheader("📈 Evolucao do H-Index por ano")
    anos_disponiveis = sorted(df["year"].dropna().unique().astype(int))
    hindex_por_ano = []
    for ano in anos_disponiveis:
        df_ate_ano = df[df["year"] <= ano]
        h, _ = calcular_hindex(df_ate_ano)
        hindex_por_ano.append({"Ano": ano, "H-Index acumulado": h})
    df_hindex_anos = pd.DataFrame(hindex_por_ano).set_index("Ano")
    st.line_chart(df_hindex_anos)
    st.caption("H-Index calculado com todas as citacoes ate cada ano (valor acumulado).")

    st.divider()
    st.caption(f"CiteFlow v1.3 · {len(df)} citacoes totais · Gmail API + Semantic Scholar")
    st.stop()

elif modo == "🔬 Dados Semantic Scholar":
    st.sidebar.markdown("---")
    st.subheader("🔬 Enriquecimento Semantic Scholar")

    total = len(df)
    enriquecidos = int(df["ss_enriched"].sum()) if "ss_enriched" in df.columns else 0
    nao_enriquecidos = total - enriquecidos
    pct = round(enriquecidos / total * 100, 1) if total > 0 else 0

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total de registos", total)
    col2.metric("Enriquecidos ✅", enriquecidos)
    col3.metric("Por enriquecer ⏳", nao_enriquecidos)
    col4.metric("Cobertura", f"{pct}%")

    st.progress(pct / 100, text=f"{pct}% dos registos enriquecidos com dados da Semantic Scholar")
    st.divider()

    df_ss = df[df["ss_enriched"] == 1].copy() if "ss_enriched" in df.columns else pd.DataFrame()

    if df_ss.empty:
        st.info("Ainda nao ha dados da Semantic Scholar. Corre: python -m citeflow.enrich")
    else:
        st.subheader(f"📋 Citacoes com dados enriquecidos ({len(df_ss)} registos)")
        df_ss = make_doi_clickable(df_ss)
        colunas_ss = ["citing_title", "ss_venue", "ss_year", "ss_citation_count", "ss_doi", "my_work_title"]
        colunas_ex = [c for c in colunas_ss if c in df_ss.columns]
        df_tabela = df_ss[colunas_ex].rename(columns={
            "citing_title":      "Artigo citante",
            "ss_venue":          "Venue (SS)",
            "ss_year":           "Ano (SS)",
            "ss_citation_count": "Citacoes do artigo",
            "ss_doi":            "DOI",
            "my_work_title":     "Meu artigo citado",
        }).sort_values("Citacoes do artigo", ascending=False, na_position="last")

        col_config = {}
        if "DOI" in df_tabela.columns:
            col_config["DOI"] = st.column_config.LinkColumn(
                "DOI", help="Clica para abrir o artigo", display_text="🔗 Abrir",
            )
        if "Citacoes do artigo" in df_tabela.columns:
            col_config["Citacoes do artigo"] = st.column_config.NumberColumn(
                "Citacoes do artigo",
                help="Numero de vezes que este artigo foi citado (fonte: Semantic Scholar)",
                format="%d",
            )

        st.dataframe(df_tabela, use_container_width=True, column_config=col_config)
        export_buttons(df_tabela, filename_base="citeflow_semantic_scholar")
        st.divider()

        st.subheader("📊 Top 20 artigos citantes com mais citacoes (SS)")
        if "ss_citation_count" in df_ss.columns:
            top20 = (
                df_ss[["citing_title", "ss_citation_count"]]
                .dropna(subset=["ss_citation_count"])
                .sort_values("ss_citation_count", ascending=False)
                .head(20)
                .set_index("citing_title")
            )
            if not top20.empty:
                st.bar_chart(top20)
            else:
                st.info("Sem dados de citacoes disponiveis.")

        st.divider()

        st.subheader("📰 Venues mais frequentes (SS)")
        if "ss_venue" in df_ss.columns:
            venues = (
                df_ss["ss_venue"]
                .dropna()
                .loc[lambda s: s.str.strip() != ""]
                .value_counts()
                .head(15)
                .reset_index()
            )
            venues.columns = ["Venue", "Nº de artigos"]
            if not venues.empty:
                st.bar_chart(venues.set_index("Venue"))
            else:
                st.info("Sem dados de venue disponiveis.")

    st.divider()
    st.caption(f"CiteFlow v1.3 · {len(df)} citacoes totais · Gmail API + Semantic Scholar")
    st.stop()


st.subheader("📊 Resumo")
col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Citacoes encontradas", len(df_filtered))
col2.metric("Artigos meus citados", df_filtered["my_work_title"].nunique())
col3.metric("Artigos que me citam", df_filtered["citing_title"].nunique())
enriquecidos_filtro = int(df_filtered["ss_enriched"].sum()) if "ss_enriched" in df_filtered.columns else 0
col4.metric("Enriquecidos (SS)", enriquecidos_filtro)
col5.metric("H-Index ≈", hindex_global, help="Calculado sobre todas as citacoes da BD")

st.divider()

st.subheader("🔍 Filtro adicional")
artigos = ["(todos)"] + sorted(df_filtered["my_work_title"].dropna().unique().tolist())
artigo_sel = st.selectbox("Filtrar por artigo meu:", artigos)
if artigo_sel != "(todos)":
    df_filtered = df_filtered[df_filtered["my_work_title"] == artigo_sel]

pesquisa = st.text_input("🔍 Pesquisa livre (titulo, autor, venue...)", value="")
if pesquisa.strip():
    mask = df_filtered.apply(
        lambda row: row.astype(str).str.contains(pesquisa, case=False, na=False).any(),
        axis=1,
    )
    df_filtered = df_filtered[mask]

st.subheader(f"📋 Citacoes ({len(df_filtered)} registos)")

df_tabela_main = make_doi_clickable(df_filtered)
colunas_mostrar = ["my_work_title", "citing_title", "citing_authors", "citing_venue", "email_date", "ss_citation_count", "ss_doi"]
colunas_existentes = [c for c in colunas_mostrar if c in df_tabela_main.columns]

col_config_main = {}
if "ss_doi" in colunas_existentes:
    col_config_main["ss_doi"] = st.column_config.LinkColumn(
        "DOI",
        help="Clica para abrir o artigo",
        display_text="🔗 Abrir",
    )
if "ss_citation_count" in colunas_existentes:
    col_config_main["ss_citation_count"] = st.column_config.NumberColumn(
        "Citacoes (SS)",
        help="Citacoes do artigo citante na Semantic Scholar",
        format="%d",
    )

df_para_tabela = df_tabela_main[colunas_existentes].sort_values("email_date", ascending=False)

st.dataframe(df_para_tabela, use_container_width=True, column_config=col_config_main)
export_buttons(df_para_tabela, filename_base="citeflow_citacoes")

st.divider()

st.subheader("📈 Citacoes por ano")
por_ano = df_filtered.groupby("year", dropna=True).size().reset_index(name="Citacoes").sort_values("year")
por_ano["year"] = por_ano["year"].astype(str)
st.bar_chart(por_ano.set_index("year"))

st.subheader("📈 Citacoes acumuladas ao longo do tempo")
acumuladas = (
    df_filtered.groupby("year", dropna=True)
    .size()
    .reset_index(name="Novas")
    .sort_values("year")
)
acumuladas["Acumuladas"] = acumuladas["Novas"].cumsum()
acumuladas["year"] = acumuladas["year"].astype(str)
st.line_chart(acumuladas.set_index("year")["Acumuladas"])

st.divider()
st.caption(f"CiteFlow v1.3 · {len(df)} citacoes totais · Gmail API + Semantic Scholar")

