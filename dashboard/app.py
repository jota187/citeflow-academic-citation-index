import io
import os
import sqlite3
import tempfile
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
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


def _get_github_headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "citeflow-streamlit/1.0",
    }


def _parse_github_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        # GitHub uses ISO 8601 like "2024-01-01T12:34:56Z"
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def _get_latest_artifact_meta() -> tuple[str | None, str | None, dict | None]:
    repo = _get_secret("GITHUB_REPO")
    token = _get_secret("GITHUB_TOKEN")
    artifact_name = _get_secret("GITHUB_ARTIFACT_NAME") or "citeflow-db"

    if not repo or not token:
        return None, None, None

    headers = _get_github_headers(token)
    url = f"https://api.github.com/repos/{repo}/actions/artifacts?per_page=100"
    resp = requests.get(url, headers=headers, timeout=30)
    if resp.status_code != 200:
        st.warning("Nao foi possivel listar artifacts no GitHub.")
        return None, None, None

    data = resp.json()
    artifacts = data.get("artifacts", []) or []
    candidates = [a for a in artifacts if a.get("name") == artifact_name and not a.get("expired")]
    if not candidates:
        st.warning("Nao foi encontrado artifact da BD.")
        return None, None, None

    candidates.sort(key=lambda a: a.get("created_at", ""), reverse=True)
    created_at = candidates[0].get("created_at")
    archive_url = candidates[0].get("archive_download_url")
    return created_at, archive_url, headers


def _artifact_is_newer(created_at: str | None, path: Path) -> bool:
    if not created_at:
        return False
    remote_dt = _parse_github_datetime(created_at)
    if not remote_dt:
        return False
    if not path.exists():
        return True
    local_dt = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    return remote_dt > local_dt


def _download_db_from_github(archive_url: str | None, headers: dict | None) -> bool:
    if not archive_url or not headers:
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
                if name.endswith("data/citeflow.db") or name.endswith("citeflow.db"):
                    target = name
                    break
            if not target:
                st.warning("Artifact nao contem citeflow.db.")
                return False
            zf.extract(target, tmpdir)
            extracted = Path(tmpdir) / target
            DB_PATH.write_bytes(extracted.read_bytes())

    return True


def _format_dt_lisbon(dt: datetime | None) -> str:
    if not dt:
        return "desconhecida"
    return dt.astimezone(ZoneInfo("Europe/Lisbon")).strftime("%d/%m/%Y %H:%M")


def _ensure_latest_db() -> tuple[float, str | None, bool]:
    created_at, archive_url, headers = _get_latest_artifact_meta()
    downloaded = False
    if not DB_PATH.exists():
        downloaded = _download_db_from_github(archive_url, headers)
    elif _artifact_is_newer(created_at, DB_PATH):
        downloaded = _download_db_from_github(archive_url, headers)
    if not DB_PATH.exists():
        return 0.0, created_at, downloaded
    return DB_PATH.stat().st_mtime, created_at, downloaded


@st.cache_data(ttl=REFRESH_INTERVAL_S)
def load_data(db_mtime: float):
    if not DB_PATH.exists():
        st.error("Base de dados nao encontrada. Verifica se o artifact existe e se os secrets do GitHub estao configurados.")
        return pd.DataFrame()
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


def _non_empty_str_series(series: pd.Series) -> pd.Series:
    return series.notna() & series.astype(str).str.strip().ne("")


def _doi_mask(df_in: pd.DataFrame) -> pd.Series:
    if "ss_doi" not in df_in.columns:
        return pd.Series([False] * len(df_in), index=df_in.index)
    return _non_empty_str_series(df_in["ss_doi"])


def _semantic_mask(df_in: pd.DataFrame) -> pd.Series:
    mask = pd.Series([False] * len(df_in), index=df_in.index)
    if "ss_url" in df_in.columns:
        mask |= _non_empty_str_series(df_in["ss_url"])
    if "ss_venue" in df_in.columns:
        mask |= _non_empty_str_series(df_in["ss_venue"])
    if "ss_year" in df_in.columns:
        mask |= df_in["ss_year"].notna()
    if "ss_citation_count" in df_in.columns:
        mask |= df_in["ss_citation_count"].notna()
    return mask


def _latest_ss_run_counts(df_in: pd.DataFrame) -> tuple[int, int, int]:
    if "ss_doi" not in df_in.columns:
        return 0, 0, 0
    if "ss_enriched_run_id" not in df_in.columns:
        total = int(_non_empty_str_series(df_in["ss_doi"]).sum())
        return 0, total, total

    run_id = df_in["ss_enriched_run_id"].dropna().max()
    if not run_id:
        return 0, 0, 0

    in_run = df_in["ss_enriched_run_id"] == run_id
    has_doi = _non_empty_str_series(df_in["ss_doi"])
    source_col = df_in["ss_doi_source"].fillna("") if "ss_doi_source" in df_in.columns else pd.Series("", index=df_in.index)
    is_cr = source_col.str.lower().eq("cr")
    is_ss = source_col.str.lower().eq("ss")

    # Fallback: infer source when missing
    has_ss_meta = pd.Series([False] * len(df_in), index=df_in.index)
    if "ss_url" in df_in.columns:
        has_ss_meta |= _non_empty_str_series(df_in["ss_url"])
    if "ss_venue" in df_in.columns:
        has_ss_meta |= _non_empty_str_series(df_in["ss_venue"])
    if "ss_year" in df_in.columns:
        has_ss_meta |= df_in["ss_year"].notna()
    if "ss_citation_count" in df_in.columns:
        has_ss_meta |= df_in["ss_citation_count"].notna()

    inferred_ss = has_doi & has_ss_meta & ~is_cr & ~is_ss
    inferred_cr = has_doi & ~has_ss_meta & ~is_cr & ~is_ss

    cr_count = int((in_run & has_doi & (is_cr | inferred_cr)).sum())
    ss_count = int((in_run & has_doi & (is_ss | inferred_ss)).sum())
    return cr_count, ss_count, cr_count + ss_count


def export_buttons(df_export: pd.DataFrame, filename_base: str, container=st):
    col_csv, col_xlsx = container.columns(2)
    csv_data = df_export.to_csv(index=False).encode("utf-8")
    col_csv.download_button(
        label="⬇️ CSV",
        data=csv_data,
        file_name=f"{filename_base}.csv",
        mime="text/csv",
        help="Descarregar em formato CSV",
        use_container_width=True,
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
        use_container_width=True,
    )


def calcular_hindex(df: pd.DataFrame):
    contagem = (
        df.groupby("my_work_title")
        .size()
        .reset_index(name="citações")
        .sort_values("citações", ascending=False)
        .reset_index(drop=True)
    )
    contagem.index += 1
    h = 0
    for rank, row in contagem.iterrows():
        if row["citações"] >= rank:
            h = rank
        else:
            break
    return h, contagem


st.set_page_config(page_title="CiteFlow", page_icon="📚", layout="wide")
st.title("📚 CiteFlow: Academic Citation Index")
st.caption("Dashboard de citações académicas — Google Scholar + CrossRef + Semantic Scholar")

db_mtime, artifact_created_at, downloaded = _ensure_latest_db()
df = load_data(db_mtime)

db_mtime_dt = datetime.fromtimestamp(db_mtime, tz=timezone.utc) if db_mtime else None
base_dt = _parse_github_datetime(artifact_created_at) or db_mtime_dt
st.caption(f"Base de Dados: {_format_dt_lisbon(base_dt)}")

if df.empty:
    st.warning("Base de dados vazia. Corre primeiro: python -m citeflow.main")
    st.stop()

df["email_date"] = pd.to_datetime(df["email_date"], errors="coerce", utc=True)
df["email_date"] = df["email_date"].dt.tz_convert(None)
df["year"] = df["email_date"].dt.year

hindex_global, tabela_hindex = calcular_hindex(df)

st.sidebar.header("🔎 Modo de visualizacao")

modo = st.sidebar.radio(
    "Citações a consultar",
    [
        "📋 Todas",
        "🕐 Mais recentes",
        "📌 Por ano",
        "📆 Por período",
        "🏆 Mais citados",
        "📐 H-Index",
        "🔬 Dados CrossRef",
        "🔬 Dados Semantic Scholar",
    ],
)

df_filtered = df.copy()

if modo == "🕐 Mais recentes":
    st.sidebar.markdown("---")
    n = st.sidebar.number_input("Número de citações:", min_value=1, max_value=len(df), value=min(50, len(df)), step=10)
    df_filtered = df.sort_values("email_date", ascending=False).head(int(n))

elif modo == "📌 Por ano":
    st.sidebar.markdown("---")
    anos = sorted(df["year"].dropna().unique().astype(int), reverse=True)
    ano = st.sidebar.selectbox("Escolhe o ano:", anos)
    df_filtered = df[df["year"] == ano]

elif modo == "📆 Por período":
    st.sidebar.markdown("---")
    anos = sorted(df["year"].dropna().unique().astype(int))
    ano_ini = st.sidebar.selectbox("De (ano):", anos, index=0)
    ano_fim = st.sidebar.selectbox("Ate (ano):", sorted(anos, reverse=True), index=0)
    if ano_ini > ano_fim:
        st.sidebar.error("O ano inicial nao pode ser maior que o ano final.")
        st.stop()
    df_filtered = df[(df["year"] >= ano_ini) & (df["year"] <= ano_fim)]

elif modo == "🏆 Mais citados":
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
    st.sidebar.markdown("---")
    export_buttons(contagem, filename_base="citeflow_top_artigos", container=st.sidebar)
    st.divider()
    st.caption(f"CiteFlow v1.3 · {len(df)} citações totais · Gmail API + Semantic Scholar")
    st.stop()

elif modo == "📐 H-Index":
    st.subheader("📐 H-Index aproximado")

    col1, col2, col3 = st.columns(3)
    col1.metric("H-Index (aproximado)", hindex_global,
                help="Baseado nas citações registadas nesta base de dados")
    col2.metric("Total de citações", len(df))
    col3.metric("Artigos com citações", df["my_work_title"].nunique())

    st.info(
        f"**Como interpretar:** tens **h-index ≈ {hindex_global}**, "
        f"o que significa que tens pelo menos **{hindex_global} artigos** "
        f"com pelo menos **{hindex_global} citações** cada. "
        "Valor aproximado — baseado apenas nas citações registadas nesta BD."
    )

    st.divider()

    st.subheader("📋 Citações por artigo")
    tabela_display = tabela_hindex.copy()
    tabela_display.index.name = "Rank"
    tabela_display.columns = ["Artigo", "Citações na BD"]
    tabela_display["Conta para h-index?"] = tabela_display.apply(
        lambda row: "✅ Sim" if row["Citações na BD"] >= row.name else "❌ Nao",
        axis=1,
    )
    st.dataframe(tabela_display, use_container_width=True)
    st.sidebar.markdown("---")
    export_buttons(tabela_display.reset_index(), filename_base="citeflow_hindex", container=st.sidebar)

    st.divider()

    st.subheader("📊 Grafico do H-Index")
    grafico = tabela_hindex.copy()
    grafico.columns = ["Artigo", "Citações"]
    grafico["Rank"] = grafico.index
    grafico["H-Index (linha)"] = hindex_global
    st.line_chart(grafico.set_index("Rank")[["Citações", "H-Index (linha)"]])
    st.caption(
        "Linha azul = citações por artigo (ordem decrescente). "
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
    st.caption("H-Index calculado com todas as citações ate cada ano (valor acumulado).")

    st.divider()
    st.caption(f"CiteFlow v1.3 · {len(df)} citações totais · Gmail API + Semantic Scholar")
    st.stop()

elif modo == "🔬 Dados CrossRef":
    st.sidebar.markdown("---")
    st.subheader("🔗 Enriquecimento CrossRef")
    st.caption("Critério: registos com DOI identificado e sem dados da Semantic Scholar.")

    total = len(df)
    mask_semantic = _semantic_mask(df)
    mask_crossref = _doi_mask(df) & ~mask_semantic
    enriquecidos = int(mask_crossref.sum())
    nao_enriquecidos = total - enriquecidos
    pct = round(enriquecidos / total * 100, 1) if total > 0 else 0

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total de registos", total)
    col2.metric("Enriquecidos ✅", enriquecidos)
    col3.metric("Por enriquecer ⏳", nao_enriquecidos)
    col4.metric("Cobertura", f"{pct}%")

    st.progress(pct / 100, text=f"{pct}% dos registos enriquecidos com dados do CrossRef")
    st.divider()

    df_cr = df[mask_crossref].copy()

    if df_cr.empty:
        st.info("Ainda nao ha dados do CrossRef. Corre: python -m citeflow.enrich")
    else:
        st.subheader(f"📋 Citações com dados enriquecidos ({len(df_cr)} registos)")
        df_cr = make_doi_clickable(df_cr)
        colunas_ss = ["citing_title", "ss_doi", "my_work_title"]
        colunas_ex = [c for c in colunas_ss if c in df_cr.columns]
        df_tabela = df_cr[colunas_ex].rename(columns={
            "citing_title":      "Artigo citante",
            "ss_doi":            "DOI",
            "my_work_title":     "Meu artigo citado",
        })

        col_config = {}
        if "DOI" in df_tabela.columns:
            col_config["DOI"] = st.column_config.LinkColumn(
                "DOI", help="Clica para abrir o artigo", display_text="🔗 Abrir",
            )

        st.dataframe(df_tabela, use_container_width=True, column_config=col_config)
        st.sidebar.markdown("---")
        export_buttons(df_tabela, filename_base="citeflow_crossref", container=st.sidebar)
        st.divider()

    st.divider()
    st.caption(f"CiteFlow v1.3 · {len(df)} citações totais · Gmail API + CrossRef + Semantic Scholar")
    st.stop()

elif modo == "🔬 Dados Semantic Scholar":
    st.sidebar.markdown("---")
    st.subheader("🔬 Enriquecimento Semantic Scholar")
    st.caption("Critério: registos com pelo menos um campo da Semantic Scholar (URL, venue, ano ou citações).")

    total = len(df)
    mask_semantic = _semantic_mask(df)
    enriquecidos = int(mask_semantic.sum())
    nao_enriquecidos = total - enriquecidos
    pct = round(enriquecidos / total * 100, 1) if total > 0 else 0

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total de registos", total)
    col2.metric("Enriquecidos ✅", enriquecidos)
    col3.metric("Por enriquecer ⏳", nao_enriquecidos)
    col4.metric("Cobertura", f"{pct}%")

    st.progress(pct / 100, text=f"{pct}% dos registos enriquecidos com dados da Semantic Scholar")
    st.divider()

    df_ss = df[mask_semantic].copy()

    if df_ss.empty:
        st.info("Ainda nao ha dados da Semantic Scholar. Corre: python -m citeflow.enrich")
    else:
        st.subheader(f"📋 Citações com dados enriquecidos ({len(df_ss)} registos)")
        df_ss = make_doi_clickable(df_ss)
        colunas_ss = ["citing_title", "ss_venue", "ss_year", "ss_citation_count", "ss_doi", "my_work_title"]
        colunas_ex = [c for c in colunas_ss if c in df_ss.columns]
        df_tabela = df_ss[colunas_ex].rename(columns={
            "citing_title":      "Artigo citante",
            "ss_venue":          "Venue (SS)",
            "ss_year":           "Ano (SS)",
            "ss_citation_count": "Citações do artigo",
            "ss_doi":            "DOI",
            "my_work_title":     "Meu artigo citado",
        }).sort_values("Citações do artigo", ascending=False, na_position="last")

        col_config = {}
        if "DOI" in df_tabela.columns:
            col_config["DOI"] = st.column_config.LinkColumn(
                "DOI", help="Clica para abrir o artigo", display_text="🔗 Abrir",
            )
        if "Citações do artigo" in df_tabela.columns:
            col_config["Citações do artigo"] = st.column_config.NumberColumn(
                "Citações do artigo",
                help="Numero de vezes que este artigo foi citado (fonte: Semantic Scholar)",
                format="%d",
            )

        st.dataframe(df_tabela, use_container_width=True, column_config=col_config)
        st.sidebar.markdown("---")
        export_buttons(df_tabela, filename_base="citeflow_semantic_scholar", container=st.sidebar)
        st.divider()

        st.subheader("📊 Top 20 artigos citantes com mais citações (SS)")
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
                st.info("Sem dados de citações disponiveis.")

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
    st.caption(f"CiteFlow v1.3 · {len(df)} citações totais · Gmail API + Semantic Scholar")
    st.stop()


st.subheader("📊 Resumo")
col1, col2, col3, col4, col5, col6 = st.columns(6)
col1.metric("Citações encontradas", len(df_filtered))
col2.metric("Artigos citados", df_filtered["my_work_title"].nunique())
col3.metric("Artigos", df_filtered["citing_title"].nunique())
enriq_cr, enriq_ss, enriq_total = _latest_ss_run_counts(df_filtered)
col4.metric("Enriquecidos (CR) DOI", enriq_cr)
col5.metric("Enriquecidos (SS) DOI", enriq_ss)
col6.metric("Total enriquecidos", enriq_total)

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

st.subheader(f"📋 Citações ({len(df_filtered)} registos)")

df_tabela_main = make_doi_clickable(df_filtered)
colunas_mostrar = ["my_work_title", "citing_title", "citing_authors", "citing_venue", "ss_doi"]
colunas_existentes = [c for c in colunas_mostrar if c in df_tabela_main.columns]

col_config_main = {}
if "ss_doi" in colunas_existentes:
    col_config_main["ss_doi"] = st.column_config.LinkColumn(
        "DOI",
        help="Clica para abrir o artigo",
        display_text="🔗 Abrir",
    )
df_para_tabela = (
    df_tabela_main
    .sort_values("email_date", ascending=False)
    [colunas_existentes]
    .rename(columns={
        "my_work_title": "Artigo citado",
        "citing_title": "Artigo",
        "citing_authors": "Autores",
        "citing_venue": "Publicação",
    })
)

st.dataframe(df_para_tabela, use_container_width=True, column_config=col_config_main)
st.sidebar.markdown("---")
export_buttons(df_para_tabela, filename_base="citeflow_citacoes", container=st.sidebar)

st.divider()

st.subheader("📈 Citações por ano")
por_ano = df_filtered.groupby("year", dropna=True).size().reset_index(name="Citações").sort_values("year")
por_ano["year"] = por_ano["year"].astype(str)
st.bar_chart(por_ano.set_index("year"))

st.subheader("📈 Citações acumuladas ao longo do tempo")
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
st.caption(f"CiteFlow v1.3 · {len(df)} citações totais · Gmail API + Semantic Scholar")
