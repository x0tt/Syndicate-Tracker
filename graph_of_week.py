#!/usr/bin/env python3
# coding: utf-8
"""
graph_of_week.py — Syndicate Tracker
=====================================
Selects, renders, and delivers the "Graph of the Week" after the Chronicler report.

Pipeline:
  1. Compute a "week in numbers" data snapshot from the CSV (Python only, fast).
  2. Pass the snapshot to Gemini → it picks the most interesting chart + reason.
  3. Build the chosen Plotly figure using app.py chart functions.
  4. Export to PNG via kaleido (dark background, high-res).
  5. Send the image then the commentary to Telegram.
  6. Record the used chart in cache/last_run.json to avoid repeats.

Preview mode (? preview_graph):
  - Runs the full pipeline but ALWAYS routes to TEST_CHAT_ID, regardless of TEST_MODE.
  - Stores the selection in last_run.json so Wednesday sends the same chart.
  - Safe to call multiple times — if a preview was already generated this week,
    it re-sends the cached selection rather than re-rolling.
"""

import json
import logging
import random
from datetime import date, timedelta
from typing import Optional

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import requests

import syndicate_core as core

log = logging.getLogger('syndicate.gotw')

# ── Constants ─────────────────────────────────────────────────────────────────

REPEAT_WINDOW = 8
EXPORT_WIDTH  = 1200
EXPORT_HEIGHT = 700
EXPORT_SCALE  = 2
EXPORT_BG     = '#1a1a2e'

# Design constants (mirror app.py)
WIN_COLOR  = '#56B4E9'
LOSS_COLOR = '#E69F00'
PUSH_COLOR = '#999999'
ACCENT     = '#56B4E9'
GRID_CLR   = '#2a2a4a'
TEXT_CLR   = '#e0e0f0'
BG_CARD    = '#16213e'
MEMBERS    = ['John', 'Richard', 'Xander']
MEMBER_COLORS = {
    'John':    '#009E73',
    'Richard': '#CC79A7',
    'Xander':  '#D55E00',
    'Team':    '#0072B2',
}

PLOTLY_EXPORT_LAYOUT = dict(
    paper_bgcolor=EXPORT_BG,
    plot_bgcolor=EXPORT_BG,
    font=dict(family="Arial, sans-serif", size=14, color=TEXT_CLR),
    xaxis=dict(gridcolor=GRID_CLR, zerolinecolor=GRID_CLR),
    yaxis=dict(gridcolor=GRID_CLR, zerolinecolor=GRID_CLR),
    margin=dict(l=60, r=40, t=70, b=80),
)

# ── Chart registry ─────────────────────────────────────────────────────────────

CHART_REGISTRY = [
    {
        'id': 'monthly_pl',
        'description': 'Monthly P/L bar chart — profit/loss per calendar month for the whole syndicate.',
    },
    {
        'id': 'cumulative_bankroll',
        'description': 'Bankroll spline — cumulative balance over time, with all-time high and max drawdown annotations.',
    },
    {
        'id': 'roi_by_bet_type',
        'description': 'ROI by bet type — horizontal bar chart showing which bet types (BTTS, Asian Handicap, etc.) have the best and worst ROI.',
    },
    {
        'id': 'member_pl_comparison',
        'description': "Individual P/L comparison — side-by-side bars showing each member's total profit/loss.",
    },
    {
        'id': 'member_roi_comparison',
        'description': "Individual ROI comparison — each member's ROI percentage side by side.",
    },
    {
        'id': 'win_loss_donut',
        'description': 'Win/loss/push donut — overall record showing win rate for the whole syndicate.',
    },
    {
        'id': 'roi_by_competition',
        'description': 'ROI by competition — which leagues/tournaments (EPL, Champions League, etc.) are most profitable.',
    },
    {
        'id': 'odds_bucket_roi',
        'description': 'ROI by odds bucket — profitability split by odds range (favourites vs longshots).',
    },
    {
        'id': 'waterfall_recent',
        'description': 'Recent form waterfall — the last 15 resolved bets shown as a waterfall of wins and losses.',
    },
    {
        'id': 'running_pl_by_member',
        'description': 'Running P/L by member — cumulative profit lines for John, Richard, and Xander over time.',
    },
    {
        'id': 'weekday_pl',
        'description': 'P/L by day of week — which days of the week the syndicate makes or loses money on.',
    },
    {
        'id': 'accumulator_record',
        'description': 'Accumulator (Multi) record — monthly P/L and win/loss split specifically for multi-leg bets.',
    },
]

CHART_IDS = [c['id'] for c in CHART_REGISTRY]


# ── Step 1: Snapshot helpers ──────────────────────────────────────────────────

def _sanitise_for_json(obj):
    """Recursively convert numpy/pandas types to plain Python for json.dumps."""
    if isinstance(obj, dict):
        return {k: _sanitise_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_sanitise_for_json(v) for v in obj]
    elif isinstance(obj, np.integer):
        return int(obj)
    elif isinstance(obj, np.floating):
        return float(obj)
    elif isinstance(obj, pd.Timestamp):
        return str(obj)[:10]
    elif hasattr(obj, 'item'):
        return obj.item()
    return obj


def _odds_bucket(o: float) -> str:
    if o < 1.4:   return '<1.40'
    elif o < 1.7: return '1.40-1.69'
    elif o < 2.0: return '1.70-1.99'
    elif o < 2.5: return '2.00-2.49'
    elif o < 3.5: return '2.50-3.49'
    else:         return '3.50+'


def _member_stats_dict(sub: pd.DataFrame) -> dict:
    wins   = int((sub['status'] == 'Win').sum())
    losses = int((sub['status'] == 'Loss').sum())
    staked = float(sub['stake'].sum())
    pl     = float(pd.to_numeric(sub['actual_winnings'], errors='coerce').fillna(0).sum())
    roi    = round(pl / staked * 100, 2) if staked > 0 else 0.0
    wr     = round(wins / (wins + losses) * 100, 2) if (wins + losses) > 0 else 0.0
    return dict(bets=len(sub), wins=wins, losses=losses,
                staked=round(staked, 2), pl=round(pl, 2),
                roi=roi, win_rate=wr)


def _streak(sub: pd.DataFrame) -> dict:
    """
    Returns two streak measures:
    - resolved: consecutive Win or Loss ignoring Pushes (e.g. '2 Loss')
    - winless:  consecutive non-Win results including Pushes (e.g. '3 winless')
    """
    all_resolved = sub[sub['status'].isin(['Win', 'Loss'])].sort_values('date_dt')
    all_bets     = sub[sub['status'].isin(['Win', 'Loss', 'Push'])].sort_values('date_dt')

    # Resolved streak (Win/Loss only)
    resolved_streak = {'count': 0, 'type': None}
    if not all_resolved.empty:
        last  = all_resolved.iloc[-1]['status']
        count = 0
        for s in reversed(all_resolved['status'].tolist()):
            if s == last: count += 1
            else:         break
        resolved_streak = {'count': count, 'type': last}

    # Winless streak (any non-Win including Push)
    winless_count = 0
    if not all_bets.empty:
        for s in reversed(all_bets['status'].tolist()):
            if s != 'Win': winless_count += 1
            else:          break

    return {
        'resolved_streak_count': resolved_streak['count'],
        'resolved_streak_type':  resolved_streak['type'],
        'winless_streak':        winless_count,
    }


def _selection_snapshot(snapshot: dict) -> dict:
    """Trimmed snapshot for Gemini — drops raw bet rows to keep prompt small."""
    return {k: v for k, v in snapshot.items() if k != 'recent_bets'}


def compute_snapshot(df: pd.DataFrame) -> dict:
    """
    Computes a structured 'week in numbers' dict covering all chart dimensions.
    Pure Python/pandas — no LLM calls.
    """
    log.info('[GOTW] snapshot: filtering working set...')
    banking_mask = (
        df['status'].isin(['Reconciliation', 'Deposit', 'Withdrawal']) |
        (df['user'].astype(str).str.lower() == 'syndicate')
    )
    work = df[~banking_mask & df['status'].isin(['Win', 'Loss', 'Push'])].copy()
    work['aw']         = pd.to_numeric(work['actual_winnings'], errors='coerce').fillna(0)
    work['date_dt']    = pd.to_datetime(work['date'])
    work['month']      = work['date_dt'].dt.to_period('M').astype(str)
    work['weekday']    = work['date_dt'].dt.day_name()
    work['odds_bucket']= work['odds'].apply(_odds_bucket)

    log.info(f'[GOTW] snapshot: working set = {len(work)} rows')

    today          = date.today()
    week_start     = today - timedelta(days=7)
    prev_week_start= week_start - timedelta(days=7)

    this_week = work[work['date_dt'].dt.date >= week_start]
    prev_week = work[
        (work['date_dt'].dt.date >= prev_week_start) &
        (work['date_dt'].dt.date <  week_start)
    ]

    # Overall record
    total_staked = float(work['stake'].sum())
    total_pl     = float(work['aw'].sum())
    overall_record = {
        'total_bets':   len(work),
        'wins':         int((work['status'] == 'Win').sum()),
        'losses':       int((work['status'] == 'Loss').sum()),
        'pushes':       int((work['status'] == 'Push').sum()),
        'total_pl':     round(total_pl, 2),
        'total_staked': round(total_staked, 2),
        'roi':          round(total_pl / total_staked * 100, 2) if total_staked else 0,
    }

    # Week delta
    week_pl = round(float(this_week['aw'].sum()), 2)
    prev_pl = round(float(prev_week['aw'].sum()), 2)
    week_delta = {
        'this_week_bets':   len(this_week),
        'this_week_pl':     week_pl,
        'prev_week_pl':     prev_pl,
        'pl_change':        round(week_pl - prev_pl, 2),
        'this_week_wins':   int((this_week['status'] == 'Win').sum()),
        'this_week_losses': int((this_week['status'] == 'Loss').sum()),
    }

    # Monthly P/L
    monthly    = work.groupby('month')['aw'].sum()
    monthly_pl = {k: round(float(v), 2) for k, v in monthly.items()}
    months_sorted = sorted(monthly_pl.keys())
    month_delta = None
    if len(months_sorted) >= 2:
        cur_m, prev_m = months_sorted[-1], months_sorted[-2]
        month_delta = {
            'current_month':    cur_m,
            'current_month_pl': monthly_pl[cur_m],
            'prev_month_pl':    monthly_pl[prev_m],
            'change':           round(monthly_pl[cur_m] - monthly_pl[prev_m], 2),
        }

    log.info('[GOTW] snapshot: member stats...')
    # Member stats — all-time and this week
    member_stats = {m: _member_stats_dict(work[work['user'] == m]) for m in MEMBERS}
    member_week  = {m: _member_stats_dict(this_week[this_week['user'] == m]) for m in MEMBERS}
    member_roi_delta = {
        m: round(member_week[m]['roi'] - member_stats[m]['roi'], 2)
        for m in MEMBERS
    }

    # Bet type ROI
    bt_grp = work.groupby('bet_type').agg(
        bets=('odds', 'count'), pl=('aw', 'sum'), staked=('stake', 'sum')
    )
    bt_grp = bt_grp[bt_grp['bets'] >= 3]
    bt_grp['roi'] = bt_grp['pl'] / bt_grp['staked'] * 100
    bet_type_roi = {
        bt: {'bets': int(row['bets']), 'pl': round(float(row['pl']), 2),
             'roi': round(float(row['roi']), 2)}
        for bt, row in bt_grp.iterrows()
    }
    sorted_bt  = sorted(bet_type_roi.items(), key=lambda x: x[1]['roi'])
    bt_summary = {
        'best':  sorted_bt[-1] if sorted_bt else None,
        'worst': sorted_bt[0]  if sorted_bt else None,
    }

    # Competition ROI
    comp_grp = work.groupby('competition').agg(
        bets=('odds', 'count'), pl=('aw', 'sum'), staked=('stake', 'sum')
    )
    comp_grp = comp_grp[comp_grp['bets'] >= 3]
    comp_grp['roi'] = comp_grp['pl'] / comp_grp['staked'] * 100
    competition_roi = {
        c: {'bets': int(row['bets']), 'pl': round(float(row['pl']), 2),
            'roi': round(float(row['roi']), 2)}
        for c, row in comp_grp.iterrows()
    }

    # Odds bucket ROI
    ob_grp = work.groupby('odds_bucket').agg(
        bets=('odds', 'count'), pl=('aw', 'sum'), staked=('stake', 'sum'),
        wins=('status', lambda x: (x == 'Win').sum())
    )
    ob_grp['roi']      = ob_grp['pl'] / ob_grp['staked'] * 100
    ob_grp['win_rate'] = ob_grp['wins'] / ob_grp['bets'] * 100
    odds_bucket = {
        b: {'bets': int(row['bets']), 'pl': round(float(row['pl']), 2),
            'roi': round(float(row['roi']), 2), 'win_rate': round(float(row['win_rate']), 2)}
        for b, row in ob_grp.iterrows()
    }

    # Recent bets (last 15) — kept in snapshot for _build_figure but stripped before Gemini
    recent = work.sort_values('date_dt').tail(15).copy()
    recent['event'] = recent['home_team'] + ' vs ' + recent['away_team']
    recent['date']  = recent['date'].astype(str)
    recent_bets = []
    for r in recent[['date', 'user', 'event', 'bet_type', 'odds', 'stake', 'status', 'aw']].to_dict('records'):
        recent_bets.append({
            'date': str(r['date']), 'user': str(r['user']), 'event': str(r['event']),
            'bet_type': str(r['bet_type']), 'odds': float(r['odds']),
            'stake': float(r['stake']), 'status': str(r['status']), 'aw': float(r['aw']),
        })

    # Weekday P/L
    wd_grp     = work.groupby('weekday')['aw'].sum()
    weekday_pl = {
        day: round(float(wd_grp.get(day, 0)), 2)
        for day in ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']
    }

    # Accumulator
    multis      = work[work['bet_type'] == 'Multi']
    multi_wins  = int((multis['status'] == 'Win').sum())
    multi_losses= int((multis['status'] == 'Loss').sum())
    accumulator = {
        'total':    len(multis),
        'wins':     multi_wins,
        'losses':   multi_losses,
        'pl':       round(float(multis['aw'].sum()), 2),
        'win_rate': round(multi_wins / (multi_wins + multi_losses) * 100, 2)
                    if (multi_wins + multi_losses) > 0 else 0,
    }

    # Running P/L
    ws = work.sort_values('date_dt').copy()
    ws['cum_pl'] = ws['aw'].cumsum()
    current_pl   = round(float(ws['cum_pl'].iloc[-1]), 2) if len(ws) else 0
    peak_pl      = round(float(ws['cum_pl'].max()), 2)    if len(ws) else 0
    max_drawdown = round(float((ws['cum_pl'].cummax() - ws['cum_pl']).max()), 2) if len(ws) else 0
    milestone    = None
    for m in [50, 100, 150, 200, 250, 300, 400, 500]:
        if abs(current_pl - m) < 5 or (peak_pl < m <= current_pl + 5):
            milestone = m
            break
    running_pl = {
        'current_pl':     current_pl,
        'peak_pl':        peak_pl,
        'max_drawdown':   max_drawdown,
        'milestone_near': milestone,
    }

    # Member running P/L
    member_running_pl = {}
    for m in MEMBERS:
        sub = work[work['user'] == m].sort_values('date_dt').copy()
        sub['cum'] = sub['aw'].cumsum()
        if len(sub):
            streak = _streak(sub)
            wl     = streak['resolved_streak_count']
            wl_t   = streak['resolved_streak_type']
            winless= streak['winless_streak']
            # Build a plain-English streak description for Gemini to use verbatim
            if winless > wl:
                streak_desc = f"{winless}-bet winless run"
            elif wl > 0 and wl_t:
                streak_desc = f"{wl}-bet {wl_t.lower()} streak"
            else:
                streak_desc = "no current streak"
            member_running_pl[m] = {
                'current_pl':   round(float(sub['cum'].iloc[-1]), 2),
                'peak_pl':      round(float(sub['cum'].max()), 2),
                'streak_desc':  streak_desc,
                'resolved_streak_count': streak['resolved_streak_count'],
                'resolved_streak_type':  streak['resolved_streak_type'],
                'winless_streak':        streak['winless_streak'],
            }

    raw = {
        'week_delta':       week_delta,
        'month_delta':      month_delta,
        'overall_record':   overall_record,
        'monthly_pl':       monthly_pl,
        'member_stats':     member_stats,
        'member_week':      member_week,
        'member_roi_delta': member_roi_delta,
        'bet_type_roi':     bet_type_roi,
        'bt_summary':       bt_summary,
        'competition_roi':  competition_roi,
        'odds_bucket':      odds_bucket,
        'recent_bets':      recent_bets,
        'weekday_pl':       weekday_pl,
        'accumulator':      accumulator,
        'running_pl':       running_pl,
        'member_running_pl':member_running_pl,
    }
    log.info('[GOTW] snapshot: serialising...')
    return _sanitise_for_json(raw)


# ── Step 2: Gemini commentary & selection ─────────────────────────────────────
# NOTE: _regenerate_commentary is defined BEFORE _select_chart so the fallback
# inside _select_chart can call it without a forward-reference error.

COMMENTARY_PROMPT = """
You are writing factual commentary for a betting syndicate's Graph of the Week.
Your job is accuracy only — tone and voice will be applied separately.
The members are John, Richard, and Xander.

The chosen chart is: {chart_desc}

RULES:
- Always use $ before money figures (e.g. $12.85, -$36.40)
- Always use % after ROI/percentage figures (e.g. +14.2%, -8.3%)
- Streak: use member_running_pl[member].streak_desc verbatim — it already accounts for Pushes correctly.
- member_roi_delta = (this week ROI%) MINUS (all-time ROI%). POSITIVE = better than their average this week. NEGATIVE = worse.
- If a member has fewer than 3 bets this week, do not cite their weekly ROI as meaningful.
- Only use numbers that appear in the snapshot. Do not invent or round differently.
- Roast the member with the worst all-time P/L (check member_stats[member].pl). Use their name.

OUTPUT: 2-3 factual sentences for story. One precise sentence for data_focus. One sharp sentence for roast.

Snapshot:
{snapshot_json}

Respond with valid JSON only, no markdown fences:
{{
  "chart_id": "{chart_id}",
  "headline": "{headline}",
  "story": "<2-3 factual sentences about what this chart shows and why it matters>",
  "data_focus": "<one precise sentence with $ and % as appropriate, naming the specific figure and member>",
  "roast": "<one factual sentence identifying the worst performer by name with their key stat>"
}}
"""

SELECTION_PROMPT = """
You are the data editor for a private betting syndicate's weekly newsletter.
Members are John, Richard, and Xander.

Pick the SINGLE most interesting chart for "Graph of the Week" — the one that tells the most compelling story RIGHT NOW for this specific group of people.

PRIORITY ORDER — work down this list and pick the first chart with a genuine story to tell:
1. PERSONAL RIVALRY & JOURNEYS: running_pl_by_member, member_pl_comparison, member_roi_comparison
   — Always prefer these when members have meaningfully different P/L or one is on a streak.
   — running_pl_by_member is the gold standard: it shows the full journey and names everyone.
2. RECENT FORM: waterfall_recent, cumulative_bankroll
   — Use when there has been a notable run of wins or losses in the last 10 bets.
3. COMPETITION/TOURNAMENT INSIGHT: roi_by_competition
   — Use when multiple competitions are active and one is clearly outperforming.
4. SEASON PATTERNS: monthly_pl, weekday_pl, odds_bucket_roi
   — Only useful once 3+ months of data exist. Check monthly_pl key count before picking monthly_pl.
5. AGGREGATE STATS (LAST RESORT): roi_by_bet_type, win_loss_donut, accumulator_record
   — Only pick these if the data is genuinely striking (e.g. one bet type has ROI > +30% or < -30%).
   — Do NOT pick roi_by_bet_type just because it has data — it needs a real story.

DATA DEPTH GUARDS — do not pick a chart if the underlying data is too thin:
- roi_by_bet_type: only pick if at least 4 distinct bet types each have 5+ bets
- roi_by_competition: only pick if at least 3 competitions each have 5+ bets
- monthly_pl: only pick if monthly_pl has 3+ keys
- odds_bucket_roi: only pick if overall_record.total_bets >= 40
- accumulator_record: only pick if accumulator.total >= 5

RULES:
- Always use $ before money figures, % after ROI/percentage figures
- Streak: use member_running_pl[member].streak_desc verbatim — it already accounts for Pushes correctly.
- member_roi_delta = (this week ROI%) MINUS (all-time ROI%). POSITIVE = better than average. NEGATIVE = worse.
- If this_week_bets < 3 for a member, their weekly ROI is not statistically meaningful — don't cite it as a trend.
- Only cite numbers that appear in the snapshot. Do not invent figures.
- Roast whoever has the worst all-time P/L (check member_stats[member].pl). Use their name.

Previously used charts (do NOT pick these): {used_charts}

Available charts:
{chart_list}

Snapshot:
{snapshot_json}

Respond with valid JSON only, no markdown fences:
{{
  "chart_id": "<id from the list above>",
  "headline": "<punchy 6-8 word headline for the chart>",
  "story": "<2-3 factual sentences: what the chart shows and why it is the most interesting thing this week>",
  "data_focus": "<one precise sentence with $ and % as appropriate, naming the specific figure and member>",
  "roast": "<one factual sentence identifying the worst performer by name with their key stat>"
}}
"""


def _parse_gemini_json(raw: str) -> dict:
    """
    Strip markdown fences and parse JSON from Gemini output.
    Handles common Gemini quirks: trailing commas, markdown fences,
    and leading/trailing whitespace.
    """
    raw = raw.strip()
    # Strip markdown code fences
    if raw.startswith('```'):
        lines = raw.split('\n')
        # Remove first line (```json or ```) and last line (```)
        raw = '\n'.join(lines[1:-1] if lines[-1].strip() == '```' else lines[1:])
    raw = raw.strip()
    # Find the outermost JSON object (in case there's any preamble)
    start = raw.find('{')
    end   = raw.rfind('}')
    if start != -1 and end != -1:
        raw = raw[start:end+1]
    # Remove trailing commas before } or ] (common Gemini mistake)
    import re
    raw = re.sub(r',\s*([}\]])', r'\1', raw)
    return json.loads(raw)


def _regenerate_commentary(selection: dict, snapshot: dict) -> dict:
    """
    Asks Gemini to write story/data_focus/roast for a pre-chosen chart_id.
    Used both when reusing a cached chart and when the selection call fails.
    Falls back to the input dict unchanged if Gemini errors.
    """
    chart_desc = next(
        (c['description'] for c in CHART_REGISTRY if c['id'] == selection['chart_id']),
        selection['chart_id']
    )
    prompt = COMMENTARY_PROMPT.format(
        chart_desc=chart_desc,
        headline=selection.get('headline', 'Graph of the Week'),
        chart_id=selection['chart_id'],
        snapshot_json=json.dumps(_selection_snapshot(snapshot), indent=2),
    )
    try:
        raw    = core._call_gemini(prompt, thinking_level='minimal', max_tokens=1000)
        result = _parse_gemini_json(raw)
        # Validate required keys present
        for key in ('chart_id', 'headline', 'story', 'data_focus', 'roast'):
            if key not in result:
                raise ValueError(f"Missing key in Gemini response: {key}")
        return result
    except Exception as e:
        log.warning(f'[GOTW] Commentary generation failed ({e}), using fallback text.')
        log.warning(f'[GOTW] Raw Gemini commentary response was: {raw!r}')
        return {
            **selection,
            'story':      'Here is your weekly chart.',
            'data_focus': '',
            'roast':      '',
        }


def _select_chart(snapshot: dict, used_charts: list) -> dict:
    """
    Asks Gemini to pick the best chart given the snapshot.
    Falls back to a random chart + regenerated commentary if Gemini errors.
    """
    available = [c for c in CHART_REGISTRY if c['id'] not in used_charts]
    if not available:
        available = CHART_REGISTRY  # all used — reset

    chart_list = '\n'.join(f"  - {c['id']}: {c['description']}" for c in available)
    prompt = SELECTION_PROMPT.format(
        used_charts=', '.join(used_charts) if used_charts else 'none',
        chart_list=chart_list,
        snapshot_json=json.dumps(_selection_snapshot(snapshot), indent=2),
    )

    try:
        raw    = core._call_gemini(prompt, thinking_level='minimal', max_tokens=1000)
        result = _parse_gemini_json(raw)
        for key in ('chart_id', 'headline', 'story', 'data_focus', 'roast'):
            if key not in result:
                raise ValueError(f"Missing key: {key}")
        if result['chart_id'] not in CHART_IDS:
            raise ValueError(f"Unknown chart_id returned: {result['chart_id']}")
        return result
    except Exception as e:
        log.warning(f'[GOTW] Gemini selection failed ({e}), falling back to random.')
        log.warning(f'[GOTW] Raw Gemini selection response was: {raw!r}')
        chart_id = random.choice([c['id'] for c in available])
        chart_desc = next(c['description'] for c in CHART_REGISTRY if c['id'] == chart_id)
        fallback = {
            'chart_id': chart_id,
            'headline': chart_desc.split('—')[0].strip(),
            'story': '', 'data_focus': '', 'roast': '',
        }
        # _regenerate_commentary is defined above — no forward reference
        return _regenerate_commentary(fallback, snapshot)


# ── Step 3: Build the Plotly figure ──────────────────────────────────────────

def _apply_export_layout(fig: go.Figure, title: str = '', height: int = 700) -> go.Figure:
    fig.update_layout(
        title=dict(text=title, font=dict(size=16, color=TEXT_CLR), x=0.01),
        height=height,
        showlegend=True,
        **PLOTLY_EXPORT_LAYOUT,
    )
    return fig


def _build_figure(chart_id: str, df: pd.DataFrame) -> go.Figure:
    """Builds and returns the Plotly figure for the selected chart_id."""
    banking_mask = (
        df['status'].isin(['Reconciliation', 'Deposit', 'Withdrawal']) |
        (df['user'].astype(str).str.lower() == 'syndicate')
    )
    work = df[~banking_mask & df['status'].isin(['Win', 'Loss', 'Push'])].copy()
    work['aw']          = pd.to_numeric(work['actual_winnings'], errors='coerce').fillna(0)
    work['date_dt']     = pd.to_datetime(work['date'])
    work['month']       = work['date_dt'].dt.to_period('M').astype(str)
    work['weekday']     = work['date_dt'].dt.day_name()
    work['odds_bucket'] = work['odds'].apply(_odds_bucket)

    if chart_id == 'monthly_pl':
        monthly = work.groupby('month')['aw'].sum().reset_index()
        fig = go.Figure(go.Bar(
            x=monthly['month'], y=monthly['aw'],
            marker_color=[WIN_COLOR if v >= 0 else LOSS_COLOR for v in monthly['aw']],
            text=[f'${v:+.2f}' for v in monthly['aw']],
            textposition='outside', textfont=dict(size=12, color=TEXT_CLR),
        ))
        fig.add_hline(y=0, line_color=GRID_CLR)
        return _apply_export_layout(fig, '📅 Monthly P/L')

    elif chart_id == 'cumulative_bankroll':
        opening  = float(core.OPENING_BANK)
        all_rows = df.sort_values('date').copy()
        all_rows['aw']       = pd.to_numeric(all_rows['actual_winnings'], errors='coerce').fillna(0)
        all_rows['bankroll'] = opening + all_rows['aw'].cumsum()
        all_rows['date_str'] = pd.to_datetime(all_rows['date']).dt.strftime('%Y-%m-%d')
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=all_rows['date_str'], y=all_rows['bankroll'], mode='lines',
            line=dict(color=ACCENT, width=3, shape='spline', smoothing=1.3),
            fill='tozeroy', fillcolor='rgba(86,180,233,0.08)', name='Bankroll',
        ))
        if not all_rows.empty:
            ath_row = all_rows.loc[all_rows['bankroll'].idxmax()]
            fig.add_annotation(
                x=ath_row['date_str'], y=ath_row['bankroll'],
                text=f"All-Time High<br>${ath_row['bankroll']:.0f}",
                showarrow=True, arrowhead=2, arrowcolor=WIN_COLOR,
                ax=0, ay=-40, font=dict(color=WIN_COLOR, size=12),
            )
        fig.add_hline(y=opening, line_dash='dash', line_color=GRID_CLR,
                      annotation_text=f'Opening ${opening:.0f}',
                      annotation_font_color=GRID_CLR, annotation_position='bottom right')
        return _apply_export_layout(fig, '📈 Cumulative Bankroll')

    elif chart_id == 'roi_by_bet_type':
        bt = work.groupby('bet_type').agg(bets=('odds','count'), pl=('aw','sum'), staked=('stake','sum'))
        bt = bt[bt['bets'] >= 3]
        bt['roi'] = bt['pl'] / bt['staked'] * 100
        bt = bt.sort_values('roi')
        fig = go.Figure(go.Bar(
            y=bt.index, x=bt['roi'], orientation='h',
            marker_color=[WIN_COLOR if r >= 0 else LOSS_COLOR for r in bt['roi']],
            text=[f'{r:+.1f}%' for r in bt['roi']], textposition='outside',
            textfont=dict(color=TEXT_CLR),
        ))
        fig.add_vline(x=0, line_color=GRID_CLR)
        return _apply_export_layout(fig, '📊 ROI by Bet Type (≥3 bets)',
                                    height=max(400, len(bt) * 50))

    elif chart_id == 'member_pl_comparison':
        pls = [float(work[work['user'] == m]['aw'].sum()) for m in MEMBERS]
        fig = go.Figure(go.Bar(
            x=MEMBERS, y=pls,
            marker_color=[MEMBER_COLORS[m] for m in MEMBERS],
            text=[f'${p:+.2f}' for p in pls], textposition='outside',
            textfont=dict(color=TEXT_CLR, size=14),
        ))
        fig.add_hline(y=0, line_color=GRID_CLR)
        return _apply_export_layout(fig, '💸 Individual P/L — All Time')

    elif chart_id == 'member_roi_comparison':
        rois = []
        for m in MEMBERS:
            sub    = work[work['user'] == m]
            staked = float(sub['stake'].sum())
            rois.append(round(float(sub['aw'].sum()) / staked * 100, 2) if staked > 0 else 0)
        fig = go.Figure(go.Bar(
            x=MEMBERS, y=rois,
            marker_color=[WIN_COLOR if r >= 0 else LOSS_COLOR for r in rois],
            text=[f'{r:+.1f}%' for r in rois], textposition='outside',
            textfont=dict(color=TEXT_CLR, size=14),
        ))
        fig.add_hline(y=0, line_color=GRID_CLR)
        return _apply_export_layout(fig, '📊 Individual ROI % — All Time')

    elif chart_id == 'win_loss_donut':
        wins   = int((work['status'] == 'Win').sum())
        losses = int((work['status'] == 'Loss').sum())
        pushes = int((work['status'] == 'Push').sum())
        wr     = wins / (wins + losses) * 100 if (wins + losses) > 0 else 0
        fig    = go.Figure(go.Pie(
            labels=['Win','Loss','Push'], values=[wins,losses,pushes],
            hole=0.55, marker=dict(colors=[WIN_COLOR,LOSS_COLOR,PUSH_COLOR]),
            textinfo='label+percent', textfont=dict(size=14, color=TEXT_CLR),
        ))
        fig.add_annotation(text=f'{wr:.1f}%<br><span style="font-size:12px">win rate</span>',
                           x=0.5, y=0.5, showarrow=False, font=dict(size=20, color=TEXT_CLR))
        return _apply_export_layout(fig, '🎯 Overall Win/Loss Record')

    elif chart_id == 'roi_by_competition':
        cg = work.groupby('competition').agg(bets=('odds','count'), pl=('aw','sum'), staked=('stake','sum'))
        cg = cg[cg['bets'] >= 3]
        cg['roi'] = cg['pl'] / cg['staked'] * 100
        cg = cg.sort_values('roi')
        fig = go.Figure(go.Bar(
            y=cg.index, x=cg['roi'], orientation='h',
            marker_color=[WIN_COLOR if r >= 0 else LOSS_COLOR for r in cg['roi']],
            text=[f'{r:+.1f}% ({int(b)} bets)' for r,b in zip(cg['roi'],cg['bets'])],
            textposition='outside', textfont=dict(color=TEXT_CLR),
        ))
        fig.add_vline(x=0, line_color=GRID_CLR)
        return _apply_export_layout(fig, '🏆 ROI by Competition',
                                    height=max(400, len(cg) * 52))

    elif chart_id == 'odds_bucket_roi':
        bucket_order = ['<1.40','1.40-1.69','1.70-1.99','2.00-2.49','2.50-3.49','3.50+']
        ob = work.groupby('odds_bucket').agg(
            bets=('odds','count'), pl=('aw','sum'), staked=('stake','sum'),
            wins=('status', lambda x: (x=='Win').sum())
        )
        ob['roi']      = ob['pl'] / ob['staked'] * 100
        ob['win_rate'] = ob['wins'] / ob['bets'] * 100
        ob = ob.reindex([b for b in bucket_order if b in ob.index])
        fig = make_subplots(specs=[[{'secondary_y': True}]])
        fig.add_trace(go.Bar(
            x=ob.index, y=ob['roi'],
            marker_color=[WIN_COLOR if r >= 0 else LOSS_COLOR for r in ob['roi']],
            name='ROI %', text=[f'{r:+.1f}%' for r in ob['roi']],
            textfont=dict(color=TEXT_CLR),
        ), secondary_y=False)
        fig.add_trace(go.Scatter(
            x=ob.index, y=ob['win_rate'], mode='lines+markers',
            line=dict(color=PUSH_COLOR, dash='dash', width=2),
            name='Win Rate %', marker=dict(size=8),
        ), secondary_y=True)
        fig.update_layout(**PLOTLY_EXPORT_LAYOUT,
                          title=dict(text='🎲 ROI & Win Rate by Odds Bucket',
                                     font=dict(size=16, color=TEXT_CLR), x=0.01),
                          height=500)
        return fig

    elif chart_id == 'waterfall_recent':
        recent = work.sort_values('date_dt').tail(15).copy()
        recent['event']        = recent['home_team'] + ' vs ' + recent['away_team']
        recent['unique_label'] = (recent['event'].str[:12] + ' [' +
                                  recent['uuid'].astype(str).str[:4] + ']')
        fig = go.Figure(go.Waterfall(
            name='Profit', orientation='v',
            x=recent['unique_label'], y=recent['aw'],
            measure=['relative'] * len(recent),
            text=[f'${v:+.2f}' for v in recent['aw']], textposition='outside',
            decreasing=dict(marker=dict(color=LOSS_COLOR)),
            increasing=dict(marker=dict(color=WIN_COLOR)),
            totals=dict(marker=dict(color=ACCENT)),
            connector=dict(line=dict(color=GRID_CLR, width=1)),
        ))
        fig.update_xaxes(
            tickmode='array', tickvals=recent['unique_label'],
            ticktext=recent['event'].str[:14] + '..',
            tickangle=45, tickfont=dict(size=11, color=TEXT_CLR),
        )
        return _apply_export_layout(fig, '🌊 Recent Form — Last 15 Bets')

    elif chart_id == 'running_pl_by_member':
        fig = go.Figure()
        for m in MEMBERS:
            sub = work[work['user'] == m].sort_values('date_dt').copy()
            sub['cum']      = sub['aw'].cumsum()
            sub['date_str'] = sub['date_dt'].dt.strftime('%Y-%m-%d')
            if not sub.empty:
                fig.add_trace(go.Scatter(
                    x=sub['date_str'], y=sub['cum'], mode='lines', name=m,
                    line=dict(color=MEMBER_COLORS[m], width=2.5),
                ))
        fig.add_hline(y=0, line_dash='dash', line_color=GRID_CLR)
        return _apply_export_layout(fig, '🏎️ Running P/L by Member')

    elif chart_id == 'weekday_pl':
        days  = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']
        wd    = work.groupby('weekday')['aw'].sum().reindex(days).fillna(0)
        fig   = go.Figure(go.Bar(
            x=wd.index, y=wd.values,
            marker_color=[WIN_COLOR if v >= 0 else LOSS_COLOR for v in wd.values],
            text=[f'${v:+.2f}' for v in wd.values],
            textposition='outside', textfont=dict(color=TEXT_CLR),
        ))
        fig.add_hline(y=0, line_color=GRID_CLR)
        return _apply_export_layout(fig, '📆 P/L by Day of Week')

    elif chart_id == 'accumulator_record':
        multis          = work[work['bet_type'] == 'Multi'].copy()
        multis['month'] = multis['date_dt'].dt.to_period('M').astype(str)
        monthly         = multis.groupby('month')['aw'].sum().reset_index()
        wins            = int((multis['status'] == 'Win').sum())
        losses          = int((multis['status'] == 'Loss').sum())
        wr              = wins / (wins + losses) * 100 if (wins + losses) > 0 else 0
        fig = make_subplots(rows=1, cols=2,
                            subplot_titles=('Monthly Multi P/L','Win/Loss Split'),
                            specs=[[{'type':'bar'},{'type':'pie'}]])
        fig.add_trace(go.Bar(
            x=monthly['month'], y=monthly['aw'],
            marker_color=[WIN_COLOR if v >= 0 else LOSS_COLOR for v in monthly['aw']],
            showlegend=False,
        ), row=1, col=1)
        fig.add_trace(go.Pie(
            labels=['Win','Loss'], values=[wins,losses], hole=0.5,
            marker=dict(colors=[WIN_COLOR,LOSS_COLOR]),
            textfont=dict(size=13, color=TEXT_CLR),
        ), row=1, col=2)
        fig.update_layout(**PLOTLY_EXPORT_LAYOUT,
                          title=dict(text=f'💀 Accumulator Curse — {wr:.0f}% win rate',
                                     font=dict(size=16, color=TEXT_CLR), x=0.01),
                          height=500)
        return fig

    else:
        fig = go.Figure()
        fig.add_annotation(text=f'Chart not found: {chart_id}', x=0.5, y=0.5,
                           showarrow=False, font=dict(color=TEXT_CLR, size=16))
        return _apply_export_layout(fig, 'Error')


# ── Step 4: Render PNG ────────────────────────────────────────────────────────

def _render_png(fig: go.Figure) -> bytes:
    return fig.to_image(format='png', width=EXPORT_WIDTH,
                        height=EXPORT_HEIGHT, scale=EXPORT_SCALE)


# ── Step 5: Send to Telegram ──────────────────────────────────────────────────

def _send_photo(image_bytes: bytes, caption: str, chat_id: str) -> bool:
    if not core.TELEGRAM_BOT_TOKEN or not chat_id:
        log.warning('[GOTW] Cannot send photo — missing token or chat_id')
        return False
    try:
        resp = requests.post(
            f'https://api.telegram.org/bot{core.TELEGRAM_BOT_TOKEN}/sendPhoto',
            data={'chat_id': chat_id, 'caption': caption},
            files={'photo': ('graph_of_week.png', image_bytes, 'image/png')},
            timeout=30,
        )
        resp.raise_for_status()
        return True
    except requests.RequestException as e:
        log.error(f'[GOTW] Failed to send photo: {e}')
        return False


def _unify_commentary(story: str, data_focus: str, roast: str, persona: dict) -> tuple:
    """
    Passes the three voiced sections back to Gemini for a final tidy.
    Removes redundant greetings, restatements and repeated persona tics
    while keeping the voice consistent. Returns (story, data_focus, roast).
    """
    prompt = f"""You are editing a three-part commentary written in the voice of "{persona['name']}".

The three sections were written separately and may have redundant greetings, repeated phrases, or restated facts. Your job is to tidy them into three clean, distinct sections that flow as a coherent whole — same voice, no repetition, no redundant openers.

Do NOT change the facts, numbers, or member names. Do NOT add new information. Just remove redundancy and smooth the joins.

SECTION 1 (story):
{story}

SECTION 2 (data focus):
{data_focus}

SECTION 3 (roast):
{roast}

Respond with valid JSON only, no markdown fences:
{{
  "story": "<cleaned story section>",
  "data_focus": "<cleaned data focus — one sentence>",
  "roast": "<cleaned roast — one sentence>"
}}"""
    try:
        raw    = core._call_gemini(prompt, thinking_level='minimal', max_tokens=800)
        raw    = raw.strip()
        start  = raw.find('{')
        end    = raw.rfind('}')
        if start != -1 and end != -1:
            raw = raw[start:end+1]
        import re
        raw    = re.sub(r',\s*([}\]])', r'\1', raw)
        result = json.loads(raw)
        return result.get('story', story), result.get('data_focus', data_focus), result.get('roast', roast)
    except Exception as e:
        log.warning(f'[GOTW] Unification pass failed ({e}), using pre-unified sections.')
        return story, data_focus, roast


def _send_commentary(selection: dict, chat_id: str) -> bool:
    """Applies persona to each block, unifies, then sends with formatting."""
    try:
        persona     = core.get_report_persona()
        persona_tag = f'_{persona["name"]}_'
        def voice(text: str) -> str:
            return core.apply_persona(text, asker_name='the syndicate', persona=persona)
    except Exception as e:
        log.warning(f'[GOTW] Persona setup failed ({e}), using raw commentary.')
        persona_tag = ''
        def voice(text: str) -> str:
            return text

    story      = voice(selection.get('story', ''))      if selection.get('story')      else ''
    data_focus = voice(selection.get('data_focus', '')) if selection.get('data_focus') else ''
    roast      = voice(selection.get('roast', ''))      if selection.get('roast')      else ''

    # Final unification pass to remove redundancy across sections
    if story or data_focus or roast:
        story, data_focus, roast = _unify_commentary(story, data_focus, roast, persona)

    lines = [f'📊 *Graph of the Week: {selection["headline"]}*']
    if persona_tag:
        lines.append(persona_tag)
    if story:
        lines.append('')
        lines.append(story)
    if data_focus:
        lines.append('')
        lines.append(f'🔍 {data_focus}')
    if roast:
        lines.append('')
        lines.append(f'🔥 {roast}')

    return core.send_telegram('\n'.join(lines), chat_id=chat_id)


# ── Cache helpers ─────────────────────────────────────────────────────────────

def _get_used_charts() -> list:
    state   = core.load_last_run()
    history = state.get('gotw_history', [])
    return [entry['chart_id'] for entry in history[-REPEAT_WINDOW:]
            if 'chart_id' in entry]


def _record_chart_used(chart_id: str, headline: str, preview: bool = False) -> None:
    state   = core.load_last_run()
    history = state.get('gotw_history', [])
    history.append({'chart_id': chart_id, 'headline': headline,
                    'date': str(date.today()), 'preview': preview})
    state['gotw_history'] = history
    iso = date.today().isocalendar()
    state['gotw_this_week'] = {
        'chart_id': chart_id, 'headline': headline,
        'week': iso.week, 'year': iso.year,
    }
    core.save_last_run(state)


def _get_this_week_selection() -> Optional[dict]:
    state  = core.load_last_run()
    cached = state.get('gotw_this_week')
    if not cached:
        return None
    iso = date.today().isocalendar()
    if cached.get('week') == iso.week and cached.get('year') == iso.year:
        return cached
    return None


# ── Public entry point ────────────────────────────────────────────────────────

def run_graph_of_week(df: pd.DataFrame, preview: bool = False,
                      send_target: str = None) -> bool:
    """
    Full pipeline: select → build → render → send.

    send_target   → explicit chat_id to send to (used by on-demand report command).
    preview=True  → always sends to TEST_CHAT_ID (safe, won't spam group).
    If neither is set, falls back to the normal group send target.
    """
    import traceback

    # ── Target ──
    try:
        if send_target:
            log.info(f'[GOTW] Explicit send_target: {send_target}')
        elif preview:
            send_target = core.TEST_CHAT_ID
            if not send_target:
                log.error('[GOTW] Preview requested but TEST_CHAT_ID not set in .env')
                return False
            log.info(f'[GOTW] PREVIEW mode — sending to TEST_CHAT_ID {send_target}')
        else:
            send_target = core.get_send_target()
            log.info(f'[GOTW] Using default send target: {send_target}')
    except Exception as e:
        log.error(f'[GOTW] Failed to determine send target: {e}\n{traceback.format_exc()}')
        return False

    # ── Snapshot ──
    try:
        log.info('[GOTW] Computing week-in-numbers snapshot...')
        snapshot = compute_snapshot(df)
        log.info(f'[GOTW] Snapshot OK — {len(snapshot)} keys, '
                 f'{len(json.dumps(snapshot))} chars')
    except Exception as e:
        log.error(f'[GOTW] compute_snapshot failed: {e}\n{traceback.format_exc()}')
        return False

    # ── Selection ──
    try:
        cached = _get_this_week_selection()
        if cached and not preview:
            log.info(f'[GOTW] Reusing previewed selection: {cached["chart_id"]}')
            stub = {'chart_id': cached['chart_id'], 'headline': cached['headline'],
                    'story': '', 'data_focus': '', 'roast': ''}
            selection = _regenerate_commentary(stub, snapshot)
        else:
            used = _get_used_charts()
            log.info(f'[GOTW] Recent charts (excluded): {used}')
            log.info('[GOTW] Asking Gemini to select chart...')
            selection = _select_chart(snapshot, used)
        log.info(f'[GOTW] Selection: chart_id={selection.get("chart_id")} '
                 f'headline={selection.get("headline")}')
    except Exception as e:
        log.error(f'[GOTW] Selection step failed: {e}\n{traceback.format_exc()}')
        return False

    # ── Validate selection keys ──
    for key in ('chart_id', 'headline', 'story', 'data_focus', 'roast'):
        if key not in selection:
            log.error(f'[GOTW] Selection dict missing key "{key}": {selection}')
            return False

    # ── Build figure ──
    try:
        log.info(f'[GOTW] Building figure: {selection["chart_id"]}')
        fig = _build_figure(selection['chart_id'], df)
        log.info('[GOTW] Figure built OK')
    except Exception as e:
        log.error(f'[GOTW] Figure build failed: {e}\n{traceback.format_exc()}')
        return False

    # ── Render PNG ──
    try:
        log.info('[GOTW] Rendering PNG...')
        png_bytes = _render_png(fig)
        log.info(f'[GOTW] PNG rendered OK — {len(png_bytes)} bytes')
    except Exception as e:
        log.error(f'[GOTW] PNG render failed: {e}\n{traceback.format_exc()}')
        return False

    # ── Send ──
    try:
        caption = f'📊 Graph of the Week\n{selection["headline"]}'
        log.info('[GOTW] Sending image...')
        ok_img = _send_photo(png_bytes, caption, send_target)
        log.info(f'[GOTW] Image send: {ok_img}')

        log.info('[GOTW] Sending commentary...')
        ok_txt = _send_commentary(selection, send_target)
        log.info(f'[GOTW] Commentary send: {ok_txt}')
    except Exception as e:
        log.error(f'[GOTW] Send step failed: {e}\n{traceback.format_exc()}')
        return False

    # ── Cache — only record on scheduled runs, not previews ──
    if not preview:
        try:
            _record_chart_used(selection['chart_id'], selection['headline'], preview=False)
        except Exception as e:
            log.warning(f'[GOTW] Cache record failed (non-fatal): {e}')

    if ok_img and ok_txt:
        log.info('[GOTW] Graph of the Week delivered successfully.')
        return True
    else:
        log.warning(f'[GOTW] Partial send — img:{ok_img} txt:{ok_txt}')
        return False
