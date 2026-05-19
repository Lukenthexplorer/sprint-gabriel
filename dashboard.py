import warnings
warnings.filterwarnings("ignore")

import streamlit as st
import pandas as pd
import numpy as np
import h3
import folium
from streamlit_folium import st_folium
import plotly.express as px
import plotly.graph_objects as go
from scipy.ndimage import gaussian_filter

# ─── Configuração da página ───────────────────────────────────────────────────
st.set_page_config(
    page_title="Gabriel — Mancha Criminal RJ 2025",
    page_icon="🗺️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Estilos ──────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .metric-card {
        background: #1a1a2e;
        border-radius: 10px;
        padding: 18px 22px;
        border-left: 4px solid #e94560;
    }
    .metric-value { font-size: 2rem; font-weight: 700; color: #e94560; }
    .metric-label { font-size: 0.85rem; color: #aaa; margin-top: 4px; }
    .section-title {
        font-size: 1.1rem; font-weight: 600; color: #fff;
        border-bottom: 1px solid #333; padding-bottom: 6px; margin-bottom: 14px;
    }
</style>
""", unsafe_allow_html=True)

# ─── Cache: carregamento e processamento ──────────────────────────────────────
@st.cache_data(show_spinner=False)
def carregar_dados():
    occ_raw = pd.read_csv("ocorrencias.csv", parse_dates=["DataOcorrencia"])
    sen_raw = pd.read_csv("sensores.csv")
    sen_raw["DataInicioServico"] = pd.to_datetime(sen_raw["DataInicioServico"], errors="coerce")

    occ = (
        occ_raw
        .query('Cidade == "Rio de Janeiro" and Estado == "RJ"')
        .query('DataOcorrencia >= "2025-01-01" and DataOcorrencia <= "2025-12-31"')
        .dropna(subset=["Latitude", "Longitude", "DataOcorrencia"])
        .copy()
    )
    sen = (
        sen_raw
        .query('Cidade == "Rio de Janeiro" and Estado == "RJ"')
        .dropna(subset=["Latitude", "Longitude"])
        .copy()
    )

    def to_h3(lat, lon, res=8):
        try:
            return h3.latlng_to_cell(lat, lon, res)
        except Exception:
            return None

    occ["h3_cell"] = occ.apply(lambda r: to_h3(r["Latitude"], r["Longitude"]), axis=1)
    sen["h3_cell"] = sen.apply(lambda r: to_h3(r["Latitude"], r["Longitude"]), axis=1)
    occ = occ.dropna(subset=["h3_cell"])
    sen = sen.dropna(subset=["h3_cell"])

    occ["AnoMes"] = occ["DataOcorrencia"].dt.to_period("M")
    occ["AnoMes_str"] = occ["AnoMes"].astype(str)
    occ["CategoriaCrime"] = occ["CategoriaCrime"].fillna("Não classificado")

    cam_por_celula = (
        sen.groupby("h3_cell")["IDDispositivo"]
        .nunique()
        .reset_index()
        .rename(columns={"IDDispositivo": "n_camaleoes"})
    )

    occ_mensal = (
        occ.groupby(["AnoMes_str", "h3_cell"])
        .size()
        .reset_index(name="n_ocorrencias")
    )
    occ_mensal = occ_mensal.merge(cam_por_celula, on="h3_cell", how="left")
    occ_mensal["n_camaleoes"] = occ_mensal["n_camaleoes"].fillna(1)
    occ_mensal["taxa_normalizada"] = occ_mensal["n_ocorrencias"] / occ_mensal["n_camaleoes"]

    def centro_h3(c):
        lat, lon = h3.cell_to_latlng(c)
        return lat, lon

    occ_mensal[["centro_lat", "centro_lon"]] = occ_mensal["h3_cell"].apply(
        lambda c: pd.Series(centro_h3(c))
    )

    bairro_por_celula = (
        occ.groupby("h3_cell")["Bairro"]
        .agg(lambda x: x.mode().iloc[0] if not x.mode().empty else "N/A")
        .reset_index()
    )

    return occ, sen, occ_mensal, cam_por_celula, bairro_por_celula


@st.cache_data(show_spinner=False)
def calcular_delta(occ_mensal, bairro_por_celula, ini1, fim1, ini2, fim2):
    def media_janela(ini, fim):
        return (
            occ_mensal[(occ_mensal["AnoMes_str"] >= ini) & (occ_mensal["AnoMes_str"] <= fim)]
            .groupby("h3_cell")["taxa_normalizada"]
            .mean()
        )

    t1 = media_janela(ini1, fim1)
    t2 = media_janela(ini2, fim2)
    delta = (
        pd.DataFrame({"taxa_h1": t1, "taxa_h2": t2})
        .dropna()
        .assign(delta=lambda d: d["taxa_h2"] - d["taxa_h1"])
        .assign(delta_pct=lambda d: (d["delta"] / d["taxa_h1"].clip(lower=0.01)) * 100)
        .reset_index()
        .merge(bairro_por_celula, on="h3_cell", how="left")
    )
    return delta


@st.cache_data(show_spinner=False)
def calcular_centroide(occ_mensal):
    def _cw(df):
        w = df["n_ocorrencias"]
        return pd.Series({
            "lat": np.average(df["centro_lat"], weights=w),
            "lon": np.average(df["centro_lon"], weights=w),
            "total": int(w.sum()),
        })

    return (
        occ_mensal.groupby("AnoMes_str", sort=True)
        .apply(_cw)
        .reset_index()
    )


# ─── Carregar ─────────────────────────────────────────────────────────────────
with st.spinner("Carregando dados..."):
    occ, sen, occ_mensal, cam_por_celula, bairro_por_celula = carregar_dados()

# ─── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.image("https://i.imgur.com/placeholder.png", width=40) if False else None
    st.markdown("## 🗺️ Mancha Criminal")
    st.markdown("**Rio de Janeiro · 2025**")
    st.divider()

    categorias_disponiveis = ["Todas"] + sorted(occ["CategoriaCrime"].dropna().unique().tolist())
    categoria_sel = st.selectbox("Categoria de crime", categorias_disponiveis)

    zonas_disponiveis = ["Todas"] + sorted(occ["Zona"].dropna().unique().tolist())
    zona_sel = st.selectbox("Zona", zonas_disponiveis)

    st.divider()
    st.caption("Sprint INSPER · Gabriel · 2025")
    st.caption("Recorte: RJ · Granularidade H3-8 (~460m)")

# ─── Filtros dinâmicos ────────────────────────────────────────────────────────
occ_f = occ.copy()
if categoria_sel != "Todas":
    occ_f = occ_f[occ_f["CategoriaCrime"] == categoria_sel]
if zona_sel != "Todas":
    occ_f = occ_f[occ_f["Zona"] == zona_sel]

# Recalcular occ_mensal filtrado
occ_mensal_f = (
    occ_f.groupby(["AnoMes_str", "h3_cell"])
    .size()
    .reset_index(name="n_ocorrencias")
    .merge(cam_por_celula, on="h3_cell", how="left")
)
occ_mensal_f["n_camaleoes"] = occ_mensal_f["n_camaleoes"].fillna(1)
occ_mensal_f["taxa_normalizada"] = occ_mensal_f["n_ocorrencias"] / occ_mensal_f["n_camaleoes"]
h3_centros = occ_mensal["h3_cell"].drop_duplicates().apply(
    lambda c: pd.Series(h3.cell_to_latlng(c), index=["centro_lat", "centro_lon"])
)
h3_centros.index = occ_mensal["h3_cell"].drop_duplicates().values
occ_mensal_f = occ_mensal_f.merge(
    h3_centros.reset_index().rename(columns={"index": "h3_cell"}),
    on="h3_cell", how="left"
)

# ─── Header ───────────────────────────────────────────────────────────────────
st.markdown("# Movimentação da Mancha Criminal")
st.markdown("#### Rio de Janeiro · 2025 · Análise espaço-temporal por hexágonos H3")
st.divider()

# ─── KPIs ─────────────────────────────────────────────────────────────────────
total_occ = len(occ_f)
total_cam = sen["IDDispositivo"].nunique()

if occ_f.empty:
    pico_mes_idx = "—"
    pico_valor   = 0
    zona_lider   = "—"
else:
    _mensal      = occ_f.groupby("AnoMes_str").size()
    pico_mes_idx = _mensal.idxmax()
    pico_valor   = int(_mensal.max())
    zona_lider   = occ_f["Zona"].value_counts().idxmax().replace("Rio de Janeiro - ", "")

col1, col2, col3, col4 = st.columns(4)
kpis = [
    (f"{total_occ:,}", "Ocorrências em 2025"),
    (f"{total_cam:,}", "Camaleões ativos (RJ)"),
    (pico_mes_idx[-2:] + "/" + pico_mes_idx[:4], f"Mês de pico ({pico_valor} ocorrências)"),
    (zona_lider, "Zona com maior volume"),
]
for col, (val, label) in zip([col1, col2, col3, col4], kpis):
    col.markdown(
        f'<div class="metric-card"><div class="metric-value">{val}</div>'
        f'<div class="metric-label">{label}</div></div>',
        unsafe_allow_html=True,
    )

st.markdown("")

# ─── Linha do tempo ───────────────────────────────────────────────────────────
st.markdown('<div class="section-title">Evolução mensal de ocorrências</div>', unsafe_allow_html=True)

mensal_zona = (
    occ_f.groupby(["AnoMes_str", "Zona"])
    .size()
    .reset_index(name="n")
)
mensal_zona["Zona"] = mensal_zona["Zona"].str.replace("Rio de Janeiro - ", "")
mensal_total = occ_f.groupby("AnoMes_str").size().reset_index(name="n")
mensal_total["Zona"] = "Total"

fig_linha = px.line(
    mensal_zona,
    x="AnoMes_str", y="n", color="Zona",
    markers=True,
    color_discrete_sequence=["#e94560", "#0f3460", "#16213e", "#533483"],
    labels={"AnoMes_str": "Mês", "n": "Ocorrências", "Zona": "Zona"},
    template="plotly_dark",
)
fig_total = go.Scatter(
    x=mensal_total["AnoMes_str"], y=mensal_total["n"],
    name="Total", mode="lines+markers",
    line=dict(color="white", width=2, dash="dot"),
    marker=dict(size=5),
)
fig_linha.add_trace(fig_total)
fig_linha.update_layout(
    height=320,
    margin=dict(l=0, r=0, t=10, b=0),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    xaxis=dict(tickangle=-45),
    plot_bgcolor="#0d0d0d",
    paper_bgcolor="#0d0d0d",
)
st.plotly_chart(fig_linha, use_container_width=True)

# ─── Mapa animado + Ranking ───────────────────────────────────────────────────
col_mapa, col_rank = st.columns([3, 1], gap="large")

with col_mapa:
    st.markdown('<div class="section-title">Mapa de calor — selecione o mês</div>', unsafe_allow_html=True)

    if occ_f.empty:
        st.info("Nenhuma ocorrência encontrada para o filtro selecionado.")
    else:
        meses_disp = sorted(occ_f["AnoMes_str"].unique())
        MESES_PT = {"01":"Jan","02":"Fev","03":"Mar","04":"Abr","05":"Mai","06":"Jun",
                    "07":"Jul","08":"Ago","09":"Set","10":"Out","11":"Nov","12":"Dez"}
        meses_label = {m: MESES_PT.get(m[-2:], m) for m in meses_disp}

        mes_sel = st.select_slider(
            "Mês",
            options=meses_disp,
            format_func=lambda m: meses_label[m],
            label_visibility="collapsed",
        )

        sub = occ_f[occ_f["AnoMes_str"] == mes_sel]

        fig_heat = px.density_mapbox(
            sub,
            lat="Latitude",
            lon="Longitude",
            radius=18,
            zoom=11,
            center={"lat": occ_f["Latitude"].mean(), "lon": occ_f["Longitude"].mean()},
            mapbox_style="carto-darkmatter",
            color_continuous_scale=["#000033", "#000080", "#ff6600", "#ff0000", "#ffffff"],
            opacity=0.75,
            title=f"Ocorrências · {meses_label[mes_sel]}/2025 · {len(sub):,} registros",
        )
        fig_heat.update_layout(
            height=460,
            margin=dict(l=0, r=0, t=36, b=0),
            coloraxis_showscale=False,
            paper_bgcolor="#0d0d0d",
        )
        st.plotly_chart(fig_heat, use_container_width=True)

with col_rank:
    st.markdown('<div class="section-title">Ranking de bairros</div>', unsafe_allow_html=True)

    delta_df = calcular_delta(
        occ_mensal_f, bairro_por_celula,
        "2025-01", "2025-06",
        "2025-07", "2025-12",
    )

    tab_aq, tab_es = st.tabs(["🔴 Aquecendo", "🔵 Esfriando"])

    with tab_aq:
        top_aq = delta_df.nlargest(8, "delta")[["Bairro", "delta_pct"]].copy()
        top_aq["delta_pct"] = top_aq["delta_pct"].round(0).astype(int)
        top_aq.columns = ["Bairro", "Δ%"]
        top_aq["Δ%"] = top_aq["Δ%"].apply(lambda x: f"+{x}%")
        st.dataframe(top_aq, use_container_width=True, hide_index=True)

    with tab_es:
        top_es = delta_df.nsmallest(8, "delta")[["Bairro", "delta_pct"]].copy()
        top_es["delta_pct"] = top_es["delta_pct"].round(0).astype(int)
        top_es.columns = ["Bairro", "Δ%"]
        top_es["Δ%"] = top_es["Δ%"].apply(lambda x: f"{x}%")
        st.dataframe(top_es, use_container_width=True, hide_index=True)

    st.caption("Δ% = variação da taxa normalizada entre 1º e 2º semestre de 2025.")

# ─── Centróide + Categoria ────────────────────────────────────────────────────
col_c, col_cat = st.columns(2, gap="large")

with col_c:
    st.markdown('<div class="section-title">Trajetória do centróide da mancha</div>', unsafe_allow_html=True)

    centroides = calcular_centroide(occ_mensal_f)

    if centroides.empty:
        st.info("Sem dados suficientes para calcular o centróide.")
    else:
        mapa_cent = folium.Map(
            location=[centroides["lat"].mean(), centroides["lon"].mean()],
            zoom_start=12,
            tiles="CartoDB positron",
        )
        coords = centroides[["lat", "lon"]].values.tolist()
        folium.PolyLine(coords, color="#e94560", weight=3, opacity=0.9).add_to(mapa_cent)

        for _, row in centroides.iterrows():
            folium.CircleMarker(
                location=[row["lat"], row["lon"]],
                radius=5,
                color="#e94560",
                fill=True,
                fill_opacity=0.9,
                tooltip=f"{row['AnoMes_str']} | {int(row['total'])} ocorrências",
            ).add_to(mapa_cent)

        if len(coords) >= 1:
            folium.Marker(
                coords[0],
                tooltip="Janeiro/2025",
                icon=folium.Icon(color="green", icon="play"),
            ).add_to(mapa_cent)
        if len(coords) >= 2:
            folium.Marker(
                coords[-1],
                tooltip="Dezembro/2025",
                icon=folium.Icon(color="red", icon="stop"),
            ).add_to(mapa_cent)

        st_folium(mapa_cent, width=None, height=380, returned_objects=[])

with col_cat:
    st.markdown('<div class="section-title">Distribuição por categoria de crime</div>', unsafe_allow_html=True)

    cat_counts = occ_f["CategoriaCrime"].value_counts().head(10).reset_index()
    cat_counts.columns = ["Categoria", "n"]
    fig_cat = px.bar(
        cat_counts.sort_values("n"),
        x="n", y="Categoria",
        orientation="h",
        color="n",
        color_continuous_scale=["#16213e", "#e94560"],
        template="plotly_dark",
        labels={"n": "Ocorrências", "Categoria": ""},
    )
    fig_cat.update_layout(
        height=380,
        margin=dict(l=0, r=0, t=10, b=0),
        coloraxis_showscale=False,
        plot_bgcolor="#0d0d0d",
        paper_bgcolor="#0d0d0d",
    )
    st.plotly_chart(fig_cat, use_container_width=True)

    # Horário de pico
    st.markdown('<div class="section-title" style="margin-top:16px">Distribuição horária</div>', unsafe_allow_html=True)
    hora_counts = occ_f["Intervalo"].value_counts().reset_index()
    hora_counts.columns = ["Intervalo", "n"]
    hora_counts = hora_counts.sort_values("Intervalo")
    fig_hora = px.bar(
        hora_counts, x="Intervalo", y="n",
        color="n",
        color_continuous_scale=["#16213e", "#e94560"],
        template="plotly_dark",
        labels={"Intervalo": "Faixa horária", "n": "Ocorrências"},
    )
    fig_hora.update_layout(
        height=240,
        margin=dict(l=0, r=0, t=10, b=0),
        coloraxis_showscale=False,
        xaxis=dict(tickangle=-90, tickfont=dict(size=9)),
        plot_bgcolor="#0d0d0d",
        paper_bgcolor="#0d0d0d",
    )
    st.plotly_chart(fig_hora, use_container_width=True)

# ─── Footer ───────────────────────────────────────────────────────────────────
st.divider()
st.caption("Gabriel · Central de Monitoramento · Sprint INSPER 2025 · Dados: snapshot 18/05/2026 · Recorte: RJ/2025 · H3 resolução 8")
