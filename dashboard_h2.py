import warnings
warnings.filterwarnings("ignore")

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans

# ─── Configuração da página ───────────────────────────────────────────────────
st.set_page_config(
    page_title="Gabriel — Comparativo entre Bairros",
    page_icon="🏘️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    .cluster-card {
        border-radius: 10px; padding: 16px 20px; margin-bottom: 10px;
        border-left: 5px solid;
    }
    .card-title  { font-size: 1rem; font-weight: 700; margin-bottom: 4px; }
    .card-body   { font-size: 0.82rem; color: #ccc; line-height: 1.5; }
    .section-title {
        font-size: 1.1rem; font-weight: 600; color: #fff;
        border-bottom: 1px solid #333; padding-bottom: 6px; margin-bottom: 14px;
    }
    .metric-mini {
        background: #1a1a2e; border-radius: 8px; padding: 12px 16px;
        border-left: 3px solid;
    }
    .metric-mini-val   { font-size: 1.5rem; font-weight: 700; }
    .metric-mini-label { font-size: 0.78rem; color: #aaa; }
</style>
""", unsafe_allow_html=True)

# ─── Constantes ───────────────────────────────────────────────────────────────
N_CLUSTERS   = 4
RANDOM_STATE = 42
MIN_OCC      = 50

CORES_CLUSTER = {0: '#f59e0b', 1: '#3b82f6', 2: '#e94560', 3: '#22c55e'}
NOMES_CLUSTER = {
    0: 'Eixo Viário',
    1: 'Zona Turística',
    2: 'Urbano Consolidado',
    3: 'Residencial Periurbano',
}
DESCRICOES_CLUSTER = {
    0: "Alto volume de acidentes de trânsito e perfil diurno. Vias de alta velocidade, Zona Oeste.",
    1: "Furto domina (34%), muito público e turístico. Zona Sul nobre com alta densidade de visitantes.",
    2: "Mix roubo/furto, perfil noturno intenso (53%), alta efetividade forense. Bairros tradicionais consolidados.",
    3: "Predominantemente residencial (41%), roubo como crime principal. Bairros de transição entre zona nobre e periferia.",
}

RADAR_FEATS  = ['pct_roubo','pct_furto','pct_tentativas','pct_acidentes',
                'pct_noturno','pct_residencial','cam_por_occ','taxa_efetividade']
RADAR_LABELS = ['Roubo','Furto','Tentativas','Acidentes',
                'Noturno','Residencial','Camaleões/Occ','Efetividade']

# ─── Pipeline de dados ────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def processar():
    occ_raw = pd.read_csv("ocorrencias.csv", parse_dates=["DataOcorrencia"])
    sen_raw = pd.read_csv("sensores.csv")

    occ = occ_raw.query('Estado == "RJ" and Cidade == "Rio de Janeiro"').copy()
    sen = sen_raw.query('Estado == "RJ" and Cidade == "Rio de Janeiro"').copy()

    vol   = occ.groupby("Bairro").size()
    validos = vol[vol >= MIN_OCC].index
    df    = occ[occ["Bairro"].isin(validos)].copy()

    feat = df.groupby("Bairro").size().rename("total_occ").reset_index()

    CATS = ["Roubo","Furto","Tentativas","Acidentes de Trânsito","Golpes e Fraudes","Vandalismo e Danos"]
    cat_pct = (
        df.groupby(["Bairro","CategoriaCrime"]).size()
        .unstack(fill_value=0)
        .reindex(columns=CATS, fill_value=0)
        .apply(lambda r: r/r.sum() if r.sum() > 0 else r, axis=1)
        .rename(columns={
            "Roubo":"pct_roubo","Furto":"pct_furto","Tentativas":"pct_tentativas",
            "Acidentes de Trânsito":"pct_acidentes","Golpes e Fraudes":"pct_golpes",
            "Vandalismo e Danos":"pct_vandalismo",
        })
        .reset_index()
    )
    feat = feat.merge(cat_pct, on="Bairro", how="left")

    def is_noturno(v):
        if pd.isna(v): return False
        return int(str(v).split("h")[0].strip()) >= 18 or int(str(v).split("h")[0].strip()) < 6

    df["noturno"] = df["Intervalo"].apply(is_noturno)
    feat = feat.merge(df.groupby("Bairro")["noturno"].mean().rename("pct_noturno").reset_index(), on="Bairro", how="left")

    gen_pct = (
        df.groupby(["Bairro","GeneroLocal"]).size()
        .unstack(fill_value=0)
        .apply(lambda r: r/r.sum() if r.sum() > 0 else r, axis=1)
        .rename(columns=str.lower).add_prefix("pct_")
        .reset_index()
    )
    feat = feat.merge(gen_pct, on="Bairro", how="left")

    cam = sen.groupby("Bairro")["IDDispositivo"].nunique().rename("n_camaleoes").reset_index()
    feat = feat.merge(cam, on="Bairro", how="left")
    feat["n_camaleoes"] = feat["n_camaleoes"].fillna(0)
    feat["cam_por_occ"] = feat["n_camaleoes"] / feat["total_occ"]

    efet = df.groupby("Bairro")["EfetividadeAnalise"].apply(
        lambda x: (x=="Efetiva").mean()
    ).rename("taxa_efetividade").reset_index()
    feat = feat.merge(efet, on="Bairro", how="left")
    feat = feat.set_index("Bairro").fillna(0)

    FEAT_COLS = [c for c in feat.columns if c not in ["total_occ","n_camaleoes"]]
    X_sc = StandardScaler().fit_transform(feat[FEAT_COLS])

    km = KMeans(n_clusters=N_CLUSTERS, random_state=RANDOM_STATE, n_init=20)
    feat["cluster"]      = km.fit_predict(X_sc)
    feat["cluster_nome"] = feat["cluster"].map(NOMES_CLUSTER)

    return feat, FEAT_COLS, df


with st.spinner("Processando clusters..."):
    feat, FEAT_COLS, df_full = processar()

# ─── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🏘️ Comparativo de Bairros")
    st.markdown("**Rio de Janeiro · Histórico Gabriel**")
    st.divider()

    bairros_disp = sorted(feat.index.tolist())
    bairro_sel   = st.selectbox("Selecione seu bairro", bairros_disp, index=bairros_disp.index("Tijuca") if "Tijuca" in bairros_disp else 0)

    cluster_do_bairro = int(feat.loc[bairro_sel, "cluster"])
    nome_cluster      = NOMES_CLUSTER[cluster_do_bairro]
    cor_cluster       = CORES_CLUSTER[cluster_do_bairro]
    pares             = feat[feat["cluster"] == cluster_do_bairro].drop(index=bairro_sel, errors="ignore")

    st.divider()
    st.markdown(f"**Cluster identificado:**")
    st.markdown(
        f'<div class="cluster-card" style="border-color:{cor_cluster};background:#1a1a2e">'
        f'<div class="card-title" style="color:{cor_cluster}">{nome_cluster}</div>'
        f'<div class="card-body">{DESCRICOES_CLUSTER[cluster_do_bairro]}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )
    st.caption("Sprint INSPER · Gabriel · 2025")
    st.caption(f"Bairros analisados: {len(feat)} (≥ {MIN_OCC} ocorrências)")

# ─── Header ───────────────────────────────────────────────────────────────────
st.markdown(f"# {bairro_sel}")
st.markdown(f"#### Cluster **{nome_cluster}** · {len(pares)} bairros com perfil parecido")
st.divider()

# ─── KPIs do bairro selecionado ───────────────────────────────────────────────
b = feat.loc[bairro_sel]
kpis = [
    (f"{int(b['total_occ']):,}",      "Ocorrências totais",        cor_cluster),
    (f"{b['pct_noturno']*100:.0f}%",  "Ocorrências noturnas",      cor_cluster),
    (f"{b['taxa_efetividade']*100:.0f}%", "Efetividade das análises", cor_cluster),
    (f"{int(b['n_camaleoes'])}",      "Camaleões no bairro",       cor_cluster),
]
cols = st.columns(4)
for col, (val, label, cor) in zip(cols, kpis):
    col.markdown(
        f'<div class="metric-mini" style="border-color:{cor}">'
        f'<div class="metric-mini-val" style="color:{cor}">{val}</div>'
        f'<div class="metric-mini-label">{label}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

st.markdown("")

# ─── Radar chart: bairro vs. pares ───────────────────────────────────────────
col_radar, col_rank = st.columns([3, 2], gap="large")

with col_radar:
    st.markdown('<div class="section-title">Perfil do seu bairro vs. bairros do mesmo cluster</div>', unsafe_allow_html=True)

    fig_radar = go.Figure()

    # Média do cluster (fundo)
    media_cluster = feat[feat["cluster"] == cluster_do_bairro][RADAR_FEATS].mean()
    vals_media    = media_cluster.values.tolist() + [media_cluster.values[0]]
    fig_radar.add_trace(go.Scatterpolar(
        r=vals_media,
        theta=RADAR_LABELS + [RADAR_LABELS[0]],
        fill="toself",
        name=f"Média {nome_cluster}",
        line=dict(color=cor_cluster, dash="dot"),
        fillcolor=cor_cluster,
        opacity=0.15,
    ))

    # Bairro selecionado (destaque)
    vals_bairro = [b[f] for f in RADAR_FEATS] + [b[RADAR_FEATS[0]]]
    fig_radar.add_trace(go.Scatterpolar(
        r=vals_bairro,
        theta=RADAR_LABELS + [RADAR_LABELS[0]],
        fill="toself",
        name=bairro_sel,
        line=dict(color="white", width=2),
        fillcolor="rgba(255,255,255,0.08)",
    ))

    fig_radar.update_layout(
        polar=dict(radialaxis=dict(visible=True, range=[0, max(0.7, max(vals_bairro)*1.1)])),
        template="plotly_dark",
        height=420,
        margin=dict(l=30, r=30, t=30, b=60),
        legend=dict(orientation="h", y=-0.15),
    )
    st.plotly_chart(fig_radar, use_container_width=True)

with col_rank:
    st.markdown('<div class="section-title">Bairros do mesmo cluster</div>', unsafe_allow_html=True)

    pares_display = pares.reset_index()[["Bairro","total_occ","pct_roubo","pct_furto","pct_noturno","taxa_efetividade"]].copy()
    pares_display.columns = ["Bairro","Ocorrências","% Roubo","% Furto","% Noturno","Efetividade"]
    pares_display["% Roubo"]     = (pares_display["% Roubo"]*100).round(0).astype(int).astype(str) + "%"
    pares_display["% Furto"]     = (pares_display["% Furto"]*100).round(0).astype(int).astype(str) + "%"
    pares_display["% Noturno"]   = (pares_display["% Noturno"]*100).round(0).astype(int).astype(str) + "%"
    pares_display["Efetividade"] = (pares_display["Efetividade"]*100).round(0).astype(int).astype(str) + "%"
    pares_display = pares_display.sort_values("Ocorrências", ascending=False)

    st.dataframe(pares_display, use_container_width=True, hide_index=True)

# ─── Comparativo em barras ────────────────────────────────────────────────────
st.markdown('<div class="section-title">Comparativo direto: seu bairro vs. pares do cluster</div>', unsafe_allow_html=True)

COMP_FEATS = {
    "pct_roubo"       : "% Roubo",
    "pct_furto"       : "% Furto",
    "pct_tentativas"  : "% Tentativas",
    "pct_acidentes"   : "% Acidentes",
    "pct_noturno"     : "% Noturno",
    "pct_residencial" : "% Residencial",
    "taxa_efetividade": "Efetividade",
}

cluster_bairros = feat[feat["cluster"] == cluster_do_bairro].reset_index()
comp_long = cluster_bairros.melt(
    id_vars="Bairro",
    value_vars=list(COMP_FEATS.keys()),
    var_name="Feature",
    value_name="Valor",
)
comp_long["Feature"] = comp_long["Feature"].map(COMP_FEATS)
comp_long["Valor"]   = (comp_long["Valor"] * 100).round(1)
comp_long["Destaque"] = comp_long["Bairro"].apply(lambda b: "★ " + b if b == bairro_sel else b)

fig_bar = px.bar(
    comp_long,
    x="Bairro", y="Valor", facet_col="Feature",
    facet_col_wrap=4,
    color="Bairro",
    color_discrete_sequence=[
        cor_cluster if b == bairro_sel else "#444" for b in cluster_bairros["Bairro"]
    ],
    template="plotly_dark",
    labels={"Valor": "%", "Bairro": ""},
)
fig_bar.update_layout(
    height=520,
    margin=dict(l=0, r=0, t=40, b=0),
    showlegend=False,
    paper_bgcolor="#0d0d0d",
    plot_bgcolor="#0d0d0d",
)
fig_bar.for_each_annotation(lambda a: a.update(text=a.text.split("=")[-1]))
fig_bar.update_xaxes(tickangle=-45, tickfont=dict(size=9))
st.plotly_chart(fig_bar, use_container_width=True)

# ─── Visão geral de todos os clusters ────────────────────────────────────────
st.markdown('<div class="section-title">Todos os clusters — visão geral</div>', unsafe_allow_html=True)

col_cards = st.columns(N_CLUSTERS)
for c in sorted(feat["cluster"].unique()):
    bairros_c = feat[feat["cluster"] == c].sort_values("total_occ", ascending=False).index.tolist()
    with col_cards[c]:
        cor  = CORES_CLUSTER[c]
        nome = NOMES_CLUSTER[c]
        st.markdown(
            f'<div class="cluster-card" style="border-color:{cor};background:#1a1a2e">'
            f'<div class="card-title" style="color:{cor}">{nome}</div>'
            f'<div class="card-body">{DESCRICOES_CLUSTER[c]}<br><br>'
            f'<b style="color:#fff">{len(bairros_c)} bairros:</b><br>'
            f'{", ".join(bairros_c)}'
            f'</div></div>',
            unsafe_allow_html=True,
        )

# ─── Radar geral ─────────────────────────────────────────────────────────────
st.markdown("")
st.markdown('<div class="section-title">Radar — perfil médio de cada cluster</div>', unsafe_allow_html=True)

perfil = feat.groupby("cluster")[RADAR_FEATS].mean()
fig_radar_geral = go.Figure()
for c in sorted(feat["cluster"].unique()):
    vals = perfil.loc[c].values.tolist() + [perfil.loc[c].values[0]]
    fig_radar_geral.add_trace(go.Scatterpolar(
        r=vals,
        theta=RADAR_LABELS + [RADAR_LABELS[0]],
        fill="toself",
        name=NOMES_CLUSTER[c],
        line_color=CORES_CLUSTER[c],
        fillcolor=CORES_CLUSTER[c],
        opacity=0.30,
    ))

fig_radar_geral.update_layout(
    polar=dict(radialaxis=dict(visible=True, range=[0, 0.65])),
    template="plotly_dark",
    height=450,
    legend=dict(orientation="h", yanchor="bottom", y=-0.2),
)
st.plotly_chart(fig_radar_geral, use_container_width=True)

# ─── Footer ───────────────────────────────────────────────────────────────────
st.divider()
st.caption("Gabriel · Sprint INSPER 2025 · Clustering K-Means k=4 · Features: perfil de crime, horário, local, cobertura Gabriel · Bairros com ≥ 50 ocorrências")
