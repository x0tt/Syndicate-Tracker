#!/usr/bin/env python3
# coding: utf-8
"""
app.py — Syndicate Tracker v6.2
================================
Streamlit UI. Mobile-optimised, tab-based, Plotly-powered.
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

def _base_layout(**overrides):
    base = {k: v for k, v in PLOTLY_LAYOUT.items() if k not in overrides}
    return {**base, **overrides}

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
    
    # Merge kwargs into base so we don't pass duplicate keyword arguments
    base.update(kwargs)
    
    fig.update_layout(
        title=dict(text=title, font=dict(size=14, color=TEXT_CLR), x=0.01), 
        height=height, 
        showlegend=showlegend, 
        **base
    )
    return fig

def status_color(s: str) -> str: return WIN_COLOR if s == "Win" else LOSS_COLOR if s == "Loss" else PUSH_COLOR
def cols(n, gap="small"): return st.columns(n, gap=gap)

_chart_counter = [0]
_PLOTLY_CONFIG = { "displaylogo": False, "scrollZoom": False, "modeBarButtons": [["toImage", "resetScale2d"]], "toImageButtonOptions": { "format": "png", "width": 1200, "height": 600, "scale": 2, "filename": "syndicate_chart" } }

def pc(fig):
    _chart_counter[0] += 1
    st.plotly_chart(fig, use_container_width=True, key=f"pc_{_chart_counter[0]}", config=_PLOTLY_CONFIG)

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

    # Bankroll tracks absolutely everything: deposits, reconciliations, bets
    bankroll_df = df.copy()
    bankroll_df["date"]     = pd.to_datetime(bankroll_df["date"])
    bankroll_df["date_str"] = bankroll_df["date"].dt.strftime("%Y-%m-%d")
    bankroll_df = bankroll_df.sort_values("date").reset_index(drop=True)
    bankroll_df["actual_winnings_num"] = pd.to_numeric(bankroll_df["actual_winnings"], errors="coerce").fillna(0)
    bankroll_df["cum_pl"]   = bankroll_df["actual_winnings_num"].cumsum()

    # Working DF focuses exclusively on betting performance
    # Exclude both specific statuses AND any user marked as 'syndicate'
    banking_mask = df["status"].isin(["Reconciliation", "Deposit", "Withdrawal"]) | (df["user"].astype(str).str.lower() == "syndicate")
    working = df[~banking_mask].copy()
    working["date"]     = pd.to_datetime(working["date"])
    working["date_str"] = working["date"].dt.strftime("%Y-%m-%d")
    working["month"]    = working["date"].dt.to_period("M").astype(str)
    working["weekday"]  = working["date"].dt.day_name()
    working["year"]     = working["date"].dt.year
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
    df2["peak"]     = df2["bankroll"].cummax()

    # Calculate total invested (opening + deposits) to plot a more useful baseline
    deposits = pd.to_numeric(src_df[src_df["status"].isin(["Deposit", "Withdrawal"])]["actual_winnings"], errors="coerce").fillna(0).sum()
    total_invested = opening + deposits

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df2["date_str"], y=df2["peak"], line=dict(color="rgba(0,0,0,0)"), showlegend=False))
    fig.add_trace(go.Scatter(x=df2["date_str"], y=df2["bankroll"], fill="tonexty", fillcolor="rgba(230,159,0,0.15)", line=dict(color=LOSS_COLOR, width=0.5, dash="dot"), name="Drawdown"))
    fig.add_trace(go.Scatter(x=df2["date_str"], y=df2["bankroll"], mode="lines+markers", line=dict(color=ACCENT, width=3), marker=dict(size=4, color=ACCENT), name="Bankroll"))
    fig.add_hline(y=total_invested, line_dash="dash", line_color=GRID_CLR, annotation_text=f"Total Invested ${total_invested:.0f}", annotation_font_color=GRID_CLR, annotation_position="bottom right")
    return apply_layout(fig, title=f"📈 Bankroll  ${df2['bankroll'].iloc[-1]:.2f}", height=420, showlegend=False)

def chart_monthly_pl(df: pd.DataFrame) -> go.Figure:
    df["aw_num"] = pd.to_numeric(df["actual_winnings"], errors="coerce").fillna(0)
    monthly = df.groupby("month")["aw_num"].sum().reset_index()
    fig = go.Figure(go.Bar(x=monthly["month"], y=monthly["aw_num"], marker_color=[WIN_COLOR if v >= 0 else LOSS_COLOR for v in monthly["aw_num"]], text=[f"${v:+.2f}" for v in monthly["aw_num"]], textposition="auto", textfont=dict(size=10, family="DM Mono")))
    fig.add_hline(y=0, line_color=GRID_CLR)
    return apply_layout(fig, title="📅 Monthly Betting P/L", height=400, showlegend=False)

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

def chart_member_cumulative(df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    for m in MEMBERS:
        sub = df[df["user"] == m].sort_values("date").copy()
        aw_num = pd.to_numeric(sub["actual_winnings"], errors="coerce").fillna(0)
        sub["cum"] = aw_num.cumsum()
        fig.add_trace(go.Scatter(x=sub["date_str"], y=sub["cum"], mode="lines+markers", name=m, line=dict(color=MEMBER_COLORS[m], width=3)))
    fig.add_hline(y=0, line_dash="dash", line_color=GRID_CLR)
    return apply_layout(fig, title="📈 Member Cumulative P/L", height=440)

def chart_member_win_rate(df: pd.DataFrame) -> go.Figure:
    wrs =[member_stats(df[df["user"] == m], m)["win_rate"] for m in MEMBERS]
    fig = go.Figure(go.Bar(y=MEMBERS, x=wrs, orientation="h", marker_color=[MEMBER_COLORS[m] for m in MEMBERS], text=[f"{w:.1f}%" for w in wrs], textposition="inside"))
    return apply_layout(fig, title="🎯 Win Rate by Member", height=260, showlegend=False)

def chart_member_odds_dist(df: pd.DataFrame, member: str) -> go.Figure:
    sub = df[df["user"] == member]
    wins = sub[sub["status"] == "Win"]["odds"]; losses = sub[sub["status"] == "Loss"]["odds"]
    fig = go.Figure()
    fig.add_trace(go.Violin(y=wins, name="Win", fillcolor=WIN_COLOR, opacity=0.7, line_color=WIN_COLOR))
    fig.add_trace(go.Violin(y=losses, name="Loss", fillcolor=LOSS_COLOR, opacity=0.7, line_color=LOSS_COLOR))
    return apply_layout(fig, title=f"🎲 {member} — Odds Distribution", height=320)

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

def chart_bet_type_sunburst(df: pd.DataFrame) -> go.Figure:
    grp = df.groupby(["bet_type", "status"]).size().reset_index(name="count")
    grp = grp[grp["status"].isin(["Win", "Loss", "Push"])]
    fig = px.sunburst(grp, path=["bet_type", "status"], values="count", color="status", color_discrete_map={"Win": WIN_COLOR, "Loss": LOSS_COLOR, "Push": PUSH_COLOR})
    return apply_layout(fig, title="🌐 Bet Type → Outcome Sunburst", height=480, showlegend=False)

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

def chart_weekday_heatmap(df: pd.DataFrame) -> go.Figure:
    df2 = df.copy()
    df2["aw_num"] = pd.to_numeric(df2["actual_winnings"], errors="coerce").fillna(0)
    df2["weekday"] = pd.Categorical(df2["weekday"], categories=["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"], ordered=True)
    pivot = df2.pivot_table(index="weekday", columns="month", values="aw_num", aggfunc="sum", fill_value=0)
    fig = go.Figure(go.Heatmap(z=pivot.values, x=pivot.columns.tolist(), y=[d[:3] for d in pivot.index.tolist()], colorscale=[[0, LOSS_COLOR],[0.5, "#1a1a2e"], [1, WIN_COLOR]], zmid=0))
    return apply_layout(fig, title="📅 P/L Heatmap — Day × Month", height=300, showlegend=False)

def chart_stake_vs_outcome(df: pd.DataFrame) -> go.Figure:
    d = df[df["status"].isin(["Win", "Loss"])].copy()
    d["aw_num"] = pd.to_numeric(d["actual_winnings"], errors="coerce").fillna(0)
    fig = go.Figure()
    for s, c, sym in[("Win", WIN_COLOR, "circle"), ("Loss", LOSS_COLOR, "triangle-up")]:
        sub = d[d["status"] == s]
        fig.add_trace(go.Scatter(x=sub["stake"], y=sub["aw_num"], mode="markers", name=s, marker=dict(color=c, size=9, symbol=sym), text=sub.apply(lambda r: f"{r['event']}<br>{r['odds']:.2f}", axis=1), hovertemplate="<b>%{text}</b><br>P/L: $%{y:.2f}<extra></extra>"))
    fig.add_hline(y=0, line_color=GRID_CLR)
    return apply_layout(fig, title="💰 Stake vs P/L", height=360)

def chart_odds_histogram(df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Histogram(x=df[df["status"] == "Win"]["odds"], name="Win", marker_color=WIN_COLOR, opacity=0.7))
    fig.add_trace(go.Histogram(x=df[df["status"] == "Loss"]["odds"], name="Loss", marker_color=LOSS_COLOR, opacity=0.7))
    fig.update_layout(barmode="overlay")
    return apply_layout(fig, title="🎲 Odds Distribution — Win vs Loss", height=320)

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
    
    def norm(val, vmin, vmax):
        if vmax == vmin: return 50
        # Map to [20, 100] so negatives/minimums don't completely vanish at the center
        return 20 + 80 * (val - vmin) / (vmax - vmin)
    
    for m in MEMBERS:
        s = stats[m]
        eff = (s["pl"] / s["staked"] * 100) if s["staked"] > 0 else 0
        
        r_vals = [
            norm(s["win_rate"], min_wr, max_wr),
            norm(s["roi"], min_roi, max_roi),
            norm(s["avg_odds"], min_odds, max_odds),
            norm(s["bets"], min_bets, max_bets),
            norm(eff, min_eff, max_eff)
        ]
        r_vals.append(r_vals[0]) # Close the loop
        
        fig.add_trace(go.Scatterpolar(
            r=r_vals, 
            theta=["Win Rate", "ROI", "Avg Odds", "Bets", "Efficiency", "Win Rate"], 
            fill="toself", name=m, 
            line=dict(color=MEMBER_COLORS[m]), 
            fillcolor=_hex_to_rgba(MEMBER_COLORS[m])
        ))
        
    fig.update_layout(polar=dict(radialaxis=dict(visible=False, range=[0, 100]), bgcolor="rgba(0,0,0,0)"))
    return apply_layout(fig, title="🕸️ Member Radar", height=400)

def chart_waterfall(df: pd.DataFrame) -> go.Figure:
    df2 = df.sort_values("date").tail(15).copy()
    df2["aw_num"] = pd.to_numeric(df2["actual_winnings"], errors="coerce").fillna(0)
    fig = go.Figure(go.Waterfall(x=df2["event"].str[:14] + "…", y=df2["aw_num"], measure=["relative"] * len(df2), text=[f"${v:+.2f}" for v in df2["aw_num"]], textposition="outside", decreasing=dict(marker=dict(color=LOSS_COLOR)), increasing=dict(marker=dict(color=WIN_COLOR))))
    return apply_layout(fig, title="🌊 Last 15 Bets — P/L Waterfall", height=420, showlegend=False)

def chart_team_vs_individual(df: pd.DataFrame) -> go.Figure:
    groups = MEMBERS + ["Team"]
    rois =[team_summary(df[df["user"] == g])["roi"] if g == "Team" else member_stats(df[df["user"] == g], g)["roi"] for g in groups]
    pls = [team_summary(df[df["user"] == g])["pl"] if g == "Team" else member_stats(df[df["user"] == g], g)["pl"] for g in groups]
    fig = make_subplots(rows=1, cols=2, subplot_titles=("ROI %", "P/L ($)"))
    fig.add_trace(go.Bar(x=groups, y=rois, marker_color=[MEMBER_COLORS.get(g, ACCENT) for g in groups], text=[f"{r:+.1f}%" for r in rois]), row=1, col=1)
    fig.add_trace(go.Bar(x=groups, y=pls, marker_color=[MEMBER_COLORS.get(g, ACCENT) for g in groups], text=[f"${p:+.2f}" for p in pls]), row=1, col=2)
    return apply_layout(fig, title="👥 Team Pool vs Individuals", height=340, showlegend=False)

def chart_stake_distribution(df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    for m in MEMBERS + ["Team"]: fig.add_trace(go.Box(y=df[df["user"] == m]["stake"], name=m, marker_color=MEMBER_COLORS.get(m, ACCENT)))
    return apply_layout(fig, title="💵 Stake Distribution", height=340, showlegend=False)

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
    return apply_layout(fig, title="🔥 Win & Loss Streaks", height=320)

def chart_ev_proxy(df: pd.DataFrame) -> go.Figure:
    grp = df[df["status"].isin(["Win", "Loss"])].groupby("odds_bucket").agg(wins=("status", lambda x: (x == "Win").sum()), bets=("status", "count"), avg_odds=("odds", "mean"))
    grp["win_rate"] = grp["wins"] / grp["bets"] * 100; grp["implied"] = 1 / grp["avg_odds"] * 100
    grp = grp.reindex(["<1.40", "1.40\u20131.69", "1.70\u20131.99", "2.00\u20132.49", "2.50\u20133.49", "3.50+"]).dropna()
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=grp.index, y=grp["win_rate"], name="Actual Win %", line=dict(color=WIN_COLOR)))
    fig.add_trace(go.Scatter(x=grp.index, y=grp["implied"], name="Implied Win %", line=dict(color=LOSS_COLOR, dash="dash")))
    return apply_layout(fig, title="📐 Edge Proxy — Actual vs Implied", height=340)

def chart_year_on_year(df: pd.DataFrame) -> go.Figure:
    df["aw_num"] = pd.to_numeric(df["actual_winnings"], errors="coerce").fillna(0)
    grp = df.groupby("year").agg(pl=("aw_num", "sum"), bets=("odds", "count")).reset_index()
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Bar(x=grp["year"].astype(str), y=grp["pl"], marker_color=[WIN_COLOR if p >= 0 else LOSS_COLOR for p in grp["pl"]], name="P/L"), secondary_y=False)
    fig.add_trace(go.Scatter(x=grp["year"].astype(str), y=grp["bets"], name="Bets", line=dict(color=PUSH_COLOR, dash="dot")), secondary_y=True)
    return apply_layout(fig, title="📆 Year-on-Year Performance", height=320)

def chart_bankroll_by_member_contrib(df: pd.DataFrame, opening: float = 0.00, bankroll_df: pd.DataFrame = None) -> go.Figure:
    bk = (bankroll_df if bankroll_df is not None else df).sort_values("date").copy()
    bk["bankroll_change"] = pd.to_numeric(bk["actual_winnings"], errors="coerce").fillna(0)
    bk["bankroll"] = opening + bk["bankroll_change"].cumsum()
    fig = go.Figure(go.Scatter(x=bk["date_str"], y=bk["bankroll"], name="Combined", line=dict(color=ACCENT), fill="tozeroy"))
    for m in MEMBERS:
        sub = df[df["user"] == m].sort_values("date").copy()
        sub["aw_num"] = pd.to_numeric(sub["actual_winnings"], errors="coerce").fillna(0)
        fig.add_trace(go.Scatter(x=sub["date_str"], y=sub["aw_num"].cumsum(), name=m, line=dict(color=MEMBER_COLORS[m], dash="dash")))
    return apply_layout(fig, title="🏦 Combined Bankroll + Individual P/L", height=440)

def chart_bet_type_win_rate_vs_roi(df: pd.DataFrame) -> go.Figure:
    df["aw_num"] = pd.to_numeric(df["actual_winnings"], errors="coerce").fillna(0)
    grp = df.groupby("bet_type").agg(wins=("status", lambda x: (x == "Win").sum()), bets=("status", lambda x: x.isin(["Win", "Loss"]).sum()), pl=("aw_num", "sum"), staked=("stake", "sum"))
    grp = grp[grp["bets"] >= 3]
    grp["win_rate"] = grp["wins"] / grp["bets"] * 100; grp["roi"] = grp["pl"] / grp["staked"] * 100
    fig = px.scatter(grp.reset_index(), x="win_rate", y="roi", size="bets", color="bet_type", text="bet_type", size_max=40)
    fig.add_hline(y=0, line_dash="dash", line_color=GRID_CLR); fig.add_vline(x=50, line_dash="dash", line_color=GRID_CLR)
    return apply_layout(fig, title="🔍 Bet Type: Win Rate vs ROI", height=420)

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
    return apply_layout(fig, title="🏹 Favourite vs Value vs Long-shot", height=340, showlegend=False)

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
        return {
            "win_rate": round(w / (w + l) * 100, 2) if (w + l) > 0 else 0,
            "roi": round(pl / st * 100, 2) if st > 0 else 0,
            "pl": round(float(pl), 2),
            "bets": int(len(sub))
        }

    ag = s(agreed)
    mbr = {m: s(solo[solo["user"] == m]) for m in MEMBERS}

    entries = [("🤝 Agreed", ag, ACCENT)] + [(m, mbr[m], MEMBER_COLORS[m]) for m in MEMBERS]
    n_rows = len(entries)
    vertical_spacing = 0.15

    fig = make_subplots(
        rows=n_rows, cols=2,
        column_widths=[0.55, 0.45],
        vertical_spacing=vertical_spacing,
        horizontal_spacing=0.04,
        specs=[[{"type": "indicator"}, {"type": "indicator"}]] * n_rows,
    )

    def wr_color(v): return WIN_COLOR if v >= 60 else (PUSH_COLOR if v >= 45 else LOSS_COLOR)
    def roi_color(v): return WIN_COLOR if v >= 0 else LOSS_COLOR

    for row_idx, (label, st_dict, color) in enumerate(entries, start=1):
        # Col 1: Win Rate gauge (No title)
        fig.add_trace(go.Indicator(
            mode="gauge+number",
            value=st_dict["win_rate"],
            number=dict(suffix="%", font=dict(size=22, family="DM Mono", color=wr_color(st_dict["win_rate"])), valueformat=".1f"),
            gauge=dict(
                axis=dict(range=[0, 100], tickcolor=GRID_CLR, tickfont=dict(color=TEXT_CLR, size=8), nticks=5),
                bar=dict(color=color, thickness=0.4),
                bgcolor="rgba(0,0,0,0)",
                bordercolor=GRID_CLR,
                steps=[
                    dict(range=[0, 45],  color="rgba(230,159,0,0.08)"),
                    dict(range=[45, 60], color="rgba(153,153,153,0.06)"),
                    dict(range=[60, 100],color="rgba(86,180,233,0.08)"),
                ],
                threshold=dict(line=dict(color=PUSH_COLOR, width=2), value=50),
            ),
        ), row=row_idx, col=1)

        # Col 2: ROI & P/L Stats (No title)
        fig.add_trace(go.Indicator(
            mode="number",
            value=st_dict["roi"],
            number=dict(suffix="%", font=dict(size=24, family="DM Mono", color=roi_color(st_dict["roi"])), valueformat="+.1f"),
        ), row=row_idx, col=2)

        # Calculate Y bottom of the current row's domain
        i = row_idx - 1
        row_height = (1.0 - (n_rows - 1) * vertical_spacing) / n_rows
        y_bottom = 1.0 - (i * row_height) - (i * vertical_spacing) - row_height

        # Add Annotation for the Gauge (Col 1)
        fig.add_annotation(
            x=0.26,
            y=y_bottom - 0.02, # Just slightly below the domain
            text=f"<b><span style='color:{color}'>{label}</span></b><br><span style='color:{TEXT_CLR};font-size:11px'>Win Rate</span>",
            showarrow=False,
            font=dict(size=14),
            xanchor="center",
            yanchor="top",
            xref="paper",
            yref="paper"
        )

        # Add Annotation for the ROI (Col 2)
        fig.add_annotation(
            x=0.78,
            y=y_bottom - 0.02,
            text=f"<b><span style='color:{color}'>{label if label == '🤝 Agreed' else label + ' Solo'} ROI</span></b><br><span style='color:{TEXT_CLR};font-size:11px'>P/L ${st_dict['pl']:+.2f} · {st_dict['bets']} bets</span>",
            showarrow=False,
            font=dict(size=14),
            xanchor="center",
            yanchor="top",
            xref="paper",
            yref="paper"
        )

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
    
    min_y = snaps[MEMBERS].min().min()
    max_y = snaps[MEMBERS].max().max()
    pad = max(10, (max_y - min_y) * 0.1)
    
    def mkt(sub): return [go.Scatter(x=sub["date"], y=sub[m], mode="lines", name=m, line=dict(color=MEMBER_COLORS[m])) for m in MEMBERS]
    frames =[go.Frame(name=snaps["date"].iloc[i], data=mkt(snaps.iloc[:i+1])) for i in range(len(snaps))]
    fig = go.Figure(data=mkt(snaps.iloc[:1]), frames=frames)
    fig.update_layout(
        updatemenus=_anim_buttons(280, 160), 
        sliders=_anim_slider(snaps["date"], 280, 160), 
        xaxis=dict(range=[snaps["date"].iloc[0], snaps["date"].iloc[-1]]),
        yaxis=dict(range=[min_y - pad, max_y + pad])
    )
    return apply_layout(fig, title="🏎️ Member P/L Worm Race", height=520, showlegend=True)

def chart_anim_monthly_roi_build(df: pd.DataFrame) -> go.Figure:
    df["aw_num"] = pd.to_numeric(df["actual_winnings"], errors="coerce").fillna(0)
    monthly = df.groupby("month").agg(pl=("aw_num", "sum"), staked=("stake", "sum")).reset_index()
    monthly["roi"] = (monthly["pl"] / monthly["staked"] * 100).round(1)
    
    min_y = min(monthly["roi"].min(), 0)
    max_y = max(monthly["roi"].max(), 0)
    pad = max(5, (max_y - min_y) * 0.1)
    
    def mkf(i): return[go.Bar(x=monthly["month"], y=[monthly["roi"].iloc[j] if j<=i else 0 for j in range(len(monthly))])]
    frames =[go.Frame(name=monthly["month"].iloc[i], data=mkf(i)) for i in range(len(monthly))]
    fig = go.Figure(data=mkf(0), frames=frames)
    fig.update_layout(
        updatemenus=_anim_buttons(), 
        sliders=_anim_slider(monthly["month"]),
        yaxis=dict(range=[min_y - pad, max_y + pad])
    )
    return apply_layout(fig, title="📅 Monthly ROI Animation", height=500, showlegend=False)

def chart_anim_bet_type_worm(df: pd.DataFrame) -> go.Figure:
    df2 = df.copy()
    df2["aw_num"] = pd.to_numeric(df2["actual_winnings"], errors="coerce").fillna(0)
    top_mkts = df2.groupby("bet_type")["aw_num"].sum().abs().nlargest(6).index.tolist()
    df3 = df2[df2["bet_type"].isin(top_mkts)].copy()
    months = sorted(df3["month"].unique())
    run = {m: 0.0 for m in top_mkts}
    snaps = []
    for mo in months:
        mod = df3[df3["month"] == mo]
        for m in top_mkts: run[m] += mod[mod["bet_type"] == m]["aw_num"].sum()
        snaps.append({"month": mo, **run})
    sdf = pd.DataFrame(snaps)
    def mkf(i): return[go.Scatter(x=sdf["month"], y=sdf[m].apply(lambda x: x if j<=i else None), mode="lines+markers", name=m) for j, m in enumerate(top_mkts)]
    frames = [go.Frame(name=months[i], data=[go.Scatter(x=sdf["month"].iloc[:i+1], y=sdf[m].iloc[:i+1], mode="lines+markers", name=m) for m in top_mkts]) for i in range(len(months))]
    fig = go.Figure(data=[go.Scatter(x=sdf["month"].iloc[:1], y=sdf[m].iloc[:1], name=m) for m in top_mkts], frames=frames)
    fig.update_layout(updatemenus=_anim_buttons(), sliders=_anim_slider(months))
    return apply_layout(fig, title="📊 Bet Type Worm Race", height=560, showlegend=True)

def chart_anim_odds_scatter_race(df: pd.DataFrame) -> go.Figure:
    closed = df[df["status"].isin(["Win", "Loss"])].sort_values("date").copy()
    closed["aw_num"] = pd.to_numeric(closed["actual_winnings"], errors="coerce").fillna(0)
    mkts = sorted(closed["bet_type"].unique().tolist())
    def mkf(sub): return [go.Scatter(x=sub[sub["bet_type"]==m]["odds"], y=sub[sub["bet_type"]==m]["aw_num"], mode="markers", name=m) for m in mkts]
    frames =[go.Frame(name=str(i), data=mkf(closed.iloc[:i+1])) for i in range(len(closed))]
    fig = go.Figure(data=mkf(closed.iloc[:1]), frames=frames)
    fig.update_layout(updatemenus=_anim_buttons(80, 40), sliders=_anim_slider(range(len(closed)), 80, 40))
    return apply_layout(fig, title="🌌 Every Bet Revealed", height=560, showlegend=True)

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
def main():
    with st.spinner("Loading ledger…"):
        df_raw, df_roi, df_free, df_pending, kpis = load_data()

    df, bankroll_df = get_enriched(df_raw)
    opening = float(core.OPENING_BANK)

    # 🚨 STRUCTURAL FINANCIAL TRUTHS 🚨
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

    st.markdown(f'''<div style="display:flex; justify-content:space-between; margin-bottom:4px;">
          <div style="font-size:1.9rem;font-weight:700;">Xanderdu 🏆</div>
          <div style="font-size:1.05rem;">
            <span style="color:#8888aa">Bank</span> <span style="color:{_bal_col};">${current_balance:.2f}</span> &nbsp;&nbsp; 
            <span style="color:#8888aa">Invested</span> <span style="color:#e0e0f0;">${total_invested:.2f}</span> &nbsp;&nbsp;
            <span style="color:#8888aa">Betting P/L</span> <span style="color:{_pl_col};">${cur_pl:+.2f}</span>
          </div>
        </div>''', unsafe_allow_html=True)
    st.divider()

    t_home, t_people, t_markets, t_extremes, t_advanced, t_anim, t_inbox, t_ledger = st.tabs([
        "🏠 Home", "👤 People", "📈 Markets", "🎯 Extremes", "🔬 Advanced", "🎬 Animated", "📥 Inbox", "📒 Ledger"
    ])

    with t_home:
        c1, c2 = cols(2)
        with c1: stat_card("💰 Betting P/L", f"${cur_pl:+.2f}", color=_pl_col)
        with c2: stat_card("📊 Overall ROI", f"{roi:+.1f}%", color=_roi_col)
        worst = worst_bet(df)
        roast(f'Worst bet: {event_label(worst)} @ {worst["odds"]:.2f} — ${worst["actual_winnings"]:.2f}')
        st.divider()
        ca, cb = cols(2)
        with ca: pc(chart_cumulative_bankroll(df, opening, bankroll_df))
        with cb: pc(chart_win_loss_donut(df))
        pc(chart_waterfall(df))

    with t_people:
        view = st.radio("Select View", ["🏆 Leaderboard"] + [f"👤 {m}" for m in MEMBERS], horizontal=True, label_visibility="collapsed", key="people_view_radio")
        st.divider()

        if view == "🏆 Leaderboard":
            c1, c2 = cols(2)
            with c1: pc(chart_member_pl_bars(df))
            with c2: pc(chart_member_roi_bars(df))
            c3, c4 = cols(2)
            with c3: pc(chart_member_win_rate(df))
            with c4: pc(chart_member_radar(df))
            pc(chart_member_cumulative(df))
            pc(chart_longest_streaks(df))
            pc(chart_team_vs_individual(df))
        else:
            m = view.replace("👤 ", "")
            mdf = df[df["user"] == m]
            s = member_stats(df, m)
            streak_n, streak_type = compute_streak(mdf)

            _mk1, _mk2, _mk3, _mk4 = cols(4)
            with _mk1: kpi(f"{m} P/L", f"${s['pl']:+.2f}")
            with _mk2: kpi("ROI", f"{s['roi']:+.1f}%")
            with _mk3: kpi("Win Rate", f"{s['win_rate']:.1f}%", delta=f"{s['wins']}W / {s['losses']}L")
            with _mk4: kpi("Streak", f"{streak_n}× {streak_type}")

            if len(mdf) > 0:
                wb = worst_bet(mdf)
                roast(f"{m}'s worst bet: {event_label(wb)} @ {wb['odds']:.2f} — ${wb['actual_winnings']:.2f}")

            c1, c2 = cols(2)
            with c1: pc(chart_win_loss_donut(mdf, f"{m}'s Record"))
            with c2: pc(chart_member_monthly_pl(df, m))

            c3, c4 = cols(2)
            with c3: pc(chart_member_odds_dist(df, m))
            with c4: pc(chart_member_market_breakdown(df, m))

    with t_markets:
        mkt_view = st.radio("Market View", ["📊 Overview", "💀 Multi Curse", "🎲 Odds Analysis", "🌐 Sunburst"], horizontal=True, label_visibility="collapsed", key="mkt_view_radio")
        st.divider()

        if mkt_view == "📊 Overview":
            c1, c2 = cols(2)
            with c1: pc(chart_bet_type_roi_bars(df))
            with c2: pc(chart_competition_roi(df))
            pc(chart_pl_by_selection(df))

        elif mkt_view == "💀 Multi Curse":
            pc(chart_accumulator_curse(df))

        elif mkt_view == "🎲 Odds Analysis":
            c1, c2 = cols(2)
            with c1: pc(chart_odds_histogram(df))
            with c2: pc(chart_odds_bucket_roi(df))
            pc(chart_ev_proxy(df))
            pc(chart_stake_vs_outcome(df))

        elif mkt_view == "🌐 Sunburst":
            pc(chart_bet_type_sunburst(df))

    with t_extremes:
        section("Hall of Fame (and Shame)")
        best = best_bet(df)
        worst = worst_bet(df)

        bc, wc = cols(2)
        with bc:
            _b_sel = str(best.get("selection", "")).strip()
            _b_date = str(best.get("date", ""))[:10]
            stat_card(
                label="🏆 Best Bet Ever",
                value=f'${best.get("aw_num", 0):+.2f}',
                sub=f'{event_label(best)}<br>📌 {_b_sel} · {best.get("odds", 0):.2f}x · {best.get("bet_type","?")}<br>{best.get("user", "?")} · {_b_date}',
                color=WIN_COLOR,
                border_color=WIN_COLOR,
            )
        with wc:
            _w_sel = str(worst.get("selection", "")).strip()
            _w_date = str(worst.get("date", ""))[:10]
            stat_card(
                label="💀 Worst Bet Ever",
                value=f'${worst.get("aw_num", 0):+.2f}',
                sub=f'{event_label(worst)}<br>📌 {_w_sel} · {worst.get("odds", 0):.2f}x · {worst.get("bet_type","?")}<br>{worst.get("user", "?")} · {_w_date}',
                color=LOSS_COLOR,
                border_color=LOSS_COLOR,
            )
            
        st.write("")
        section("Top 10 Wins")
        _show_cols = [c for c in["date", "user", "home_team", "away_team", "competition", "bet_type", "selection", "odds", "stake", "actual_winnings"] if c in df.columns]
        
        df["aw_num"] = pd.to_numeric(df["actual_winnings"], errors="coerce").fillna(0)
        st.dataframe(df[df["status"] == "Win"].nlargest(10, "aw_num")[_show_cols], hide_index=True)
        
        section("Top 10 Losses")
        st.dataframe(df[df["status"] == "Loss"].nsmallest(10, "aw_num")[_show_cols], hide_index=True)
        
        pc(chart_weekday_heatmap(df))
        pc(chart_top_teams(df))

    with t_advanced:
        pc(chart_roi_rollercoaster(df))
        pc(chart_bankroll_by_member_contrib(df, opening, bankroll_df))
        pc(chart_bet_type_win_rate_vs_roi(df))
        pc(chart_voting_success(df))
        pc(chart_monthly_volatility(df))
        pc(chart_longshot_vs_fav(df))

        st.divider()
        section("🤖 Betbot — Ask the Ledger")
        asker = st.selectbox("Who's asking?", core.SYNDICATE_MEMBERS, key="betbot_asker")
        question = st.text_input("Question", placeholder="What's our ROI on BTTS bets?", key="betbot_q")
        if st.button("Ask", type="primary") and question:
            with st.spinner("Consulting the LangChain oracle…"):
                try:
                    if "agent" not in st.session_state:
                        st.session_state.agent = build_agent()
                    raw_ans = agent_query(st.session_state.agent, question)
                    reply = core.apply_persona(raw_ans, asker_name=asker)
                    st.info(reply)
                except Exception as e:
                    st.error(f"Betbot error: {e}")

    with t_anim:
        st.caption("Press ▶ Play or drag the slider.")
        pc(chart_anim_bankroll_worm(df, opening, bankroll_df))
        pc(chart_anim_member_worm(df))
        pc(chart_anim_monthly_roi_build(df))
        pc(chart_anim_bet_type_worm(df))
        pc(chart_anim_odds_scatter_race(df))
        pc(chart_anim_win_rate_evolution(df))

    with t_inbox:
        # --- NEW DATA SYNC SECTION ---
        st.subheader("Data Management")
        if st.button("🔄 Pull Latest from Google Sheets", use_container_width=True):
            with st.spinner("Downloading ledger from Google Sheets..."):
                success = core.sync_local_csv()
                if success:
                    st.cache_data.clear() # Dump the old cached data
                    st.success("Ledger synced successfully!")
                    st.rerun() # Reload the UI with the fresh data
                else:
                    st.error("Sync failed — check your API limits or credentials.")
                    
        st.divider()

        # --- EXISTING PENDING BETS SECTION ---
        st.subheader("Pending Bets")
        if len(df_pending) == 0:
            st.success("No pending bets — all caught up.")
        else:
            st.info(f"{len(df_pending)} bet(s) awaiting grading.")
            for _, row in df_pending.iterrows():
                with st.expander(
                    f"**{row['event']}** | {row['competition']} | {row['bet_type']} | {row['selection']} @ {row['odds']:.2f} "
                    f"(${row['stake']:.2f}) — *{row['date'].date()}*"
                ):
                    col1, col2, col3 = cols(3)
                    with col1:
                        new_status = st.selectbox(
                            "Result",
                            options=["Pending", "Win", "Loss", "Push", "Void", "manual_review"],
                            key=f"status_{row['uuid']}",
                        )
                    with col2:
                        actual_winnings = st.number_input(
                            "Actual winnings ($)", value=0.0, step=0.01,
                            format="%.2f", key=f"winnings_{row['uuid']}",
                        )
                    with col3:
# ... the rest continues as normal ...
                        st.write(""); st.write("")
                        if st.button("Commit", key=f"commit_{row['uuid']}", type="primary", use_container_width=True):
                            if new_status == "Pending":
                                st.warning("Select a result before committing.")
                            else:
                                with st.spinner("Writing to Google Sheets…"):
                                    ok = core.update_grade(row["uuid"], new_status, actual_winnings)
                                if ok:
                                    st.success(f"✅ {row['uuid']} → {new_status} ${actual_winnings:.2f}")
                                    st.cache_data.clear(); st.rerun()
                                else:
                                    st.error("Write failed — check logs/failed_writes.log")

        st.divider()

        # MANUAL ADD BET
        st.subheader("Add a Bet Manually")
        with st.form("add_bet_form", clear_on_submit=True):
            col1, col2 = cols(2)
            with col1:
                user        = st.selectbox("Member", core.SYNDICATE_MEMBERS + ["Syndicate"])
                home_team   = st.text_input("Home Team (e.g. Arsenal)")
                away_team   = st.text_input("Away Team (e.g. Chelsea)")
                competition = st.selectbox("Competition", COMPETITIONS)
                bet_type    = st.selectbox("Bet Type", BET_TYPES)
                selection   = st.text_input("Selection")
            with col2:
                odds     = st.number_input("Odds", min_value=1.01, value=1.80, step=0.01)
                stake    = st.number_input("Stake ($)", min_value=0.0, value=5.0, step=0.5)
                bet_date = st.date_input("Date")
                status   = st.selectbox("Status",["Pending", "Win", "Loss", "Push", "Deposit", "Withdrawal", "Reconciliation"])
                aw       = st.number_input("Actual Winnings", value=0.0)

            if st.form_submit_button("Add Bet / Record", type="primary"):
                if not home_team or not selection:
                    st.warning("Home team and selection are required.")
                else:
                    new_uuid = core.append_bet(user, home_team, away_team, competition, bet_type, selection, odds, stake, bet_date, status, aw)
                    st.success(f"Added {new_uuid}")
                    st.cache_data.clear(); st.rerun()

    with t_ledger:
        st.subheader("Full Ledger")

        all_users     = sorted(df_raw["user"].dropna().unique().tolist())
        all_bet_types = sorted(df_raw["bet_type"].dropna().unique().tolist())
        all_years     = sorted(df_raw["date"].dt.year.unique().tolist())

        with st.expander("Filters", expanded=False):
            fc = cols(4)
            with fc[0]:
                f_user = st.multiselect("Member", options=all_users, default=all_users)
            with fc[1]:
                f_bet_type = st.multiselect("Bet Type", options=all_bet_types, default=all_bet_types)
            with fc[2]:
                f_status = st.multiselect(
                    "Status",
                    options=["Win", "Loss", "Push", "Void", "Pending", "manual_review", "Deposit", "Reconciliation"],
                    default=["Win", "Loss", "Push"],
                )
            with fc[3]:
                f_year = st.multiselect("Year", options=all_years, default=all_years)

        # Apply to raw data so Deposits etc. can be viewed
        mask = (
            df_raw["user"].isin(f_user) &
            df_raw["bet_type"].isin(f_bet_type) &
            df_raw["status"].isin(f_status) &
            df_raw["date"].dt.year.isin(f_year)
        )
        df_filtered = df_raw[mask].copy()
        st.caption(f"Showing {len(df_filtered)} of {len(df_raw)} rows")

        # DISPLAY COLUMNS (Including UUID)
        display_cols = [c for c in["uuid", "date", "user", "home_team", "away_team", "competition", "bet_type", "selection",
                                    "odds", "stake", "status", "actual_winnings"] if c in df_filtered.columns]
        
        ledger_display = df_filtered[display_cols].sort_values("date", ascending=False).copy()
        
        # Avoid crashing on deposits by mapping correctly
        ledger_display["actual_winnings"] = pd.to_numeric(ledger_display["actual_winnings"], errors="coerce").fillna(0).map("${:+.2f}".format)
        ledger_display["stake"]           = ledger_display["stake"].map("${:.2f}".format)
        ledger_display["date"]            = ledger_display["date"].dt.date
        ledger_display.columns =[c.replace("_", " ").title() for c in ledger_display.columns]
        
        st.dataframe(ledger_display, use_container_width=True, hide_index=True)

        st.divider()

        # MANUAL CORRECTIONS
        with st.expander("Manual correction", expanded=False):
            mc1, mc2, mc3 = cols(3)
            with mc1: mc_uuid  = st.text_input("UUID")
            with mc2: mc_field = st.selectbox("Field", options=list(core.COLUMN_MAP.keys()))
            with mc3: mc_value = st.text_input("New value")
            if st.button("Apply correction", type="secondary"):
                if not mc_uuid or not mc_value:
                    st.warning("UUID and new value are required.")
                else:
                    with st.spinner("Updating…"):
                        ok = core.manual_correction(mc_uuid, mc_field, mc_value)
                    if ok:
                        st.success(f"✅ {mc_uuid} · {mc_field} = {mc_value}")
                        st.cache_data.clear(); st.rerun()
                    else:
                        st.error("Correction failed — UUID not found or write error.")

if __name__ == "__main__":
    main()