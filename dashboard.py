import warnings
warnings.filterwarnings("ignore")

import streamlit as st
import pandas as pd
import numpy as np
import h3
import plotly.express as px
import plotly.graph_objects as go

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


# ─── Helpers ──────────────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def build_geojson(cells: tuple) -> dict:
    features = []
    for cell in sorted(set(cells)):
        boundary = h3.cell_to_boundary(cell)
        coords   = [[lng, lat] for lat, lng in boundary]
        coords.append(coords[0])
        features.append({
            "type": "Feature",
            "properties": {"h3_index": cell},
            "geometry": {"type": "Polygon", "coordinates": [coords]},
        })
    return {"type": "FeatureCollection", "features": features}


# ─── Carregamento e processamento ─────────────────────────────────────────────
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

    occ["AnoMes_str"]    = occ["DataOcorrencia"].dt.to_period("M").astype(str)
    occ["CategoriaCrime"] = occ["CategoriaCrime"].fillna("Não classificado")

    cam_por_celula = (
        sen.groupby("h3_cell")["IDDispositivo"]
        .nunique()
        .reset_index()
        .rename(columns={"IDDispositivo": "n_camaleoes"})
    )

    bairro_por_celula = (
        occ.groupby("h3_cell")["Bairro"]
        .agg(lambda x: x.mode().iloc[0] if not x.mode().empty else "N/A")
        .reset_index()
    )

    return occ, sen, cam_por_celula, bairro_por_celula


@st.cache_data(show_spinner=False)
def agregar_mensal(occ_f: pd.DataFrame, cam_por_celula: pd.DataFrame) -> pd.DataFrame:
    agg = (
        occ_f.groupby(["AnoMes_str", "h3_cell"], as_index=False)
        .size()
        .rename(columns={"size": "qtd_ocorrencias"})
        .merge(cam_por_celula, on="h3_cell", how="left")
    )
    agg["n_camaleoes"]      = agg["n_camaleoes"].fillna(1)
    agg["taxa_normalizada"] = agg["qtd_ocorrencias"] / agg["n_camaleoes"]

    centros = (
        agg["h3_cell"]
        .drop_duplicates()
        .apply(lambda c: pd.Series(h3.cell_to_latlng(c), index=["centro_lat", "centro_lon"]))
    )
    centros.index = agg["h3_cell"].drop_duplicates().values
    agg = agg.merge(centros.reset_index().rename(columns={"index": "h3_cell"}), on="h3_cell", how="left")
    return agg


@st.cache_data(show_spinner=False)
def calcular_delta(agg: pd.DataFrame, bairro_por_celula: pd.DataFrame) -> pd.DataFrame:
    def media(ini, fim):
        return (
            agg[(agg["AnoMes_str"] >= ini) & (agg["AnoMes_str"] <= fim)]
            .groupby("h3_cell")["taxa_normalizada"].mean()
        )

    t1 = media("2025-01", "2025-06")
    t2 = media("2025-07", "2025-12")
    return (
        pd.DataFrame({"taxa_h1": t1, "taxa_h2": t2})
        .dropna()
        .assign(delta    = lambda d: d["taxa_h2"] - d["taxa_h1"])
        .assign(delta_pct= lambda d: (d["delta"] / d["taxa_h1"].clip(lower=0.01)) * 100)
        .reset_index()
        .merge(bairro_por_celula, on="h3_cell", how="left")
    )


@st.cache_data(show_spinner=False)
def calcular_centroide(agg: pd.DataFrame) -> pd.DataFrame:
    def _cw(df):
        w = df["qtd_ocorrencias"]
        return pd.Series({
            "lat"  : np.average(df["centro_lat"], weights=w),
            "lon"  : np.average(df["centro_lon"], weights=w),
            "total": int(w.sum()),
        })
    return agg.groupby("AnoMes_str", sort=True).apply(_cw).reset_index()


# ─── Carregar dados ───────────────────────────────────────────────────────────
with st.spinner("Carregando dados..."):
    occ, sen, cam_por_celula, bairro_por_celula = carregar_dados()

# ─── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🗺️ Mancha Criminal")
    st.markdown("**Rio de Janeiro · 2025**")
    st.divider()

    cat_opts  = ["Todas"] + sorted(occ["CategoriaCrime"].dropna().unique().tolist())
    zona_opts = ["Todas"] + sorted(occ["Zona"].dropna().unique().tolist())

    categoria_sel = st.selectbox("Categoria de crime", cat_opts)
    zona_sel      = st.selectbox("Zona", zona_opts)

    st.divider()
    st.caption("Sprint INSPER · Gabriel · 2025")
    st.caption("Recorte: RJ · Granularidade H3-8 (~460 m)")

# ─── Filtros dinâmicos ────────────────────────────────────────────────────────
occ_f = occ.copy()
if categoria_sel != "Todas":
    occ_f = occ_f[occ_f["CategoriaCrime"] == categoria_sel]
if zona_sel != "Todas":
    occ_f = occ_f[occ_f["Zona"] == zona_sel]

# ─── Header ───────────────────────────────────────────────────────────────────
st.markdown("# Movimentação da Mancha Criminal")
st.markdown("#### Rio de Janeiro · 2025 · Hexágonos H3 resolução 8 (~460 m)")
st.divider()

# ─── KPIs ─────────────────────────────────────────────────────────────────────
total_occ = len(occ_f)
total_cam = sen["IDDispositivo"].nunique()

if occ_f.empty:
    pico_label = "—"
    pico_valor = 0
    zona_lider = "—"
else:
    _mensal    = occ_f.groupby("AnoMes_str").size()
    pico_idx   = _mensal.idxmax()
    pico_valor = int(_mensal.max())
    MESES_PT   = {"01":"Jan","02":"Fev","03":"Mar","04":"Abr","05":"Mai","06":"Jun",
                  "07":"Jul","08":"Ago","09":"Set","10":"Out","11":"Nov","12":"Dez"}
    pico_label = MESES_PT.get(pico_idx[-2:], pico_idx)
    zona_lider = occ_f["Zona"].value_counts().idxmax().replace("Rio de Janeiro - ", "")

col1, col2, col3, col4 = st.columns(4)
for col, (val, label) in zip(
    [col1, col2, col3, col4],
    [
        (f"{total_occ:,}",  "Ocorrências em 2025"),
        (f"{total_cam:,}",  "Camaleões ativos (RJ)"),
        (pico_label,        f"Mês de pico ({pico_valor} ocorrências)"),
        (zona_lider,        "Zona com maior volume"),
    ],
):
    col.markdown(
        f'<div class="metric-card">'
        f'<div class="metric-value">{val}</div>'
        f'<div class="metric-label">{label}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

st.markdown("")

# ─── Linha do tempo ───────────────────────────────────────────────────────────
st.markdown('<div class="section-title">Evolução mensal de ocorrências</div>', unsafe_allow_html=True)

if not occ_f.empty:
    mensal_zona = (
        occ_f.groupby(["AnoMes_str", "Zona"]).size().reset_index(name="n")
    )
    mensal_zona["Zona"] = mensal_zona["Zona"].str.replace("Rio de Janeiro - ", "")
    mensal_total        = occ_f.groupby("AnoMes_str").size().reset_index(name="n")
    mensal_total["Zona"] = "Total"

    fig_linha = px.line(
        mensal_zona, x="AnoMes_str", y="n", color="Zona",
        markers=True,
        color_discrete_sequence=["#e94560", "#0f3460", "#533483", "#1a7abf"],
        labels={"AnoMes_str": "Mês", "n": "Ocorrências", "Zona": "Zona"},
        template="plotly_dark",
    )
    fig_linha.add_trace(go.Scatter(
        x=mensal_total["AnoMes_str"], y=mensal_total["n"],
        name="Total", mode="lines+markers",
        line=dict(color="white", width=2, dash="dot"),
        marker=dict(size=5),
    ))
    fig_linha.update_layout(
        height=300,
        margin=dict(l=0, r=0, t=10, b=0),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        xaxis=dict(tickangle=-45),
        plot_bgcolor="#0d0d0d",
        paper_bgcolor="#0d0d0d",
    )
    st.plotly_chart(fig_linha, use_container_width=True)

# ─── Mapa choropleth animado + Ranking ───────────────────────────────────────
col_mapa, col_rank = st.columns([3, 1], gap="large")

with col_mapa:
    st.markdown('<div class="section-title">Mancha criminal por hexágono H3 (animação mensal)</div>', unsafe_allow_html=True)

    if occ_f.empty:
        st.info("Nenhuma ocorrência encontrada para o filtro selecionado.")
    else:
        agg = agregar_mensal(occ_f, cam_por_celula)

        # Bairro como hover
        agg = agg.merge(bairro_por_celula, on="h3_cell", how="left")

        geojson = build_geojson(tuple(agg["h3_cell"].unique()))

        fig_mapa = px.choropleth_mapbox(
            agg.sort_values("AnoMes_str"),
            geojson=geojson,
            locations="h3_cell",
            featureidkey="properties.h3_index",
            color="qtd_ocorrencias",
            animation_frame="AnoMes_str",
            color_continuous_scale="YlOrRd",
            mapbox_style="carto-darkmatter",
            center={"lat": occ_f["Latitude"].mean(), "lon": occ_f["Longitude"].mean()},
            zoom=10,
            opacity=0.80,
            hover_name="Bairro",
            hover_data={
                "AnoMes_str"      : True,
                "qtd_ocorrencias" : True,
                "taxa_normalizada": ":.2f",
                "h3_cell"         : False,
            },
            labels={
                "qtd_ocorrencias" : "Ocorrências",
                "taxa_normalizada": "Taxa/Camaleão",
                "AnoMes_str"      : "Mês",
            },
        )
        fig_mapa.update_layout(
            height=500,
            margin=dict(l=0, r=0, t=0, b=0),
            coloraxis_colorbar=dict(
                title="Ocorrências",
                thickness=12,
                len=0.6,
            ),
            paper_bgcolor="#0d0d0d",
        )
        # Velocidade da animação
        fig_mapa.layout.updatemenus[0].buttons[0].args[1]["frame"]["duration"] = 800
        fig_mapa.layout.updatemenus[0].buttons[0].args[1]["transition"]["duration"] = 300

        st.plotly_chart(fig_mapa, use_container_width=True)

with col_rank:
    st.markdown('<div class="section-title">Ranking de bairros</div>', unsafe_allow_html=True)

    if occ_f.empty:
        st.info("Sem dados.")
    else:
        delta_df = calcular_delta(agg, bairro_por_celula)
        tab_aq, tab_es = st.tabs(["🔴 Aquecendo", "🔵 Esfriando"])

        with tab_aq:
            top = delta_df.nlargest(8, "delta")[["Bairro", "delta_pct"]].copy()
            top["delta_pct"] = top["delta_pct"].round(0).astype(int).apply(lambda x: f"+{x}%")
            top.columns = ["Bairro", "Δ%"]
            st.dataframe(top, use_container_width=True, hide_index=True)

        with tab_es:
            bot = delta_df.nsmallest(8, "delta")[["Bairro", "delta_pct"]].copy()
            bot["delta_pct"] = bot["delta_pct"].round(0).astype(int).apply(lambda x: f"{x}%")
            bot.columns = ["Bairro", "Δ%"]
            st.dataframe(bot, use_container_width=True, hide_index=True)

        st.caption("Δ% = variação da taxa normalizada entre 1º e 2º semestre de 2025.")

# ─── Centróide + Categorias ───────────────────────────────────────────────────
col_c, col_cat = st.columns(2, gap="large")

with col_c:
    st.markdown('<div class="section-title">Trajetória do centróide da mancha</div>', unsafe_allow_html=True)

    if occ_f.empty:
        st.info("Sem dados suficientes.")
    else:
        centroides = calcular_centroide(agg)

        fig_cent = go.Figure()

        # Linha da trajetória
        fig_cent.add_trace(go.Scattermapbox(
            lat=centroides["lat"],
            lon=centroides["lon"],
            mode="lines",
            line=dict(width=2, color="#888"),
            hoverinfo="skip",
            showlegend=False,
        ))

        # Pontos mensais
        fig_cent.add_trace(go.Scattermapbox(
            lat=centroides["lat"],
            lon=centroides["lon"],
            mode="markers+text",
            marker=dict(
                size=10,
                color=list(range(len(centroides))),
                colorscale=[[0, "#0f3460"], [1, "#e94560"]],
                showscale=False,
            ),
            text=centroides["AnoMes_str"].str[-2:],
            textposition="top right",
            textfont=dict(size=9, color="white"),
            customdata=centroides[["AnoMes_str", "total"]].values,
            hovertemplate="<b>%{customdata[0]}</b><br>%{customdata[1]} ocorrências<extra></extra>",
            showlegend=False,
        ))

        # Marcadores início/fim
        for i, (label, color) in enumerate([(centroides.iloc[0], "#00c853"), (centroides.iloc[-1], "#e94560")]):
            fig_cent.add_trace(go.Scattermapbox(
                lat=[label["lat"]], lon=[label["lon"]],
                mode="markers",
                marker=dict(size=14, color=color, symbol="circle"),
                name=["Jan/2025", "Dez/2025"][i],
                hovertemplate=f"{'Jan' if i==0 else 'Dez'}/2025<br>{int(label['total'])} ocorrências<extra></extra>",
            ))

        fig_cent.update_layout(
            mapbox=dict(
                style="carto-darkmatter",
                center=dict(lat=centroides["lat"].mean(), lon=centroides["lon"].mean()),
                zoom=11,
            ),
            height=400,
            margin=dict(l=0, r=0, t=0, b=0),
            paper_bgcolor="#0d0d0d",
            legend=dict(
                orientation="h", yanchor="bottom", y=1.01,
                font=dict(color="white", size=11),
            ),
        )
        st.plotly_chart(fig_cent, use_container_width=True)

with col_cat:
    st.markdown('<div class="section-title">Distribuição por categoria de crime</div>', unsafe_allow_html=True)

    if not occ_f.empty:
        cat_counts = occ_f["CategoriaCrime"].value_counts().head(10).reset_index()
        cat_counts.columns = ["Categoria", "n"]
        fig_cat = px.bar(
            cat_counts.sort_values("n"),
            x="n", y="Categoria", orientation="h",
            color="n",
            color_continuous_scale=["#16213e", "#e94560"],
            template="plotly_dark",
            labels={"n": "Ocorrências", "Categoria": ""},
        )
        fig_cat.update_layout(
            height=300,
            margin=dict(l=0, r=0, t=10, b=0),
            coloraxis_showscale=False,
            plot_bgcolor="#0d0d0d",
            paper_bgcolor="#0d0d0d",
        )
        st.plotly_chart(fig_cat, use_container_width=True)

    st.markdown('<div class="section-title" style="margin-top:16px">Distribuição horária</div>', unsafe_allow_html=True)

    if not occ_f.empty:
        hora_counts = (
            occ_f["Intervalo"].value_counts()
            .reset_index()
            .rename(columns={"index": "Intervalo", "count": "n"})
            .sort_values("Intervalo")
        )
        fig_hora = px.bar(
            hora_counts, x="Intervalo", y="n",
            color="n",
            color_continuous_scale=["#16213e", "#e94560"],
            template="plotly_dark",
            labels={"Intervalo": "", "n": "Ocorrências"},
        )
        fig_hora.update_layout(
            height=240,
            margin=dict(l=0, r=0, t=0, b=0),
            coloraxis_showscale=False,
            xaxis=dict(tickangle=-90, tickfont=dict(size=9)),
            plot_bgcolor="#0d0d0d",
            paper_bgcolor="#0d0d0d",
        )
        st.plotly_chart(fig_hora, use_container_width=True)

# ─── Footer ───────────────────────────────────────────────────────────────────
st.divider()
st.caption("Gabriel · Central de Monitoramento · Sprint INSPER 2025 · Snapshot: 18/05/2026 · Recorte: RJ/2025 · H3 resolução 8")
