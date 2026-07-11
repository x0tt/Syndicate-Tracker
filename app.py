#!/usr/bin/env python3
# coding: utf-8
"""
app.py — Syndicate Tracker v6.4
================================
Streamlit UI. Mobile-optimised, tab-based, Plotly-powered.
Includes advanced calibration, matchday tracking, ghost-chart fix,
and "Information is Beautiful" visual upgrades with Logic Expanders.
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots

import syndicate_core as core
from agent import build_agent, query as agent_query

# ─────────────────────────────────────────────────────────────────────────────
# DESIGN CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────
WIN_COLOR   = "#56B4E9"
LOSS_COLOR  = "#E69F00"
PUSH_COLOR  = "#999999"

MEMBER_COLORS = {
    "John":    "#009E73",
    "Richard": "#CC79A7",
    "Xander":  "#D55E00",
    "Team":    "#0072B2",
}

OKABE_ITO =["#E69F00","#56B4E9","#009E73","#F0E442","#0072B2","#D55E00","#CC79A7","#999999"]
BG_DARK   = "#1a1a2e"
BG_CARD   = "#16213e"
BG_CHART  = "#0f3460"
GRID_CLR  = "#2a2a4a"
TEXT_CLR  = "#e0e0f0"
ACCENT    = "#56B4E9"
MEMBERS =["John", "Richard", "Xander"]

BET_TYPES = sorted(['Full Time Result', 'Asian Handicap', 'Double Chance', 'Draw No Bet', 'Handicap', 'Relegation', 'BTTS', 'Goal Line', 'Goal Line (1H)', 'Total Goals', 'Multi', 'To Score Anytime', 'To Qualify', 'Winner', 'Method of Victory', 'To Score'])
COMPETITIONS = sorted(["EPL 25/26", "EPL 24/25", "FA cup 2026", "Champions League 2025", "Club World Cup", "International Football", "NFL", "A-League 2025", "Other"])

PLOTLY_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="'DM Mono', 'Courier New', monospace", size=13, color=TEXT_CLR),
    xaxis=dict(gridcolor=GRID_CLR, zerolinecolor=GRID_CLR, title_font=dict(size=11), tickfont=dict(size=11)),
    yaxis=dict(gridcolor=GRID_CLR, zerolinecolor=GRID_CLR, title_font=dict(size=11), tickfont=dict(size=11)),
    margin=dict(l=6,  r=6,  t=52, b=60),
    modebar=dict(orientation="v", bgcolor="rgba(0,0,0,0)", color="#555577", activecolor=ACCENT),
    dragmode=False, 
    legend=dict(bgcolor="rgba(0,0,0,0.3)", bordercolor=GRID_CLR, borderwidth=1, font=dict(size=12), orientation="h", yanchor="top", y=-0.18, xanchor="center", x=0.5),
)

st.set_page_config(page_title="Xanderdu 🏆", page_icon="🏆", layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@300;400;500&family=Space+Grotesk:wght@400;600;700&display=swap');
html, body,[class*="css"] { background-color: #1a1a2e; color: #e0e0f0; font-family: 'Space Grotesk', sans-serif; }
.stTabs[data-baseweb="tab-list"] { gap: 4px; background: #16213e; border-radius: 12px; padding: 4px; }
.stTabs[data-baseweb="tab"] { background: transparent; border-radius: 8px; color: #8888aa; font-size: 14px; font-weight: 600; padding: 8px 16px; font-family: 'Space Grotesk', sans-serif; }
.stTabs[aria-selected="true"] { background: #56B4E9 !important; color: #1a1a2e !important; }
[data-testid="metric-container"] { background: #16213e; border: 1px solid #2a2a4a; border-radius: 12px; padding: 16px; }[data-testid="stMetricValue"] { font-family: 'DM Mono', monospace; font-size: 1.8rem !important; font-weight: 500; color: #56B4E9; }[data-testid="stMetricLabel"] { font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.1em; color: #8888aa; }[data-testid="stMetricDelta"] { font-family: 'DM Mono', monospace; font-size: 0.85rem; }
.roast-strip { background: linear-gradient(90deg, #16213e, #0f3460); border-left: 3px solid #E69F00; border-radius: 0 8px 8px 0; padding: 10px 16px; margin: 8px 0; font-family: 'DM Mono', monospace; font-size: 0.85rem; color: #E69F00; font-style: italic; }
.stButton>button { background: #16213e; border: 1px solid #2a2a4a; color: #8888aa; border-radius: 8px; font-weight: 600; font-size: 14px; padding: 8px 20px; transition: all 0.2s; }
.stButton>button:hover { background: #0f3460; color: #e0e0f0; border-color: #56B4E9; }
[data-testid="stDataFrame"] { border-radius: 8px; overflow: hidden; }
.section-header { font-family: 'Space Grotesk', sans-serif; font-size: 1.1rem; font-weight: 700; color: #56B4E9; text-transform: uppercase; letter-spacing: 0.08em; margin: 20px 0 8px; border-bottom: 1px solid #2a2a4a; padding-bottom: 6px; }
</style>
""", unsafe_allow_html=True)

def section(label: str): st.markdown(f'<div class="section-header">{label}</div>', unsafe_allow_html=True)
def apply_layout(fig, title="", height=420, showlegend=True, **kwargs):
    base = dict(PLOTLY_LAYOUT)
    if not showlegend: base["margin"] = dict(base["margin"], b=10)
    base.update(kwargs)
    fig.update_layout(title=dict(text=title, font=dict(size=14, color=TEXT_CLR), x=0.01), height=height, showlegend=showlegend, **base)
    return fig

def cols(n, gap="small"): return st.columns(n, gap=gap)

_PLOTLY_CONFIG = { "displaylogo": False, "scrollZoom": False, "modeBarButtons": [["toImage", "resetScale2d"]], "toImageButtonOptions": { "format": "png", "width": 1200, "height": 600, "scale": 2, "filename": "syndicate_chart" } }

# The ghost chart fix: Streamlit natively hashes the figure, so we removed the global key counter
def pc(fig):
    st.plotly_chart(fig, width='stretch', config=_PLOTLY_CONFIG)

def kpi(label, value, delta=None, delta_color="normal"): st.metric(label=label, value=value, delta=delta, delta_color=delta_color)
def roast(text: str): st.markdown(f'<div class="roast-strip">🔥 {text}</div>', unsafe_allow_html=True)
def stat_card(label: str, value: str, sub: str = "", color: str = None, border_color: str = None):
    c = color or ACCENT; bc = border_color or f"{c}55"
    st.markdown(f'''<div style="background:{BG_CARD};border:1px solid {bc};border-radius:12px;padding:14px 16px;text-align:center;margin-bottom:4px;">
  <div style="color:#8888aa;font-size:0.72rem;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:4px;">{label}</div>
  <div style="font-family:DM Mono,monospace;font-size:1.55rem;font-weight:500;color:{c};line-height:1.1;">{value}</div>
  <div style="color:#8888aa;font-size:0.78rem;margin-top:4px;">{sub}</div></div>''', unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# DATA LOADING
# ─────────────────────────────────────────────────────────────────────────────
@st.cache_data(ttl=300)
def load_data():
    if core.USE_GSHEETS_LIVE:
        core.sync_local_csv()
    df, df_roi, df_free, df_pending, kpis = core.load_ledger()
    return df, df_roi, df_free, df_pending, kpis

@st.cache_data(ttl=300)
def get_enriched(df: pd.DataFrame) -> tuple:
    df = df.copy()
    def odds_bucket(o):
        if o < 1.4:   return "<1.40"
        elif o < 1.7: return "1.40\u20131.69"
        elif o < 2.0: return "1.70\u20131.99"
        elif o < 2.5: return "2.00\u20132.49"
        elif o < 3.5: return "2.50\u20133.49"
        else:         return "3.50+"

    bankroll_df = df.copy()
    bankroll_df["date"]     = pd.to_datetime(bankroll_df["date"])
    bankroll_df["date_str"] = bankroll_df["date"].dt.strftime("%Y-%m-%d")
    bankroll_df = bankroll_df.sort_values("date").reset_index(drop=True)
    bankroll_df["actual_winnings_num"] = pd.to_numeric(bankroll_df["actual_winnings"], errors="coerce").fillna(0)
    bankroll_df["cum_pl"]   = bankroll_df["actual_winnings_num"].cumsum()

    banking_mask = df["status"].isin(["Reconciliation", "Deposit", "Withdrawal"]) | (df["user"].astype(str).str.lower() == "syndicate")
    working = df[~banking_mask].copy()
    working["date"]     = pd.to_datetime(working["date"])
    working["date_str"] = working["date"].dt.strftime("%Y-%m-%d")
    working["month"]    = working["date"].dt.to_period("M").astype(str)
    working["weekday"]  = working["date"].dt.day_name()
    working["year"]     = working["date"].dt.year
    working["season"]   = df["season"]
    working["matchday"] = df["matchday"]
    working["sport"]    = df.get("sport", "Football")
    
    working = working.sort_values("date").reset_index(drop=True)
    working["cum_pl"]       = pd.to_numeric(working["actual_winnings"], errors="coerce").fillna(0).cumsum()
    working["implied_prob"] = 1.0 / working["odds"].replace(0, np.nan)
    working["odds_bucket"]  = working["odds"].apply(odds_bucket)

    return working, bankroll_df

def member_stats(df: pd.DataFrame, member: str) -> dict:
    sub = df[df["user"] == member]
    wins = (sub["status"] == "Win").sum(); losses = (sub["status"] == "Loss").sum(); pushes = (sub["status"] == "Push").sum()
    staked = sub["stake"].sum(); pl = pd.to_numeric(sub["actual_winnings"], errors="coerce").fillna(0).sum()
    roi = pl / staked * 100 if staked > 0 else 0
    wr = wins / (wins + losses) * 100 if (wins + losses) > 0 else 0
    return dict(bets=len(sub), wins=wins, losses=losses, pushes=pushes, staked=staked, pl=pl, roi=roi, win_rate=wr, avg_odds=sub["odds"].mean())

def team_summary(df: pd.DataFrame) -> dict:
    wins = (df["status"] == "Win").sum(); losses = (df["status"] == "Loss").sum(); pushes = (df["status"] == "Push").sum()
    staked = df["stake"].sum(); pl = pd.to_numeric(df["actual_winnings"], errors="coerce").fillna(0).sum()
    roi = pl / staked * 100 if staked > 0 else 0
    wr = wins / (wins + losses) * 100 if (wins + losses) > 0 else 0
    return dict(bets=len(df), wins=wins, losses=losses, pushes=pushes, staked=staked, pl=pl, roi=roi, win_rate=wr)

def compute_streak(df: pd.DataFrame) -> tuple[int, str]:
    sub = df[df["status"].isin(["Win", "Loss"])].sort_values("date")
    if len(sub) == 0: return 0, "–"
    last = sub.iloc[-1]["status"]
    count = 0
    for _, row in sub.iloc[::-1].iterrows():
        if row["status"] == last: count += 1
        else: break
    return count, last

def worst_bet(df: pd.DataFrame) -> pd.Series:
    closed = df[df["status"].isin(["Win", "Loss"])].copy()
    if not closed.empty:
        closed["aw_num"] = pd.to_numeric(closed["actual_winnings"], errors="coerce").fillna(0)
        return closed.loc[closed["aw_num"].idxmin()]
    return df.iloc[0]

def best_bet(df: pd.DataFrame) -> pd.Series:
    closed = df[df["status"].isin(["Win", "Loss"])].copy()
    if not closed.empty:
        closed["aw_num"] = pd.to_numeric(closed["actual_winnings"], errors="coerce").fillna(0)
        return closed.loc[closed["aw_num"].idxmax()]
    return df.iloc[0]

def event_label(row: pd.Series) -> str:
    if row.get('event'): return str(row['event'])
    return f"{row.get('home_team', '')} vs {row.get('away_team', '')}"

def rolling_roi(df: pd.DataFrame, window: int = 20) -> pd.Series:
    df = df.sort_values("date").copy()
    aw_num = pd.to_numeric(df["actual_winnings"], errors="coerce").fillna(0)
    return (aw_num.rolling(window).sum() / df["stake"].rolling(window).sum() * 100)

# ─────────────────────────────────────────────────────────────────────────────
# CHART FACTORY
# ─────────────────────────────────────────────────────────────────────────────

def chart_cumulative_bankroll(df: pd.DataFrame, opening: float = 0.00, bankroll_df: pd.DataFrame = None) -> go.Figure:
    src_df = bankroll_df if bankroll_df is not None else df
    df2 = src_df.sort_values("date").copy()
    aw_num = pd.to_numeric(df2["actual_winnings"], errors="coerce").fillna(0)
    df2["bankroll"] = opening + aw_num.cumsum()
    df2["peak"] = df2["bankroll"].cummax()
    df2["drawdown"] = df2["peak"] - df2["bankroll"]
    
    deposits = pd.to_numeric(src_df[src_df["status"].isin(["Deposit", "Withdrawal"])]["actual_winnings"], errors="coerce").fillna(0).sum()
    total_invested = opening + deposits

    fig = go.Figure()
    
    fig.add_trace(go.Scatter(
        x=df2["date_str"], y=df2["bankroll"], mode="lines", 
        line=dict(color=ACCENT, width=3, shape='spline', smoothing=1.3), 
        fill="tozeroy", fillcolor="rgba(86,180,233,0.08)", name="Bankroll"
    ))
    
    if not df2.empty:
        ath_idx = df2["bankroll"].idxmax()
        ath_row = df2.loc[ath_idx]
        dd_idx = df2["drawdown"].idxmax()
        dd_row = df2.loc[dd_idx]
        
        fig.add_annotation(x=ath_row["date_str"], y=ath_row["bankroll"], text=f"All-Time High<br>${ath_row['bankroll']:.0f}", showarrow=True, arrowhead=2, arrowcolor=WIN_COLOR, ax=0, ay=-40, font=dict(color=WIN_COLOR, size=11))
        if dd_row["drawdown"] > 0:
            fig.add_annotation(x=dd_row["date_str"], y=dd_row["bankroll"], text=f"Max Drawdown<br>-${dd_row['drawdown']:.0f}", showarrow=True, arrowhead=2, arrowcolor=LOSS_COLOR, ax=0, ay=40, font=dict(color=LOSS_COLOR, size=11))

    fig.add_hline(y=total_invested, line_dash="dash", line_color=GRID_CLR, annotation_text=f"Invested ${total_invested:.0f}", annotation_font_color=GRID_CLR, annotation_position="bottom right")

    # Journey milestones — understated dashed markers at the first bet of each big event.
    # Drawn as an explicit shape + annotation (avoids add_vline's annotation auto-positioning,
    # which errors on a categorical/string date axis in some plotly versions).
    MILESTONES = [("EPL 24/25", "EPL 24/25"), ("Club World Cup", "Club WC"),
                  ("EPL 25/26", "EPL 25/26"), ("FIFA World Cup 2026", "World Cup")]
    if "competition" in df2.columns:
        for comp, label in MILESTONES:
            cm = df2[df2["competition"] == comp]
            if cm.empty: continue
            x0 = cm["date_str"].iloc[0]
            fig.add_shape(type="line", xref="x", yref="paper", layer="below",
                          x0=x0, x1=x0, y0=0, y1=1,
                          line=dict(color="rgba(136,136,170,0.35)", width=1, dash="dot"))
            fig.add_annotation(x=x0, xref="x", y=1, yref="paper",
                               text=label, showarrow=False, textangle=-90,
                               xanchor="left", yanchor="top",
                               font=dict(size=9, color="#8888aa"))

    fig.update_yaxes(visible=False, showgrid=False)
    fig.update_xaxes(showgrid=False)
    
    return apply_layout(fig, title=f"📈 Bankroll Spline  ${df2['bankroll'].iloc[-1]:.2f}", height=420, showlegend=False)


def chart_cumulative_roi(df: pd.DataFrame) -> go.Figure:
    d = df[df["status"].isin(["Win", "Loss", "Push"])].sort_values("date").copy()
    d["aw_num"] = pd.to_numeric(d["actual_winnings"], errors="coerce").fillna(0)
    d["cum_pl"] = d["aw_num"].cumsum()
    d["cum_stake"] = d["stake"].cumsum()
    d["cum_roi"] = (d["cum_pl"] / d["cum_stake"] * 100).fillna(0)
    fig = go.Figure(go.Scatter(x=d["date_str"], y=d["cum_roi"], mode="lines", line=dict(color=ACCENT, width=2.5)))
    fig.add_hline(y=0, line_dash="dash", line_color=GRID_CLR)
    return apply_layout(fig, title="📉 Cumulative ROI % Over Time", height=380, showlegend=False)

def chart_cumulative_win_rate(df: pd.DataFrame) -> go.Figure:
    d = df[df["status"].isin(["Win", "Loss"])].sort_values("date").copy()
    d["win_count"] = (d["status"] == "Win").cumsum()
    d["loss_count"] = (d["status"] == "Loss").cumsum()
    d["total_resolved"] = np.arange(1, len(d) + 1)
    d["win_pct"] = d["win_count"] / d["total_resolved"] * 100
    d["loss_pct"] = d["loss_count"] / d["total_resolved"] * 100
    
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=d["total_resolved"], y=d["win_pct"], name="Win %", mode="lines", line=dict(color=WIN_COLOR, width=2.5)))
    fig.add_trace(go.Scatter(x=d["total_resolved"], y=d["loss_pct"], name="Loss %", mode="lines", line=dict(color=LOSS_COLOR, width=2.5)))
    fig.update_layout(xaxis_title="Bets Resolved", yaxis_ticksuffix="%")
    return apply_layout(fig, title="⚖️ Cumulative Win % vs Loss %", height=380)

def chart_monthly_pl(df: pd.DataFrame) -> go.Figure:
    df["aw_num"] = pd.to_numeric(df["actual_winnings"], errors="coerce").fillna(0)
    monthly = df.groupby("month")["aw_num"].sum().reset_index()
    fig = go.Figure(go.Bar(x=monthly["month"], y=monthly["aw_num"], marker_color=[WIN_COLOR if v >= 0 else LOSS_COLOR for v in monthly["aw_num"]], text=[f"${v:+.2f}" for v in monthly["aw_num"]], textposition="auto", textfont=dict(size=10, family="DM Mono")))
    fig.add_hline(y=0, line_color=GRID_CLR)
    return apply_layout(fig, title="📅 Monthly Betting P/L", height=340, showlegend=False)

def chart_pl_by_matchday(df: pd.DataFrame) -> go.Figure:
    d = df.dropna(subset=["matchday"]).copy()
    if d.empty: return go.Figure().update_layout(title="No Matchday Data")
    d["aw_num"] = pd.to_numeric(d["actual_winnings"], errors="coerce").fillna(0)
    d["md_num"] = d["matchday"].astype(str).str.extract(r'(\d+)').astype(float)
    d = d.sort_values(["md_num", "matchday"])
    
    fig = go.Figure()
    seasons = sorted(d["season"].dropna().unique())
    colors = [ACCENT, OKABE_ITO[2], OKABE_ITO[6]]
    
    for i, season in enumerate(seasons):
        sub = d[d["season"] == season].groupby("matchday", sort=False)["aw_num"].sum().reset_index()
        fig.add_trace(go.Bar(name=season, x=sub["matchday"], y=sub["aw_num"], marker_color=colors[i % len(colors)]))
        
    fig.update_layout(barmode="group")
    fig.add_hline(y=0, line_color=GRID_CLR)
    return apply_layout(fig, title="🏟️ P/L by Matchday / Round", height=400)

def chart_pl_by_sport(df: pd.DataFrame) -> go.Figure:
    d = df.copy()
    d["aw_num"] = pd.to_numeric(d["actual_winnings"], errors="coerce").fillna(0)
    grp = d.groupby("sport").agg(pl=("aw_num", "sum")).sort_values("pl", ascending=False)
    fig = go.Figure(go.Bar(x=grp.index, y=grp["pl"], marker_color=[WIN_COLOR if p >= 0 else LOSS_COLOR for p in grp["pl"]], text=[f"${p:+.2f}" for p in grp["pl"]], textposition="auto"))
    fig.add_hline(y=0, line_color=GRID_CLR)
    return apply_layout(fig, title="⚽ P/L by Sport", height=360, showlegend=False)

def chart_win_loss_donut(df: pd.DataFrame, title: str = "Overall Record") -> go.Figure:
    wins, losses, pushes = (df["status"] == "Win").sum(), (df["status"] == "Loss").sum(), (df["status"] == "Push").sum()
    fig = go.Figure(go.Pie(labels=["Win", "Loss", "Push"], values=[wins, losses, pushes], hole=0.55, marker=dict(colors=[WIN_COLOR, LOSS_COLOR, PUSH_COLOR]), textinfo="label+percent"))
    wr = wins / (wins + losses) * 100 if (wins + losses) > 0 else 0
    fig.add_annotation(text=f"{wr:.1f}%<br><span style='font-size:10px'>win rate</span>", x=0.5, y=0.5, showarrow=False, font=dict(size=18, family="DM Mono", color=TEXT_CLR))
    return apply_layout(fig, title=f"🎯 {title}", height=360, showlegend=True)

def chart_member_pl_bars(df: pd.DataFrame) -> go.Figure:
    pls =[member_stats(df[df["user"] == m], m)["pl"] for m in MEMBERS]
    fig = go.Figure(go.Bar(x=MEMBERS, y=pls, marker_color=[MEMBER_COLORS[m] for m in MEMBERS], text=[f"${p:+.2f}" for p in pls], textposition="auto"))
    fig.add_hline(y=0, line_color=GRID_CLR)
    return apply_layout(fig, title="💸 Individual P/L", height=340, showlegend=False)

def chart_member_roi_bars(df: pd.DataFrame) -> go.Figure:
    rois =[member_stats(df[df["user"] == m], m)["roi"] for m in MEMBERS]
    fig = go.Figure(go.Bar(x=MEMBERS, y=rois, marker_color=[WIN_COLOR if r >= 0 else LOSS_COLOR for r in rois], text=[f"{r:+.1f}%" for r in rois], textposition="auto"))
    fig.add_hline(y=0, line_color=GRID_CLR)
    return apply_layout(fig, title="📊 Individual ROI %", height=340, showlegend=False)

def chart_member_win_rate(df: pd.DataFrame) -> go.Figure:
    wrs =[member_stats(df[df["user"] == m], m)["win_rate"] for m in MEMBERS]
    fig = go.Figure(go.Bar(y=MEMBERS, x=wrs, orientation="h", marker_color=[MEMBER_COLORS[m] for m in MEMBERS], text=[f"{w:.1f}%" for w in wrs], textposition="inside"))
    return apply_layout(fig, title="🎯 Win Rate by Member", height=260, showlegend=False)

def chart_member_odds_violin(df: pd.DataFrame, member: str) -> go.Figure:
    sub = df[(df["user"] == member) & (df["status"].isin(["Win", "Loss"]))].copy()
    if sub.empty: return go.Figure().update_layout(title="No odds data")
    
    sub["aw_num"] = pd.to_numeric(sub["actual_winnings"], errors="coerce").fillna(0)
    
    fig = px.violin(
        sub, x="status", y="odds", color="status", 
        box=True, points="all", 
        color_discrete_map={"Win": WIN_COLOR, "Loss": LOSS_COLOR},
        hover_data=["event", "selection", "stake", "aw_num"]
    )
    
    fig.update_traces(
        marker=dict(size=5, opacity=0.7, line=dict(width=0)), 
        meanline_visible=True,
        pointpos=0,
        jitter=0.5
    )
    
    fig.update_traces(hovertemplate="<b>%{customdata[0]}</b><br>%{customdata[1]}<br>Odds: %{y}<br>Stake: $%{customdata[2]:.2f}<br>P/L: $%{customdata[3]:.2f}<extra></extra>")
    fig.update_xaxes(title="")
    return apply_layout(fig, title=f"🎻 {member} — Odds Distribution (Violin)", height=340, showlegend=False)

def _weighted_kde(x, w, grid):
    """Dependency-free 1-D Gaussian KDE weighted by w (stake). Silverman bandwidth, floored."""
    x = np.asarray(x, float); w = np.asarray(w, float)
    if x.size == 0 or w.sum() <= 0:
        return np.zeros_like(grid)
    wn = w / w.sum()
    mean = (wn * x).sum()
    std = np.sqrt(max((wn * (x - mean) ** 2).sum(), 1e-9))
    n_eff = 1.0 / np.sum(wn ** 2)
    h = max(1.06 * std * n_eff ** (-0.2), 0.035)
    u = (grid[:, None] - x[None, :]) / h
    K = np.exp(-0.5 * u * u) / np.sqrt(2 * np.pi)
    return (K * wn[None, :]).sum(axis=1) / h


def chart_global_odds_beeswarm(df: pd.DataFrame) -> go.Figure:
    """
    Dollar Density — v3
    ───────────────────
    Two stacked panels (Wins / Losses). Within each, one horizontal violin per
    member, superimposed on a shared log-odds axis. The violin is weighted by
    STAKE (a dependency-free weighted KDE), so the shape shows where the *dollars*
    concentrate on the odds line, not merely the count of bets. Each violin's area
    is scaled by that member's total staked (one common factor across both panels),
    so a bigger shape = more money on the table. Dotted tick = stake-weighted mean
    odds. X-axis capped at 8 (98.9% of all bets sit below it).
    """
    LABEL = {"John": "John", "Richard": "Richard", "Xander": "Xander", "Team": "Bot"}
    ORDER = ["John", "Richard", "Xander", "Team"]
    OUT_COLOR = {"Win": WIN_COLOR, "Loss": LOSS_COLOR}

    d = df[df["status"].isin(["Win", "Loss"])].copy()
    d["odds"] = pd.to_numeric(d["odds"], errors="coerce")
    d["stake"] = pd.to_numeric(d["stake"], errors="coerce").fillna(0)
    d = d.dropna(subset=["odds"])
    d = d[d["stake"] > 0]
    if d.empty:
        return go.Figure().update_layout(title="No odds data")
    d["log"] = np.log10(d["odds"].clip(1.0))

    def _rgba(hexc, a):
        h = hexc.lstrip("#"); return f"rgba({int(h[0:2],16)},{int(h[2:4],16)},{int(h[4:6],16)},{a})"

    TICKO = [1.2, 1.5, 2, 2.5, 3, 4, 5, 8]
    XLO, XHI = np.log10(1.0) - 0.03, np.log10(8) + 0.03
    grid = np.linspace(XLO, XHI, 240)
    MAXHALF = 0.94

    # PASS 1 — weighted density × total stake for each (outcome, member)
    prof = {}
    for outcome in ["Win", "Loss"]:
        ga = d[d["status"] == outcome]
        for m in ORDER:
            g = ga[ga["user"] == m]
            if len(g) < 2:
                continue
            dens = _weighted_kde(g["log"].values, g["stake"].values, grid)
            if dens.max() <= 0:
                continue
            prof[(outcome, m)] = dict(
                curve=dens * g["stake"].sum(), tot=g["stake"].sum(), n=len(g),
                wmean=np.average(g["odds"], weights=g["stake"]), umean=g["odds"].mean())
    if not prof:
        return go.Figure().update_layout(title="No odds data")
    scale = MAXHALF / max(p["curve"].max() for p in prof.values())

    # PASS 2 — draw
    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.13,
        subplot_titles=["✅  WINS — dollar density per member (violin area ∝ total staked)",
                        "❌  LOSSES — dollar density per member (violin area ∝ total staked)"])
    seen = set()
    for outcome, row in [("Win", 1), ("Loss", 2)]:
        for m in ORDER:
            p = prof.get((outcome, m))
            if not p:
                continue
            c = MEMBER_COLORS.get(m, ACCENT); show = m not in seen; seen.add(m)
            dy = p["curve"] * scale
            xs = np.concatenate([grid, grid[::-1]])
            ys = np.concatenate([dy, -dy[::-1]])
            fig.add_trace(go.Scatter(
                x=xs, y=ys, mode="lines", fill="toself",
                line=dict(color=c, width=1.7), fillcolor=_rgba(c, 0.16),
                name=LABEL.get(m, m), legendgroup=m, showlegend=show, hoverinfo="skip"),
                row=row, col=1)
            wm = np.log10(max(p["wmean"], 1.0)); tick = dy.max() * 0.9
            fig.add_trace(go.Scatter(
                x=[wm, wm], y=[-tick, tick], mode="lines",
                line=dict(color=c, width=1.4, dash="dot"), legendgroup=m, showlegend=False,
                hovertemplate=(f"{LABEL.get(m, m)} · {outcome}<br>${p['tot']:.0f} staked over {p['n']} bets<br>"
                               f"$-weighted mean odds {p['wmean']:.2f} (unweighted {p['umean']:.2f})<extra></extra>")),
                row=row, col=1)

    fig.update_layout(
        title=dict(text="🎯 Dollar Density — odds spread weighted by stake, wins vs losses",
                   font=dict(size=14, color=TEXT_CLR), x=0.01),
        height=680, showlegend=True, violinmode="overlay",
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="'DM Mono', 'Courier New', monospace", size=13, color=TEXT_CLR),
        margin=dict(l=6, r=6, t=56, b=60),
        modebar=dict(orientation="v", bgcolor="rgba(0,0,0,0)", color="#555577", activecolor=ACCENT),
        dragmode=False,
        legend=dict(bgcolor="rgba(0,0,0,0.3)", bordercolor=GRID_CLR, borderwidth=1,
                    font=dict(size=12), orientation="h", yanchor="top", y=-0.05, xanchor="center", x=0.5))
    for ann in fig.layout.annotations:
        ann.update(font=dict(size=12, color="#8888aa"), x=0.01, xanchor="left")
    fig.update_yaxes(showticklabels=False, showgrid=False, zeroline=False, range=[-1.05, 1.05])
    for r in (1, 2):
        fig.update_xaxes(gridcolor=GRID_CLR, range=[XLO, XHI], row=r, col=1)
    fig.update_xaxes(tickmode="array", tickvals=[np.log10(t) for t in TICKO],
                     ticktext=[str(t) for t in TICKO],
                     title_text="odds (log scale) · dotted tick = stake-weighted mean odds", row=2, col=1)
    return fig

def chart_member_market_breakdown(df: pd.DataFrame, member: str) -> go.Figure:
    sub = df[df["user"] == member]
    grp = sub.groupby(["bet_type", "status"]).size().unstack(fill_value=0)
    for col in ["Win", "Loss", "Push"]:
        if col not in grp.columns: grp[col] = 0
    fig = go.Figure()
    fig.add_trace(go.Bar(name="Win", x=grp.index, y=grp["Win"], marker_color=WIN_COLOR))
    fig.add_trace(go.Bar(name="Loss", x=grp.index, y=grp["Loss"], marker_color=LOSS_COLOR))
    if grp["Push"].sum() > 0: fig.add_trace(go.Bar(name="Push", x=grp.index, y=grp["Push"], marker_color=PUSH_COLOR))
    fig.update_layout(barmode="stack")
    return apply_layout(fig, title=f"📊 {member} — Bets by Type", height=340)

def chart_member_monthly_pl(df: pd.DataFrame, member: str) -> go.Figure:
    df["aw_num"] = pd.to_numeric(df["actual_winnings"], errors="coerce").fillna(0)
    monthly = df[df["user"] == member].groupby("month")["aw_num"].sum().reset_index()
    fig = go.Figure(go.Bar(x=monthly["month"], y=monthly["aw_num"], marker_color=[WIN_COLOR if v >= 0 else LOSS_COLOR for v in monthly["aw_num"]], text=[f"${v:+.2f}" for v in monthly["aw_num"]], textposition="outside"))
    fig.add_hline(y=0, line_color=GRID_CLR)
    return apply_layout(fig, title=f"📅 {member} — Monthly P/L", height=320, showlegend=False)

def chart_bet_type_roi_bars(df: pd.DataFrame) -> go.Figure:
    df["aw_num"] = pd.to_numeric(df["actual_winnings"], errors="coerce").fillna(0)
    grp = df.groupby("bet_type").agg(bets=("odds", "count"), pl=("aw_num", "sum"), staked=("stake", "sum"))
    grp["roi"] = grp["pl"] / grp["staked"] * 100
    grp = grp[grp["bets"] >= 3].sort_values("roi")
    fig = go.Figure(go.Bar(y=grp.index, x=grp["roi"], orientation="h", marker_color=[WIN_COLOR if r >= 0 else LOSS_COLOR for r in grp["roi"]], text=[f"{r:+.1f}%" for r in grp["roi"]], textposition="outside"))
    fig.add_vline(x=0, line_color=GRID_CLR)
    return apply_layout(fig, title="📊 ROI by Bet Type (≥3 bets)", height=max(300, len(grp)*38), showlegend=False)


def chart_flow_of_money_sankey(df: pd.DataFrame) -> go.Figure:
    # Restrict to the 3 individuals and resolved bets
    users_to_track = ["John", "Richard", "Xander"]
    d = df[df["user"].isin(users_to_track) & df["status"].isin(["Win", "Loss", "Push"])].copy()
    
    if d.empty: 
        return go.Figure().update_layout(title="No individual data for Sankey")
        
    # Ensure numerical actual_winnings for accurate math
    d["aw_num"] = pd.to_numeric(d["actual_winnings"], errors="coerce").fillna(0)
    
    bet_types = sorted(d["bet_type"].unique().tolist())
    statuses = ["Win", "Loss", "Push"]
    
    labels = users_to_track + bet_types + statuses
    node_dict = {label: i for i, label in enumerate(labels)}
    
    # ─── 1. CALCULATE NODE STATS (The Blocks) ───
    node_stats = {l: {"bets": 0, "pl": 0.0, "stake": 0.0} for l in labels}
    
    for l in users_to_track:
        sub = d[d["user"] == l]
        node_stats[l] = {"bets": len(sub), "pl": sub["aw_num"].sum(), "stake": sub["stake"].sum()}
    for l in bet_types:
        sub = d[d["bet_type"] == l]
        node_stats[l] = {"bets": len(sub), "pl": sub["aw_num"].sum(), "stake": sub["stake"].sum()}
    for l in statuses:
        sub = d[d["status"] == l]
        node_stats[l] = {"bets": len(sub), "pl": sub["aw_num"].sum(), "stake": sub["stake"].sum()}
        
    node_customdata = []
    for l in labels:
        stk = node_stats[l]["stake"]
        pl = node_stats[l]["pl"]
        bets = node_stats[l]["bets"]
        roi = (pl / stk * 100) if stk > 0 else 0
        node_customdata.append([bets, f"${pl:+.2f}", f"{roi:+.2f}%"])

    # ─── 2. CALCULATE LINK STATS (The Flows) ───
    source, target, value, link_color, link_hovercolor, link_customdata = [], [], [], [], [], []
    
    # Link 1: User -> Bet Type
    user_mkt = d.groupby(["user", "bet_type"]).agg(
        stake=("stake", "sum"), bets=("uuid", "count"), pl=("aw_num", "sum")
    ).reset_index()
    
    for _, row in user_mkt.iterrows():
        source.append(node_dict[row["user"]])
        target.append(node_dict[row["bet_type"]])
        value.append(row["stake"])
        
        roi = (row["pl"] / row["stake"] * 100) if row["stake"] > 0 else 0
        link_customdata.append([row["bets"], f"${row['pl']:+.2f}", f"{roi:+.2f}%"])
        
        c = MEMBER_COLORS.get(row["user"], "#ffffff")
        link_color.append(_hex_to_rgba(c, 0.25))       # Resting: 25% opacity
        link_hovercolor.append(_hex_to_rgba(c, 0.85))  # Hovering: 85% opacity (Bright!)
        
    # Link 2: Bet Type -> Outcome
    mkt_stat = d.groupby(["bet_type", "status"]).agg(
        stake=("stake", "sum"), bets=("uuid", "count"), pl=("aw_num", "sum")
    ).reset_index()
    
    for _, row in mkt_stat.iterrows():
        source.append(node_dict[row["bet_type"]])
        target.append(node_dict[row["status"]])
        value.append(row["stake"])
        
        roi = (row["pl"] / row["stake"] * 100) if row["stake"] > 0 else 0
        link_customdata.append([row["bets"], f"${row['pl']:+.2f}", f"{roi:+.2f}%"])
        
        if row["status"] == "Win": c = WIN_COLOR
        elif row["status"] == "Loss": c = LOSS_COLOR
        else: c = PUSH_COLOR
        
        link_color.append(_hex_to_rgba(c, 0.25))       # Resting: 25% opacity
        link_hovercolor.append(_hex_to_rgba(c, 0.85))  # Hovering: 85% opacity (Bright!)

    # ─── 3. BUILD THE SANKEY ───
    fig = go.Figure(data=[go.Sankey(
        arrangement="snap", 
        node = dict(
            pad = 45, 
            thickness = 10, 
            line = dict(color = GRID_CLR, width = 0.5),
            label = labels,
            color = BG_CARD,
            customdata = node_customdata,
            hovertemplate = "<b>%{label}</b><br>Volume: $%{value:.2f}<br>Bets: %{customdata[0]}<br>P/L: %{customdata[1]}<br>ROI: %{customdata[2]}<extra></extra>"
        ),
        link = dict(
            source = source, 
            target = target, 
            value = value, 
            color = link_color,
            hovercolor = link_hovercolor,  # <--- The magic happens here
            customdata = link_customdata,
            hovertemplate = "<b>%{source.label} ➔ %{target.label}</b><br>Volume: $%{value:.2f}<br>Bets: %{customdata[0]}<br>P/L: %{customdata[1]}<br>ROI: %{customdata[2]}<extra></extra>"
        )
    )])
    
    return apply_layout(fig, title="", height=550)


def chart_accumulator_curse(df: pd.DataFrame) -> go.Figure:
    multis = df[df["bet_type"] == "Multi"].copy()
    multis["aw_num"] = pd.to_numeric(multis["actual_winnings"], errors="coerce").fillna(0)
    wins = (multis["status"] == "Win").sum(); losses = (multis["status"] == "Loss").sum()
    monthly = multis.groupby("month")["aw_num"].sum().reset_index()
    fig = make_subplots(rows=1, cols=2, subplot_titles=("Monthly Multi P/L", "Win/Loss Split"), specs=[[{"type": "bar"}, {"type": "pie"}]])
    fig.add_trace(go.Bar(x=monthly["month"], y=monthly["aw_num"], marker_color=[WIN_COLOR if v >= 0 else LOSS_COLOR for v in monthly["aw_num"]], showlegend=False), row=1, col=1)
    fig.add_trace(go.Pie(labels=["Win", "Loss"], values=[wins, losses], hole=0.5, marker=dict(colors=[WIN_COLOR, LOSS_COLOR])), row=1, col=2)
    return apply_layout(fig, title=f"💀 The Accumulator Curse — {wins/(wins+losses)*100 if wins+losses else 0:.0f}% win rate", height=360)

def chart_odds_bucket_roi(df: pd.DataFrame) -> go.Figure:
    df["aw_num"] = pd.to_numeric(df["actual_winnings"], errors="coerce").fillna(0)
    grp = df.groupby("odds_bucket").agg(bets=("odds", "count"), pl=("aw_num", "sum"), staked=("stake", "sum"), wins=("status", lambda x: (x == "Win").sum()))
    grp["roi"] = grp["pl"] / grp["staked"] * 100; grp["win_rate"] = grp["wins"] / grp["bets"] * 100
    grp = grp.reindex(["<1.40", "1.40\u20131.69", "1.70\u20131.99", "2.00\u20132.49", "2.50\u20133.49", "3.50+"]).dropna()
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Bar(x=grp.index, y=grp["roi"], marker_color=[WIN_COLOR if r >= 0 else LOSS_COLOR for r in grp["roi"]], name="ROI %"), secondary_y=False)
    fig.add_trace(go.Scatter(x=grp.index, y=grp["win_rate"], mode="lines+markers", line=dict(color=PUSH_COLOR, dash="dash"), name="Win Rate %"), secondary_y=True)
    return apply_layout(fig, title="🎲 ROI & Win Rate by Odds Bucket", height=340)

def chart_competition_roi(df: pd.DataFrame) -> go.Figure:
    df["aw_num"] = pd.to_numeric(df["actual_winnings"], errors="coerce").fillna(0)
    grp = df.groupby("competition").agg(pl=("aw_num", "sum"), staked=("stake", "sum"), bets=("odds", "count"))
    grp["roi"] = grp["pl"] / grp["staked"] * 100
    grp = grp[grp["bets"] >= 3].sort_values("roi")
    fig = go.Figure(go.Bar(y=grp.index, x=grp["roi"], orientation="h", marker_color=[WIN_COLOR if r >= 0 else LOSS_COLOR for r in grp["roi"]], text=[f"{r:+.1f}% ({int(b)} bets)" for r, b in zip(grp["roi"], grp["bets"])], textposition="outside"))
    fig.add_vline(x=0, line_color=GRID_CLR)
    return apply_layout(fig, title="🏆 ROI by Competition", height=max(280, len(grp)*40), showlegend=False)

def chart_roi_rollercoaster(df: pd.DataFrame) -> go.Figure:
    df2 = df.sort_values("date").copy()
    df2["rolling_roi"] = rolling_roi(df2, 20)
    fig = go.Figure(go.Scatter(x=df2["date_str"], y=df2["rolling_roi"], fill="tozeroy", fillcolor="rgba(86,180,233,0.12)", line=dict(color=ACCENT, width=2.5)))
    fig.add_hline(y=0, line_dash="dash", line_color=GRID_CLR)
    return apply_layout(fig, title="🎢 20-Bet Rolling ROI", height=400, showlegend=False)


def chart_weekday_bubble(df: pd.DataFrame) -> go.Figure:
    d = df[df["status"].isin(["Win", "Loss", "Push"])].copy()
    d["aw_num"] = pd.to_numeric(d["actual_winnings"], errors="coerce").fillna(0)
    
    grp = d.groupby(["month", "weekday"]).agg(bets=("uuid", "count"), pl=("aw_num", "sum")).reset_index()
    
    days_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    grp["weekday"] = pd.Categorical(grp["weekday"], categories=days_order, ordered=True)
    grp = grp.sort_values(["month", "weekday"])

    fig = go.Figure()
    
    colors = [WIN_COLOR if p > 0 else (LOSS_COLOR if p < 0 else PUSH_COLOR) for p in grp["pl"]]
    fig.add_trace(go.Scatter(
        x=grp["month"], y=grp["weekday"], 
        mode="markers",
        marker=dict(
            size=grp["bets"], 
            sizemode="area", sizeref=2.*max(grp["bets"])/(40.**2), sizemin=4, 
            color=colors,
            opacity=0.8,
            line=dict(width=1, color=BG_DARK)
        ),
        text=[f"P/L: ${p:+.2f}<br>Bets: {b}" for p, b in zip(grp["pl"], grp["bets"])],
        hovertemplate="<b>%{x} %{y}</b><br>%{text}<extra></extra>"
    ))

    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(showgrid=False)
    
    return apply_layout(fig, title="🫧 Day × Month Volume & P/L", height=340, showlegend=False)


def chart_odds_correlations(df: pd.DataFrame) -> go.Figure:
    d = df[df["status"].isin(["Win", "Loss", "Push"])].copy()
    d["aw_num"] = pd.to_numeric(d["actual_winnings"], errors="coerce").fillna(0)
    
    fig = make_subplots(rows=1, cols=2, subplot_titles=("Stake vs Odds", "Odds vs P/L"))
    fig.add_trace(go.Scatter(x=d["stake"], y=d["odds"], mode="markers", marker=dict(color=ACCENT, size=6, opacity=0.6), name="Stake vs Odds"), row=1, col=1)
    colors = [WIN_COLOR if p > 0 else (LOSS_COLOR if p < 0 else PUSH_COLOR) for p in d["aw_num"]]
    fig.add_trace(go.Scatter(x=d["odds"], y=d["aw_num"], mode="markers", marker=dict(color=colors, size=6, opacity=0.7), name="Odds vs P/L"), row=1, col=2)
    
    fig.update_xaxes(title_text="Stake ($)", title_font=dict(size=10), row=1, col=1)
    fig.update_yaxes(title_text="Odds", title_font=dict(size=10), row=1, col=1)
    fig.update_xaxes(title_text="Odds", title_font=dict(size=10), row=1, col=2)
    fig.update_yaxes(title_text="P/L ($)", title_font=dict(size=10), row=1, col=2)
    return apply_layout(fig, title="🔗 Odds & Stake Correlations", height=360, showlegend=False)

def _hex_to_rgba(hex_color: str, alpha: float = 0.15) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"

def chart_member_radar(df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    stats = {m: member_stats(df[df["user"] == m], m) for m in MEMBERS}
    min_wr, max_wr = 0, max([s["win_rate"] for s in stats.values()] + [1])
    min_roi, max_roi = min([s["roi"] for s in stats.values()] + [0]), max([s["roi"] for s in stats.values()] + [1])
    min_odds, max_odds = 1.0, max([s["avg_odds"] for s in stats.values()] + [1.1])
    min_bets, max_bets = 0, max([s["bets"] for s in stats.values()] + [1])
    effs = [(stats[m]["pl"] / stats[m]["staked"] * 100) if stats[m]["staked"] > 0 else 0 for m in MEMBERS]
    min_eff, max_eff = min(effs + [0]), max(effs + [1])
    def norm(val, vmin, vmax): return 50 if vmax == vmin else 20 + 80 * (val - vmin) / (vmax - vmin)
    
    for m in MEMBERS:
        s = stats[m]
        eff = (s["pl"] / s["staked"] * 100) if s["staked"] > 0 else 0
        r_vals = [norm(s["win_rate"], min_wr, max_wr), norm(s["roi"], min_roi, max_roi), norm(s["avg_odds"], min_odds, max_odds), norm(s["bets"], min_bets, max_bets), norm(eff, min_eff, max_eff)]
        r_vals.append(r_vals[0]) 
        fig.add_trace(go.Scatterpolar(r=r_vals, theta=["Win Rate", "ROI", "Avg Odds", "Bets", "Efficiency", "Win Rate"], fill="toself", name=m, line=dict(color=MEMBER_COLORS[m]), fillcolor=_hex_to_rgba(MEMBER_COLORS[m])))
    fig.update_layout(polar=dict(radialaxis=dict(visible=False, range=[0, 100]), bgcolor="rgba(0,0,0,0)"))
    return apply_layout(fig, title="🕸️ Member Radar", height=400)

def chart_waterfall(df: pd.DataFrame) -> go.Figure:
    # Filter for resolved bets only (exclude Pending and Voids)
    resolved_bets = df[df["status"].isin(["Win", "Loss", "Push"])]
    
    # Get the last 15 resolved bets across the entire syndicate
    df2 = resolved_bets.sort_values("date").tail(15).copy()
    title = "🌊 Recent Syndicate Form (All Members)"

    df2["aw_num"] = pd.to_numeric(df2["actual_winnings"], errors="coerce").fillna(0)
    
    # Create a mathematically unique ID for the X-axis to prevent 
    # identical string values (like two matches on the same day) from stacking.
    df2["unique_label"] = df2["event"].astype(str).str[:12] + " [" + df2["uuid"].astype(str).str[:4] + "]"
    
    fig = go.Figure(go.Waterfall(
        name="Profit",
        orientation="v",
        x=df2["unique_label"],
        y=df2["aw_num"],
        measure=["relative"] * len(df2),
        text=[f"${v:+.2f}" for v in df2["aw_num"]],
        textposition="outside",
        decreasing=dict(marker=dict(color=LOSS_COLOR)),
        increasing=dict(marker=dict(color=WIN_COLOR)),
        totals=dict(marker=dict(color=ACCENT)),
        connector=dict(line=dict(color=GRID_CLR, width=1))
    ))

    # Clean up the display so the user only sees the readable event name
    clean_labels = df2["event"].astype(str).str[:14] + ".."
    fig.update_xaxes(
        tickmode='array',
        tickvals=df2["unique_label"],
        ticktext=clean_labels,
        tickangle=45
    )
    
    return apply_layout(fig, title=title, height=450, showlegend=False)

def chart_team_vs_individual(df: pd.DataFrame) -> go.Figure:
    groups = MEMBERS + ["Team"]
    rois =[team_summary(df[df["user"] == g])["roi"] if g == "Team" else member_stats(df[df["user"] == g], g)["roi"] for g in groups]
    pls = [team_summary(df[df["user"] == g])["pl"] if g == "Team" else member_stats(df[df["user"] == g], g)["pl"] for g in groups]
    fig = make_subplots(rows=1, cols=2, subplot_titles=("ROI %", "P/L ($)"))
    fig.add_trace(go.Bar(x=groups, y=rois, marker_color=[MEMBER_COLORS.get(g, ACCENT) for g in groups], text=[f"{r:+.1f}%" for r in rois]), row=1, col=1)
    fig.add_trace(go.Bar(x=groups, y=pls, marker_color=[MEMBER_COLORS.get(g, ACCENT) for g in groups], text=[f"${p:+.2f}" for p in pls]), row=1, col=2)
    return apply_layout(fig, title="👥 Team Pool vs Individuals", height=340, showlegend=False)

def chart_top_teams(df: pd.DataFrame) -> go.Figure:
    teams = pd.concat([df['home_team'], df['away_team']]).dropna()
    teams = teams[teams.str.lower() != 'multiple']
    top = teams.value_counts().head(15)
    fig = go.Figure(go.Bar(y=top.index[::-1], x=top.values[::-1], orientation="h", marker_color=OKABE_ITO[1], text=top.values[::-1], textposition="outside"))
    return apply_layout(fig, title="⚽ Most Bet-On Teams", height=max(300, len(top)*32), showlegend=False)

def chart_pl_by_selection(df: pd.DataFrame) -> go.Figure:
    df["aw_num"] = pd.to_numeric(df["actual_winnings"], errors="coerce").fillna(0)
    grp = df.groupby("selection").agg(pl=("aw_num", "sum"), bets=("odds", "count")).sort_values("pl")
    grp = grp[grp["bets"] >= 3]
    fig = go.Figure(go.Bar(y=grp.index, x=grp["pl"], orientation="h", marker_color=[WIN_COLOR if p >= 0 else LOSS_COLOR for p in grp["pl"]], text=[f"${p:+.2f}" for p in grp["pl"]]))
    return apply_layout(fig, title="🎯 P/L by Selection (≥3 bets)", height=max(300, len(grp)*32), showlegend=False)

def chart_longest_streaks(df: pd.DataFrame) -> go.Figure:
    def max_s(sub, target):
        b = c = 0
        for s in sub.sort_values("date")["status"]:
            if s == target: c += 1; b = max(b, c)
            elif s in ("Win", "Loss"): c = 0
        return b
    w_str = [max_s(df[df["user"] == m], "Win") for m in MEMBERS]
    l_str =[max_s(df[df["user"] == m], "Loss") for m in MEMBERS]
    fig = go.Figure()
    fig.add_trace(go.Bar(x=MEMBERS, y=w_str, name="Win Streak", marker_color=WIN_COLOR, text=w_str))
    fig.add_trace(go.Bar(x=MEMBERS, y=[-x for x in l_str], name="Loss Streak", marker_color=LOSS_COLOR, text=[f"-{x}" for x in l_str]))
    return apply_layout(fig, title="🔥 Longest Streaks", height=320)

def chart_ev_proxy(df: pd.DataFrame, title: str = "📐 Edge Proxy — Actual vs Implied") -> go.Figure:
    grp = df[df["status"].isin(["Win", "Loss"])].groupby("odds_bucket").agg(wins=("status", lambda x: (x == "Win").sum()), bets=("status", "count"), avg_odds=("odds", "mean"))
    grp["win_rate"] = grp["wins"] / grp["bets"] * 100; grp["implied"] = 1 / grp["avg_odds"] * 100
    grp = grp.reindex(["<1.40", "1.40\u20131.69", "1.70\u20131.99", "2.00\u20132.49", "2.50\u20133.49", "3.50+"]).dropna()
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=grp.index, y=grp["win_rate"], name="Actual Win %", line=dict(color=WIN_COLOR)))
    fig.add_trace(go.Scatter(x=grp.index, y=grp["implied"], name="Implied Win %", line=dict(color=LOSS_COLOR, dash="dash")))
    return apply_layout(fig, title=title, height=340)

def chart_year_on_year(df: pd.DataFrame) -> go.Figure:
    df["aw_num"] = pd.to_numeric(df["actual_winnings"], errors="coerce").fillna(0)
    grp = df.groupby("year").agg(pl=("aw_num", "sum"), bets=("odds", "count")).reset_index()
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Bar(x=grp["year"].astype(str), y=grp["pl"], marker_color=[WIN_COLOR if p >= 0 else LOSS_COLOR for p in grp["pl"]], name="P/L"), secondary_y=False)
    fig.add_trace(go.Scatter(x=grp["year"].astype(str), y=grp["bets"], name="Bets", line=dict(color=PUSH_COLOR, dash="dot")), secondary_y=True)
    return apply_layout(fig, title="📆 Year-on-Year", height=320)

def chart_monthly_volatility(df: pd.DataFrame) -> go.Figure:
    df["aw_num"] = pd.to_numeric(df["actual_winnings"], errors="coerce").fillna(0)
    monthly = df.groupby("month")["aw_num"].agg(std="std", count="count", mean="mean").reset_index()
    monthly = monthly[monthly["count"] >= 3]
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Bar(x=monthly["month"], y=monthly["std"], name="Std Dev", marker_color=OKABE_ITO[4]), secondary_y=False)
    fig.add_trace(go.Scatter(x=monthly["month"], y=monthly["mean"], name="Avg P/L", line=dict(color=WIN_COLOR)), secondary_y=True)
    return apply_layout(fig, title="📊 Monthly Volatility", height=340)

def chart_longshot_vs_fav(df: pd.DataFrame) -> go.Figure:
    def tier(o): return "Favourite (<2.0)" if o < 2.0 else "Value (2.0–3.49)" if o < 3.5 else "Long-shot (3.5+)"
    d = df[df["status"].isin(["Win", "Loss"])].copy()
    d["tier"] = d["odds"].apply(tier)
    d["aw_num"] = pd.to_numeric(d["actual_winnings"], errors="coerce").fillna(0)
    grp = d.groupby("tier").agg(bets=("odds", "count"), wins=("status", lambda x: (x == "Win").sum()), pl=("aw_num", "sum"), staked=("stake", "sum"))
    grp["roi"] = grp["pl"] / grp["staked"] * 100; grp["win_rate"] = grp["wins"] / grp["bets"] * 100
    grp = grp.reindex(["Favourite (<2.0)", "Value (2.0–3.49)", "Long-shot (3.5+)"]).dropna()
    fig = make_subplots(rows=1, cols=2, subplot_titles=("ROI % by Tier", "Win Rate % by Tier"))
    fig.add_trace(go.Bar(x=grp.index, y=grp["roi"], marker_color=[WIN_COLOR if r >= 0 else LOSS_COLOR for r in grp["roi"]]), row=1, col=1)
    fig.add_trace(go.Bar(x=grp.index, y=grp["win_rate"], marker_color=OKABE_ITO[2]), row=1, col=2)
    return apply_layout(fig, title="🏹 Edge by Odds Tier", height=340, showlegend=False)

def chart_voting_success(df: pd.DataFrame) -> go.Figure:
    ind = df[df["user"].isin(MEMBERS) & df["status"].isin(["Win", "Loss", "Push"])].copy()
    ind["aw_num"] = pd.to_numeric(ind["actual_winnings"], errors="coerce").fillna(0)
    ind["agreed"] = ind.groupby(["event", "selection"])["user"].transform("nunique") >= 2
    agreed = ind[ind["agreed"]].groupby(["event", "selection"]).first().reset_index()
    solo = ind[~ind["agreed"]]
    
    def s(sub):
        w = (sub["status"] == "Win").sum()
        l = (sub["status"] == "Loss").sum()
        pl = sub["aw_num"].sum()
        st = sub["stake"].sum()
        return {"win_rate": round(w / (w + l) * 100, 2) if (w + l) > 0 else 0, "roi": round(pl / st * 100, 2) if st > 0 else 0, "pl": round(float(pl), 2), "bets": int(len(sub))}

    ag = s(agreed)
    mbr = {m: s(solo[solo["user"] == m]) for m in MEMBERS}
    entries = [("🤝 Agreed", ag, ACCENT)] + [(m, mbr[m], MEMBER_COLORS[m]) for m in MEMBERS]
    
    fig = make_subplots(rows=len(entries), cols=2, column_widths=[0.55, 0.45], vertical_spacing=0.15, horizontal_spacing=0.04, specs=[[{"type": "indicator"}, {"type": "indicator"}]] * len(entries))

    def wr_color(v): return WIN_COLOR if v >= 60 else (PUSH_COLOR if v >= 45 else LOSS_COLOR)
    def roi_color(v): return WIN_COLOR if v >= 0 else LOSS_COLOR

    for row_idx, (label, st_dict, color) in enumerate(entries, start=1):
        fig.add_trace(go.Indicator(mode="gauge+number", value=st_dict["win_rate"], number=dict(suffix="%", font=dict(size=22, family="DM Mono", color=wr_color(st_dict["win_rate"])), valueformat=".1f"), gauge=dict(axis=dict(range=[0, 100], tickcolor=GRID_CLR, tickfont=dict(color=TEXT_CLR, size=8), nticks=5), bar=dict(color=color, thickness=0.4), bgcolor="rgba(0,0,0,0)", bordercolor=GRID_CLR, steps=[dict(range=[0, 45], color="rgba(230,159,0,0.08)"), dict(range=[45, 60], color="rgba(153,153,153,0.06)"), dict(range=[60, 100], color="rgba(86,180,233,0.08)")], threshold=dict(line=dict(color=PUSH_COLOR, width=2), value=50))), row=row_idx, col=1)
        fig.add_trace(go.Indicator(mode="number", value=st_dict["roi"], number=dict(suffix="%", font=dict(size=24, family="DM Mono", color=roi_color(st_dict["roi"])), valueformat="+.1f")), row=row_idx, col=2)
        
        row_height = (1.0 - (len(entries) - 1) * 0.15) / len(entries)
        y_bottom = 1.0 - ((row_idx - 1) * row_height) - ((row_idx - 1) * 0.15) - row_height
        
        fig.add_annotation(x=0.26, y=y_bottom - 0.02, text=f"<b><span style='color:{color}'>{label}</span></b><br><span style='color:{TEXT_CLR};font-size:11px'>Win Rate</span>", showarrow=False, font=dict(size=14), xanchor="center", yanchor="top", xref="paper", yref="paper")
        fig.add_annotation(x=0.78, y=y_bottom - 0.02, text=f"<b><span style='color:{color}'>{label if label == '🤝 Agreed' else label + ' Solo'} ROI</span></b><br><span style='color:{TEXT_CLR};font-size:11px'>P/L ${st_dict['pl']:+.2f} · {st_dict['bets']} bets</span>", showarrow=False, font=dict(size=14), xanchor="center", yanchor="top", xref="paper", yref="paper")

    return apply_layout(fig, title="🗳️ Agreed Picks vs Solo Bets", height=850, showlegend=False, margin=dict(l=6, r=6, t=52, b=90))

# ─────────────────────────────────────────────────────────────────────────────
# ANIMATED CHARTS
# ─────────────────────────────────────────────────────────────────────────────
def _anim_buttons(duration=400, transition=200): return[dict(type="buttons", showactive=False, y=-0.20, x=0.0, buttons=[dict(label="▶ Play", method="animate", args=[None, dict(frame=dict(duration=duration, redraw=True), fromcurrent=True, transition=dict(duration=transition))]), dict(label="⏸ Pause", method="animate", args=[[None], dict(frame=dict(duration=0, redraw=False), mode="immediate")])])]
def _anim_slider(labels, duration=400, transition=200): return [dict(steps=[dict(method="animate", args=[[lbl], dict(mode="immediate", frame=dict(duration=duration, redraw=True), transition=dict(duration=transition))], label=str(lbl)) for lbl in labels], active=0, y=-0.12, len=1.0, x=0)]

def chart_anim_bankroll_worm(df: pd.DataFrame, opening: float = 0.00, bankroll_df: pd.DataFrame = None) -> go.Figure:
    src_df = (bankroll_df if bankroll_df is not None else df).sort_values("date").copy()
    src_df["bankroll_change"] = pd.to_numeric(src_df["actual_winnings"], errors="coerce").fillna(0)
    src_df["bankroll"] = opening + src_df["bankroll_change"].cumsum()
    if "date_str" not in src_df.columns: src_df["date_str"] = src_df["date"].dt.strftime("%Y-%m-%d")
    frames =[go.Frame(name=str(i), data=[go.Scatter(x=src_df["date_str"].iloc[:i], y=src_df["bankroll"].iloc[:i], mode="lines")]) for i in range(1, len(src_df) + 1)]
    fig = go.Figure(data=[go.Scatter(x=src_df["date_str"].iloc[:1], y=src_df["bankroll"].iloc[:1])], frames=frames)
    fig.update_layout(updatemenus=_anim_buttons(60, 30), sliders=_anim_slider(range(1, len(src_df) + 1), 60, 30), xaxis=dict(range=[src_df["date_str"].iloc[0], src_df["date_str"].iloc[-1]]))
    return apply_layout(fig, title="📈 Bankroll Worm", height=500, showlegend=False)

def chart_anim_member_worm(df: pd.DataFrame) -> go.Figure:
    ind = df[df["user"].isin(MEMBERS)].sort_values("date").copy()
    ind["aw_num"] = pd.to_numeric(ind["actual_winnings"], errors="coerce").fillna(0)
    all_dates = sorted(ind["date"].unique())
    running = {m: 0.0 for m in MEMBERS}
    snaps =[]
    for d in all_dates:
        for _, row in ind[ind["date"] == d].iterrows(): running[row["user"]] += row["aw_num"]
        snaps.append({"date": str(d)[:10], **{m: round(running[m], 2) for m in MEMBERS}})
    snaps = pd.DataFrame(snaps)
    min_y, max_y = snaps[MEMBERS].min().min(), snaps[MEMBERS].max().max()
    pad = max(10, (max_y - min_y) * 0.1)
    
    def mkt(sub): return [go.Scatter(x=sub["date"], y=sub[m], mode="lines", name=m, line=dict(color=MEMBER_COLORS[m])) for m in MEMBERS]
    frames =[go.Frame(name=snaps["date"].iloc[i], data=mkt(snaps.iloc[:i+1])) for i in range(len(snaps))]
    fig = go.Figure(data=mkt(snaps.iloc[:1]), frames=frames)
    fig.update_layout(updatemenus=_anim_buttons(280, 160), sliders=_anim_slider(snaps["date"], 280, 160), xaxis=dict(range=[snaps["date"].iloc[0], snaps["date"].iloc[-1]]), yaxis=dict(range=[min_y - pad, max_y + pad]))
    return apply_layout(fig, title="🏎️ Member P/L Worm Race", height=520, showlegend=True)

def chart_anim_win_rate_evolution(df: pd.DataFrame) -> go.Figure:
    fig_data = {}
    for m in MEMBERS:
        sub = df[(df["user"] == m) & df["status"].isin(["Win", "Loss"])].sort_values("date").reset_index(drop=True)
        sub["roll_wr"] = sub["status"].eq("Win").rolling(10, min_periods=5).mean() * 100
        sub = sub.dropna(subset=["roll_wr"]).reset_index(drop=True)
        sub["date_str"] = sub["date"].dt.strftime("%Y-%m-%d")
        fig_data[m] = sub
    all_dates = sorted(set(d for m in MEMBERS for d in fig_data[m]["date_str"].tolist()))
    if not all_dates: return go.Figure().update_layout(title="Not enough data")
    def mkf(c): return [go.Scatter(x=fig_data[m][fig_data[m]["date_str"] <= c]["date_str"], y=fig_data[m][fig_data[m]["date_str"] <= c]["roll_wr"], mode="lines", name=m, line=dict(color=MEMBER_COLORS[m])) for m in MEMBERS]
    frames =[go.Frame(name=d, data=mkf(d)) for d in all_dates]
    fig = go.Figure(data=mkf(all_dates[0]), frames=frames)
    fig.update_layout(updatemenus=_anim_buttons(300, 150), sliders=_anim_slider(all_dates, 300, 150), yaxis=dict(range=[0, 108]))
    return apply_layout(fig, title="🎯 10-Bet Rolling Win Rate", height=520, showlegend=True)


# ─────────────────────────────────────────────────────────────────────────────
# MAIN APP
# ─────────────────────────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────
# WORLD CUP 2026
# ─────────────────────────────────────────────────────────────────────────────
# ── WORLD CUP CONFIG ───────────────────────────────────────────────────────────
WC_COMPETITION = "FIFA World Cup 2026"
WC_ROUND_MAP = {1:"Group · MD1", 2:"Group · MD2", 3:"Group · MD3", 4:"Round of 32",
                5:"Round of 16", 6:"Quarter-finals", 7:"Semi-finals", 8:"Final"}
WC_ROUND_SHORT = {1:"MD1", 2:"MD2", 3:"MD3", 4:"R32", 5:"R16", 6:"QF", 7:"SF", 8:"Final"}
WC_LABEL = {"John":"John","Richard":"Richard","Xander":"Xander","Team":"Bot"}
WC_ORDER = ["John","Richard","Xander","Team"]
_SETTLED = ["Win","Loss","Push"]


def wc_prepare(df: pd.DataFrame) -> pd.DataFrame:
    """Filter the enriched ledger to the World Cup and attach round labels."""
    w = df[df["competition"] == WC_COMPETITION].copy()
    if w.empty: return w
    w["date"] = pd.to_datetime(w["date"])
    w["aw_num"] = pd.to_numeric(w["actual_winnings"], errors="coerce").fillna(0)
    w["stake"]  = pd.to_numeric(w["stake"], errors="coerce").fillna(0)
    w["odds"]   = pd.to_numeric(w["odds"], errors="coerce")
    md = pd.to_numeric(w["matchday"], errors="coerce")
    w["round_num"]   = md
    w["round_label"] = md.map(WC_ROUND_MAP).fillna("Outright / Other")
    w["round_short"] = md.map(WC_ROUND_SHORT).fillna("—")
    w["label"] = w["user"].map(WC_LABEL).fillna(w["user"])
    w["implied"] = 1.0 / w["odds"].replace(0, np.nan)
    w = w.sort_values(["date"]).reset_index(drop=True)
    return w


def wc_round_options(w: pd.DataFrame):
    """Ordered list of round labels present in the data (group stages collapsed option handled in UI)."""
    present = sorted(w["round_num"].dropna().unique())
    return [WC_ROUND_MAP.get(int(r), f"Round {int(r)}") for r in present]


def wc_stats(w: pd.DataFrame, user: str) -> dict:
    s = w[(w["user"] == user) & (w["status"].isin(_SETTLED))]
    wins = (s["status"]=="Win").sum(); losses=(s["status"]=="Loss").sum(); pushes=(s["status"]=="Push").sum()
    staked = s["stake"].sum(); pl = s["aw_num"].sum()
    roi = pl/staked*100 if staked>0 else 0
    decisive = wins+losses
    hit = wins/decisive*100 if decisive>0 else 0
    implied = s[s["status"].isin(["Win","Loss"])]["implied"].mean()*100 if decisive>0 else 0
    return dict(bets=len(s), wins=wins, losses=losses, pushes=pushes, staked=staked,
                pl=pl, roi=roi, hit=hit, implied=implied, avg_odds=s["odds"].mean())


# 1 ── CUMULATIVE WORM (date-aligned, all players share the x-axis) ─────────────
def chart_wc_worm(w: pd.DataFrame, title="📈 Cumulative Profit — The Reckoning") -> go.Figure:
    s = w[w["status"].isin(_SETTLED)].sort_values("date").copy()
    if s.empty: return apply_layout(go.Figure(), title="No settled bets", height=360, showlegend=False)
    fig = go.Figure()
    fig.add_hline(y=0, line_dash="dash", line_color=GRID_CLR)
    for user in WC_ORDER:
        u = s[s["user"] == user].sort_values("date").copy()
        if u.empty: continue
        u["cum"] = u["aw_num"].cumsum()
        color = MEMBER_COLORS.get(user, ACCENT)
        x = u["date"].tolist(); y = u["cum"].tolist()
        fig.add_trace(go.Scatter(
            x=x, y=y, mode="lines", name=WC_LABEL.get(user, user),
            line=dict(color=color, width=3, shape="spline", smoothing=0.5),
            hovertemplate=f"{WC_LABEL.get(user,user)}<br>%{{x|%b %d}}<br>cum $%{{y:+.2f}}<extra></extra>"))
        fig.add_trace(go.Scatter(
            x=[x[-1]], y=[y[-1]], mode="markers+text", showlegend=False,
            marker=dict(color=color, size=9),
            text=[f" {WC_LABEL.get(user,user)} ${y[-1]:+.0f}"], textposition="middle right",
            textfont=dict(color=color, size=11, family="DM Mono"), cliponaxis=False))
    fig.update_xaxes(title="")
    fig.update_yaxes(title="cumulative P/L ($)")
    return apply_layout(fig, title=title, height=440)


# 2 ── THE TAPE (per-bet running total, coloured by player · 1 trace/player) ─────
def chart_wc_tape(w: pd.DataFrame) -> go.Figure:
    s = w[w["status"].isin(_SETTLED)].sort_values("date").reset_index(drop=True).copy()
    if s.empty: return apply_layout(go.Figure(), title="No settled bets", height=360, showlegend=False)
    s["cum"] = s["aw_num"].cumsum()
    s["prev"] = s["cum"].shift(1).fillna(0)
    s["x"] = np.arange(len(s))
    fig = go.Figure()
    for user in WC_ORDER:
        u = s[s["user"] == user]
        if u.empty: continue
        color = MEMBER_COLORS.get(user, ACCENT)
        cd = np.column_stack([u["round_short"].astype(str), u["home_team"].astype(str),
                              u["away_team"].astype(str), u["bet_type"].astype(str),
                              u["odds"].to_numpy(), u["cum"].to_numpy()])
        fig.add_trace(go.Bar(
            x=u["x"], y=u["aw_num"], base=u["prev"], width=0.82,
            marker=dict(color=color, line=dict(width=0)),
            name=WC_LABEL.get(user, user), customdata=cd,
            hovertemplate=("%{customdata[1]} v %{customdata[2]} · %{customdata[0]}<br>"
                           "%{customdata[3]} @ %{customdata[4]:.2f}<br>"
                           "P/L $%{y:+.2f} → running $%{customdata[5]:+.2f}<extra></extra>")))
    fig.add_trace(go.Scatter(x=s["x"], y=s["cum"], mode="lines",
                             line=dict(color=TEXT_CLR, width=1.4, shape="hv"),
                             name="running net", hoverinfo="skip"))
    fig.add_hline(y=0, line_color=GRID_CLR)
    fig.update_xaxes(title="every bet, in chronological order", showticklabels=False)
    fig.update_yaxes(title="running profit ($)")
    return apply_layout(fig, title="🎞️ The Tape — every bet, and how deep the hole got",
                        height=420, barmode="overlay")


# 3 ── DRAWDOWN ─────────────────────────────────────────────────────────────────
def chart_wc_drawdown(w: pd.DataFrame) -> go.Figure:
    s = w[w["status"].isin(_SETTLED)].sort_values("date").reset_index(drop=True).copy()
    if s.empty: return apply_layout(go.Figure(), title="No settled bets", height=320, showlegend=False)
    s["cum"] = s["aw_num"].cumsum()
    s["peak"] = s["cum"].cummax()
    s["dd"] = s["cum"] - s["peak"]
    fig = go.Figure(go.Scatter(x=list(s.index), y=s["dd"], mode="lines",
                               line=dict(color=LOSS_COLOR, width=2), fill="tozeroy",
                               fillcolor="rgba(230,159,0,0.15)", name="drawdown"))
    mx = s["dd"].idxmin()
    if s.loc[mx, "dd"] < 0:
        fig.add_annotation(x=mx, y=s.loc[mx, "dd"], text=f"max drawdown<br>${s.loc[mx,'dd']:.2f}",
                           showarrow=True, arrowhead=2, arrowcolor=LOSS_COLOR, ay=-34,
                           font=dict(color=LOSS_COLOR, size=11))
    fig.add_hline(y=0, line_color=GRID_CLR)
    fig.update_xaxes(title="bet number", showticklabels=False)
    fig.update_yaxes(title="distance below high-water mark ($)")
    return apply_layout(fig, title="🌊 Drawdown — below the high-water mark", height=320, showlegend=False)


# 4 ── MONEY FLOW SANKEY (Member → Bet Type → Outcome) ──────────────────────────
def chart_wc_sankey(w: pd.DataFrame) -> go.Figure:
    s = w[w["status"].isin(_SETTLED)].copy()
    if s.empty: return apply_layout(go.Figure(), title="No settled bets", height=420, showlegend=False)
    s["outcome"] = s["status"].map({"Win":"Won","Loss":"Lost","Push":"Push"})
    members = [WC_LABEL.get(m, m) for m in WC_ORDER if not s[s["user"]==m].empty]
    member_src = [m for m in WC_ORDER if not s[s["user"]==m].empty]
    bet_types = sorted(s["bet_type"].dropna().unique())
    outcomes = [o for o in ["Won","Push","Lost"] if o in s["outcome"].values]
    nodes = members + bet_types + outcomes
    idx = {n:i for i,n in enumerate(nodes)}
    m_idx = {m: idx[WC_LABEL.get(m,m)] for m in member_src}
    node_colors = ([MEMBER_COLORS.get(m, ACCENT) for m in member_src]
                   + [ACCENT]*len(bet_types)
                   + [WIN_COLOR if o=="Won" else PUSH_COLOR if o=="Push" else LOSS_COLOR for o in outcomes])

    def rgba(hexc, a=0.45):
        h = hexc.lstrip("#"); return f"rgba({int(h[0:2],16)},{int(h[2:4],16)},{int(h[4:6],16)},{a})"

    src, tgt, val, lcol = [], [], [], []
    # member → bet type
    for (m, bt), g in s.groupby(["user","bet_type"]):
        src.append(m_idx[m]); tgt.append(idx[bt]); val.append(float(g["stake"].sum()))
        lcol.append(rgba(MEMBER_COLORS.get(m, ACCENT)))
    # bet type → outcome
    for (bt, oc), g in s.groupby(["bet_type","outcome"]):
        src.append(idx[bt]); tgt.append(idx[oc]); val.append(float(g["stake"].sum()))
        c = WIN_COLOR if oc=="Won" else PUSH_COLOR if oc=="Push" else LOSS_COLOR
        lcol.append(rgba(c, 0.35))

    fig = go.Figure(go.Sankey(
        arrangement="snap",
        node=dict(pad=14, thickness=16, line=dict(color=GRID_CLR, width=0.5),
                  label=nodes, color=node_colors,
                  hovertemplate="%{label}<br>$%{value:.0f} staked<extra></extra>"),
        link=dict(source=src, target=tgt, value=val, color=lcol,
                  hovertemplate="%{source.label} → %{target.label}<br>$%{value:.0f}<extra></extra>")))
    return apply_layout(fig, title="🌐 Money Flow — Member → Market → Outcome (width = stake)",
                        height=520, showlegend=False)


# 5 ── P/L BY MARKET TYPE (diverging bars) ──────────────────────────────────────
def chart_wc_market_pl(w: pd.DataFrame) -> go.Figure:
    s = w[w["status"].isin(_SETTLED)].copy()
    if s.empty: return apply_layout(go.Figure(), title="No settled bets", height=360, showlegend=False)
    grp = s.groupby("bet_type").agg(pl=("aw_num","sum"), n=("aw_num","count")).sort_values("pl")
    fig = go.Figure(go.Bar(
        y=grp.index, x=grp["pl"], orientation="h",
        marker=dict(color=[WIN_COLOR if v>=0 else LOSS_COLOR for v in grp["pl"]]),
        text=[f"${v:+.2f}  (n{n})" for v,n in zip(grp["pl"], grp["n"])],
        textposition="outside", textfont=dict(size=10, family="DM Mono")))
    fig.add_vline(x=0, line_color=GRID_CLR)
    fig.update_xaxes(title="net profit / loss ($)")
    return apply_layout(fig, title="🎯 P/L by Market Type", height=max(320, len(grp)*34), showlegend=False)


# 6 ── CALIBRATION / RELIABILITY (implied vs observed, per operator) ────────────
def _wilson(k, n, z=1.96):
    if n == 0: return (0, 0, 0)
    p = k/n; denom = 1 + z*z/n
    centre = (p + z*z/(2*n))/denom
    half = z*np.sqrt(p*(1-p)/n + z*z/(4*n*n))/denom
    return (centre, max(0, centre-half), min(1, centre+half))

def chart_wc_calibration(w: pd.DataFrame) -> go.Figure:
    s = w[w["status"].isin(["Win","Loss"])].copy()  # decisive only
    if s.empty: return apply_layout(go.Figure(), title="No decisive bets", height=420, showlegend=False)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=[0,100], y=[0,100], mode="lines",
                             line=dict(color=GRID_CLR, dash="dash", width=1),
                             name="fair (implied = observed)", hoverinfo="skip"))
    for user in WC_ORDER:
        u = s[s["user"] == user]
        if u.empty: continue
        n = len(u); k = (u["status"]=="Win").sum()
        implied = u["implied"].mean()*100
        centre, lo, hi = _wilson(k, n)
        color = MEMBER_COLORS.get(user, ACCENT)
        fig.add_trace(go.Scatter(
            x=[implied], y=[centre*100], mode="markers+text",
            error_y=dict(type="data", symmetric=False,
                         array=[(hi-centre)*100], arrayminus=[(centre-lo)*100],
                         color=color, thickness=1.4, width=6),
            marker=dict(color=color, size=8+min(22, n)),
            name=WC_LABEL.get(user, user),
            text=[f" {WC_LABEL.get(user,user)}"], textposition="middle right",
            textfont=dict(color=color, size=11, family="DM Mono"), cliponaxis=False,
            hovertemplate=(f"{WC_LABEL.get(user,user)}<br>implied %{{x:.1f}}%<br>"
                           f"observed %{{y:.1f}}%<br>n={n}, wins={k}<extra></extra>")))
    fig.update_xaxes(title="implied win % (1 / odds)", range=[20, 85])
    fig.update_yaxes(title="observed win % (Wilson 95%)", range=[20, 85])
    return apply_layout(fig, title="🎚️ Calibration — priced fairly? (marker size = n)", height=440)


# 7 ── PER-BET RETURN DISTRIBUTION (violin per operator) ────────────────────────
def chart_wc_return_dist(w: pd.DataFrame) -> go.Figure:
    s = w[w["status"].isin(_SETTLED)].copy()
    if s.empty: return apply_layout(go.Figure(), title="No settled bets", height=420, showlegend=False)
    s["r"] = s["aw_num"] / s["stake"].replace(0, np.nan)
    s = s.dropna(subset=["r"])
    fig = go.Figure()
    for user in WC_ORDER:
        u = s[s["user"] == user]
        if u.empty: continue
        color = MEMBER_COLORS.get(user, ACCENT)
        fig.add_trace(go.Violin(
            y=[WC_LABEL.get(user, user)]*len(u), x=u["r"], orientation="h",
            name=WC_LABEL.get(user, user), line_color=color, fillcolor=color, opacity=0.55,
            points="all", pointpos=0, jitter=0.4, meanline_visible=True, spanmode="soft",
            marker=dict(size=5, color=color, opacity=0.8, line=dict(width=0)),
            hovertemplate=f"{WC_LABEL.get(user,user)}<br>return on stake %{{x:+.2f}}<extra></extra>"))
    fig.add_vline(x=0, line_color=GRID_CLR)
    fig.update_xaxes(title="per-bet return on stake  (r = profit ÷ stake)")
    fig.update_traces(width=0.85)
    return apply_layout(fig, title="🎻 Return Distribution — who swings widest", height=440, showlegend=False)


# 8 ── ODDS STRIP / BEESWARM (dot per bet, hollow = loss) ───────────────────────
def chart_wc_odds_strip(w: pd.DataFrame) -> go.Figure:
    """Bubble chart: x = odds (log), y = operator row, bubble radius ∝ stake,
    filled = won / hollow = lost, vertical tick = member median odds."""
    s = w[w["status"].isin(["Win","Loss"])].copy()
    if s.empty: return apply_layout(go.Figure(), title="No decisive bets", height=460, showlegend=False)
    s = s.dropna(subset=["odds"])
    s["logodds"] = np.log10(s["odds"].clip(1.0))
    yorder = [WC_LABEL.get(u, u) for u in WC_ORDER if not s[s["user"]==u].empty]
    ymap = {lab:i for i, lab in enumerate(yorder)}

    def _rgba(hexc, a):
        h = hexc.lstrip("#"); return f"rgba({int(h[0:2],16)},{int(h[2:4],16)},{int(h[4:6],16)},{a})"

    # area ∝ stake → sizemode="area" with a shared sizeref so bubbles are comparable.
    # sizeref = 2 * max(value) / (desired_max_diameter ** 2)  [plotly convention]
    max_stake = max(float(s["stake"].max()), 1.0)
    MAX_DIA = 44.0
    sizeref = 2.0 * max_stake / (MAX_DIA ** 2)

    fig = go.Figure()
    seen_w = seen_l = False
    rng = np.random.default_rng(7)
    for user in WC_ORDER:
        u = s[s["user"] == user]
        if u.empty: continue
        color = MEMBER_COLORS.get(user, ACCENT); lab = WC_LABEL.get(user, user)
        base = ymap[lab]
        jit = (rng.random(len(u)) - 0.5) * 0.5
        for status, filled in [("Win", True), ("Loss", False)]:
            mask = (u["status"] == status).values
            g = u[mask]
            if g.empty: continue
            gj = jit[mask]
            marker = (dict(color=_rgba(color, 0.50), size=g["stake"].astype(float),
                           sizemode="area", sizeref=sizeref, sizemin=5,
                           line=dict(color=color, width=1.2)) if filled
                      else dict(color="rgba(0,0,0,0)", size=g["stake"].astype(float),
                                sizemode="area", sizeref=sizeref, sizemin=5,
                                line=dict(color=color, width=1.6)))
            showleg = (filled and not seen_w) or ((not filled) and not seen_l)
            if filled: seen_w = seen_w or showleg
            else: seen_l = seen_l or showleg
            fig.add_trace(go.Scatter(
                x=np.log10(g["odds"].clip(1.0)), y=base + gj, mode="markers",
                name=("won" if filled else "lost"), legendgroup=("won" if filled else "lost"),
                showlegend=showleg, marker=marker,
                customdata=np.column_stack([g["home_team"].astype(str), g["away_team"].astype(str),
                                            g["selection"].astype(str), g["odds"], g["stake"], g["aw_num"]]),
                hovertemplate=("%{customdata[0]} v %{customdata[1]}<br>%{customdata[2]}<br>"
                               "odds %{customdata[3]:.2f} · stake $%{customdata[4]:.0f} · "
                               "P/L $%{customdata[5]:+.2f}<extra></extra>")))
        # median tick
        med = u["logodds"].median()
        fig.add_shape(type="line", x0=med, x1=med, y0=base-0.36, y1=base+0.36,
                      line=dict(color=color, width=2))
    ticks = [1.2, 1.5, 2, 2.5, 3, 4, 5, 7, 10]
    fig.update_xaxes(title="odds taken (log scale) · vertical bar = member median",
                     tickmode="array", tickvals=[np.log10(t) for t in ticks],
                     ticktext=[str(t) for t in ticks])
    fig.update_yaxes(tickmode="array", tickvals=list(ymap.values()), ticktext=list(ymap.keys()),
                     range=[-0.7, len(yorder)-0.3])
    return apply_layout(fig, title="⚪ Who Takes What Price — bubble size = stake · filled = won · hollow = lost",
                        height=460)


# 9 ── MONTE CARLO FAN (actual path vs zero-edge cone) ──────────────────────────
def chart_wc_montecarlo(w: pd.DataFrame, n_sims=8000, seed=42) -> go.Figure:
    s = w[w["status"].isin(["Win","Loss"])].sort_values("date").reset_index(drop=True).copy()
    if len(s) < 3: return apply_layout(go.Figure(), title="Not enough bets", height=420, showlegend=False)
    stake = s["stake"].to_numpy(); odds = s["odds"].to_numpy()
    p = (1.0 / odds)                       # fair implied prob
    win_profit = stake * (odds - 1.0)      # profit if win
    lose_profit = -stake                   # loss if lose
    rng = np.random.default_rng(seed)
    draws = rng.random((n_sims, len(s))) < p               # True = win
    pnl = np.where(draws, win_profit, lose_profit)
    cum = np.cumsum(pnl, axis=1)                            # (sims, bets)
    x = np.arange(1, len(s)+1)
    q = {k: np.percentile(cum, k, axis=0) for k in (10, 25, 50, 75, 90)}
    actual = s["aw_num"].cumsum().to_numpy()
    final_pctile = (cum[:, -1] < actual[-1]).mean() * 100

    def band(a, b): return f"rgba(86,180,233,{a})"
    fig = go.Figure()
    # 10–90 band
    fig.add_trace(go.Scatter(x=np.concatenate([x, x[::-1]]),
                             y=np.concatenate([q[90], q[10][::-1]]), fill="toself",
                             fillcolor="rgba(136,136,170,0.12)", line=dict(width=0),
                             name="10–90% (no edge)", hoverinfo="skip"))
    # 25–75 band
    fig.add_trace(go.Scatter(x=np.concatenate([x, x[::-1]]),
                             y=np.concatenate([q[75], q[25][::-1]]), fill="toself",
                             fillcolor="rgba(136,136,170,0.20)", line=dict(width=0),
                             name="25–75%", hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=x, y=q[50], mode="lines",
                             line=dict(color=PUSH_COLOR, dash="dash", width=1.2),
                             name="zero-edge median", hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=x, y=actual, mode="lines",
                             line=dict(color=ACCENT, width=3),
                             name=f"actual (${actual[-1]:+.2f})",
                             hovertemplate="bet %{x}<br>cum $%{y:+.2f}<extra></extra>"))
    fig.add_annotation(x=x[-1], y=actual[-1], text=f"{final_pctile:.0f}th pct",
                       showarrow=True, arrowhead=2, arrowcolor=ACCENT, ax=-30, ay=-24,
                       font=dict(color=ACCENT, size=11))
    fig.add_hline(y=0, line_color=GRID_CLR)
    fig.update_xaxes(title="bet number (in time order)")
    fig.update_yaxes(title="cumulative P/L ($)")
    return apply_layout(fig, title=f"🎲 Monte Carlo — actual vs {n_sims:,} zero-edge seasons", height=440)


def wc_standings(w: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for user in WC_ORDER + [u for u in w["user"].unique() if u not in WC_ORDER]:
        st = wc_stats(w, user)
        if st["bets"] == 0: continue
        rows.append({"Member": WC_LABEL.get(user, user),
                     "Bets": st["bets"],
                     "W–L–P": f'{st["wins"]}–{st["losses"]}–{st["pushes"]}',
                     "Hit %": f'{st["hit"]:.0f}%',
                     "Staked": f'${st["staked"]:.0f}',
                     "Net": f'${st["pl"]:+.2f}',
                     "ROI %": f'{st["roi"]:+.1f}%'})
    # syndicate total (humans + bot)
    st_all = wc_stats(w, None) if False else None
    settled = w[w["status"].isin(_SETTLED)]
    tot_stake = settled["stake"].sum(); tot_pl = settled["aw_num"].sum()
    wins=(settled["status"]=="Win").sum(); losses=(settled["status"]=="Loss").sum(); pushes=(settled["status"]=="Push").sum()
    rows.append({"Member":"SYNDICATE","Bets":len(settled),
                 "W–L–P":f"{wins}–{losses}–{pushes}",
                 "Hit %":f'{wins/(wins+losses)*100:.0f}%' if wins+losses else "—",
                 "Staked":f"${tot_stake:.0f}","Net":f"${tot_pl:+.2f}",
                 "ROI %":f"{tot_pl/tot_stake*100:+.1f}%" if tot_stake else "—"})
    return pd.DataFrame(rows)


# ── WORLD CUP TAB RENDERER ─────────────────────────────────────────────────────
def render_world_cup(df: pd.DataFrame):
    """Self-contained World Cup 2026 tab: round selector + a wall of graphs."""
    w_all = wc_prepare(df)
    if w_all.empty:
        st.info("No FIFA World Cup 2026 bets in the ledger yet.")
        return

    round_opts = ["🌍 Whole Tournament", "⚽ Group Stage (MD1–3)"] + wc_round_options(w_all)
    choice = st.radio("Round", round_opts, horizontal=True, label_visibility="collapsed")
    if choice == "🌍 Whole Tournament":
        w = w_all
    elif choice == "⚽ Group Stage (MD1–3)":
        w = w_all[w_all["round_num"].isin([1, 2, 3])]
    else:
        w = w_all[w_all["round_label"] == choice]

    settled = w[w["status"].isin(_SETTLED)]
    pending = (w["status"] == "Pending").sum()
    if settled.empty:
        st.info("No settled bets in this round yet." + (f"  ({pending} pending)" if pending else ""))
        return
    st.caption(f"{len(settled)} settled bets" + (f" · {pending} still open" if pending else "")
               + f" · staked ${settled['stake'].sum():.0f}")

    # ── KPI cards: combined first, then one per active operator ────────────────
    section("🏁 The Table")
    active = [u for u in WC_ORDER if wc_stats(w, u)["bets"] > 0]

    # combined (whole syndicate on the current round subset)
    sett = w[w["status"].isin(_SETTLED)]
    tw = int((sett["status"] == "Win").sum()); tl = int((sett["status"] == "Loss").sum())
    tp = int((sett["status"] == "Push").sum())
    t_stake = sett["stake"].sum(); t_pl = sett["aw_num"].sum()
    t_roi = t_pl / t_stake * 100 if t_stake > 0 else 0
    t_dec = tw + tl
    t_hit = tw / t_dec * 100 if t_dec > 0 else 0
    t_imp = sett[sett["status"].isin(["Win", "Loss"])]["implied"].mean() * 100 if t_dec > 0 else 0
    t_col = WIN_COLOR if t_pl >= 0 else LOSS_COLOR

    ccols = cols(len(active) + 1)
    with ccols[0]:
        stat_card("🌍 Combined", f'${t_pl:+.2f}',
                  sub=(f'{tw}–{tl}–{tp} · ROI {t_roi:+.1f}%<br>'
                       f'hit {t_hit:.0f} / imp {t_imp:.0f} · {len(sett)} bets'),
                  color=t_col, border_color=ACCENT + "88")
    for col, user in zip(ccols[1:], active):
        s = wc_stats(w, user); c = MEMBER_COLORS.get(user, ACCENT)
        pl_col = WIN_COLOR if s["pl"] >= 0 else LOSS_COLOR
        with col:
            stat_card(WC_LABEL.get(user, user), f'${s["pl"]:+.2f}',
                      sub=(f'{s["wins"]}–{s["losses"]}–{s["pushes"]} · ROI {s["roi"]:+.1f}%<br>'
                           f'hit {s["hit"]:.0f} / imp {s["implied"]:.0f} · odds {s["avg_odds"]:.2f}'),
                      color=pl_col, border_color=c + "88")

    # ── centrepiece + standings ───────────────────────────────────────────────
    pc(chart_wc_worm(w))
    section("📋 Standings")
    st.dataframe(wc_standings(w), hide_index=True, use_container_width=True)

    # ── the money trail ───────────────────────────────────────────────────────
    st.divider(); section("🌐 The Money Trail")
    pc(chart_wc_sankey(w))
    pc(chart_wc_tape(w))
    pc(chart_wc_drawdown(w))
    pc(chart_wc_market_pl(w))

    # ── the quant centrefold ──────────────────────────────────────────────────
    st.divider(); section("🎲 The Quant Centrefold")
    pc(chart_wc_montecarlo(w))
    q1, q2 = cols(2)
    with q1: pc(chart_wc_calibration(w))
    with q2: pc(chart_wc_return_dist(w))
    pc(chart_wc_odds_strip(w))


def main():
    with st.spinner("Loading ledger…"):
        df_raw, df_roi, df_free, df_pending, kpis = load_data()

    df, bankroll_df = get_enriched(df_raw)

    # --- THE PRESENTATION MODE INTERCEPT ---
    # If the URL contains ?view=sankey, ONLY draw the Sankey chart and stop.
    if st.query_params.get("view") == "sankey":
        st.markdown("<h2 style='text-align: center; color: #56B4E9;'>Syndicate Stake Flow</h2>", unsafe_allow_html=True)
        # Increase the height so it looks epic on full screen
        fig = chart_flow_of_money_sankey(df)
        fig.update_layout(height=800) 
        pc(fig)
        return  # Stop executing the rest of the app
    # ---------------------------------------
    
    opening = float(core.OPENING_BANK)
    
    banking_mask = df_raw["status"].isin(["Reconciliation", "Deposit", "Withdrawal"]) | (df_raw["user"].astype(str).str.lower() == "syndicate")
    df_banking = df_raw[banking_mask]
    df_bets = df_raw[~banking_mask]

    net_deposits = pd.to_numeric(df_banking["actual_winnings"], errors="coerce").fillna(0).sum()
    total_invested = opening + net_deposits

    cur_pl = pd.to_numeric(df_bets["actual_winnings"], errors="coerce").fillna(0).sum()
    total_staked = pd.to_numeric(df_bets["stake"], errors="coerce").fillna(0).sum()
    roi = (cur_pl / total_staked * 100) if total_staked > 0 else 0
    
    current_balance = total_invested + cur_pl

    _bal_col = WIN_COLOR if current_balance >= total_invested else LOSS_COLOR
    _pl_col  = WIN_COLOR if cur_pl >= 0 else LOSS_COLOR
    _roi_col = WIN_COLOR if roi >= 0 else LOSS_COLOR

    st.markdown(f'''<div style="display:flex; justify-content:space-between; align-items:baseline; margin-bottom:4px;">
          <div style="font-size:1.9rem;font-weight:700;">Xanderdu 🏆</div>
          <div style="font-size:1.05rem;">
            <span style="color:#8888aa">Invested</span> <span style="color:#e0e0f0;">${total_invested:.2f}</span>
          </div>
        </div>''', unsafe_allow_html=True)
    st.divider()

    t_home, t_worldcup, t_people, t_markets, t_timeline, t_analytics, t_extremes, t_anim, t_inbox, t_ledger = st.tabs([
        "🏠 Home", "🏆 World Cup", "👤 People", "📈 Markets", "📆 Timeline", "📐 Analytics", "🎯 Extremes", "🎬 Anim", "📥 Inbox", "📒 Ledger"
    ])

    # 1. HOME
    with t_home:
        c1, c2, c3 = cols(3)
        with c1: stat_card("💰 Bankroll", f"${current_balance:.2f}", sub=f"invested ${total_invested:.0f}", color=_bal_col)
        with c2: stat_card("📈 Betting P/L", f"${cur_pl:+.2f}", color=_pl_col)
        with c3: stat_card("📊 Overall ROI", f"{roi:+.1f}%", color=_roi_col)
        worst = worst_bet(df)
        roast(f'Worst bet: {event_label(worst)} @ {worst["odds"]:.2f} — ${worst["actual_winnings"]:.2f}')
        st.divider()
        ca, cb = cols(2)
        with ca: 
            pc(chart_cumulative_bankroll(df, opening, bankroll_df))
        with cb: 
            pc(chart_cumulative_roi(df)) 
            with st.expander("📐 Show Logic: Cumulative ROI"):
                st.latex(r"ROI_t = \left( \frac{\sum_{i=1}^{t} Profit_i}{\sum_{i=1}^{t} Stake_i} \right) \times 100")
        
        c3, c4 = cols(2)
        with c3: pc(chart_win_loss_donut(df))
        with c4: pc(chart_waterfall(df))

    # 1b. WORLD CUP 2026
    with t_worldcup:
        render_world_cup(df_raw)

    # 2. PEOPLE
    with t_people:
        view = st.radio("Select View", ["🏆 Leaderboard"] + [f"👤 {m}" for m in MEMBERS], horizontal=True, label_visibility="collapsed")
        st.divider()

        if view == "🏆 Leaderboard":
            # --- THE NEW SHOWSTOPPER CENTERPIECE ---
            section("🌊 Individual Stake Flow")
            pc(chart_flow_of_money_sankey(df))
            st.divider()
            # ---------------------------------------

            c1, c2 = cols(2)
            with c1: pc(chart_member_pl_bars(df))
            with c2: pc(chart_member_roi_bars(df))
            c3, c4 = cols(2)
            with c3: pc(chart_member_win_rate(df))
            with c4: 
                pc(chart_member_radar(df))
                with st.expander("📐 Show Logic: Radar Normalization"):
                    st.markdown("Metrics are normalized so the lowest value is mapped to 20 and the highest to 100 to fit the radar scale.")
                    st.latex(r"Norm(x) = 20 + 80 \times \left( \frac{x - \min}{\max - \min} \right)")
            
            pc(chart_longest_streaks(df))
            pc(chart_team_vs_individual(df))

        else:
            # Individual member pages
            member = view.replace("👤 ", "")
            member_df = df[df["user"] == member].copy()
            stats = member_stats(member_df, member)
            streak_count, streak_type = compute_streak(member_df)

            color = MEMBER_COLORS.get(member, ACCENT)
            _m_pl_col  = WIN_COLOR if stats["pl"] >= 0 else LOSS_COLOR
            _m_roi_col = WIN_COLOR if stats["roi"] >= 0 else LOSS_COLOR

            c1, c2, c3, c4 = cols(4)
            with c1: stat_card("💰 P/L", f"${stats['pl']:+.2f}", color=_m_pl_col)
            with c2: stat_card("📊 ROI", f"{stats['roi']:+.1f}%", color=_m_roi_col)
            with c3: stat_card("🎯 Win Rate", f"{stats['win_rate']:.1f}%", color=color)
            with c4:
                streak_col = WIN_COLOR if streak_type == "Win" else (LOSS_COLOR if streak_type == "Loss" else PUSH_COLOR)
                stat_card("🔥 Streak", f"{streak_count} {streak_type}", color=streak_col)

            st.divider()

            section(f"🌊 {member}'s Stake Flow")
            pc(chart_flow_of_money_sankey(member_df))

            st.divider()

            ca, cb = cols(2)
            with ca: pc(chart_member_monthly_pl(df, member))
            with cb: pc(chart_member_market_breakdown(df, member))

            pc(chart_member_odds_violin(df, member))
            pc(chart_ev_proxy(member_df, title=f"📐 {member} — Edge Proxy (Actual vs Implied)"))

    # 3. MARKETS
    with t_markets:
        c1, c2 = cols(2)
        with c1: pc(chart_pl_by_sport(df))
        with c2: pc(chart_competition_roi(df))
        c3, c4 = cols(2)
        with c3: pc(chart_bet_type_roi_bars(df))
        with c4: pc(chart_pl_by_selection(df))
        
        pc(chart_top_teams(df))

    # 4. TIMELINE
    with t_timeline:
        pc(chart_pl_by_matchday(df))
        c1, c2 = cols(2)
        with c1: pc(chart_monthly_pl(df))
        with c2: pc(chart_monthly_volatility(df))
        pc(chart_weekday_bubble(df))
        pc(chart_year_on_year(df))

    # 5. ANALYTICS
    with t_analytics:
        pc(chart_global_odds_beeswarm(df))
        
        pc(chart_cumulative_win_rate(df))
        with st.expander("📐 Show Logic: Cumulative Win %"):
            st.latex(r"\text{Win \%} = \left( \frac{\text{Cumulative Wins}}{\text{Resolved Bets}} \right) \times 100")
            st.caption("Resolved Bets = Wins + Losses (Pushes and Voids are excluded).")
            
        pc(chart_odds_correlations(df))
        
        pc(chart_ev_proxy(df, title="📐 Global Edge Proxy — Actual vs Implied"))
        with st.expander("📐 Show Logic: Edge & Implied Probability"):
            st.latex(r"\text{Implied Win \%} = \left( \frac{1}{\text{Avg Odds}} \right) \times 100")
            st.caption("A positive gap between Actual and Implied Win % suggests a profitable edge over the bookmaker's margin.")

        c1, c2 = cols(2)
        with c1: 
            pc(chart_odds_bucket_roi(df))
            with st.expander("📐 Show Logic: ROI & Win Rate"):
                st.latex(r"ROI = \left( \frac{\sum \text{Profit}}{\sum \text{Stake}} \right) \times 100")
                st.caption("Pushes are excluded from Win Rate calculations, but included in ROI stakes.")
        with c2: 
            pc(chart_longshot_vs_fav(df))
            
        pc(chart_roi_rollercoaster(df))
        with st.expander("📐 Show Logic: 20-Bet Rolling ROI"):
            st.latex(r"Rolling\ ROI_n = \left( \frac{\sum_{i=n-19}^{n} Profit_i}{\sum_{i=n-19}^{n} Stake_i} \right) \times 100")
            
        pc(chart_voting_success(df))

    # 6. EXTREMES
    with t_extremes:
        best = best_bet(df)
        worst = worst_bet(df)
        bc, wc = cols(2)
        with bc:
            _b_sel = str(best.get("selection", "")).strip()
            _b_date = str(best.get("date", ""))[:10]
            stat_card("🏆 Best Bet Ever", f'${best.get("aw_num", 0):+.2f}', sub=f'{event_label(best)}<br>📌 {_b_sel} · {best.get("odds", 0):.2f}x<br>{best.get("user", "?")} · {_b_date}', color=WIN_COLOR)
        with wc:
            _w_sel = str(worst.get("selection", "")).strip()
            _w_date = str(worst.get("date", ""))[:10]
            stat_card("💀 Worst Bet Ever", f'${worst.get("aw_num", 0):+.2f}', sub=f'{event_label(worst)}<br>📌 {_w_sel} · {worst.get("odds", 0):.2f}x<br>{worst.get("user", "?")} · {_w_date}', color=LOSS_COLOR)
        
        st.write("")
        section("Top 10 Wins")
        _show_cols = [c for c in["date", "user", "home_team", "away_team", "competition", "bet_type", "selection", "odds", "stake", "actual_winnings"] if c in df.columns]
        df["aw_num"] = pd.to_numeric(df["actual_winnings"], errors="coerce").fillna(0)
        st.dataframe(df[df["status"] == "Win"].nlargest(10, "aw_num")[_show_cols], hide_index=True)
        
        section("Top 10 Losses")
        st.dataframe(df[df["status"] == "Loss"].nsmallest(10, "aw_num")[_show_cols], hide_index=True)
        
        pc(chart_accumulator_curse(df))

    # 7. ANIMATED
    with t_anim:
        st.caption("Press ▶ Play or drag the slider.")
        pc(chart_anim_bankroll_worm(df, opening, bankroll_df))
        pc(chart_anim_member_worm(df))
        pc(chart_anim_win_rate_evolution(df))

    # 8. INBOX (Data Sync & Grading)
    with t_inbox:
        st.subheader("Data Management")
        if st.button("🔄 Pull Latest from Google Sheets", use_container_width=True):
            with st.spinner("Downloading ledger from Google Sheets..."):
                if core.sync_local_csv():
                    st.cache_data.clear()
                    st.success("Ledger synced successfully!")
                    st.rerun()
                else: st.error("Sync failed.")
                    
        st.divider()
        st.subheader("Pending Bets")
        if len(df_pending) == 0: st.success("No pending bets — all caught up.")
        else:
            st.info(f"{len(df_pending)} bet(s) awaiting grading.")
            for _, row in df_pending.iterrows():
                with st.expander(f"**{row['event']}** | {row['competition']} | {row['selection']} @ {row['odds']:.2f}"):
                    col1, col2, col3 = cols(3)
                    with col1: new_status = st.selectbox("Result", ["Pending", "Win", "Loss", "Push", "Void"], key=f"status_{row['uuid']}")
                    with col2: actual_winnings = st.number_input("Winnings ($)", value=0.0, format="%.2f", key=f"winnings_{row['uuid']}")
                    with col3:
                        st.write(""); st.write("")
                        if st.button("Commit", key=f"commit_{row['uuid']}", type="primary", use_container_width=True):
                            if new_status != "Pending":
                                if core.update_grade(row["uuid"], new_status, actual_winnings):
                                    st.success(f"✅ {row['uuid']} → {new_status}"); st.cache_data.clear(); st.rerun()

        st.divider()
        st.subheader("Add a Bet Manually")
        with st.form("add_bet_form", clear_on_submit=True):
            col1, col2 = cols(2)
            with col1:
                user = st.selectbox("Member", core.SYNDICATE_MEMBERS + ["Syndicate"])
                home_team = st.text_input("Home Team (e.g. Arsenal)")
                away_team = st.text_input("Away Team")
                comp_options = sorted(set(COMPETITIONS) | set(df_raw["competition"].dropna().astype(str).str.strip()) - {""})
                competition = st.selectbox("Competition", comp_options)
                bet_type_options = sorted((set(BET_TYPES) | (set(df_raw["bet_type"].dropna().astype(str).str.strip()) - {""})) - {"Deposit", "Withdrawal", "Reconciliation"})
                bet_type = st.selectbox("Bet Type", bet_type_options)
                selection = st.text_input("Selection")
            with col2:
                odds = st.number_input("Odds", min_value=1.01, value=1.80, step=0.01)
                stake = st.number_input("Stake ($)", value=5.0)
                bet_date = st.date_input("Date")
                status = st.selectbox("Status",["Pending", "Win", "Loss", "Push", "Deposit", "Withdrawal", "Reconciliation"])
                aw = st.number_input("Actual Winnings", value=0.0)

            if st.form_submit_button("Add Bet", type="primary"):
                if home_team and selection:
                    core.append_bet(user, home_team, away_team, competition, bet_type, selection, odds, stake, bet_date, status, aw)
                    st.success("Added!"); st.cache_data.clear(); st.rerun()

    # 9. LEDGER & BETBOT
    with t_ledger:
        section("🤖 Betbot — Ask the Ledger")
        asker = st.selectbox("Who's asking?", core.SYNDICATE_MEMBERS, key="betbot_asker")
        question = st.text_input("Question", placeholder="What's our ROI on BTTS bets?", key="betbot_q")
        if st.button("Ask", type="primary") and question:
            with st.spinner("Consulting the LangChain oracle…"):
                try:
                    if "agent" not in st.session_state: st.session_state.agent = build_agent()
                    reply = core.apply_persona(agent_query(st.session_state.agent, question), asker_name=asker)
                    st.info(reply)
                except Exception as e: st.error(f"Betbot error: {e}")

        st.divider()
        st.subheader("Full Ledger")
        with st.expander("Filters", expanded=False):
            fc = cols(4)
            with fc[0]: f_user = st.multiselect("Member", options=sorted(df_raw["user"].dropna().unique()), default=sorted(df_raw["user"].dropna().unique()))
            with fc[1]: f_bet_type = st.multiselect("Bet Type", options=sorted(df_raw["bet_type"].dropna().unique()), default=sorted(df_raw["bet_type"].dropna().unique()))
            with fc[2]: f_status = st.multiselect("Status", options=["Win", "Loss", "Push", "Void", "Pending", "Deposit", "Reconciliation"], default=["Win", "Loss", "Push"])
            with fc[3]:
                years = sorted(int(y) for y in df_raw["date"].dt.year.dropna().unique())
                f_year = st.multiselect("Year", options=years, default=years)

        mask = (df_raw["user"].isin(f_user) & df_raw["bet_type"].isin(f_bet_type) & df_raw["status"].isin(f_status) & df_raw["date"].dt.year.isin(f_year))
        df_filtered = df_raw[mask].copy()
        display_cols = [c for c in["uuid", "date", "user", "home_team", "away_team", "competition", "bet_type", "selection", "odds", "stake", "status", "actual_winnings"] if c in df_filtered.columns]
        
        ledger_display = df_filtered[display_cols].sort_values("date", ascending=False).copy()
        ledger_display["actual_winnings"] = pd.to_numeric(ledger_display["actual_winnings"], errors="coerce").fillna(0).map("${:+.2f}".format)
        ledger_display["stake"]           = ledger_display["stake"].map("${:.2f}".format)
        ledger_display["date"]            = ledger_display["date"].dt.date
        ledger_display.columns =[c.replace("_", " ").title() for c in ledger_display.columns]
        
        st.dataframe(ledger_display, use_container_width=True, hide_index=True)

if __name__ == "__main__":
    main()