#!/usr/bin/env python3
# coding: utf-8
"""
app.py — Syndicate Tracker v5.0
================================
Streamlit UI. Mobile-optimised, tab-based, Plotly-powered.

Tabs:
  🏠 Home       — KPIs, bankroll, monthly cadence
  👤 People     — Per-member deep-dive (sub-nav)
  📈 Markets    — Bet-type, competition, odds analysis
  🎯 Extremes   — Best/worst bets, streaks, roast material
  🔬 Advanced   — Correlations, radar, rolling stats
  📥 Inbox      — Pending bets + manual grading
  📒 Ledger     — Full bet history with filters

Usage:
  streamlit run app.py
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots

import syndicate_core as core

# ─────────────────────────────────────────────────────────────────────────────
# DESIGN CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────
# Okabe-Ito palette — gold standard for colorblind safety
WIN_COLOR   = "#56B4E9"   # sky blue  → wins
LOSS_COLOR  = "#E69F00"   # amber     → losses
PUSH_COLOR  = "#999999"   # grey      → pushes

# Per-member colors (colorblind-safe, distinct)
MEMBER_COLORS = {
    "John":    "#009E73",   # teal-green
    "Richard": "#CC79A7",   # pink-purple
    "Xander":  "#D55E00",   # vermilion
    "Team":    "#0072B2",   # deep blue
}

# Okabe-Ito categorical (8 colors)
OKABE_ITO = ["#E69F00","#56B4E9","#009E73","#F0E442","#0072B2","#D55E00","#CC79A7","#999999"]

# Dark charcoal theme
BG_DARK   = "#1a1a2e"
BG_CARD   = "#16213e"
BG_CHART  = "#0f3460"
GRID_CLR  = "#2a2a4a"
TEXT_CLR  = "#e0e0f0"
ACCENT    = "#56B4E9"

MEMBERS = ["John", "Richard", "Xander"]

def _base_layout(**overrides):
    """PLOTLY_LAYOUT minus any keys supplied in overrides, to avoid duplicate-kwarg errors."""
    base = {k: v for k, v in PLOTLY_LAYOUT.items() if k not in overrides}
    return {**base, **overrides}

PLOTLY_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="'DM Mono', 'Courier New', monospace", size=13, color=TEXT_CLR),
    xaxis=dict(gridcolor=GRID_CLR, zerolinecolor=GRID_CLR,
               title_font=dict(size=11), tickfont=dict(size=11)),
    yaxis=dict(gridcolor=GRID_CLR, zerolinecolor=GRID_CLR,
               title_font=dict(size=11), tickfont=dict(size=11)),
    margin=dict(l=6,  r=6,  t=52, b=60),
    modebar=dict(
        orientation="v",
        bgcolor="rgba(0,0,0,0)",
        color="#555577",
        activecolor=ACCENT,
    ),
    dragmode=False,  # disables touch drag-to-zoom — use fullscreen + pinch instead
    legend=dict(
        bgcolor="rgba(0,0,0,0.3)",
        bordercolor=GRID_CLR,
        borderwidth=1,
        font=dict(size=12),
        orientation="h",
        yanchor="top",
        y=-0.18,
        xanchor="center",
        x=0.5,
    ),
)

# ─────────────────────────────────────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Xanderdu 🏆",
    page_icon="🏆",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ─────────────────────────────────────────────────────────────────────────────
# CUSTOM CSS
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@300;400;500&family=Space+Grotesk:wght@400;600;700&display=swap');

html, body, [class*="css"] {
    background-color: #1a1a2e;
    color: #e0e0f0;
    font-family: 'Space Grotesk', sans-serif;
}

/* Tabs */
.stTabs [data-baseweb="tab-list"] {
    gap: 4px;
    background: #16213e;
    border-radius: 12px;
    padding: 4px;
}
.stTabs [data-baseweb="tab"] {
    background: transparent;
    border-radius: 8px;
    color: #8888aa;
    font-size: 14px;
    font-weight: 600;
    padding: 8px 16px;
    font-family: 'Space Grotesk', sans-serif;
}
.stTabs [aria-selected="true"] {
    background: #56B4E9 !important;
    color: #1a1a2e !important;
}

/* Metrics */
[data-testid="metric-container"] {
    background: #16213e;
    border: 1px solid #2a2a4a;
    border-radius: 12px;
    padding: 16px;
}
[data-testid="stMetricValue"] {
    font-family: 'DM Mono', monospace;
    font-size: 1.8rem !important;
    font-weight: 500;
    color: #56B4E9;
}
[data-testid="stMetricLabel"] {
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: #8888aa;
}
[data-testid="stMetricDelta"] {
    font-family: 'DM Mono', monospace;
    font-size: 0.85rem;
}

/* KPI roast strip */
.roast-strip {
    background: linear-gradient(90deg, #16213e, #0f3460);
    border-left: 3px solid #E69F00;
    border-radius: 0 8px 8px 0;
    padding: 10px 16px;
    margin: 8px 0;
    font-family: 'DM Mono', monospace;
    font-size: 0.85rem;
    color: #E69F00;
    font-style: italic;
}

/* Segmented sub-nav buttons */
.stButton>button {
    background: #16213e;
    border: 1px solid #2a2a4a;
    color: #8888aa;
    border-radius: 8px;
    font-family: 'Space Grotesk', sans-serif;
    font-weight: 600;
    font-size: 14px;
    padding: 8px 20px;
    transition: all 0.2s;
}
.stButton>button:hover {
    background: #0f3460;
    color: #e0e0f0;
    border-color: #56B4E9;
}

/* Dataframe */
[data-testid="stDataFrame"] {
    border-radius: 8px;
    overflow: hidden;
}

/* Section headers */
.section-header {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 1.1rem;
    font-weight: 700;
    color: #56B4E9;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin: 20px 0 8px;
    border-bottom: 1px solid #2a2a4a;
    padding-bottom: 6px;
}
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────
def section(label: str):
    st.markdown(f'<div class="section-header">{label}</div>', unsafe_allow_html=True)


def plotly_defaults(fig) -> go.Figure:
    """Apply dark theme defaults to any Plotly figure."""
    fig.update_layout(**PLOTLY_LAYOUT)
    return fig


def apply_layout(fig, title="", height=420, showlegend=True, **kwargs):
    base = dict(PLOTLY_LAYOUT)
    # Tighten bottom margin when there is no legend — saves ~50px on every no-legend chart
    if not showlegend:
        base["margin"] = dict(base["margin"], b=10)
    fig.update_layout(
        title=dict(text=title, font=dict(size=14, color=TEXT_CLR), x=0.01),
        height=height,
        showlegend=showlegend,
        **base,
        **kwargs,
    )
    return fig


def status_color(s: str) -> str:
    return WIN_COLOR if s == "Win" else LOSS_COLOR if s == "Loss" else PUSH_COLOR


def cols(n, gap="small"):
    """Thin wrapper — accepts int or list[int], same as st.columns."""
    return st.columns(n, gap=gap)


# Auto-incrementing key for st.plotly_chart — prevents duplicate-element-ID errors
# when the same chart function is rendered in multiple tabs/views.
_chart_counter: list[int] = [0]

_PLOTLY_CONFIG = {
    "displaylogo": False,
    "scrollZoom": False,
    # Allowlist — only show camera (toImage) and reset (resetScale2d)
    "modeBarButtons": [["toImage", "resetScale2d"]],
    "toImageButtonOptions": {
        "format": "png",
        "width":  1200,
        "height": 600,
        "scale":  2,
        "filename": "syndicate_chart",
    },
}


def pc(fig):
    """st.plotly_chart with a guaranteed-unique key and high-res export config."""
    _chart_counter[0] += 1
    st.plotly_chart(
        fig,
        use_container_width=True,
        key=f"pc_{_chart_counter[0]}",
        config=_PLOTLY_CONFIG,
    )


def kpi(label, value, delta=None, delta_color="normal"):
    st.metric(label=label, value=value, delta=delta, delta_color=delta_color)


def roast(text: str):
    st.markdown(f'<div class="roast-strip">🔥 {text}</div>', unsafe_allow_html=True)


def stat_card(label: str, value: str, sub: str = "", color: str = None, border_color: str = None):
    """Unified KPI card — same style used on Home, Leaderboard and Extremes."""
    color       = color        or ACCENT
    border_color = border_color or f"{color}55"
    st.markdown(
        f'''<div style="background:{BG_CARD};border:1px solid {border_color};
border-radius:12px;padding:14px 16px;text-align:center;margin-bottom:4px;">
  <div style="color:#8888aa;font-size:0.72rem;text-transform:uppercase;
              letter-spacing:0.08em;margin-bottom:4px;">{label}</div>
  <div style="font-family:DM Mono,monospace;font-size:1.55rem;font-weight:500;
              color:{color};line-height:1.1;">{value}</div>
  <div style="color:#8888aa;font-size:0.78rem;margin-top:4px;">{sub}</div>
</div>''',
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────────────────────────────────────
# DATA LOADING & PREPROCESSING
# ─────────────────────────────────────────────────────────────────────────────
@st.cache_data(ttl=300)
def load_data():
    df, df_roi, df_free, df_pending, kpis = core.load_ledger()
    return df, df_roi, df_free, df_pending, kpis


@st.cache_data(ttl=300)
def get_enriched(df: pd.DataFrame) -> tuple:
    """
    Returns (working, bankroll_df):
      - working      : graded bets only (no Deposit/Reconciliation) for analytics
      - bankroll_df  : includes Deposit rows so bankroll line is accurate
    """
    df = df.copy()
    USER_MAP = {
        "Xanderdu middle debut": "Team",
        "Xanderdu middle 2 electric boogaloo": "Team",
        "Syndicate": "Team",
        "Taken with the intent of cashing out at $4.80 or after 6 weeks": "Team",
    }
    df["user"] = df["user"].replace(USER_MAP)

    MULTI_PATS = ["accumulator", "multi", "parlay", "fa cup multi", "round"]
    def norm_mkt(m):
        if pd.isna(m): return m
        ml = str(m).lower().strip()
        return "Multi" if any(p in ml for p in MULTI_PATS) else str(m).strip()
    df["market"] = df["market"].apply(norm_mkt)

    def odds_bucket(o):
        if o < 1.4:   return "<1.40"
        elif o < 1.7: return "1.40\u20131.69"
        elif o < 2.0: return "1.70\u20131.99"
        elif o < 2.5: return "2.00\u20132.49"
        elif o < 3.5: return "2.50\u20133.49"
        else:         return "3.50+"

    # bankroll_df: keeps Deposit rows so the top-up is reflected in the line chart
    bankroll_df = df[~df["status"].isin(["Reconciliation"])].copy()
    bankroll_df["date"]     = pd.to_datetime(bankroll_df["date"])
    bankroll_df["date_str"] = bankroll_df["date"].dt.strftime("%Y-%m-%d")
    bankroll_df = bankroll_df.sort_values("date").reset_index(drop=True)
    bankroll_df["cum_pl"]   = bankroll_df["actual_winnings"].cumsum()

    # working: pure bet analytics — no Deposit, no Reconciliation
    working = df[~df["status"].isin(["Reconciliation", "Deposit"])].copy()
    working["date"]     = pd.to_datetime(working["date"])
    working["date_str"] = working["date"].dt.strftime("%Y-%m-%d")  # clean string for x-axes
    working["month"]    = working["date"].dt.to_period("M").astype(str)
    working["weekday"]  = working["date"].dt.day_name()
    working["year"]     = working["date"].dt.year
    working = working.sort_values("date").reset_index(drop=True)
    working["cum_pl"]       = working["actual_winnings"].cumsum()
    working["implied_prob"] = 1.0 / working["odds"].replace(0, np.nan)
    working["odds_bucket"]  = working["odds"].apply(odds_bucket)

    return working, bankroll_df


def member_stats(df: pd.DataFrame, member: str) -> dict:
    sub = df[df["user"] == member]
    wins   = (sub["status"] == "Win").sum()
    losses = (sub["status"] == "Loss").sum()
    pushes = (sub["status"] == "Push").sum()
    staked = sub["stake"].sum()
    pl     = sub["actual_winnings"].sum()
    roi    = pl / staked * 100 if staked > 0 else 0
    wr     = wins / (wins + losses) * 100 if (wins + losses) > 0 else 0
    avg_odds = sub["odds"].mean()
    return dict(
        bets=len(sub), wins=wins, losses=losses, pushes=pushes,
        staked=staked, pl=pl, roi=roi, win_rate=wr, avg_odds=avg_odds,
    )


def team_summary(df: pd.DataFrame) -> dict:
    wins   = (df["status"] == "Win").sum()
    losses = (df["status"] == "Loss").sum()
    pushes = (df["status"] == "Push").sum()
    staked = df["stake"].sum()
    pl     = df["actual_winnings"].sum()
    roi    = pl / staked * 100 if staked > 0 else 0
    wr     = wins / (wins + losses) * 100 if (wins + losses) > 0 else 0
    return dict(bets=len(df), wins=wins, losses=losses, pushes=pushes,
                staked=staked, pl=pl, roi=roi, win_rate=wr)


def compute_streak(df: pd.DataFrame) -> tuple[int, str]:
    """Current streak for a member's bets."""
    sub = df[df["status"].isin(["Win", "Loss"])].sort_values("date")
    if len(sub) == 0:
        return 0, "–"
    last = sub.iloc[-1]["status"]
    count = 0
    for _, row in sub.iloc[::-1].iterrows():
        if row["status"] == last:
            count += 1
        else:
            break
    return count, last


def worst_bet(df: pd.DataFrame) -> pd.Series:
    closed = df[df["status"].isin(["Win", "Loss"])]
    if closed.empty:
        return df.iloc[0]
    return closed.loc[closed["actual_winnings"].idxmin()]


def best_bet(df: pd.DataFrame) -> pd.Series:
    closed = df[df["status"].isin(["Win", "Loss"])]
    if closed.empty:
        return df.iloc[0]
    return closed.loc[closed["actual_winnings"].idxmax()]


def event_label(row: pd.Series) -> str:
    """Return a display label for a bet row regardless of column name."""
    for col in ("event", "home_team", "selection", "market"):
        val = row.get(col)
        if val and str(val) not in ("nan", "Multiple", ""):
            return str(val)
    return "?"


def rolling_roi(df: pd.DataFrame, window: int = 20) -> pd.Series:
    df = df.sort_values("date").copy()
    return (
        df["actual_winnings"].rolling(window).sum()
        / df["stake"].rolling(window).sum()
        * 100
    )


# ─────────────────────────────────────────────────────────────────────────────
# CHART FACTORY
# ─────────────────────────────────────────────────────────────────────────────

def chart_cumulative_bankroll(df: pd.DataFrame, opening: float = 300, bankroll_df: pd.DataFrame = None) -> go.Figure:
    """Chart 1 — Cumulative bankroll line with max-drawdown shading.
    Uses bankroll_df (includes deposits) if provided, else falls back to df."""
    src_df = bankroll_df if bankroll_df is not None else df
    df2 = src_df.sort_values("date").copy()
    df2["bankroll"] = opening + df2["actual_winnings"].cumsum()
    df2["peak"]     = df2["bankroll"].cummax()
    df2["drawdown"] = df2["bankroll"] - df2["peak"]

    fig = go.Figure()

    # Drawdown fill
    fig.add_trace(go.Scatter(
        x=df2["date_str"], y=df2["peak"],
        fill=None, mode="lines",
        line=dict(color="rgba(0,0,0,0)"),
        showlegend=False, name="Peak",
    ))
    fig.add_trace(go.Scatter(
        x=df2["date_str"], y=df2["bankroll"],
        fill="tonexty",
        fillcolor="rgba(230,159,0,0.15)",
        mode="lines",
        line=dict(color=LOSS_COLOR, width=0.5, dash="dot"),
        name="Drawdown",
    ))

    # Bankroll line
    fig.add_trace(go.Scatter(
        x=df2["date_str"], y=df2["bankroll"],
        mode="lines+markers",
        line=dict(color=ACCENT, width=3),
        marker=dict(size=4, color=ACCENT),
        name="Bankroll",
    ))

    # Opening bank reference
    fig.add_hline(y=opening, line_dash="dash", line_color=GRID_CLR,
                  annotation_text=f"Opening ${opening:.0f}",
                  annotation_font_color=GRID_CLR, annotation_position="bottom right")

    # Current value in title — avoids floating label stealing right-side space
    cur = df2["bankroll"].iloc[-1]
    _cur_color = WIN_COLOR if cur >= opening else LOSS_COLOR

    apply_layout(fig, title=f"📈 Bankroll  ${cur:.2f}", height=420, showlegend=False)
    return fig


def chart_monthly_pl(df: pd.DataFrame) -> go.Figure:
    """Chart 2 — Monthly P/L waterfall bars."""
    monthly = df.groupby("month")["actual_winnings"].sum().reset_index()
    monthly.columns = ["month", "pl"]
    colors = [WIN_COLOR if v >= 0 else LOSS_COLOR for v in monthly["pl"]]

    fig = go.Figure(go.Bar(
        x=monthly["month"],
        y=monthly["pl"],
        marker_color=colors,
        text=[f"${v:+.2f}" for v in monthly["pl"]],
        textposition="auto",
        textfont=dict(size=10, family="DM Mono"),
        insidetextanchor="middle",
    ))
    fig.update_layout(uniformtext=dict(mode="hide", minsize=8))
    fig.add_hline(y=0, line_color=GRID_CLR, line_width=1)
    apply_layout(fig, title="📅 Monthly P/L", height=400, showlegend=False)
    return fig


def chart_win_loss_donut(df: pd.DataFrame, title: str = "Overall Record") -> go.Figure:
    """Chart 3 — Win/Loss/Push donut."""
    wins   = (df["status"] == "Win").sum()
    losses = (df["status"] == "Loss").sum()
    pushes = (df["status"] == "Push").sum()

    fig = go.Figure(go.Pie(
        labels=["Win", "Loss", "Push"],
        values=[wins, losses, pushes],
        hole=0.55,
        marker=dict(colors=[WIN_COLOR, LOSS_COLOR, PUSH_COLOR]),
        textinfo="label+percent",
        textfont=dict(size=13),
        pull=[0.04, 0.04, 0.01],
    ))
    wr = wins / (wins + losses) * 100 if (wins + losses) > 0 else 0
    fig.add_annotation(text=f"{wr:.1f}%<br><span style='font-size:10px'>win rate</span>",
                       x=0.5, y=0.5, showarrow=False,
                       font=dict(size=18, family="DM Mono", color=TEXT_CLR))
    apply_layout(fig, title=f"🎯 {title}", height=360, showlegend=True)
    return fig


def chart_member_pl_bars(df: pd.DataFrame) -> go.Figure:
    """Chart 4 — Member P/L comparison bars."""
    data = [member_stats(df[df["user"] == m], m) for m in MEMBERS]
    members = [d["member"] if "member" in d else m for d, m in zip(data, MEMBERS)]
    pls     = [d["pl"] for d in data]
    colors  = [WIN_COLOR if p >= 0 else LOSS_COLOR for p in pls]

    fig = go.Figure(go.Bar(
        x=MEMBERS, y=pls,
        marker_color=[MEMBER_COLORS[m] for m in MEMBERS],
        text=[f"${p:+.2f}" for p in pls],
        textposition="auto",
        textfont=dict(size=11, family="DM Mono"),
        insidetextanchor="middle",
    ))
    fig.update_layout(uniformtext=dict(mode="hide", minsize=9))
    fig.add_hline(y=0, line_color=GRID_CLR)
    apply_layout(fig, title="💸 Individual P/L", height=340, showlegend=False)
    return fig


def chart_member_roi_bars(df: pd.DataFrame) -> go.Figure:
    """Chart 5 — Member ROI comparison."""
    rois    = [member_stats(df[df["user"] == m], m)["roi"] for m in MEMBERS]
    colors  = [WIN_COLOR if r >= 0 else LOSS_COLOR for r in rois]

    fig = go.Figure(go.Bar(
        x=MEMBERS, y=rois,
        marker_color=colors,
        text=[f"{r:+.1f}%" for r in rois],
        textposition="auto",
        textfont=dict(size=11, family="DM Mono"),
        insidetextanchor="middle",
    ))
    fig.update_layout(uniformtext=dict(mode="hide", minsize=9))
    fig.add_hline(y=0, line_color=GRID_CLR)
    apply_layout(fig, title="📊 Individual ROI %", height=340, showlegend=False)
    return fig


def chart_member_cumulative(df: pd.DataFrame) -> go.Figure:
    """Chart 6 — Per-member cumulative P/L lines."""
    fig = go.Figure()
    for m in MEMBERS:
        sub = df[df["user"] == m].sort_values("date")
        sub = sub.copy()
        sub["cum"] = sub["actual_winnings"].cumsum()
        fig.add_trace(go.Scatter(
            x=sub["date_str"], y=sub["cum"],
            mode="lines+markers",
            name=m,
            line=dict(color=MEMBER_COLORS[m], width=3),
            marker=dict(size=5, symbol="circle"),
        ))
    fig.add_hline(y=0, line_dash="dash", line_color=GRID_CLR)
    apply_layout(fig, title="📈 Member Cumulative P/L", height=440)
    return fig


def chart_member_win_rate(df: pd.DataFrame) -> go.Figure:
    """Chart 7 — Win rate comparison horizontal bars."""
    stats = {m: member_stats(df[df["user"] == m], m) for m in MEMBERS}
    wrs = [stats[m]["win_rate"] for m in MEMBERS]

    fig = go.Figure(go.Bar(
        y=MEMBERS, x=wrs,
        orientation="h",
        marker_color=[MEMBER_COLORS[m] for m in MEMBERS],
        text=[f"{w:.1f}%" for w in wrs],
        textposition="inside",
        textfont=dict(size=13, family="DM Mono"),
    ))
    apply_layout(fig, title="🎯 Win Rate by Member", height=260, showlegend=False)
    return fig


def chart_member_odds_dist(df: pd.DataFrame, member: str) -> go.Figure:
    """Chart 8 — Odds distribution violin for a member."""
    sub = df[df["user"] == member]
    wins   = sub[sub["status"] == "Win"]["odds"]
    losses = sub[sub["status"] == "Loss"]["odds"]

    fig = go.Figure()
    fig.add_trace(go.Violin(
        y=wins, name="Win", box_visible=True, meanline_visible=True,
        fillcolor=WIN_COLOR, opacity=0.7, line_color=WIN_COLOR,
    ))
    fig.add_trace(go.Violin(
        y=losses, name="Loss", box_visible=True, meanline_visible=True,
        fillcolor=LOSS_COLOR, opacity=0.7, line_color=LOSS_COLOR,
    ))
    apply_layout(fig, title=f"🎲 {member} — Odds Distribution W/L", height=320)
    return fig


def chart_member_market_breakdown(df: pd.DataFrame, member: str) -> go.Figure:
    """Chart 9 — Member market breakdown stacked bars."""
    sub = df[df["user"] == member]
    grp = sub.groupby(["market", "status"]).size().unstack(fill_value=0)
    for col in ["Win", "Loss", "Push"]:
        if col not in grp.columns:
            grp[col] = 0

    fig = go.Figure()
    fig.add_trace(go.Bar(name="Win",  x=grp.index, y=grp["Win"],  marker_color=WIN_COLOR))
    fig.add_trace(go.Bar(name="Loss", x=grp.index, y=grp["Loss"], marker_color=LOSS_COLOR))
    if grp["Push"].sum() > 0:
        fig.add_trace(go.Bar(name="Push", x=grp.index, y=grp["Push"], marker_color=PUSH_COLOR))
    fig.update_layout(barmode="stack")
    apply_layout(fig, title=f"📊 {member} — Bets by Market", height=340)
    return fig


def chart_member_monthly_pl(df: pd.DataFrame, member: str) -> go.Figure:
    """Chart 10 — Member monthly P/L bar chart."""
    sub = df[df["user"] == member]
    monthly = sub.groupby("month")["actual_winnings"].sum().reset_index()
    monthly.columns = ["month", "pl"]

    fig = go.Figure(go.Bar(
        x=monthly["month"], y=monthly["pl"],
        marker_color=[WIN_COLOR if v >= 0 else LOSS_COLOR for v in monthly["pl"]],
        text=[f"${v:+.2f}" for v in monthly["pl"]],
        textposition="outside",
        textfont=dict(size=11, family="DM Mono"),
    ))
    fig.add_hline(y=0, line_color=GRID_CLR)
    apply_layout(fig, title=f"📅 {member} — Monthly P/L", height=320, showlegend=False)
    return fig


def chart_market_roi_bars(df: pd.DataFrame) -> go.Figure:
    """Chart 11 — ROI by market type horizontal bars."""
    grp = df.groupby("market").agg(
        bets=("odds", "count"),
        pl=("actual_winnings", "sum"),
        staked=("stake", "sum"),
    )
    grp["roi"] = grp["pl"] / grp["staked"] * 100
    grp = grp[grp["bets"] >= 3].sort_values("roi")

    fig = go.Figure(go.Bar(
        y=grp.index, x=grp["roi"],
        orientation="h",
        marker_color=[WIN_COLOR if r >= 0 else LOSS_COLOR for r in grp["roi"]],
        text=[f"{r:+.1f}%" for r in grp["roi"]],
        textposition="outside",
        textfont=dict(size=11, family="DM Mono"),
    ))
    fig.add_vline(x=0, line_color=GRID_CLR)
    apply_layout(fig, title="📊 ROI by Market (≥3 bets)", height=max(300, len(grp)*38), showlegend=False)
    fig.update_yaxes(tickfont=dict(size=10))
    return fig


def chart_market_sunburst(df: pd.DataFrame) -> go.Figure:
    """Chart 12 — Market → Status sunburst."""
    grp = df.groupby(["market", "status"]).size().reset_index(name="count")
    grp = grp[grp["status"].isin(["Win", "Loss", "Push"])]

    fig = px.sunburst(
        grp,
        path=["market", "status"],
        values="count",
        color="status",
        color_discrete_map={"Win": WIN_COLOR, "Loss": LOSS_COLOR, "Push": PUSH_COLOR},
    )
    fig.update_traces(textfont_size=12)
    apply_layout(fig, title="🌐 Market → Outcome Sunburst", height=480, showlegend=False)
    return fig


def chart_accumulator_curse(df: pd.DataFrame) -> go.Figure:
    """Chart 13 — Accumulator legs vs outcome, with P/L annotation."""
    multis = df[df["market"] == "Multi"].copy()
    total_pl = multis["actual_winnings"].sum()
    wins = (multis["status"] == "Win").sum()
    losses = (multis["status"] == "Loss").sum()
    wr = wins / (wins + losses) * 100 if (wins + losses) > 0 else 0

    # Monthly accumulator P/L
    monthly = multis.groupby("month")["actual_winnings"].sum().reset_index()
    monthly.columns = ["month", "pl"]

    fig = make_subplots(
        rows=1, cols=2,
        subplot_titles=("Monthly Multi P/L", "Win/Loss Split"),
        specs=[[{"type": "bar"}, {"type": "pie"}]],
    )

    # Left: monthly bars
    fig.add_trace(go.Bar(
        x=monthly["month"], y=monthly["pl"],
        marker_color=[WIN_COLOR if v >= 0 else LOSS_COLOR for v in monthly["pl"]],
        text=[f"${v:+.2f}" for v in monthly["pl"]],
        textposition="outside",
        showlegend=False,
    ), row=1, col=1)

    # Right: donut
    fig.add_trace(go.Pie(
        labels=["Win", "Loss"],
        values=[wins, losses],
        hole=0.5,
        marker=dict(colors=[WIN_COLOR, LOSS_COLOR]),
        textinfo="label+percent",
    ), row=1, col=2)

    fig.add_annotation(
        text=f"${total_pl:+.2f}<br>total", x=0.78, y=0.5,
        xref="paper", yref="paper",
        showarrow=False, font=dict(size=16, family="DM Mono", color=LOSS_COLOR),
    )

    apply_layout(fig, title=f"💀 The Accumulator Curse — {wr:.0f}% win rate", height=360)
    return fig


def chart_odds_bucket_roi(df: pd.DataFrame) -> go.Figure:
    """Chart 14 — ROI by odds bucket."""
    BUCKET_ORDER = ["<1.40", "1.40–1.69", "1.70–1.99", "2.00–2.49", "2.50–3.49", "3.50+"]
    grp = df.groupby("odds_bucket").agg(
        bets=("odds", "count"),
        pl=("actual_winnings", "sum"),
        staked=("stake", "sum"),
        wins=("status", lambda x: (x == "Win").sum()),
    )
    grp["roi"]      = grp["pl"] / grp["staked"] * 100
    grp["win_rate"] = grp["wins"] / grp["bets"] * 100
    grp = grp.reindex([b for b in BUCKET_ORDER if b in grp.index])

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Bar(
        x=grp.index, y=grp["roi"],
        marker_color=[WIN_COLOR if r >= 0 else LOSS_COLOR for r in grp["roi"]],
        name="ROI %",
        text=[f"{r:+.1f}%" for r in grp["roi"]],
        textposition="outside",
        textfont=dict(size=11),
    ), secondary_y=False)
    fig.add_trace(go.Scatter(
        x=grp.index, y=grp["win_rate"],
        mode="lines+markers",
        name="Win Rate %",
        line=dict(color=PUSH_COLOR, width=2, dash="dash"),
        marker=dict(size=8, symbol="diamond"),
    ), secondary_y=True)

    fig.add_hline(y=0, line_color=GRID_CLR, secondary_y=False)
    apply_layout(fig, title="🎲 ROI & Win Rate by Odds Bucket", height=340)
    fig.update_layout(margin=dict(l=6,  r=28, t=52, b=60))
    fig.update_yaxes(secondary_y=False, gridcolor=GRID_CLR, tickfont=dict(size=11))
    fig.update_yaxes(title_text="Win%", secondary_y=True, showgrid=False,
                     title_font=dict(size=11), tickfont=dict(size=11))
    return fig


def chart_competition_roi(df: pd.DataFrame) -> go.Figure:
    """Chart 15 — ROI by competition."""
    grp = df.groupby("market").agg(      # use market here as competition proxy
        pl=("actual_winnings", "sum"),
        staked=("stake", "sum"),
        bets=("odds", "count"),
    )
    # Use event-derived competition if available, else market
    if "season" in df.columns:
        grp = df.groupby("season").agg(
            pl=("actual_winnings", "sum"),
            staked=("stake", "sum"),
            bets=("odds", "count"),
        )
        grp["roi"] = grp["pl"] / grp["staked"] * 100
        grp = grp[grp["bets"] >= 3].sort_values("roi")
        x_label = grp.index
        title = "🏆 ROI by Season"
    else:
        grp["roi"] = grp["pl"] / grp["staked"] * 100
        grp = grp[grp["bets"] >= 3].sort_values("roi")
        x_label = grp.index
        title = "🏆 ROI by Market"

    fig = go.Figure(go.Bar(
        y=x_label, x=grp["roi"],
        orientation="h",
        marker_color=[WIN_COLOR if r >= 0 else LOSS_COLOR for r in grp["roi"]],
        text=[f"{r:+.1f}% ({int(b)} bets)" for r, b in zip(grp["roi"], grp["bets"])],
        textposition="outside",
        textfont=dict(size=11, family="DM Mono"),
    ))
    fig.add_vline(x=0, line_color=GRID_CLR)
    apply_layout(fig, title=title, height=max(280, len(grp)*40), showlegend=False)
    return fig


def chart_roi_rollercoaster(df: pd.DataFrame) -> go.Figure:
    """Chart 16 — Rolling 20-bet ROI (the rollercoaster)."""
    df2 = df.sort_values("date").copy()
    df2["rolling_roi"] = rolling_roi(df2, 20)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df2["date_str"], y=df2["rolling_roi"],
        mode="lines",
        fill="tozeroy",
        fillcolor="rgba(86,180,233,0.12)",
        line=dict(color=ACCENT, width=2.5),
        name="20-bet ROI",
    ))
    fig.add_hline(y=0, line_dash="dash", line_color=GRID_CLR)

    # Annotate worst point
    worst_idx = df2["rolling_roi"].idxmin()
    if not pd.isna(worst_idx):
        wr = df2.loc[worst_idx]
        fig.add_annotation(
            x=wr["date_str"], y=wr["rolling_roi"],
            text=f"🔥 {wr['rolling_roi']:.1f}%",
            showarrow=True, arrowhead=2,
            arrowcolor=LOSS_COLOR, font=dict(color=LOSS_COLOR, size=12),
            bgcolor="rgba(26,26,46,0.8)",
        )

    apply_layout(fig, title="🎢 20-Bet Rolling ROI", height=400, showlegend=False)
    return fig


def chart_weekday_heatmap(df: pd.DataFrame) -> go.Figure:
    """Chart 17 — Weekday × Month P/L heatmap."""
    order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    df2   = df.copy()
    df2["weekday"] = pd.Categorical(df2["weekday"], categories=order, ordered=True)

    pivot = df2.pivot_table(
        index="weekday", columns="month", values="actual_winnings",
        aggfunc="sum", fill_value=0,
    )

    # Shorten day names to 3 chars so y-axis labels don't eat space
    short_days = [d[:3] for d in pivot.index.tolist()]

    fig = go.Figure(go.Heatmap(
        z=pivot.values,
        x=pivot.columns.tolist(),
        y=short_days,
        colorscale=[[0, LOSS_COLOR], [0.5, "#1a1a2e"], [1, WIN_COLOR]],
        zmid=0,
        # No cell labels — colour gradient tells the story; labels are unreadable on mobile
        colorbar=dict(thickness=10, len=0.8, tickfont=dict(size=10),
                      title=dict(text="$", font=dict(size=10))),
        hovertemplate="<b>%{y} %{x}</b><br>P/L: $%{z:.2f}<extra></extra>",
    ))
    apply_layout(fig, title="📅 P/L Heatmap — Day × Month", height=300, showlegend=False)
    fig.update_xaxes(tickangle=45, tickfont=dict(size=10), automargin=True)
    fig.update_yaxes(tickfont=dict(size=11))
    return fig


def chart_stake_vs_outcome(df: pd.DataFrame) -> go.Figure:
    """Chart 18 — Stake vs actual winnings scatter."""
    d = df[df["status"].isin(["Win", "Loss"])].copy()
    d["color"] = d["status"].map({"Win": WIN_COLOR, "Loss": LOSS_COLOR})
    d["symbol"] = d["status"].map({"Win": "circle", "Loss": "triangle-up"})

    fig = go.Figure()
    for status, color, sym in [("Win", WIN_COLOR, "circle"), ("Loss", LOSS_COLOR, "triangle-up")]:
        sub = d[d["status"] == status]
        fig.add_trace(go.Scatter(
            x=sub["stake"], y=sub["actual_winnings"],
            mode="markers",
            name=status,
            marker=dict(
                color=color, size=9, symbol=sym,
                line=dict(color="rgba(0,0,0,0.3)", width=1),
            ),
            text=sub.apply(lambda r: f"{r['event']}<br>{r['odds']:.2f} odds", axis=1),
            hovertemplate="<b>%{text}</b><br>Stake: $%{x:.2f}<br>P/L: $%{y:.2f}<extra></extra>",
        ))
    fig.add_hline(y=0, line_color=GRID_CLR)
    apply_layout(fig, title="💰 Stake vs P/L", height=360)
    fig.update_xaxes(title_text="Stake $", title_font=dict(size=11))
    fig.update_yaxes(title_text="P/L $", title_font=dict(size=11))
    fig.update_xaxes(title_text="Stake $")
    return fig


def chart_odds_histogram(df: pd.DataFrame) -> go.Figure:
    """Chart 19 — Odds histogram W/L overlaid."""
    wins   = df[df["status"] == "Win"]["odds"]
    losses = df[df["status"] == "Loss"]["odds"]

    fig = go.Figure()
    fig.add_trace(go.Histogram(
        x=wins, name="Win", nbinsx=20,
        marker_color=WIN_COLOR, opacity=0.7,
    ))
    fig.add_trace(go.Histogram(
        x=losses, name="Loss", nbinsx=20,
        marker_color=LOSS_COLOR, opacity=0.7,
    ))
    fig.update_layout(barmode="overlay")
    apply_layout(fig, title="🎲 Odds Distribution — Win vs Loss", height=320)
    fig.update_xaxes(title_text="Odds")
    return fig


def _hex_to_rgba(hex_color: str, alpha: float = 0.15) -> str:
    """Convert a #rrggbb hex string to rgba(r,g,b,alpha) for Plotly."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


def chart_member_radar(df: pd.DataFrame) -> go.Figure:
    """Chart 20 — Spider/radar comparing members across 5 metrics."""
    metrics = ["Win Rate", "ROI", "Avg Odds", "Bets", "Stake Efficiency"]

    raw = {}
    for m in MEMBERS:
        s = member_stats(df[df["user"] == m], m)
        raw[m] = [s["win_rate"], max(0, s["roi"] + 30), s["avg_odds"], s["bets"],
                  s["pl"] / s["staked"] * 100 + 50 if s["staked"] > 0 else 50]

    fig = go.Figure()
    for m in MEMBERS:
        vals = raw[m]
        vals_norm = [v / max(max(raw[mm][i] for mm in MEMBERS), 0.001) * 100
                     for i, v in enumerate(vals)]
        vals_closed = vals_norm + [vals_norm[0]]
        fig.add_trace(go.Scatterpolar(
            r=vals_closed,
            theta=metrics + [metrics[0]],
            fill="toself",
            name=m,
            line=dict(color=MEMBER_COLORS[m], width=2),
            fillcolor=_hex_to_rgba(MEMBER_COLORS[m], 0.15),
            marker=dict(size=6),
        ))
    apply_layout(fig, title="🕸️ Member Radar", height=400)
    fig.update_layout(
        polar=dict(
            radialaxis=dict(visible=True, range=[0, 100], gridcolor=GRID_CLR,
                            color=TEXT_CLR, tickfont=dict(size=9)),
            angularaxis=dict(gridcolor=GRID_CLR, color=TEXT_CLR,
                             tickfont=dict(size=10)),
            bgcolor="rgba(0,0,0,0)",
        )
    )
    return fig


def chart_waterfall(df: pd.DataFrame) -> go.Figure:
    """Chart 21 — Running P/L waterfall (last 15 bets)."""
    df2 = df.sort_values("date").tail(15).copy()

    def _wf_label(r):
        lbl = event_label(r)
        return lbl[:14] + "…" if len(lbl) > 14 else lbl

    df2["label"] = df2.apply(_wf_label, axis=1)

    fig = go.Figure(go.Waterfall(
        x=df2["label"],
        y=df2["actual_winnings"],
        measure=["relative"] * len(df2),
        connector=dict(line=dict(color=GRID_CLR, width=1)),
        increasing=dict(marker=dict(color=WIN_COLOR)),
        decreasing=dict(marker=dict(color=LOSS_COLOR)),
        totals=dict(marker=dict(color=ACCENT)),
        text=[f"${v:+.2f}" for v in df2["actual_winnings"]],
        textposition="outside",
        textfont=dict(size=10, family="DM Mono"),
    ))
    apply_layout(fig, title="🌊 Last 15 Bets — P/L Waterfall", height=420, showlegend=False)
    fig.update_xaxes(tickangle=45, tickfont=dict(size=10), automargin=True)
    return fig


def chart_team_vs_individual(df: pd.DataFrame) -> go.Figure:
    """Chart 22 — Team pool vs individual ROI comparison."""
    groups = MEMBERS + ["Team"]
    rois   = []
    pls    = []
    bets   = []
    for g in groups:
        s = team_summary(df[df["user"] == g]) if g == "Team" else member_stats(df[df["user"] == g], g)
        rois.append(s["roi"])
        pls.append(s["pl"])
        bets.append(s["bets"])

    colors = [MEMBER_COLORS.get(g, ACCENT) for g in groups]

    fig = make_subplots(
        rows=1, cols=2,
        subplot_titles=("ROI %", "P/L ($)"),
    )
    fig.add_trace(go.Bar(
        x=groups, y=rois, name="ROI %",
        marker_color=colors,
        text=[f"{r:+.1f}%" for r in rois],
        textposition="outside",
        showlegend=False,
    ), row=1, col=1)
    fig.add_trace(go.Bar(
        x=groups, y=pls, name="P/L",
        marker_color=colors,
        text=[f"${p:+.2f}" for p in pls],
        textposition="outside",
        showlegend=False,
    ), row=1, col=2)

    fig.add_hline(y=0, row=1, col=1, line_color=GRID_CLR)
    fig.add_hline(y=0, row=1, col=2, line_color=GRID_CLR)
    apply_layout(fig, title="👥 Team Pool vs Individuals", height=340)
    return fig


def chart_stake_distribution(df: pd.DataFrame) -> go.Figure:
    """Chart 23 — Stake distribution box by member."""
    fig = go.Figure()
    for m in MEMBERS + ["Team"]:
        sub = df[df["user"] == m]["stake"]
        fig.add_trace(go.Box(
            y=sub, name=m,
            marker_color=MEMBER_COLORS.get(m, ACCENT),
            boxmean=True,
            line_width=2,
        ))
    apply_layout(fig, title="💵 Stake Distribution by Bettor", height=340)
    fig.update_yaxes(title_text="Stake $")
    return fig


def chart_top_teams(df: pd.DataFrame) -> go.Figure:
    """Chart 24 — Most bet on teams (from event field)."""
    event_col = "event" if "event" in df.columns else None
    teams = []
    if event_col:
        for e in df[event_col].dropna():
            parts = str(e).split(" vs ")
            if len(parts) == 2:
                for t in [parts[0].strip(), parts[1].strip()]:
                    if t.lower() not in ("multiple", "multi", "various", ""):
                        teams.append(t)

    if not teams:
        fig = go.Figure()
        apply_layout(fig, title="⚽ Most Bet-On Teams — no event data", height=300, showlegend=False)
        return fig

    top = pd.Series(teams).value_counts().head(15)

    fig = go.Figure(go.Bar(
        y=top.index[::-1], x=top.values[::-1],
        orientation="h",
        marker_color=OKABE_ITO[1],
        text=top.values[::-1],
        textposition="outside",
        textfont=dict(size=11, family="DM Mono"),
    ))
    apply_layout(fig, title="⚽ Most Bet-On Teams (appearances)", height=max(300, len(top)*32), showlegend=False)
    fig.update_yaxes(tickfont=dict(size=10))
    return fig


def chart_pl_by_selection(df: pd.DataFrame) -> go.Figure:
    """Chart 25 — P/L by selection type (Home/Draw/Away/Yes/No etc)."""
    grp = df.groupby("selection").agg(
        pl=("actual_winnings", "sum"),
        bets=("odds", "count"),
    ).sort_values("pl")
    grp = grp[grp["bets"] >= 3]

    fig = go.Figure(go.Bar(
        y=grp.index, x=grp["pl"],
        orientation="h",
        marker_color=[WIN_COLOR if p >= 0 else LOSS_COLOR for p in grp["pl"]],
        text=[f"${p:+.2f}" for p in grp["pl"]],
        textposition="outside",
        textfont=dict(size=10, family="DM Mono"),
    ))
    fig.add_vline(x=0, line_color=GRID_CLR)
    apply_layout(fig, title="🎯 P/L by Selection (≥3 bets)", height=max(300, len(grp)*32), showlegend=False)
    fig.update_yaxes(tickfont=dict(size=10))
    return fig


def chart_longest_streaks(df: pd.DataFrame) -> go.Figure:
    """Chart 26 — Longest winning and losing streaks per member."""
    def max_streak(sub, target):
        best = cur = 0
        for s in sub.sort_values("date")["status"]:
            if s == target:
                cur += 1
                best = max(best, cur)
            elif s in ("Win", "Loss"):
                cur = 0
        return best

    data = {m: {
        "win_streak":  max_streak(df[df["user"] == m], "Win"),
        "loss_streak": max_streak(df[df["user"] == m], "Loss"),
    } for m in MEMBERS}

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=MEMBERS, y=[data[m]["win_streak"] for m in MEMBERS],
        name="Best Win Streak",
        marker_color=WIN_COLOR,
        text=[data[m]["win_streak"] for m in MEMBERS],
        textposition="outside",
    ))
    fig.add_trace(go.Bar(
        x=MEMBERS, y=[-data[m]["loss_streak"] for m in MEMBERS],
        name="Worst Loss Streak",
        marker_color=LOSS_COLOR,
        text=[f"-{data[m]['loss_streak']}" for m in MEMBERS],
        textposition="outside",
    ))
    fig.add_hline(y=0, line_color=GRID_CLR)
    apply_layout(fig, title="🔥 Win & Loss Streaks", height=320)
    return fig


def chart_ev_proxy(df: pd.DataFrame) -> go.Figure:
    """Chart 27 — EV proxy: implied probability vs win rate per bucket."""
    BUCKET_ORDER = ["<1.40", "1.40–1.69", "1.70–1.99", "2.00–2.49", "2.50–3.49", "3.50+"]
    grp = df[df["status"].isin(["Win", "Loss"])].groupby("odds_bucket").agg(
        wins=("status", lambda x: (x == "Win").sum()),
        bets=("status", "count"),
        avg_odds=("odds", "mean"),
    )
    grp["win_rate"]   = grp["wins"] / grp["bets"] * 100
    grp["implied"]    = 1 / grp["avg_odds"] * 100
    grp["edge"]       = grp["win_rate"] - grp["implied"]
    grp = grp.reindex([b for b in BUCKET_ORDER if b in grp.index])

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=grp.index, y=grp["win_rate"],
        mode="lines+markers", name="Actual Win Rate %",
        line=dict(color=WIN_COLOR, width=3),
        marker=dict(size=10, symbol="circle"),
    ))
    fig.add_trace(go.Scatter(
        x=grp.index, y=grp["implied"],
        mode="lines+markers", name="Implied Win Rate %",
        line=dict(color=LOSS_COLOR, width=2, dash="dash"),
        marker=dict(size=8, symbol="diamond"),
    ))
    apply_layout(fig, title="📐 Edge Proxy — Actual vs Implied Win Rate", height=340)
    return fig


def chart_year_on_year(df: pd.DataFrame) -> go.Figure:
    """Chart 28 — Year-on-year P/L comparison (2024/25/26)."""
    df2 = df.copy()
    df2["year"] = df2["date"].dt.year
    grp = df2.groupby("year").agg(
        pl=("actual_winnings", "sum"),
        bets=("odds", "count"),
        roi=("actual_winnings", lambda x: x.sum() / df2.loc[x.index, "stake"].sum() * 100),
    ).reset_index()

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Bar(
        x=grp["year"].astype(str), y=grp["pl"],
        name="P/L ($)",
        marker_color=[WIN_COLOR if p >= 0 else LOSS_COLOR for p in grp["pl"]],
        text=[f"${p:+.2f}" for p in grp["pl"]],
        textposition="outside",
    ), secondary_y=False)
    fig.add_trace(go.Scatter(
        x=grp["year"].astype(str), y=grp["bets"],
        name="Bet Count",
        mode="lines+markers",
        line=dict(color=PUSH_COLOR, width=2, dash="dot"),
        marker=dict(size=8),
    ), secondary_y=True)

    apply_layout(fig, title="📆 Year-on-Year Performance", height=320)
    fig.update_layout(margin=dict(l=6,  r=28, t=52, b=60))
    fig.update_yaxes(secondary_y=False, tickfont=dict(size=11))
    fig.update_yaxes(title_text="Bets", secondary_y=True, showgrid=False,
                     title_font=dict(size=11), tickfont=dict(size=11))
    return fig


def chart_bankroll_by_member_contrib(df: pd.DataFrame, opening: float = 300, bankroll_df: pd.DataFrame = None) -> go.Figure:
    """Chart 29 — Combined bankroll (deposit-aware) + individual P/L lines."""
    bk = (bankroll_df if bankroll_df is not None else df).sort_values("date").copy()
    bk["bankroll"] = opening + bk["actual_winnings"].cumsum()

    fig = go.Figure()

    # Overall bankroll line (deposit-corrected)
    cum_all = bk["bankroll"].values
    fig.add_trace(go.Scatter(
        x=bk["date_str"], y=cum_all,
        mode="lines",
        name="Combined",
        line=dict(color=ACCENT, width=3),
        fill="tozeroy",
        fillcolor="rgba(86,180,233,0.08)",
    ))

    for m in MEMBERS:
        sub = df[df["user"] == m].sort_values("date")
        cum = sub["actual_winnings"].cumsum()
        fig.add_trace(go.Scatter(
            x=sub["date_str"], y=cum,
            mode="lines",
            name=m,
            line=dict(color=MEMBER_COLORS[m], width=2, dash="dash"),
        ))

    fig.add_hline(y=opening, line_dash="dot", line_color=GRID_CLR,
                  annotation_text="Opening Bank")
    apply_layout(fig, title="🏦 Bankroll + Individual Running P/L", height=440)
    return fig


def chart_market_win_rate_vs_roi(df: pd.DataFrame) -> go.Figure:
    """Chart 30 — Scatter: market win rate vs ROI (bubble = bet count)."""
    grp = df.groupby("market").agg(
        wins=("status", lambda x: (x == "Win").sum()),
        bets=("status", lambda x: x.isin(["Win", "Loss"]).sum()),
        pl=("actual_winnings", "sum"),
        staked=("stake", "sum"),
    )
    grp = grp[grp["bets"] >= 3]
    grp["win_rate"] = grp["wins"] / grp["bets"] * 100
    grp["roi"]      = grp["pl"] / grp["staked"] * 100

    fig = px.scatter(
        grp.reset_index(),
        x="win_rate", y="roi",
        size="bets", color="market",
        text="market",
        color_discrete_sequence=OKABE_ITO,
        size_max=40,
    )
    fig.update_traces(textposition="top center", textfont=dict(size=10))
    fig.add_hline(y=0, line_dash="dash", line_color=GRID_CLR)
    fig.add_vline(x=50, line_dash="dash", line_color=GRID_CLR)
    apply_layout(fig, title="🔍 Market: Win Rate vs ROI (bubble = bets)", height=420)
    fig.update_xaxes(title_text="Win%")
    return fig



# ── New charts: Plan items not yet covered ────────────────────────────────────

def chart_member_single_cumulative(df: pd.DataFrame, member: str) -> go.Figure:
    """Per-member cumulative P/L line — cleaner individual view."""
    sub = df[df["user"] == member].sort_values("date").copy()
    sub["cum"] = sub["actual_winnings"].cumsum()

    color = MEMBER_COLORS.get(member, ACCENT)
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=sub["date_str"], y=sub["cum"],
        mode="lines+markers",
        line=dict(color=color, width=3),
        marker=dict(
            size=8,
            color=[WIN_COLOR if v >= 0 else LOSS_COLOR for v in sub["actual_winnings"]],
            symbol=["circle" if v >= 0 else "triangle-up" for v in sub["actual_winnings"]],
            line=dict(color=color, width=1),
        ),
        name=member,
        hovertemplate="<b>%{x}</b><br>Running P/L: $%{y:.2f}<extra></extra>",
    ))
    fig.add_hline(y=0, line_dash="dash", line_color=GRID_CLR)
    # Value in title — avoids annotation stealing right-side space
    final = sub["cum"].iloc[-1] if len(sub) else 0
    apply_layout(fig, title=f"📈 {member}  ${final:+.2f}", height=340, showlegend=False)
    return fig


def chart_member_odds_scatter(df: pd.DataFrame, member: str) -> go.Figure:
    """Scatter: odds vs actual winnings, size=stake, color=market."""
    sub = df[(df["user"] == member) & df["status"].isin(["Win", "Loss"])].copy()
    if sub.empty:
        fig = go.Figure()
        apply_layout(fig, title=f"🎯 {member} — Odds vs Outcome (no data)", height=360, showlegend=False)
        return fig

    markets = sub["market"].unique().tolist()
    color_map = {m: OKABE_ITO[i % len(OKABE_ITO)] for i, m in enumerate(markets)}

    fig = go.Figure()
    for mkt in markets:
        msub = sub[sub["market"] == mkt]
        fig.add_trace(go.Scatter(
            x=msub["odds"],
            y=msub["actual_winnings"],
            mode="markers",
            name=mkt,
            marker=dict(
                size=msub["stake"].clip(lower=1).apply(lambda s: max(8, min(30, s * 2.5))),
                color=color_map[mkt],
                opacity=0.75,
                symbol=["circle" if v >= 0 else "triangle-up" for v in msub["actual_winnings"]],
                line=dict(color="rgba(0,0,0,0.3)", width=1),
            ),
            hovertemplate=(
                "<b>%{customdata}</b><br>"
                "Odds: %{x:.2f}<br>P/L: $%{y:.2f}<extra></extra>"
            ),
            customdata=(msub["event"] if "event" in msub.columns else msub["selection"]).fillna("?").values,
        ))
    fig.add_hline(y=0, line_color=GRID_CLR, line_dash="dash")
    apply_layout(fig, title=f"🎯 {member} — Odds vs P/L (size = stake)", height=380)
    fig.update_xaxes(title_text="Odds")
    return fig


def chart_monthly_volatility(df: pd.DataFrame) -> go.Figure:
    """Monthly standard deviation of returns — who's riding the variance train."""
    monthly = df.groupby("month")["actual_winnings"].agg(
        std="std", count="count", mean="mean"
    ).reset_index()
    monthly = monthly[monthly["count"] >= 3].copy()

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Bar(
        x=monthly["month"], y=monthly["std"],
        name="Std Dev ($)",
        marker_color=OKABE_ITO[4],
        opacity=0.8,
    ), secondary_y=False)
    fig.add_trace(go.Scatter(
        x=monthly["month"], y=monthly["mean"],
        mode="lines+markers",
        name="Avg P/L per bet ($)",
        line=dict(color=WIN_COLOR, width=2),
        marker=dict(
            size=8,
            color=[WIN_COLOR if v >= 0 else LOSS_COLOR for v in monthly["mean"]],
            symbol=["circle" if v >= 0 else "triangle-up" for v in monthly["mean"]],
        ),
    ), secondary_y=True)
    apply_layout(fig, title="📊 Monthly Volatility (std dev of returns)", height=340)
    fig.update_layout(margin=dict(l=6,  r=28, t=52, b=60))
    fig.update_yaxes(secondary_y=False, gridcolor=GRID_CLR, tickfont=dict(size=11))
    fig.update_yaxes(title_text="Avg P/L", secondary_y=True, showgrid=False,
                     title_font=dict(size=11), tickfont=dict(size=11))
    return fig


def chart_longshot_vs_fav(df: pd.DataFrame) -> go.Figure:
    """Long-shot (<2.0) vs Value (2.0–3.5) vs Long-shot (3.5+) performance."""
    def tier(o):
        if o < 2.0:  return "Favourite (<2.0)"
        elif o < 3.5: return "Value (2.0–3.49)"
        else:         return "Long-shot (3.5+)"

    d = df[df["status"].isin(["Win", "Loss"])].copy()
    d["tier"] = d["odds"].apply(tier)
    grp = d.groupby("tier").agg(
        bets=("odds", "count"),
        wins=("status", lambda x: (x == "Win").sum()),
        pl=("actual_winnings", "sum"),
        staked=("stake", "sum"),
    )
    grp["roi"]      = grp["pl"] / grp["staked"] * 100
    grp["win_rate"] = grp["wins"] / grp["bets"] * 100
    tier_order = ["Favourite (<2.0)", "Value (2.0–3.49)", "Long-shot (3.5+)"]
    grp = grp.reindex([t for t in tier_order if t in grp.index])

    fig = make_subplots(
        rows=1, cols=2,
        subplot_titles=("ROI % by Tier", "Win Rate % by Tier"),
    )
    fig.add_trace(go.Bar(
        x=grp.index, y=grp["roi"],
        marker_color=[WIN_COLOR if r >= 0 else LOSS_COLOR for r in grp["roi"]],
        text=[f"{r:+.1f}%" for r in grp["roi"]],
        textposition="outside",
        showlegend=False,
    ), row=1, col=1)
    fig.add_trace(go.Bar(
        x=grp.index, y=grp["win_rate"],
        marker_color=OKABE_ITO[2],
        text=[f"{w:.1f}%" for w in grp["win_rate"]],
        textposition="outside",
        showlegend=False,
    ), row=1, col=2)
    fig.add_hline(y=0, row=1, col=1, line_color=GRID_CLR)
    apply_layout(fig, title="🏹 Favourite vs Value vs Long-shot", height=340)
    return fig


def _get_agreed_solo(df: pd.DataFrame):
    """
    Split individual member bets into:
      - agreed_unique: one row per bet where 2+ members picked the same event+selection
      - solo_bets:     bets unique to a single member
    Returns (agreed_unique, solo_bets).
    """
    ind = df[df["user"].isin(MEMBERS) & df["status"].isin(["Win", "Loss", "Push"])].copy()
    # Flag rows where 2+ different members placed identical event+selection
    counts = ind.groupby(["event", "selection"])["user"].transform("nunique")
    ind["agreed"] = counts >= 2
    agreed_unique = (
        ind[ind["agreed"]]
        .groupby(["event", "selection"])
        .first()
        .reset_index()
    )
    solo_bets = ind[~ind["agreed"]].copy()
    return agreed_unique, solo_bets


def chart_voting_success(df: pd.DataFrame) -> go.Figure:
    """
    Agreed picks vs each member's solo picks.
    Layout: 4 rows (Agreed, John, Richard, Xander) × 2 cols (Win Rate gauge | ROI number).
    Vertical stack works on mobile; 4-across at ~90px each does not.
    """
    agreed, solo = _get_agreed_solo(df)

    def stats(sub):
        w  = (sub["status"] == "Win").sum()
        l  = (sub["status"] == "Loss").sum()
        pl = sub["actual_winnings"].sum()
        st = sub["stake"].sum()
        return {
            "win_rate": round(w / (w + l) * 100, 2) if (w + l) > 0 else 0,
            "roi":      round(pl / st * 100, 2) if st > 0 else 0,
            "pl":       round(float(pl), 2),
            "bets":     int(len(sub)),
        }

    ag  = stats(agreed)
    mbr = {m: stats(solo[solo["user"] == m]) for m in MEMBERS}

    entries = [("🤝 Agreed", ag, ACCENT)] + [
        (m, mbr[m], MEMBER_COLORS[m]) for m in MEMBERS
    ]
    n_rows = len(entries)  # 4

    fig = make_subplots(
        rows=n_rows, cols=2,
        column_widths=[0.55, 0.45],
        vertical_spacing=0.06,   # less spacing — height is taller now
        horizontal_spacing=0.04,
        specs=[[{"type": "indicator"}, {"type": "indicator"}]] * n_rows,
    )

    def wr_color(v): return WIN_COLOR if v >= 60 else (PUSH_COLOR if v >= 45 else LOSS_COLOR)
    def roi_color(v): return WIN_COLOR if v >= 0 else LOSS_COLOR

    for row_idx, (label, s, color) in enumerate(entries, start=1):
        # Col 1: Win Rate gauge — label colour matches the trace colour
        fig.add_trace(go.Indicator(
            mode="gauge+number",
            value=s["win_rate"],
            title=dict(
                text=f"<b><span style='color:{color}'>{label}</span></b>"
                     f"<span style='color:{TEXT_CLR};font-size:11px'>  Win Rate</span>",
                font=dict(size=13),
            ),
            number=dict(suffix="%", font=dict(size=22, family="DM Mono",
                                              color=wr_color(s["win_rate"])),
                        valueformat=".1f"),
            gauge=dict(
                axis=dict(range=[0, 100], tickcolor=GRID_CLR,
                          tickfont=dict(color=TEXT_CLR, size=8), nticks=5),
                bar=dict(color=color, thickness=0.4),  # member colour = identity
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

        # Col 2: ROI — colour matches the member colour
        fig.add_trace(go.Indicator(
            mode="number",
            value=s["roi"],
            title=dict(
                text=f"<span style='color:{color};font-size:13px'><b>ROI</b></span>"
                     f"<br><span style='font-size:11px;color:{TEXT_CLR}'>"
                     f"P/L ${s['pl']:+.2f} · {s['bets']} bets</span>",
                font=dict(size=13),
            ),
            number=dict(suffix="%", font=dict(size=24, family="DM Mono",
                                              color=roi_color(s["roi"])),
                        valueformat="+.1f"),
        ), row=row_idx, col=2)

    fig.update_layout(
        **_base_layout(margin=dict(l=6, r=6, t=52, b=10), showlegend=False),
        title=dict(text="🗳️ Agreed Picks vs Solo Bets",
                   font=dict(size=14, color=TEXT_CLR), x=0.01),
        height=680,   # taller — phones have long screens, give each row room
    )
    return fig




# ─────────────────────────────────────────────────────────────────────────────
# ANIMATED CHARTS  — true Plotly frame-based animations
# ─────────────────────────────────────────────────────────────────────────────

def _anim_buttons(duration_ms: int = 400, transition_ms: int = 200):
    """Standard Play/Pause updatemenus block — positioned bottom-left, away from zoom toolbar."""
    return [dict(
        type="buttons", showactive=False,
        y=-0.20, x=0.0, xanchor="left", yanchor="top",
        buttons=[
            dict(label="▶  Play", method="animate",
                 args=[None, dict(frame=dict(duration=duration_ms, redraw=True),
                                  fromcurrent=True,
                                  transition=dict(duration=transition_ms, easing="cubic-in-out"))]),
            dict(label="⏸ Pause", method="animate",
                 args=[[None], dict(frame=dict(duration=0, redraw=False), mode="immediate")]),
        ],
        font=dict(color=TEXT_CLR, size=13),
        bgcolor="#16213e", bordercolor=GRID_CLR, borderwidth=1,
    )]


def _anim_slider(labels, duration_ms=400, transition_ms=200, prefix=""):
    """Standard frame slider — sits below the play button."""
    return [dict(
        steps=[dict(
            method="animate",
            args=[[lbl], dict(mode="immediate",
                              frame=dict(duration=duration_ms, redraw=True),
                              transition=dict(duration=transition_ms))],
            label=str(lbl),
        ) for lbl in labels],
        active=0, y=-0.12, len=1.0, x=0,
        currentvalue=dict(
            prefix=prefix + " ", font=dict(color=TEXT_CLR, size=11), xanchor="center",
        ),
        font=dict(color=TEXT_CLR, size=9),
        bgcolor="#16213e", bordercolor=GRID_CLR, tickcolor=GRID_CLR,
        pad=dict(t=10, b=10),
    )]


def chart_anim_bankroll_worm(df: pd.DataFrame, opening: float = 300,
                              bankroll_df: pd.DataFrame = None) -> go.Figure:
    """
    Animated Chart A — Bankroll worm: the line grows bet by bet.
    Each frame reveals one more point. Play button + slider.
    """
    src_df = (bankroll_df if bankroll_df is not None else df).sort_values("date").copy()
    src_df["bankroll"]  = opening + src_df["actual_winnings"].cumsum()
    # Use string dates to prevent Plotly showing time component on axis
    if "date_str" not in src_df.columns:
        src_df["date_str"] = src_df["date"].dt.strftime("%Y-%m-%d")
    src_df["label"]    = src_df["date"].astype(str).str[:10]

    n = len(src_df)
    frames = []
    for i in range(1, n + 1):
        sub = src_df.iloc[:i]
        col = WIN_COLOR if sub["bankroll"].iloc[-1] >= opening else LOSS_COLOR
        frames.append(go.Frame(
            name=str(i),
            data=[
                go.Scatter(                          # worm line — use date_str (plain string)
                    x=sub["date_str"].tolist(), y=sub["bankroll"].tolist(),
                    mode="lines",
                    line=dict(color=ACCENT, width=3),
                    showlegend=False,
                ),
                go.Scatter(                          # moving dot
                    x=[sub["date_str"].iloc[-1]],
                    y=[sub["bankroll"].iloc[-1]],
                    mode="markers",
                    marker=dict(size=12, color=col,
                                symbol="circle",
                                line=dict(color="white", width=2)),
                    showlegend=False,
                ),
            ],
        ))

    # Pre-compute full x/y range — lock axis from the start so it never expands frame-by-frame
    all_dates_str = src_df["date_str"].tolist()
    all_bankroll  = src_df["bankroll"].tolist()
    y_pad   = (max(all_bankroll) - min(all_bankroll)) * 0.12 + 5
    y_range_a = [min(all_bankroll) - y_pad, max(all_bankroll) + y_pad]

    fig = go.Figure(
        data=[
            go.Scatter(x=src_df["date_str"].iloc[:1], y=src_df["bankroll"].iloc[:1],
                       mode="lines", line=dict(color=ACCENT, width=3), showlegend=False),
            go.Scatter(x=src_df["date_str"].iloc[:1], y=src_df["bankroll"].iloc[:1],
                       mode="markers", marker=dict(size=12, color=ACCENT,
                       line=dict(color="white", width=2)), showlegend=False),
        ],
        frames=frames,
    )
    fig.add_hline(y=opening, line_dash="dash", line_color=GRID_CLR,
                  annotation_text=f"Opening ${opening:.0f}",
                  annotation_font_color=PUSH_COLOR)
    fig.update_layout(
        updatemenus=_anim_buttons(duration_ms=60, transition_ms=30),
        sliders=_anim_slider(
            list(range(1, n + 1)), duration_ms=60, transition_ms=30, prefix="Bet #"
        ),
        xaxis=dict(
            gridcolor=GRID_CLR, tickangle=45,
            range=[all_dates_str[0], all_dates_str[-1]],
            autorange=False,
        ),
        yaxis=dict(gridcolor=GRID_CLR, range=y_range_a, autorange=False),
    )
    apply_layout(fig, title="📈 Bankroll Worm — every bet adds one dot", height=500, showlegend=False)
    fig.update_layout(margin=dict(l=6,  r=6,  t=52, b=130))
    return fig


def chart_anim_member_worm(df: pd.DataFrame) -> go.Figure:
    """
    B — Member P/L worm race. Three lines grow one frame per unique bet-date.
    Fixed at exactly 6 traces (3 lines + 3 dots) in base AND every frame.
    Animation controls set last so nothing clobbers them.
    """
    ind = df[df["user"].isin(MEMBERS)].sort_values("date").copy()
    all_dates = sorted(ind["date"].unique())
    running   = {m: 0.0 for m in MEMBERS}
    snapshots = []
    for d in all_dates:
        for _, row in ind[ind["date"] == d].iterrows():
            running[row["user"]] += row["actual_winnings"]
        snapshots.append({"date": str(d)[:10], **{m: round(running[m], 2) for m in MEMBERS}})
    snaps = pd.DataFrame(snapshots)   # date is now a plain string → no dtype surprises
    n = len(snaps)

    all_vals = snaps[MEMBERS].values.flatten()
    pad = (all_vals.max() - all_vals.min()) * 0.20 + 3
    y_range = [float(all_vals.min()) - pad, float(all_vals.max()) + pad]

    def make_traces(sub):
        """Always returns exactly 6 traces in fixed order."""
        traces = []
        for m in MEMBERS:                          # 3 line traces
            traces.append(go.Scatter(
                x=sub["date"].tolist(), y=sub[m].tolist(),
                mode="lines", line=dict(color=MEMBER_COLORS[m], width=3),
                name=m, legendgroup=m,
            ))
        for m in MEMBERS:                          # 3 dot+label traces
            traces.append(go.Scatter(
                x=[sub["date"].iloc[-1]], y=[sub[m].iloc[-1]],
                mode="markers+text",
                marker=dict(size=12, color=MEMBER_COLORS[m],
                            line=dict(color="white", width=2)),
                text=[f"${sub[m].iloc[-1]:+.1f}"],
                textposition="top right",
                textfont=dict(color=MEMBER_COLORS[m], size=11, family="DM Mono"),
                showlegend=False, legendgroup=m,
            ))
        return traces

    frame_labels = snaps["date"].tolist()
    frames = [
        go.Frame(
            name=frame_labels[i],
            data=make_traces(snaps.iloc[:i + 1]),
        )
        for i in range(n)
    ]

    # Lock x to the full date range up front
    all_snap_dates = snaps["date"].tolist()

    fig = go.Figure(data=make_traces(snaps.iloc[:1]), frames=frames)
    fig.add_shape(type="line", x0=0, x1=1, xref="paper",
                  y0=0, y1=0, yref="y",
                  line=dict(color=GRID_CLR, dash="dash", width=1))
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="'DM Mono','Courier New',monospace", size=13, color=TEXT_CLR),
        margin=dict(l=6,  r=6,  t=60, b=130),
        legend=dict(bgcolor="rgba(0,0,0,0.3)", bordercolor=GRID_CLR, borderwidth=1,
                    orientation="h", yanchor="top", y=-0.28, xanchor="center", x=0.5),
        title=dict(text="🏎️ Member P/L Worm Race — press ▶ Play",
                   font=dict(size=14, color=TEXT_CLR), x=0.01),
        height=520,
        xaxis=dict(
            gridcolor=GRID_CLR, tickangle=45, tickfont=dict(size=10), automargin=True,
            range=[all_snap_dates[0], all_snap_dates[-1]],
            autorange=False),
        yaxis=dict(gridcolor=GRID_CLR, range=y_range, autorange=False),
        updatemenus=_anim_buttons(duration_ms=280, transition_ms=160),
        sliders=_anim_slider(frame_labels, 280, 160, "→"),
    )
    return fig


def chart_anim_monthly_roi_build(df: pd.DataFrame) -> go.Figure:
    """
    C — Monthly ROI bars revealed one at a time.
    Single go.Bar trace with all x pre-set. Animate y+colors only.
    This is the only approach that guarantees 1 trace in every frame.
    """
    monthly = df.groupby("month").agg(
        pl=("actual_winnings", "sum"), staked=("stake", "sum"),
    ).reset_index()
    monthly["roi"] = (monthly["pl"] / monthly["staked"] * 100).round(1)
    months   = monthly["month"].tolist()
    roi_vals = monthly["roi"].tolist()
    n        = len(months)
    roi_min, roi_max = min(roi_vals), max(roi_vals)
    pad    = (roi_max - roi_min) * 0.22 + 8
    y_range = [roi_min - pad, roi_max + pad]

    def make_frame_data(up_to_i):
        ys     = [roi_vals[j] if j <= up_to_i else 0.0 for j in range(n)]
        # Future bars are transparent — but still present so all x categories register
        colors = [WIN_COLOR if roi_vals[j] >= 0 else LOSS_COLOR
                  if j <= up_to_i else "rgba(26,26,46,0)" for j in range(n)]
        texts  = [f"{roi_vals[j]:+.1f}%" if j <= up_to_i else "" for j in range(n)]
        return [go.Bar(
            x=months, y=ys,           # ALL months always present — keeps axis fully sized
            marker_color=colors,
            text=texts,
            textposition="outside",
            textfont=dict(size=11, family="DM Mono", color=TEXT_CLR),
        )]

    frames = [
        go.Frame(
            name=months[i],
            data=make_frame_data(i),
            layout=go.Layout(
                yaxis=dict(range=y_range, autorange=False),
                xaxis=dict(categoryorder="array", categoryarray=months,
                           range=[-0.5, len(months) - 0.5], autorange=False),
            ),
        )
        for i in range(n)
    ]

    fig = go.Figure(data=make_frame_data(0), frames=frames)
    fig.add_shape(type="line", x0=0, x1=1, xref="paper", y0=0, y1=0, yref="y",
                  line=dict(color=GRID_CLR, width=1))
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="'DM Mono','Courier New',monospace", size=13, color=TEXT_CLR),
        margin=dict(l=6,  r=6,  t=60, b=130),
        showlegend=False,
        title=dict(text="📅 Monthly ROI — building up month by month",
                   font=dict(size=14, color=TEXT_CLR), x=0.01),
        height=500,
        # Lock x to full month range from frame 0 — prevents axis expanding mid-animation
        xaxis=dict(gridcolor=GRID_CLR, tickangle=45, tickfont=dict(size=10), automargin=True,
                   categoryorder="array", categoryarray=months,
                   range=[-0.5, len(months) - 0.5], autorange=False),
        yaxis=dict(gridcolor=GRID_CLR, title_text="ROI%",
                   range=y_range, autorange=False),
        updatemenus=_anim_buttons(duration_ms=550, transition_ms=300),
        sliders=_anim_slider(months, 550, 300, "→"),
    )
    return fig


def chart_anim_market_worm(df: pd.DataFrame) -> go.Figure:
    """
    D — Market P/L worm race. 6 go.Scatter traces, one per market.
    All x values pre-set in every frame. Animate y values.
    month column must come from df (already has normalised market names).
    """
    MULTI_PATS = ["accumulator", "multi", "parlay", "fa cup multi", "round"]
    def norm_mkt(m):
        if pd.isna(m): return m
        ml = str(m).lower().strip()
        return "Multi" if any(p in ml for p in MULTI_PATS) else str(m).strip()

    df2 = df.copy()
    df2["market"] = df2["market"].apply(norm_mkt)
    top_mkts = (
        df2.groupby("market")["actual_winnings"]
        .sum().abs().nlargest(6).index.tolist()
    )
    df3     = df2[df2["market"].isin(top_mkts)].copy()
    months  = sorted(df3["month"].unique())
    n_mo    = len(months)
    colors  = {mkt: OKABE_ITO[i % len(OKABE_ITO)] for i, mkt in enumerate(top_mkts)}

    # Build full cumulative snapshot for all months
    running = {mkt: 0.0 for mkt in top_mkts}
    snaps   = []
    for mo in months:
        mo_data = df3[df3["month"] == mo]
        for mkt in top_mkts:
            running[mkt] += mo_data[mo_data["market"] == mkt]["actual_winnings"].sum()
        snaps.append({"month": mo, **{mkt: round(running[mkt], 2) for mkt in top_mkts}})
    snaps_df = pd.DataFrame(snaps)

    all_vals = snaps_df[top_mkts].values.flatten()
    y_min = float(all_vals.min())
    y_max = float(all_vals.max())
    pad   = (y_max - y_min) * 0.18 + 2
    y_range = [y_min - pad, y_max + pad]

    def make_frame_data(up_to_i):
        """6 Scatter traces — all x pre-set, y revealed up to frame i."""
        sub = snaps_df.iloc[:up_to_i + 1]
        traces = []
        for mkt in top_mkts:
            col = colors[mkt]
            traces.append(go.Scatter(
                x=sub["month"].tolist(),
                y=sub[mkt].tolist(),
                mode="lines+markers",
                line=dict(color=col, width=2.5),
                marker=dict(size=5, color=col),
                name=mkt,
            ))
        return traces

    frames = [
        go.Frame(
            name=months[i],
            data=make_frame_data(i),
            layout=go.Layout(
                yaxis=dict(range=y_range, autorange=False),
                xaxis=dict(categoryorder="array", categoryarray=months,
                           range=[-0.5, len(months) - 0.5], autorange=False),
            ),
        )
        for i in range(n_mo)
    ]

    fig = go.Figure(data=make_frame_data(0), frames=frames)
    fig.add_shape(type="line", x0=0, x1=1, xref="paper", y0=0, y1=0, yref="y",
                  line=dict(color=GRID_CLR, dash="dash", width=1))
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="'DM Mono','Courier New',monospace", size=13, color=TEXT_CLR),
        margin=dict(l=6,  r=6,  t=60, b=130),
        legend=dict(bgcolor="rgba(0,0,0,0.3)", bordercolor=GRID_CLR, borderwidth=1,
                    title_text="Market", orientation="h", yanchor="top",
                    y=-0.28, xanchor="center", x=0.5),
        title=dict(text="📊 Market P/L Worm Race — which one drags you down?",
                   font=dict(size=14, color=TEXT_CLR), x=0.01),
        height=560,
        # Lock x to full month range from frame 0 — prevents axis expanding mid-animation
        xaxis=dict(gridcolor=GRID_CLR, tickangle=45, tickfont=dict(size=10), automargin=True,
                   categoryorder="array", categoryarray=months,
                   range=[-0.5, len(months) - 0.5], autorange=False),
        yaxis=dict(gridcolor=GRID_CLR, range=y_range, autorange=False),
        updatemenus=_anim_buttons(duration_ms=500, transition_ms=280),
        sliders=_anim_slider(months, 500, 280, "→"),
    )
    return fig


def chart_anim_odds_scatter_race(df: pd.DataFrame) -> go.Figure:
    """
    E — Every bet revealed in date order. X=odds, Y=P/L, size=stake, color=market.
    FIX: always emit ALL market traces in every frame (empty arrays for unseen markets)
    so Plotly trace-count is constant and animation works correctly.
    """
    closed  = df[df["status"].isin(["Win", "Loss"])].sort_values("date").copy()
    if closed.empty:
        fig = go.Figure()
        fig.update_layout(title="No closed bets", height=400)
        return fig

    all_mkts  = sorted(closed["market"].unique().tolist())
    color_map = {mkt: OKABE_ITO[i % len(OKABE_ITO)] for i, mkt in enumerate(all_mkts)}

    def make_traces(sub):
        """One trace per market — always all markets, empty arrays if none yet."""
        traces = []
        for mkt in all_mkts:
            msub = sub[sub["market"] == mkt]
            traces.append(go.Scatter(
                x=msub["odds"].tolist(),
                y=msub["actual_winnings"].tolist(),
                mode="markers",
                name=mkt,
                marker=dict(
                    size=[max(8, min(28, s * 2.2)) for s in msub["stake"].tolist()] if len(msub) else [],
                    color=color_map[mkt],
                    opacity=0.85,
                    symbol=["circle" if v >= 0 else "triangle-up"
                            for v in msub["actual_winnings"].tolist()],
                    line=dict(color="rgba(255,255,255,0.25)", width=1),
                ),
                hovertemplate="Odds:%{x:.2f} P/L:$%{y:.2f}<extra>" + mkt + "</extra>",
            ))
        return traces

    n = len(closed)
    # Sample frames to keep it snappy: every bet but skip duplicates on same date
    frame_indices = list(range(n))
    frame_labels  = [f"#{i+1} {str(closed.iloc[i]['date'])[:10]}" for i in frame_indices]

    frames = [
        go.Frame(
            name=frame_labels[i],
            data=make_traces(closed.iloc[:i + 1]),
            layout=go.Layout(
                title_text=(
                    f"Bet #{i+1}  "
                    f"{'✅' if closed.iloc[i]['status']=='Win' else '❌'}  "
                    f"{str(closed.iloc[i].get('selection','?'))[:25]}  "
                    f"@ {closed.iloc[i]['odds']:.2f}"
                )
            ),
        )
        for i in frame_indices
    ]

    x_min, x_max = float(closed["odds"].min()), float(closed["odds"].max())
    y_min, y_max = float(closed["actual_winnings"].min()), float(closed["actual_winnings"].max())
    x_pad = (x_max - x_min) * 0.05 + 0.1
    y_pad = (y_max - y_min) * 0.08 + 1

    fig = go.Figure(data=make_traces(closed.iloc[:1]), frames=frames)
    fig.add_shape(type="line", x0=0, x1=1, xref="paper", y0=0, y1=0, yref="y",
                  line=dict(color=GRID_CLR, dash="dash", width=1))
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="'DM Mono','Courier New',monospace", size=12, color=TEXT_CLR),
        margin=dict(l=6,  r=6,  t=60, b=130),
        legend=dict(bgcolor="rgba(0,0,0,0.3)", bordercolor=GRID_CLR, borderwidth=1,
                    font=dict(size=10), orientation="h", yanchor="top",
                    y=-0.28, xanchor="center", x=0.5),
        title=dict(text="🌌 Every Bet Revealed — the ledger comes alive",
                   font=dict(size=14, color=TEXT_CLR), x=0.01),
        height=560,
        xaxis=dict(title_text="Odds", range=[x_min - x_pad, x_max + x_pad],
                   gridcolor=GRID_CLR, tickfont=dict(size=10)),
        yaxis=dict(range=[y_min - y_pad, y_max + y_pad],
                   gridcolor=GRID_CLR),
        updatemenus=_anim_buttons(duration_ms=80, transition_ms=40),
        sliders=_anim_slider(frame_labels, 80, 40, ""),
    )
    return fig


def chart_anim_win_rate_evolution(df: pd.DataFrame) -> go.Figure:
    """
    F — 10-bet rolling win rate per member, animated by date.
    Always 6 traces (3 lines + 3 dots). X-axis locked to full date range
    so it never starts too small or jumps.
    """
    fig_data = {}
    for m in MEMBERS:
        sub = df[df["user"] == m].sort_values("date").copy()
        sub = sub[sub["status"].isin(["Win", "Loss"])].reset_index(drop=True)
        sub["roll_wr"] = (
            sub["status"].eq("Win").rolling(10, min_periods=5).mean() * 100
        )
        sub = sub.dropna(subset=["roll_wr"]).reset_index(drop=True)
        # Convert to plain date string to prevent time component on axis
        sub["date"] = sub["date"].dt.strftime("%Y-%m-%d")
        fig_data[m] = sub

    # Full x extent as strings
    full_x_min = min(fig_data[m]["date"].min() for m in MEMBERS if len(fig_data[m]))
    full_x_max = max(fig_data[m]["date"].max() for m in MEMBERS if len(fig_data[m]))
    # Add a small buffer so dots/labels aren't clipped
    _buf   = pd.Timedelta(days=10)
    x_range = [
        (pd.to_datetime(full_x_min) - _buf).strftime("%Y-%m-%d"),
        (pd.to_datetime(full_x_max) + _buf).strftime("%Y-%m-%d"),
    ]

    # Only frames where at least one member has rolling data
    all_dates = sorted(set(
        d for m in MEMBERS for d in fig_data[m]["date"].tolist()
    ))
    all_dates = [d for d in all_dates
                 if any(len(fig_data[m][fig_data[m]["date"] <= d]) > 0 for m in MEMBERS)]

    if not all_dates:
        fig = go.Figure()
        fig.update_layout(title="Not enough data", height=400)
        return fig

    def make_traces(cutoff):
        """Always 6 traces: 3 lines first, 3 dots second."""
        traces = []
        for m in MEMBERS:
            sub = fig_data[m][fig_data[m]["date"] <= cutoff]
            col = MEMBER_COLORS[m]
            traces.append(go.Scatter(
                x=sub["date"].tolist(),
                y=sub["roll_wr"].tolist(),
                mode="lines",
                line=dict(color=col, width=3),
                name=m,
            ))
        for m in MEMBERS:
            sub = fig_data[m][fig_data[m]["date"] <= cutoff]
            col = MEMBER_COLORS[m]
            if len(sub):
                x_dot = [sub["date"].iloc[-1]]
                y_dot = [sub["roll_wr"].iloc[-1]]
                txt   = [f"{sub['roll_wr'].iloc[-1]:.0f}%"]
            else:
                x_dot, y_dot, txt = [], [], []
            traces.append(go.Scatter(
                x=x_dot, y=y_dot,
                mode="markers+text",
                marker=dict(size=12, color=col, line=dict(color="white", width=2)),
                text=txt,
                textposition="top right",
                textfont=dict(color=col, size=11, family="DM Mono"),
                showlegend=False,
            ))
        return traces

    frame_labels = [str(d)[:10] for d in all_dates]
    frames = [
        go.Frame(
            name=frame_labels[i],
            data=make_traces(all_dates[i]),
            layout=go.Layout(
                xaxis=dict(range=x_range),
                yaxis=dict(range=[0, 108]),
            ),
        )
        for i in range(len(all_dates))
    ]

    fig = go.Figure(data=make_traces(all_dates[0]), frames=frames)
    fig.add_shape(type="line", x0=0, x1=1, xref="paper",
                  y0=50, y1=50, yref="y",
                  line=dict(color=PUSH_COLOR, dash="dash", width=1))
    fig.add_annotation(x=1, y=50, xref="paper", yref="y",
                       text=" 50% coin flip", showarrow=False, xanchor="left",
                       font=dict(color=PUSH_COLOR, size=10, family="DM Mono"))
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="'DM Mono','Courier New',monospace", size=13, color=TEXT_CLR),
        margin=dict(l=6,  r=6,  t=60, b=130),
        legend=dict(bgcolor="rgba(0,0,0,0.3)", bordercolor=GRID_CLR, borderwidth=1,
                    orientation="h", yanchor="top", y=-0.28, xanchor="center", x=0.5),
        title=dict(text="🎯 10-Bet Rolling Win Rate — who's hot right now?",
                   font=dict(size=14, color=TEXT_CLR), x=0.01),
        height=520,
        xaxis=dict(range=x_range, gridcolor=GRID_CLR, tickangle=45),
        yaxis=dict(range=[0, 108], gridcolor=GRID_CLR, title_text="Win%"),
        updatemenus=_anim_buttons(duration_ms=300, transition_ms=150),
        sliders=_anim_slider(frame_labels, 300, 150, "→"),
    )
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# MAIN APP
# ─────────────────────────────────────────────────────────────────────────────
def main():
    with st.spinner("Loading ledger…"):
        df_raw, df_roi, df_free, df_pending, kpis = load_data()

    df, bankroll_df = get_enriched(df_raw)
    team_df = df[df["user"] == "Team"]
    ind_df  = df[df["user"].isin(MEMBERS)]
    opening = float(core.OPENING_BANK) if hasattr(core, "OPENING_BANK") else 300.0

    # ── Header ──────────────────────────────────────────────────────────────
    cur_pl = df["actual_winnings"].sum()
    roi    = cur_pl / df["stake"].sum() * 100 if df["stake"].sum() > 0 else 0
    _pl_col  = WIN_COLOR if cur_pl >= 0 else LOSS_COLOR
    _roi_col = WIN_COLOR if roi    >= 0 else LOSS_COLOR
    st.markdown(
        f'''<div style="
            display:flex; flex-wrap:wrap; align-items:center;
            justify-content:space-between; gap:8px; margin-bottom:4px;">
          <div style="font-family:Space Grotesk,sans-serif;
                      font-size:1.9rem;font-weight:700;color:#e0e0f0;">
            Xanderdu 🏆
          </div>
          <div style="font-family:DM Mono,monospace;font-size:1.05rem;
                      text-align:right;white-space:nowrap;">
            <span style="color:#8888aa">P/L</span>&nbsp;
            <span style="color:{_pl_col};font-size:1.3rem;font-weight:600">${cur_pl:+.2f}</span>
            &nbsp;&nbsp;
            <span style="color:#8888aa">ROI</span>&nbsp;
            <span style="color:{_roi_col}">{roi:+.1f}%</span>
          </div>
        </div>''',
        unsafe_allow_html=True,
    )

    st.divider()

    # ── Tab structure ────────────────────────────────────────────────────────
    t_home, t_people, t_markets, t_extremes, t_advanced, t_anim, t_inbox, t_ledger = st.tabs([
        "🏠 Home", "👤 People", "📈 Markets", "🎯 Extremes", "🔬 Advanced", "🎬 Animated", "📥 Inbox", "📒 Ledger"
    ])


    # ═══════════════════════════════════════════════════════════════════════
    # 🏠 HOME
    # ═══════════════════════════════════════════════════════════════════════
    with t_home:
        # KPI row 1
        total_bets = len(df)
        wins   = (df["status"] == "Win").sum()
        losses = (df["status"] == "Loss").sum()
        pushes = (df["status"] == "Push").sum()
        wr     = wins / (wins + losses) * 100 if (wins + losses) > 0 else 0
        staked = df["stake"].sum()
        _pl_color = WIN_COLOR if cur_pl >= 0 else LOSS_COLOR
        _roi_color = WIN_COLOR if roi >= 0 else LOSS_COLOR
        _r1c1, _r1c2 = cols(2)
        with _r1c1:
            stat_card("💰 Total P/L", f"${cur_pl:+.2f}", color=_pl_color)
        with _r1c2:
            stat_card("📊 Overall ROI", f"{roi:+.1f}%", color=_roi_color)
        _r2c1, _r2c2 = cols(2)
        with _r2c1:
            stat_card("🎯 Win Rate", f"{wr:.1f}%", sub=f"{wins}W / {losses}L / {pushes}P")
        with _r2c2:
            stat_card("🎲 Total Bets", str(total_bets), sub=f"${staked:.0f} staked")

        # Roast line
        worst = worst_bet(df)
        roast(f'Worst bet: {event_label(worst)} @ {worst["odds"]:.2f} — ${worst["actual_winnings"]:.2f}. Exquisite.')

        st.divider()

        # Charts row 1: bankroll + monthly
        ca, cb = cols(2)
        with ca:
            pc(chart_cumulative_bankroll(df, opening, bankroll_df))
        with cb:
            pc(chart_monthly_pl(df))

        # Charts row 2: donut + year-on-year
        cc, cd = cols(2)
        with cc:
            pc(chart_win_loss_donut(df))
        with cd:
            pc(chart_year_on_year(df))

        # Full-width: waterfall last 30
        pc(chart_waterfall(df))


    # ═══════════════════════════════════════════════════════════════════════
    # 👤 PEOPLE
    # ═══════════════════════════════════════════════════════════════════════
    with t_people:
        # Sub-navigation
        view = st.radio(
            "Select View",
            ["🏆 Leaderboard", "👤 John", "👤 Richard", "👤 Xander"],
            horizontal=True, label_visibility="collapsed", key="people_view_radio",
        )
        st.divider()

        if view == "🏆 Leaderboard":
            section("Member Comparison")

            # KPI row per member
            m_cols = cols(3)
            for i, m in enumerate(MEMBERS):
                s = member_stats(df[df["user"] == m], m)
                with m_cols[i]:
                    _c = MEMBER_COLORS[m]
                    _pl_c = WIN_COLOR if s["pl"] >= 0 else LOSS_COLOR
                    stat_card(
                        label=m,
                        value=f'${s["pl"]:+.2f}',
                        sub=f'{s["roi"]:+.1f}% ROI · {s["win_rate"]:.1f}% WR',
                        color=_pl_c,
                        border_color=f"{_c}55",
                    )

            st.write("")
            c1, c2 = cols(2)
            with c1: pc(chart_member_pl_bars(df))
            with c2: pc(chart_member_roi_bars(df))

            c3, c4 = cols(2)
            with c3: pc(chart_member_win_rate(df))
            with c4: pc(chart_member_radar(df))

            pc(chart_member_cumulative(df))
            pc(chart_team_vs_individual(df))
            pc(chart_longest_streaks(df))

        else:
            m = view.replace("👤 ", "")
            mdf = df[df["user"] == m]
            s   = member_stats(mdf, m)
            streak_n, streak_type = compute_streak(mdf)

            # Member KPI strip — 2×2 on mobile
            _mk1, _mk2 = cols(2)
            with _mk1: kpi(f"{m} P/L", f"${s['pl']:+.2f}")
            with _mk2: kpi("ROI", f"{s['roi']:+.1f}%")
            _mk3, _mk4 = cols(2)
            with _mk3: kpi("Win Rate", f"{s['win_rate']:.1f}%", delta=f"{s['wins']}W/{s['losses']}L")
            with _mk4: kpi("Streak", f"{streak_n}× {streak_type}")

            # Roast
            if len(mdf) > 0:
                wb = worst_bet(mdf)
                roast(f"{m}'s finest hour: {event_label(wb)} @ {wb['odds']:.2f} → ${wb['actual_winnings']:.2f}")

            c1, c2 = cols(2)
            with c1: pc(chart_win_loss_donut(mdf, f"{m}'s Record"))
            with c2: pc(chart_member_monthly_pl(df, m))

            pc(chart_member_single_cumulative(df, m))
            pc(chart_member_odds_dist(df, m))
            pc(chart_member_market_breakdown(df, m))
            pc(chart_member_odds_scatter(df, m))


    # ═══════════════════════════════════════════════════════════════════════
    # 📈 MARKETS
    # ═══════════════════════════════════════════════════════════════════════
    with t_markets:
        mkt_view = st.radio(
            "Market View",
            ["📊 Overview", "💀 Multi Curse", "🎲 Odds Analysis", "🌐 Sunburst"],
            horizontal=True, label_visibility="collapsed", key="mkt_view_radio",
        )
        st.divider()

        with st.container():
            if mkt_view == "📊 Overview":
                c1, c2 = cols(2)
                with c1: pc(chart_market_roi_bars(df))
                with c2: pc(chart_competition_roi(df))
                pc(chart_market_win_rate_vs_roi(df))
                pc(chart_pl_by_selection(df))

            elif mkt_view == "💀 Multi Curse":
                pc(chart_accumulator_curse(df))
                multi_pl = df[df["market"] == "Multi"]["actual_winnings"].sum()
                roast(f"Multis have cost the syndicate ${abs(multi_pl):.2f}. The house always wins. THE HOUSE ALWAYS WINS.")

            elif mkt_view == "🎲 Odds Analysis":
                c1, c2 = cols(2)
                with c1: pc(chart_odds_histogram(df))
                with c2: pc(chart_odds_bucket_roi(df))
                pc(chart_ev_proxy(df))
                pc(chart_stake_vs_outcome(df))

            elif mkt_view == "🌐 Sunburst":
                pc(chart_market_sunburst(df))


    # ═══════════════════════════════════════════════════════════════════════
    # 🎯 EXTREMES
    # ═══════════════════════════════════════════════════════════════════════
    with t_extremes:
        section("Hall of Fame (and Shame)")

        best = best_bet(df)
        worst = worst_bet(df)

        bc, wc = cols(2)
        with bc:
            _b_sel = str(best.get("selection", "")).strip()
            stat_card(
                label="🏆 Best Bet Ever",
                value=f'${best["actual_winnings"]:+.2f}',
                sub=f'{event_label(best)}<br>📌 {_b_sel} · {best["odds"]:.2f}x · {best.get("market","?")}<br>{best["user"]} · {str(best["date"])[:10]}',
                color=WIN_COLOR,
                border_color=WIN_COLOR,
            )
        with wc:
            _w_sel = str(worst.get("selection", "")).strip()
            stat_card(
                label="💀 Worst Bet Ever",
                value=f'${worst["actual_winnings"]:+.2f}',
                sub=f'{event_label(worst)}<br>📌 {_w_sel} · {worst["odds"]:.2f}x · {worst.get("market","?")}<br>{worst["user"]} · {str(worst["date"])[:10]}',
                color=LOSS_COLOR,
                border_color=LOSS_COLOR,
            )

        st.write("")

        # Top 10 wins + losses
        section("Top 10 Wins")
        _show_cols = [c for c in ["date", "user", "event", "selection", "market", "odds", "stake", "actual_winnings"] if c in df.columns]
        top_wins = df[df["status"] == "Win"].nlargest(10, "actual_winnings")[_show_cols].copy()
        top_wins["actual_winnings"] = top_wins["actual_winnings"].map("${:+.2f}".format)
        top_wins["stake"] = top_wins["stake"].map("${:.2f}".format)
        st.dataframe(top_wins, use_container_width=True, hide_index=True)

        section("Top 10 Losses")
        top_losses = df[df["status"] == "Loss"].nsmallest(10, "actual_winnings")[_show_cols].copy()
        top_losses["actual_winnings"] = top_losses["actual_winnings"].map("${:+.2f}".format)
        top_losses["stake"] = top_losses["stake"].map("${:.2f}".format)
        st.dataframe(top_losses, use_container_width=True, hide_index=True)

        section("Charts")
        c1, c2 = cols(2)
        with c1: pc(chart_weekday_heatmap(df))
        with c2: pc(chart_stake_distribution(df))
        pc(chart_top_teams(df))

        section("Betting Patterns")
        c1, c2 = cols(2)
        with c1: pc(chart_longshot_vs_fav(df))
        with c2: pc(chart_voting_success(df))
        pc(chart_monthly_volatility(df))


    # ═══════════════════════════════════════════════════════════════════════
    # 🔬 ADVANCED
    # ═══════════════════════════════════════════════════════════════════════
    with t_advanced:
        section("Advanced Analytics")

        pc(chart_roi_rollercoaster(df))
        pc(chart_bankroll_by_member_contrib(df, opening, bankroll_df))

        c1, c2 = cols(2)
        with c1: pc(chart_ev_proxy(df))
        with c2: pc(chart_odds_bucket_roi(df))

        pc(chart_market_win_rate_vs_roi(df))

        # Raw stats table
        section("Full Stats Table")
        grp = df.groupby("market").agg(
            Bets=("odds", "count"),
            Wins=("status", lambda x: (x == "Win").sum()),
            Losses=("status", lambda x: (x == "Loss").sum()),
            Staked=("stake", "sum"),
            PL=("actual_winnings", "sum"),
        ).copy()
        grp["ROI %"] = (grp["PL"] / grp["Staked"] * 100).round(1)
        grp["Win %"] = (grp["Wins"] / (grp["Wins"] + grp["Losses"]) * 100).round(1)
        grp["Staked"] = grp["Staked"].map("${:.2f}".format)
        grp["PL"]     = grp["PL"].map("${:+.2f}".format)
        st.dataframe(grp.sort_values("ROI %", ascending=False), use_container_width=True)

        # 🤖 Betbot
        st.divider()
        section("🤖 Betbot — Ask the Ledger")
        st.caption("Powered by Gemini. Plain English questions about any stat.")
        asker = st.selectbox("Who's asking?", core.SYNDICATE_MEMBERS, key="betbot_asker")
        question = st.text_input("Question", placeholder="What's our ROI on BTTS bets?", key="betbot_q")
        if st.button("Ask", type="primary") and question:
            with st.spinner("Consulting the oracle…"):
                try:
                    reply = core.betbot_query(question, df_roi, asker_name=asker)
                    st.info(reply)
                except Exception as e:
                    st.error(f"Betbot error: {e}")



    # ═══════════════════════════════════════════════════════════════════════
    # 🎬 ANIMATED
    # ═══════════════════════════════════════════════════════════════════════
    with t_anim:
        section("Animated Charts")
        st.caption("All charts use Plotly frame-based animation. Press ▶ Play or drag the slider.")

        st.markdown('<div class="section-header">A — Bankroll Worm</div>', unsafe_allow_html=True)
        st.caption("The bankroll line grows one bet at a time. Watch the Aug 2025 top-up land.")
        pc(chart_anim_bankroll_worm(df, opening, bankroll_df))

        st.markdown('<div class="section-header">B — Member P/L Worm Race</div>', unsafe_allow_html=True)
        st.caption("Three worms crawl through time. John pulls away. Xander does not.")
        pc(chart_anim_member_worm(df))

        st.markdown('<div class="section-header">C — Monthly ROI Building Up</div>', unsafe_allow_html=True)
        st.caption("One bar per month, revealed in order. Green hope, orange despair.")
        pc(chart_anim_monthly_roi_build(df))

        st.markdown('<div class="section-header">D — Market P/L Worm Race</div>', unsafe_allow_html=True)
        st.caption("Six market lines race each other. Spot the exact month Multi went off a cliff.")
        pc(chart_anim_market_worm(df))

        st.markdown('<div class="section-header">E — Every Bet Revealed</div>', unsafe_allow_html=True)
        st.caption("The entire ledger drops one bet at a time. X=odds, Y=P/L, size=stake, color=market.")
        pc(chart_anim_odds_scatter_race(df))

        st.markdown('<div class="section-header">F — Rolling Win Rate Worm</div>', unsafe_allow_html=True)
        st.caption("NEW — 10-bet rolling win rate per member. Who's on form? Who's in a slump? Now animated.")
        pc(chart_anim_win_rate_evolution(df))

    # ═══════════════════════════════════════════════════════════════════════
    # 📥 INBOX
    # ═══════════════════════════════════════════════════════════════════════
    with t_inbox:
        st.subheader("Pending Bets")
        if len(df_pending) == 0:
            st.success("No pending bets — all caught up.")
        else:
            st.info(f"{len(df_pending)} bet(s) awaiting grading.")
            for _, row in df_pending.iterrows():
                with st.expander(
                    f"**{row['event']}** | {row['market']} | {row['selection']} @ {row['odds']:.2f} "
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
        st.subheader("Add a Bet Manually")
        with st.form("add_bet_form", clear_on_submit=True):
            col1, col2 = cols(2)
            with col1:
                user      = st.selectbox("Member", core.SYNDICATE_MEMBERS)
                event     = st.text_input("Event (e.g. Arsenal vs Chelsea)")
                market    = st.selectbox("Market", sorted(core.MARKET_ALIASES.values()))
                selection = st.text_input("Selection")
            with col2:
                odds     = st.number_input("Odds", min_value=1.01, value=1.80, step=0.01, format="%.2f")
                stake    = st.number_input("Stake ($)", min_value=0.0, value=5.0, step=0.5, format="%.2f")
                bet_date = st.date_input("Date")
                status   = st.selectbox("Status", ["Pending", "Win", "Loss", "Push"])
            actual_winnings = 0.0
            if status in ("Win", "Loss", "Push"):
                actual_winnings = st.number_input("Actual winnings ($)", value=0.0, step=0.01, format="%.2f")
            submitted = st.form_submit_button("Add Bet", type="primary", use_container_width=True)
            if submitted:
                if not event or not selection:
                    st.warning("Event and selection are required.")
                else:
                    with st.spinner("Appending to Google Sheets…"):
                        new_uuid = core.append_bet(
                            user=user, event=event, market=market, selection=selection,
                            odds=odds, stake=stake, bet_date=bet_date,
                            status=status, actual_winnings=actual_winnings,
                        )
                    st.success(f"✅ Bet added: {new_uuid}")
                    st.cache_data.clear(); st.rerun()


    # ═══════════════════════════════════════════════════════════════════════
    # 📒 LEDGER
    # ═══════════════════════════════════════════════════════════════════════
    with t_ledger:
        st.subheader("Full Ledger")

        # Build filter options from the normalised df (not df_raw)
        all_users   = sorted(df["user"].dropna().unique().tolist())
        all_markets = sorted(df["market"].dropna().unique().tolist())
        all_years   = sorted(df["date"].dt.year.unique().tolist())

        with st.expander("Filters", expanded=False):
            fc = cols(4)
            with fc[0]:
                f_user = st.multiselect("Member", options=all_users, default=all_users)
            with fc[1]:
                f_market = st.multiselect("Market", options=all_markets, default=all_markets)
            with fc[2]:
                f_status = st.multiselect(
                    "Status",
                    options=["Win", "Loss", "Push", "Void", "Pending", "manual_review"],
                    default=["Win", "Loss", "Push"],
                )
            with fc[3]:
                f_year = st.multiselect("Year", options=all_years, default=all_years)

        mask = (
            df["user"].isin(f_user) &
            df["market"].isin(f_market) &
            df["status"].isin(f_status) &
            df["date"].dt.year.isin(f_year)
        )
        df_filtered = df[mask].copy()
        st.caption(f"Showing {len(df_filtered)} of {len(df)} bets")

        display_cols = [c for c in ["date", "user", "event", "market", "selection",
                                    "odds", "stake", "status", "actual_winnings"] if c in df_filtered.columns]
        ledger_display = df_filtered[display_cols].sort_values("date", ascending=False).copy()
        ledger_display["actual_winnings"] = ledger_display["actual_winnings"].map("${:+.2f}".format)
        ledger_display["stake"]           = ledger_display["stake"].map("${:.2f}".format)
        ledger_display["date"]            = ledger_display["date"].dt.date
        ledger_display.columns = [c.replace("_", " ").title() for c in ledger_display.columns]
        st.dataframe(ledger_display, use_container_width=True, hide_index=True)

        st.divider()
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
