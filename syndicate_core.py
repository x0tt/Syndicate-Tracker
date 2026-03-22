#!/usr/bin/env python3
# coding: utf-8
"""
syndicate_core.py — Syndicate Tracker v6.3
==========================================
Pure logic layer. No UI, no Telegram, no scheduling.

v6.3 changes vs v6.2:
  - _log_failed_write now always writes structured, replayable JSON
  - update_grade wraps write_with_retry in try/except and logs structured args on failure
  - append_bet does the same
  - replay_failed_writes now actually re-executes logged operations instead of being a stub
"""

import os
import re as _re
import json
import time as _time
import uuid as _uuid
import logging
from pathlib import Path
from datetime import date, timedelta, datetime, timezone
from datetime import date as _date

import numpy as np
import pandas as pd
import requests as _requests
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
log = logging.getLogger('syndicate')

# ── C0: Config & secrets ──────────────────────────────────────────────────────
PROJECT_ROOT  = Path(__file__).parent
DATA_DIR      = PROJECT_ROOT / 'data'
CACHE_DIR     = PROJECT_ROOT / 'cache'
REPORTS_DIR   = PROJECT_ROOT / 'reports'
LOGS_DIR      = PROJECT_ROOT / 'logs'

LEDGER_CSV    = DATA_DIR  / 'syndicate_ledger.csv'
LAST_RUN_JSON = CACHE_DIR / 'last_run.json'
FAILED_WRITES = LOGS_DIR  / 'failed_writes.log'

for _d in[DATA_DIR, CACHE_DIR, REPORTS_DIR, LOGS_DIR]:
    _d.mkdir(parents=True, exist_ok=True)

GSHEET_ID          = os.getenv('GSHEET_ID', '')
GSHEET_TAB         = os.getenv('GSHEET_TAB', 'syndicate_ledger_v3')
GOOGLE_CREDS_PATH  = Path(os.getenv('GOOGLE_CREDENTIALS_PATH', 'credentials.json'))
ODDS_API_KEY       = os.getenv('ODDS_API_KEY', '')
GEMINI_API_KEY     = os.getenv('GEMINI_API_KEY', '')
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_ID   = os.getenv('TELEGRAM_CHAT_ID', '')

# Baseline is 0.00 so the "Deposit" rows act as the true source of funds
OPENING_BANK       = float(os.getenv('OPENING_BANK', '0.00'))

TEST_MODE    = os.getenv('TEST_MODE', 'false').lower() == 'true'
TEST_CHAT_ID = os.getenv('TEST_CHAT_ID', '')

USE_GSHEETS_LIVE  = os.getenv('USE_GSHEETS_LIVE',  'true').lower()  == 'true'
USE_ODDS_API_LIVE = os.getenv('USE_ODDS_API_LIVE', 'true').lower()  == 'true'
GRADING_DRY_RUN   = os.getenv('GRADING_DRY_RUN',  'true').lower()  == 'true'
BETBOT_LIVE       = os.getenv('BETBOT_LIVE',       'true').lower()  == 'true'

GEMINI_MODEL              = os.getenv('GEMINI_MODEL', 'gemini-3.1-flash-lite-preview')
BETBOT_THINKING_LEVEL     = 'minimal'
CHRONICLER_THINKING_LEVEL = 'low'
_THINKING_BUDGET          = {'minimal': 0, 'low': 512, 'medium': 1024, 'high': 2048}

GRADING_SPORT     = 'soccer_epl'
GRADING_RETRY_MAX = 3
GRADING_BACKOFF   = 2

SYNDICATE_MEMBERS =['John', 'Richard', 'Xander', 'Team']

COLUMN_MAP = {
    'uuid': 'A', 'date': 'B', 'user': 'C', 'home_team': 'D', 'away_team': 'E',
    'competition': 'F', 'bet_type': 'G', 'selection': 'H', 'odds': 'I',
    'stake': 'J', 'status': 'K', 'actual_winnings': 'L', 'matchday': 'M', 'sport': 'N'
}


CHRONICLER_PERSONAS =[
    {'name': 'The Statistician', 'instruction': 'You are a dry, precise statistician. Present every result with unnecessary decimal places and passive-voice hedging.'},
    {'name': 'The Pundit', 'instruction': 'You are an overconfident TV football pundit. Speak in clichés, take full credit for correct predictions, and blame "the lads" for losses.'},
    {'name': 'The Accountant', 'instruction': 'You are a deeply boring accountant who hates cheese and is mildly offended by gambling but keeps doing the report anyway. Mention cheese at least once. Refer to winnings as "revenue events".'},
    {'name': 'The Alien', 'instruction': 'You are an alien anthropologist studying human gambling rituals. You do not fully understand what "winning" means in this context. Refer to the syndicate as "the tribe" and to money as "the tokens".'},
    {'name': 'The Victorian Gentleman', 'instruction': 'You are a Victorian gentleman who finds the whole enterprise frightfully vulgar but cannot stop reading the ledger. Express moral disapproval while clearly being riveted. Use "frightful", "beastly", and "capital".'},
    {'name': 'The Cricket Commentator', 'instruction': 'You are a cricket commentator who only knows cricket. Describe all football results using cricket terminology. Seem confused but carry on professionally. Refer to goals as "wickets" and matches as "overs".'},
    {'name': 'The Degenerate Gambler', 'instruction': 'You are a completely unhinged sports bettor who is absolutely certain the next bet will turn everything around. Every loss is "basically a win" because you nearly got it. Every win is proof the system works. You are already mentally spending the profits. You refer to the syndicate as "we" with intense emotional investment, use phrases like "trust the process", "value everywhere", and "this is it lads". You are dangerously optimistic at all times.'},
    {'name': 'The Conspiracy Theorist', 'instruction': 'You are convinced that all draws are rigged by Big Football. Every loss is suspicious. Every win is "despite them". Connect unrelated results into a coherent (but wrong) narrative.'},
    {'name': 'The Pirate', 'instruction': 'You are a pirate who desperately wants to attack Australia but keeps getting distracted by the betting results. Nautical metaphors throughout. End every report with a revised plan to sail east.'},
]

SPORT_KEY_MAP = {
    'EPL 24/25'                        : 'soccer_epl',
    'EPL 25/26'                        : 'soccer_epl',
    'FA cup 2025'                      : 'soccer_fa_cup',
    'FA cup 2026'                      : 'soccer_fa_cup',
    'Champions League 2025'            : 'soccer_uefa_champs_league',
    'Club World Cup'                   : 'soccer_fifa_club_world_cup',
    'World Cup OFC qualification'      : 'soccer_fifa_world_cup_qualification',
    'International Football'           : 'soccer_fifa_world_cup',
    'A-League 2025'                    : 'soccer_australia_aleague',
    'Superbowl 60'                     : 'americanfootball_nfl',
}

MANUAL_REVIEW_MARKETS = {'Multi', 'To Qualify', 'Winner', 'Relegation', 'To Score Anytime', 'Method of Victory', 'To Score'}

TEAM_NAME_MAP = {
    'Man City': 'Manchester City', 'Man Utd': 'Manchester United',
    'Wolves': 'Wolverhampton Wanderers', 'Villa': 'Aston Villa',
    'Spurs': 'Tottenham Hotspur', 'Tottenham': 'Tottenham Hotspur',
    'Palace': 'Crystal Palace', 'Brighton': 'Brighton and Hove Albion',
    'Forest': 'Nottingham Forest', 'West Ham': 'West Ham United',
    'Newcastle': 'Newcastle United', 'Leicester': 'Leicester City',
    'Leeds': 'Leeds United', 'Ipswich': 'Ipswich Town',
    'Southampton': 'Southampton', 'Bournemouth': 'Bournemouth',
    'Brentford': 'Brentford', 'Fulham': 'Fulham', 'Arsenal': 'Arsenal',
    'Chelsea': 'Chelsea', 'Liverpool': 'Liverpool', 'Everton': 'Everton',
    'Sunderland': 'Sunderland', 'Burnley': 'Burnley',
    'PSG': 'Paris Saint-Germain', 'Real Madrid': 'Real Madrid',
    'Bayern Munich': 'Bayern Munich', 'Borussia Dortmund': 'Borussia Dortmund',
    'Al Hilal Riyadh': 'Al-Hilal',
}

CHRONICLER_SYSTEM_TEMPLATE = """You are writing the weekly betting syndicate report.
Your persona this week: {persona_name}
Your character instruction: {persona_instruction}

=== BETTING GLOSSARY & TERMINOLOGY ===
You MUST adhere strictly to these definitions to avoid financial miscalculations:
- Stake: The amount of money risked on a single bet.
- Turnover (or Handle): The total sum of all stakes placed over a given period.
- Gross Payout: The total amount returned on a winning bet (Stake + Net Profit). Never refer to this as just "winnings."
- Winnings (or Net Profit): The gross payout minus the original stake. (e.g., A $10 stake at 2.0 odds yields a $20 gross payout, but the Net Profit/Winnings is $10). If a bet loses, the net profit is exactly negative the stake.
- ROI (Return on Investment) / Yield: Net Profit divided by Total Turnover, multiplied by 100.
- Free Bet: A bet where the stake is $0. The Net Profit is the entire payout.

STRICT RULES:
1. Every number, stat, profit figure, and result MUST come verbatim from the JSON summary below. Do not invent any values.
2. {length_instruction}
3. Structure:   - Opening: In persona voice, set the scene.
   - The Bottom Line: State the weekly profit/loss and the overall bank standing.
   - Player of the Week: Highlight the member with the best weekly profit based on "member_performance". Roast the worst.
   - Best & Worst Bets: Call out the specific best and worst bets of the week (ONLY if worst_bet is not null).
   - Market Watch: Mention which bet types (markets) worked or failed based on "market_breakdown".
   - Streaks: Call out any active streaks or broken streaks.
   - Closing: Persona sign-off.
4. Address the syndicate informally.
5. Use the currency symbol $ for all money figures.
6. NO markdown formatting whatsoever. Use plain text and blank lines between sections.
7. NEVER use JSON key names in the prose. Write naturally.

BALANCE FIELDS — read carefully before mentioning money:
- total_deposited: all top-up deposits + starting bank.
- net_profit_all: total P&L from all betting (paid + free combined). Negative means a net loss.
- current_balance: cash in the bank right now (total_deposited + net_profit_all).
- To say if the syndicate is UP or DOWN overall: compare current_balance to total_deposited.

Weekly summary data:
{summary_json}
"""

# ── C1: Data ingestion & feature engineering ──────────────────────────────────

def load_ledger(csv_path: Path = LEDGER_CSV) -> tuple:
    df = pd.read_csv(csv_path, parse_dates=['date'])

    df['status'] = df['status'].astype(str).str.strip()
    df['user'] = df['user'].fillna('Team')

    # Synthetic event column so tooltips/charts still look nice
    def make_event(r):
        if str(r.get('home_team', '')).lower() == 'multiple' or pd.isna(r.get('home_team')):
            return 'Multiple'
        if pd.isna(r.get('away_team')):
            return str(r.get('home_team', ''))
        return f"{r['home_team']} vs {r['away_team']}"
    df['event'] = df.apply(make_event, axis=1)

    df['is_free_bet'] = df['stake'] == 0.0
    df['profit']       = pd.to_numeric(df['actual_winnings'], errors='coerce').fillna(0.0)
    df['implied_prob'] = 1 / df['odds'].replace(0, np.nan)
    df['is_win']       = df['status'] == 'Win'
    df['is_loss']      = df['status'] == 'Loss'
    df['is_push']      = df['status'] == 'Push'

    df['dotw']  = df['date'].dt.day_name()
    df['month'] = df['date'].dt.to_period('M').astype(str)
    df['year']  = df['date'].dt.year
    df['season'] = df['date'].apply(lambda d: '2024/25' if d < pd.Timestamp('2025-07-01') else '2025/26')

    # Cumulative calculations
    df_sorted = df.sort_values('date').reset_index(drop=True)

    # Bankroll completely tracks all actual_winnings (deposits, recons, bets)
    df_sorted['balance']      = OPENING_BANK + df_sorted['profit'].cumsum()
    df_sorted['peak_balance'] = df_sorted['balance'].cummax()
    df_sorted['drawdown']     = df_sorted['balance'] - df_sorted['peak_balance']
    df_sorted['drawdown_pct'] = df_sorted['drawdown'] / df_sorted['peak_balance'].replace(0, 1) * 100

    # Segmented views: Exclude ANY banking action (specific status OR user='syndicate')
    banking_mask = df_sorted['status'].isin(['Deposit', 'Withdrawal', 'Reconciliation']) | (df_sorted['user'].astype(str).str.lower() == 'syndicate')
    df_sorted['is_bet'] = ~banking_mask

    df_bet     = df_sorted[~banking_mask].copy()
    df_roi     = df_bet[(df_bet['status'].isin(['Win', 'Loss', 'Push'])) & (~df_bet['is_free_bet'])].copy()
    df_free    = df_bet[(df_bet['status'].isin(['Win', 'Loss', 'Push'])) & (df_bet['is_free_bet'])].copy()
    df_pending = df_bet[df_bet['status'] == 'Pending'].copy()

    # KPIs
    total_staked  = df_roi['stake'].sum()
    profit_all    = df_bet[df_bet['status'].isin(['Win','Loss','Push'])]['profit'].sum()
    profit_roi    = df_roi['profit'].sum()
    current_balance = df_sorted['balance'].iloc[-1] if not df_sorted.empty else OPENING_BANK

    win_rate   = df_roi['is_win'].mean()   if not df_roi.empty else 0.0
    avg_odds   = df_roi['odds'].mean()     if not df_roi.empty else 0.0

    if not df_roi.empty:
        best_bet  = df_roi.loc[df_roi['profit'].idxmax()]
        worst_bet = df_roi.loc[df_roi['profit'].idxmin()]
        best_bet_kpis = {
            'best_bet_event': best_bet['event'], 'best_bet_user': best_bet['user'], 'best_bet_profit': round(float(best_bet['profit']), 2),
            'worst_bet_event': worst_bet['event'], 'worst_bet_user': worst_bet['user'], 'worst_bet_profit': round(float(worst_bet['profit']), 2),
        }
    else:
        best_bet_kpis = {
            'best_bet_event': 'No bets', 'best_bet_user': '—', 'best_bet_profit': 0.0,
            'worst_bet_event': 'No bets', 'worst_bet_user': '—', 'worst_bet_profit': 0.0,
        }

    kpis = {
        'total_bets': len(df_bet), 'total_pending': len(df_pending),
        'opening_bank': round(OPENING_BANK, 2), 'current_balance': round(current_balance, 2),
        'total_staked': round(total_staked, 2), 'profit_all': round(profit_all, 2),
        'profit_roi': round(profit_roi, 2), 'free_bet_contrib': round(df_free['profit'].sum(), 2),
        'roi_pct': round(profit_roi / total_staked * 100 if total_staked else 0, 2),
        'win_rate': round(float(win_rate), 4), 'avg_odds': round(float(avg_odds), 4),
        'peak_balance': round(df_sorted['peak_balance'].max() if not df_sorted.empty else OPENING_BANK, 2),
        **best_bet_kpis,
    }

    return df_sorted, df_roi, df_free, df_pending, kpis

# ── C2: Analytics helpers ─────────────────────────────────────────────────────

def get_leaderboard(df_roi: pd.DataFrame) -> pd.DataFrame:
    lb = df_roi.groupby('user').agg(
        bets=('uuid', 'count'), wins=('is_win', 'sum'), losses=('is_loss', 'sum'),
        pushes=('is_push', 'sum'), staked=('stake', 'sum'), profit=('profit', 'sum'),
        avg_odds=('odds', 'mean'), avg_stake=('stake', 'mean'),
        implied_prob=('implied_prob', 'mean'), win_rate=('is_win', 'mean'),
    ).assign(
        roi_pct=lambda x: x['profit'] / x['staked'] * 100,
    ).sort_values('profit', ascending=False)
    for col in['wins', 'losses', 'pushes']: lb[col] = lb[col].astype(int)
    return lb

def get_user_streak_summary(df_roi: pd.DataFrame) -> dict:
    result = {}
    df = df_roi[df_roi['status'].isin(['Win', 'Loss', 'Push'])].sort_values('date')
    for user, grp in df.groupby('user'):
        if grp.empty: continue
        statuses = grp['status'].tolist()
        current_type = statuses[-1]
        current_len = 1
        for s in reversed(statuses[:-1]):
            if s == current_type: current_len += 1
            else: break
        unbeaten = sum(1 for s in reversed(statuses) if s != 'Loss')
        winless = sum(1 for s in reversed(statuses) if s != 'Win')
        result[user] = {'type': current_type, 'length': current_len, 'unbeaten': unbeaten, 'winless': winless}
    return result

def get_user_streaks(df_roi: pd.DataFrame) -> dict: return get_user_streak_summary(df_roi)

def get_weekly_streak_breaks(df_roi: pd.DataFrame, week_start: date, week_end: date) -> list:
    events = []
    df = df_roi[df_roi['status'].isin(['Win', 'Loss', 'Push'])].sort_values('date').copy()
    for user, grp in df.groupby('user'):
        if len(grp) < 2: continue
        statuses, dates = grp['status'].tolist(),[d.date() for d in grp['date'].tolist()]
        streak_len, streak_type = 1, statuses[0]
        for i in range(1, len(statuses)):
            if statuses[i] == streak_type:
                streak_len += 1
            else:
                if streak_len >= 3 and week_start <= dates[i] <= week_end:
                    events.append(f"{user} broke a {streak_len}-{streak_type.lower()} streak.")
                streak_len, streak_type = 1, statuses[i]
    return events

# ── C2b: Hardcoded command formatters ────────────────────────────────────────
def format_pending(df_pending: pd.DataFrame) -> str:
    if df_pending.empty: return "\u23f3 No pending bets right now."
    lines =[f"\u23f3 Pending Bets ({len(df_pending)}):"]
    for _, r in df_pending.iterrows(): lines.append(f"\u2022 {r['user']}: {r['event']} \u2014 {r['selection']} @ {r['odds']}")
    return "\n".join(lines)

def format_leaderboard(df_roi: pd.DataFrame) -> str:
    lb = get_leaderboard(df_roi)
    lb = lb[lb.index != 'Team']
    lines =["\U0001f3c6 Leaderboard:"]
    for user, row in lb.iterrows(): lines.append(f"\u2022 {user}: ${row['profit']:.2f} profit ({row['roi_pct']:.1f}% ROI, {int(row['bets'])} bets)")
    return "\n".join(lines)

def format_bank(df: pd.DataFrame) -> str:
    if df.empty: return "Bank: no data."
    bal = df['balance'].iloc[-1]

    # Calculate Total Invested accurately
    banking_mask = df['status'].isin(['Deposit', 'Withdrawal', 'Reconciliation']) | (df['user'].astype(str).str.lower() == 'syndicate')
    net_deposits = df[banking_mask]['profit'].sum()
    total_invested = OPENING_BANK + net_deposits

    # Calculate strictly Betting P/L
    bets_mask = df['status'].isin(['Win', 'Loss', 'Push', 'Void']) & (df['user'].astype(str).str.lower() != 'syndicate')
    pl = df[bets_mask]['profit'].sum()

    return f"\U0001f3e6 Current Bank: ${bal:.2f}\nTotal Invested: ${total_invested:.2f}  |  Betting P/L: ${pl:+.2f}"

def _format_streak_line(user: str, s: dict) -> str:
    if s['type'] == 'Win': return f"• {user}: {s['length']}-win streak ✅"
    elif s['type'] == 'Loss': return f"• {user}: {s['length']}-loss streak ❌"
    else:
        if s['unbeaten'] > 1 and s['unbeaten'] >= s['winless']: return f"• {user}: 1-push ({s['unbeaten']} unbeaten) 〰️"
        elif s['winless'] > 1: return f"• {user}: 1-push ({s['winless']} winless) 〰️"
        else: return f"• {user}: 1-push 〰️"

def format_streaks(df_roi: pd.DataFrame) -> str:
    streaks = get_user_streak_summary(df_roi)
    if not streaks: return "No streak data yet."
    individuals = {u: s for u, s in streaks.items() if u != 'Team'}
    team = streaks.get('Team')
    sorted_members = sorted(individuals.items(), key=lambda x: max(x[1]['length'], x[1]['unbeaten'], x[1]['winless']), reverse=True)
    lines =["🔥 Current Streaks:"]
    for user, s in sorted_members: lines.append(_format_streak_line(user, s))
    if team: lines.append(""); lines.append(_format_streak_line('Team', team))
    return "\n".join(lines)

# ── C3: Grading engine ────────────────────────────────────────────────────────
def normalise_team(name: str) -> str: return TEAM_NAME_MAP.get(name.strip(), name.strip())

def fetch_scores_cached(sport_key: str, event_date: str) -> list:
    cache_file = CACHE_DIR / f'{sport_key}_{event_date}.json'
    if cache_file.exists(): return json.loads(cache_file.read_text())
    if not USE_ODDS_API_LIVE: return[]
    try:
        r = _requests.get(f'https://api.the-odds-api.com/v4/sports/{sport_key}/scores', params={'apiKey': ODDS_API_KEY, 'daysFrom': 1, 'dateFormat': 'iso'}, timeout=10)
        r.raise_for_status()
        completed = [e for e in r.json() if e.get('completed')]
        if completed: cache_file.write_text(json.dumps(completed, indent=2))
        return r.json()
    except Exception: return[]

def find_event(ledger_home: str, ledger_away: str, api_events: list) -> dict | None:
    home_norm = normalise_team(ledger_home)
    away_norm = normalise_team(ledger_away)
    for event in api_events:
        api_home = event.get('home_team', '')
        api_away = event.get('away_team', '')
        if api_home == home_norm and api_away == away_norm: return event
        if home_norm.lower() in api_home.lower() and away_norm.lower() in api_away.lower(): return event
    return None

def parse_score(event: dict) -> tuple | None:
    if not event.get('completed'): return None
    scores = event.get('scores')
    if not scores or len(scores) < 2: return None
    score_map = {s['name']: int(s['score']) for s in scores if s.get('score') is not None}
    if event['home_team'] not in score_map: return None
    return score_map.get(event['home_team']), score_map.get(event['away_team'])

def grade_bet(row: dict, home_score: int, away_score: int) -> tuple:
    bet_type  = row['bet_type']
    selection = str(row['selection']).strip()
    stake     = float(row['stake'])
    odds      = float(row['odds'])
    home_team = normalise_team(str(row.get('home_team', '')))
    away_team = normalise_team(str(row.get('away_team', '')))
    sel_norm  = normalise_team(selection)
    win_pay   = round(stake * (odds - 1), 2)

    if bet_type in MANUAL_REVIEW_MARKETS: return 'manual_review', 0.0

    if bet_type == 'Full Time Result':
        if selection.lower() == 'draw': won = home_score == away_score
        elif sel_norm == home_team: won = home_score > away_score
        elif sel_norm == away_team: won = away_score > home_score
        else: return 'manual_review', 0.0
        return ('Win', win_pay) if won else ('Loss', -stake)

    if bet_type == 'Draw No Bet':
        if home_score == away_score: return 'Push', 0.0
        won = (sel_norm == home_team and home_score > away_score) or (sel_norm == away_team and away_score > home_score)
        return ('Win', win_pay) if won else ('Loss', -stake)

    if bet_type == 'BTTS':
        btts = home_score > 0 and away_score > 0
        if selection.lower() in ('yes', 'btts yes'): won = btts
        elif selection.lower() in ('no', 'btts no'): won = not btts
        else: return 'manual_review', 0.0
        return ('Win', win_pay) if won else ('Loss', -stake)

    if bet_type == 'Double Chance':
        opts =[normalise_team(s.strip()) for s in (selection.split('/') if '/' in selection else [selection])]
        actual = home_team if home_score > away_score else (away_team if away_score > home_score else 'Draw')
        return ('Win', win_pay) if actual in opts else ('Loss', -stake)

    if bet_type in ('Handicap', 'Asian Handicap'):
        m = _re.match(r'^(.+?)\s*([+-]\d+\.?\d*)$', selection)
        if not m: return 'manual_review', 0.0
        sel_team, handicap = normalise_team(m.group(1).strip()), float(m.group(2))
        adj = (home_score + handicap) if sel_team == home_team else (away_score + handicap)
        opp = away_score if sel_team == home_team else home_score
        if adj > opp: return 'Win', win_pay
        if adj == opp: return 'Push', 0.0
        return 'Loss', -stake

    if bet_type in ('Total Goals', 'Goal Line', 'Goal Line (1H)'):
        total = home_score + away_score
        m = _re.match(r'(Over|Under)\s*(\d+\.?\d*)', selection, _re.IGNORECASE)
        if not m: return 'manual_review', 0.0
        direction, line = m.group(1).lower(), float(m.group(2))
        if total == line: return 'Push', 0.0
        won = (direction == 'over' and total > line) or (direction == 'under' and total < line)
        return ('Win', win_pay) if won else ('Loss', -stake)

    return 'manual_review', 0.0

def run_grading(df_pending_in: pd.DataFrame) -> pd.DataFrame:
    if len(df_pending_in) == 0: return pd.DataFrame()
    results =[]
    for competition, grp in df_pending_in.groupby('competition'):
        sport_key = SPORT_KEY_MAP.get(competition)
        if sport_key is None:
            for _, row in grp.iterrows(): results.append({'uuid': row['uuid'], 'old_status': row['status'], 'new_status': 'manual_review', 'actual_winnings': 0.0})
            continue
        try: api_events = fetch_scores_cached(sport_key, str(grp['date'].iloc[0].date()))
        except Exception:
            for _, row in grp.iterrows(): results.append({'uuid': row['uuid'], 'old_status': row['status'], 'new_status': 'manual_review', 'actual_winnings': 0.0})
            continue
        for _, row in grp.iterrows():
            if row['bet_type'] in MANUAL_REVIEW_MARKETS:
                results.append({'uuid': row['uuid'], 'old_status': row['status'], 'new_status': 'manual_review', 'actual_winnings': 0.0})
                continue
            matched = find_event(str(row['home_team']), str(row['away_team']), api_events)
            if not matched:
                results.append({'uuid': row['uuid'], 'old_status': row['status'], 'new_status': 'manual_review', 'actual_winnings': 0.0})
                continue
            score = parse_score(matched)
            if not score:
                results.append({'uuid': row['uuid'], 'old_status': row['status'], 'new_status': 'manual_review', 'actual_winnings': 0.0})
                continue

            row_dict = row.to_dict()
            row_dict['home_team'], row_dict['away_team'] = matched.get('home_team', ''), matched.get('away_team', '')
            new_status, winnings = grade_bet(row_dict, score[0], score[1])
            results.append({'uuid': row['uuid'], 'old_status': row['status'], 'new_status': new_status, 'actual_winnings': winnings})
    return pd.DataFrame(results)

# ── C4: Chronicler ───────────────────────────────────────────────────────────
def get_report_window(days: int = 7) -> tuple:
    today = date.today()
    return today - timedelta(days=days), today - timedelta(days=1)


def get_matchday_window(df_roi: pd.DataFrame, matchday: int) -> tuple:
    """Returns (week_start, week_end) date range covering all bets in the given EPL matchday,
    scoped to the current (most recent) season in the ledger."""
    if df_roi.empty:
        raise ValueError("No bet data in ledger")
    current_season = df_roi['season'].max()
    mask = (df_roi['matchday'].astype(str) == str(matchday)) & (df_roi['season'] == current_season)
    if not mask.any():
        raise ValueError(f"No bets found for matchday {matchday} in {current_season}")
    dates = df_roi.loc[mask, 'date'].dt.date
    return dates.min(), dates.max()

def get_report_persona(report_date: date = None) -> dict:
    if report_date is None: report_date = date.today()
    return CHRONICLER_PERSONAS[report_date.isocalendar().week % len(CHRONICLER_PERSONAS)]

def apply_persona(raw_answer: str, asker_name: str = 'mate', persona: dict = None) -> str:
    if not BETBOT_LIVE: return raw_answer
    if persona is None: persona = get_report_persona()
    prompt = f"You are {persona['name']}. {persona['instruction']}\nA syndicate member named {asker_name} asked a question and received this answer:\n\n{raw_answer}\n\nRewrite this answer in your character's voice. Do not change any numbers. No markdown."
    try: return _call_gemini(prompt, thinking_level='minimal', max_tokens=350)
    except Exception: return raw_answer

def build_weekly_summary(df: pd.DataFrame, df_roi: pd.DataFrame, df_free: pd.DataFrame, week_start: date, week_end: date) -> dict:
    week = df_roi[(df_roi['date'].dt.date >= week_start) & (df_roi['date'].dt.date <= week_end)]
    closed = week[week['status'].isin(['Win', 'Loss', 'Push'])]
    free_week = df_free[(df_free['date'].dt.date >= week_start) & (df_free['date'].dt.date <= week_end)]

    best_bet = worst_bet = None
    if len(closed):
        b = closed.loc[closed['profit'].idxmax()]
        best_bet  = {'event': b['event'], 'bet_type': b['bet_type'], 'selection': b['selection'], 'odds': float(b['odds']), 'profit': round(float(b['profit']), 2), 'user': b['user']}
        w = closed.loc[closed['profit'].idxmin()]
        if float(w['profit']) < 0:
            worst_bet = {'event': w['event'], 'bet_type': w['bet_type'], 'selection': w['selection'], 'odds': float(w['odds']), 'profit': round(float(w['profit']), 2), 'user': w['user']}

    market_summary = {mkt: {'bets': len(grp), 'wins': int(grp['is_win'].sum()), 'profit': round(float(grp['profit'].sum()), 2)} for mkt, grp in closed.groupby('bet_type') if len(grp) >= 2}

    # Add Member Performance logic so the Chronicler can pick a "Player of the Week"
    member_summary = {}
    for user, grp in closed.groupby('user'):
        if len(grp) == 0:
            continue  # skip members with no settled bets this week
        member_summary[user] = {
            'bets': len(grp),
            'profit': round(float(grp['profit'].sum()), 2),
            'roi_pct': round(float(grp['profit'].sum() / grp['stake'].sum() * 100), 2) if grp['stake'].sum() else 0
        }

    banking_mask = df['status'].isin(['Deposit', 'Withdrawal', 'Reconciliation']) | (df['user'].astype(str).str.lower() == 'syndicate')
    total_deposited = OPENING_BANK + round(float(df[banking_mask]['profit'].sum()), 2)

    all_bet_pl = round(float(df[~banking_mask & df['status'].isin(['Win', 'Loss', 'Push'])]['profit'].sum()), 2)

    return {
        'period': f"{week_start.strftime('%d %b')} – {week_end.strftime('%d %b %Y')}",
        'bets_placed': len(closed), 'wins': int(closed['is_win'].sum()), 'losses': int(closed['is_loss'].sum()), 'pushes': int(closed['is_push'].sum()),
        'net_profit': round(float(closed['profit'].sum()), 2), 'free_bet_profit': round(float(free_week['profit'].sum()), 2),
        'member_performance': member_summary,
        'best_bet': best_bet, 'worst_bet': worst_bet, 'market_breakdown': market_summary,
        'season_profit': round(float(df_roi['profit'].sum()), 2), 'season_roi_pct': round(float(df_roi['profit'].sum() / df_roi['stake'].sum() * 100), 2) if df_roi['stake'].sum() else 0,
        'current_balance': round(float(df['balance'].iloc[-1]), 2), 'opening_bank': round(OPENING_BANK, 2),
        'total_deposited': total_deposited, 'net_profit_all': all_bet_pl,
        'current_streaks': get_user_streaks(df_roi), 'streak_events': get_weekly_streak_breaks(df_roi, week_start, week_end),
    }

def _call_gemini(prompt: str, thinking_level: str = 'low', max_tokens: int = 1000) -> str:
    if not GEMINI_API_KEY: raise ValueError("GEMINI_API_KEY not set")
    url = f'https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent'
    headers = {'Content-Type': 'application/json', 'x-goog-api-key': GEMINI_API_KEY}
    budget = _THINKING_BUDGET.get(thinking_level, 512)
    payload = {'contents':[{'role': 'user', 'parts': [{'text': prompt}]}], 'generationConfig': {'maxOutputTokens': max_tokens, 'thinkingConfig': {'thinkingBudget': budget}}}
    for attempt in range(GRADING_RETRY_MAX):
        try:
            r = _requests.post(url, headers=headers, json=payload, timeout=30)
            r.raise_for_status()
            return '\n'.join(p['text'] for p in r.json().get('candidates', [{}])[0].get('content', {}).get('parts',[]) if 'text' in p).strip()
        except _requests.RequestException:
            if attempt == GRADING_RETRY_MAX - 1: raise
            _time.sleep(GRADING_BACKOFF ** attempt)

def get_send_target(override_chat_id: str = None) -> str:
    if override_chat_id: return override_chat_id
    if TEST_MODE: return TEST_CHAT_ID or TELEGRAM_CHAT_ID
    return TELEGRAM_CHAT_ID

def send_telegram(text: str, chat_id: str = None) -> bool:
    target = get_send_target(chat_id)
    if not TELEGRAM_BOT_TOKEN or not target: return False
    try:
        _requests.post(f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage', json={'chat_id': target, 'text': text}, timeout=10).raise_for_status()
        return True
    except _requests.RequestException: return False

def save_report_locally(text: str, report_date: date) -> Path:
    path = REPORTS_DIR / f"{report_date.strftime('%Y-%m-%d')}_report.md"
    path.write_text(text)
    return path

def run_chronicler(df: pd.DataFrame, df_roi: pd.DataFrame, df_free: pd.DataFrame,
                   concise: bool = False, days: int = 7, matchday: int = None) -> str | None:
    """Generate the Chronicler report. Always runs — scheduling is the caller's responsibility.
    Returns the report text, or None if generation fails.
    """
    rep_date = date.today()

    # Determine date window — matchday takes priority over days
    if matchday is not None:
        try:
            w_start, w_end = get_matchday_window(df_roi, matchday)
        except ValueError as e:
            return f"Could not generate report: {e}"
    else:
        w_start, w_end = get_report_window(days=days)

    persona = get_report_persona(rep_date)
    summary = build_weekly_summary(df, df_roi, df_free, w_start, w_end)

    length_instruction = (
        "Write a short, punchy summary — 3 paragraphs maximum, around 120-180 words. "
        "Cover: bottom line, player of the week, one notable bet. Skip Market Watch and Streaks."
        if concise else
        "Write a comprehensive, engaging report (around 300-450 words)."
    )
    max_tokens = 400 if concise else 1000

    text = _call_gemini(
        CHRONICLER_SYSTEM_TEMPLATE.format(
            persona_name=persona['name'],
            persona_instruction=persona['instruction'],
            length_instruction=length_instruction,
            summary_json=json.dumps(summary, indent=2),
        ),
        thinking_level=CHRONICLER_THINKING_LEVEL,
        max_tokens=max_tokens,
    )

    # Always save locally as an archive, regardless of send target
    save_report_locally(text, rep_date)

    state = load_last_run()
    state['last_report_date'] = str(rep_date)
    state['last_report_persona'] = persona['name']
    save_last_run(state)
    return text

# ── C5: Betbot ────────────────────────────────────────────────────────────────
BETBOT_HELP_TEXT = """\
🤖 Betbot — Commands

  pending        — unresolved bets
  leaderboard    — season P/L rankings
  bank           — current bankroll
  streaks        — active win/loss streaks
  report         — generate the Chronicler report
  preview_graph  — send P/L graph to your DM
  status         — bot mode & feature flags
  fixtures       — upcoming EPL fixtures

Report flags (combine freely):
  -concise       — short 3-para summary
  -days N        — look back N days (default 7)
  -round N       — cover EPL matchday N

Ask me anything:
  ? who has the best ROI this month?
  ? how did we do on BTTS bets?
  ? what's our record vs away favourites?\
"""

def parse_betbot_flags(text: str) -> tuple: return text, {'raw': False, 'persona': None}

def betbot_query(question: str, df_roi: pd.DataFrame, df_free: pd.DataFrame = None, df: pd.DataFrame = None, asker_name: str = "mate") -> str:
    return "Use the main chat input to speak with the Betbot Langchain Agent."

def fetch_upcoming_fixtures(sport_key: str = 'soccer_epl', days: int = 7) -> list:
    if not ODDS_API_KEY: return[]
    try:
        r = _requests.get(f'https://api.the-odds-api.com/v4/sports/{sport_key}/events', params={'apiKey': ODDS_API_KEY, 'dateFormat': 'iso'}, timeout=10)
        r.raise_for_status()
        cutoff = datetime.now(timezone.utc) + timedelta(days=days)
        return[e for e in r.json() if datetime.fromisoformat(e['commence_time'].replace('Z', '+00:00')) <= cutoff][:10]
    except Exception: return[]

def format_fixtures_message(fixtures: list, sport_label: str = 'EPL') -> str:
    if not fixtures: return f"No upcoming {sport_label} fixtures found."
    lines =[f"\U0001f4c5 Upcoming {sport_label} fixtures:"]
    for f in fixtures:
        try: lines.append(f"\u2022 {f.get('home_team','?')} vs {f.get('away_team','?')} — {datetime.fromisoformat(f['commence_time'].replace('Z', '+00:00')).strftime('%a %d %b %H:%M UTC')}")
        except Exception: lines.append(f"\u2022 {f.get('home_team','?')} vs {f.get('away_team','?')}")
    return '\n'.join(lines)

# ── C6: Google Sheets write-back ──────────────────────────────────────────────
def load_last_run() -> dict: return json.loads(LAST_RUN_JSON.read_text()) if LAST_RUN_JSON.exists() else {}
def save_last_run(state: dict): CACHE_DIR.mkdir(parents=True, exist_ok=True); LAST_RUN_JSON.write_text(json.dumps(state, indent=2))

def get_worksheet():
    import gspread
    import json
    from google.oauth2.service_account import Credentials

    # 1. Try to use the local file first (for bot_runner and local testing)
    if GOOGLE_CREDS_PATH.exists():
        creds = Credentials.from_service_account_file(str(GOOGLE_CREDS_PATH), scopes=['https://www.googleapis.com/auth/spreadsheets'])
    else:
        # 2. If no local file, assume we are on Streamlit Cloud and use secrets
        import streamlit as st
        try:
            creds_info = json.loads(st.secrets["gcp_service_account"])
            creds = Credentials.from_service_account_info(creds_info, scopes=['https://www.googleapis.com/auth/spreadsheets'])
        except Exception as e:
            raise Exception(f"No local {GOOGLE_CREDS_PATH} found, and Streamlit secrets failed: {e}")

    return gspread.authorize(creds).open_by_key(GSHEET_ID).worksheet(GSHEET_TAB)


def _log_failed_write(record: dict) -> None:
    """Append a structured, replayable record to the failed writes log."""
    with open(FAILED_WRITES, 'a') as f:
        f.write(json.dumps(record) + '\n')


def write_with_retry(fn, *args, max_retries=3, backoff_base=2, **kwargs):
    for attempt in range(max_retries):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            if attempt == max_retries - 1:
                # Log a minimal debug record — callers that need replayability
                # must catch this exception and log their own structured record.
                _log_failed_write({
                    'fn': fn.__name__,
                    'args': str(args)[:200],
                    'error': str(e),
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                })
                raise
            _time.sleep(backoff_base ** attempt)


def replay_failed_writes() -> int:
    """
    Re-attempt any writes that previously failed and were logged to failed_writes.log.

    Each log entry must be a JSON object with a 'fn' key identifying the operation.
    Supported operations: 'update_grade', 'append_bet'.

    Entries that succeed are removed from the log.
    Entries that fail again, or belong to unknown operations, are kept for manual review.

    Returns the number of entries still pending after the replay attempt.
    """
    if not FAILED_WRITES.exists():
        return 0

    raw = FAILED_WRITES.read_text().strip()
    if not raw:
        return 0

    lines = raw.splitlines()
    still_pending = []

    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            log.error(f"[REPLAY] Malformed log entry (not valid JSON) — keeping for manual review: {line[:120]}")
            still_pending.append(line)
            continue

        fn = record.get('fn')

        if fn == 'update_grade':
            # Requires structured keys written by update_grade's except block
            uuid      = record.get('uuid')
            status    = record.get('new_status')
            winnings  = record.get('actual_winnings')

            if not all([uuid, status, winnings is not None]):
                log.warning(f"[REPLAY] update_grade entry missing required fields — keeping: {record}")
                still_pending.append(line)
                continue

            try:
                success = update_grade(uuid, status, float(winnings))
                if success:
                    log.info(f"[REPLAY] ✅ Replayed update_grade for uuid={uuid}")
                else:
                    # update_grade returns False if the uuid wasn't found in the sheet
                    log.warning(f"[REPLAY] update_grade returned False for uuid={uuid} (row not found) — keeping")
                    still_pending.append(line)
            except Exception as e:
                log.error(f"[REPLAY] update_grade failed again for uuid={uuid}: {e} — keeping")
                still_pending.append(line)

        elif fn == 'append_bet':
            # Requires structured keys written by append_bet's except block
            required = ['user', 'home_team', 'away_team', 'competition', 'bet_type',
                        'selection', 'odds', 'stake']
            if not all(k in record for k in required):
                log.warning(f"[REPLAY] append_bet entry missing required fields — keeping: {record}")
                still_pending.append(line)
                continue

            try:
                append_bet(
                    user            = record['user'],
                    home_team       = record['home_team'],
                    away_team       = record['away_team'],
                    competition     = record['competition'],
                    bet_type        = record['bet_type'],
                    selection       = record['selection'],
                    odds            = float(record['odds']),
                    stake           = float(record['stake']),
                    bet_date        = date.fromisoformat(record['bet_date']) if record.get('bet_date') else None,
                    status          = record.get('status', 'Pending'),
                    actual_winnings = float(record.get('actual_winnings', 0.0)),
                    matchday        = record.get('matchday'),
                    sport           = record.get('sport', 'Football'),
                )
                log.info(f"[REPLAY] ✅ Replayed append_bet for {record.get('home_team')} vs {record.get('away_team')}")
            except Exception as e:
                log.error(f"[REPLAY] append_bet failed again: {e} — keeping")
                still_pending.append(line)

        else:
            log.warning(f"[REPLAY] Unknown fn='{fn}' — cannot auto-replay, keeping for manual review")
            still_pending.append(line)

    # Rewrite the log with only the entries that still need attention
    FAILED_WRITES.write_text('\n'.join(still_pending) + '\n' if still_pending else '')

    if still_pending:
        log.warning(f"[REPLAY] {len(still_pending)} entry/entries still pending after replay.")
    else:
        log.info("[REPLAY] All failed writes replayed successfully. Log cleared.")

    return len(still_pending)


def sync_local_csv() -> bool:
    if not USE_GSHEETS_LIVE:
        log.warning("USE_GSHEETS_LIVE is set to False in .env. Skipping sync.")
        return True

    try:
        log.info("Attempting to pull fresh ledger from Google Sheets...")
        df_sync = pd.DataFrame(get_worksheet().get_all_records())

        # Replace spaces in headers with underscores to match our CSV format
        df_sync.columns = [c.lower().replace(' ', '_') for c in df_sync.columns]

        banking_statuses = ['Deposit', 'Withdrawal', 'Reconciliation']
        is_banking = df_sync['status'].isin(banking_statuses) | (df_sync['user'].astype(str).str.lower() == 'syndicate')
        df_sync['is_bet'] = ~is_banking
        df_sync['is_banking'] = is_banking

        # Overwrite the local CSV with the fresh Google Sheets data
        df_sync.to_csv(LEDGER_CSV, index=False)

        # Force rebuilding of the SQLite database
        from db import build_database
        build_database()

        log.info("✅ Successfully synced from Google Sheets and rebuilt local DB.")
        return True

    except Exception as e:
        log.error(f"❌ CRITICAL: Failed to sync with Google Sheets! Error: {e}")
        return False


def _audit_log(bet_uuid: str, field: str, new_value):
    with open(LOGS_DIR / 'audit.log', 'a') as f:
        f.write(json.dumps({'uuid': bet_uuid, 'field': field, 'new_value': str(new_value), 'timestamp': datetime.now(timezone.utc).isoformat(), 'operator': 'manual'}) + '\n')


def append_bet(user: str, home_team: str, away_team: str, competition: str, bet_type: str, selection: str,
               odds: float, stake: float, bet_date: _date = None,
               status: str = 'Pending', actual_winnings: float = 0.0, matchday=None, sport='Football') -> str:
    new_uuid = _uuid.uuid4().hex[:8]
    bet_date = bet_date or _date.today()

    row = [new_uuid, str(bet_date), user, home_team, away_team, competition, bet_type, selection,
           round(float(odds), 3), round(float(stake), 2), status, round(float(actual_winnings), 2), matchday, sport]

    if not USE_GSHEETS_LIVE:
        return new_uuid

    ws = get_worksheet()
    try:
        write_with_retry(ws.append_row, row, value_input_option='USER_ENTERED')
    except Exception as e:
        # write_with_retry already logged a debug record; overwrite with structured replayable args
        _log_failed_write({
            'fn':              'append_bet',
            'user':            user,
            'home_team':       home_team,
            'away_team':       away_team,
            'competition':     competition,
            'bet_type':        bet_type,
            'selection':       selection,
            'odds':            round(float(odds), 3),
            'stake':           round(float(stake), 2),
            'bet_date':        str(bet_date),
            'status':          status,
            'actual_winnings': round(float(actual_winnings), 2),
            'matchday':        matchday,
            'sport':           sport,
            'error':           str(e),
            'timestamp':       datetime.now(timezone.utc).isoformat(),
        })
        log.error(f"[SHEETS] append_bet failed for {home_team} vs {away_team} — logged for replay.")
        return new_uuid  # Return uuid so the caller isn't left with nothing

    sync_local_csv()
    return new_uuid


def update_grade(bet_uuid: str, new_status: str, actual_winnings: float) -> bool:
    if not USE_GSHEETS_LIVE:
        return True

    ws = get_worksheet()
    try:
        row_num = ws.col_values(1).index(bet_uuid) + 1
    except ValueError:
        log.warning(f"[SHEETS] update_grade: uuid {bet_uuid} not found in sheet.")
        return False

    try:
        write_with_retry(ws.batch_update, [
            {'range': f'K{row_num}', 'values': [[new_status]]},
            {'range': f'L{row_num}', 'values': [[round(float(actual_winnings), 2)]]}
        ], value_input_option='USER_ENTERED')
    except Exception as e:
        # write_with_retry already logged a debug record; overwrite with structured replayable args
        _log_failed_write({
            'fn':              'update_grade',
            'uuid':            bet_uuid,
            'new_status':      new_status,
            'actual_winnings': round(float(actual_winnings), 2),
            'error':           str(e),
            'timestamp':       datetime.now(timezone.utc).isoformat(),
        })
        log.error(f"[SHEETS] update_grade failed for uuid={bet_uuid} — logged for replay.")
        return False

    sync_local_csv()
    return True


def manual_correction(bet_uuid: str, field: str, new_value) -> bool:
    if field not in COLUMN_MAP: return False
    if not USE_GSHEETS_LIVE: _audit_log(bet_uuid, field, new_value); return True
    ws = get_worksheet()
    try: row_num = ws.col_values(1).index(bet_uuid) + 1
    except ValueError: return False
    write_with_retry(ws.update, f'{COLUMN_MAP[field]}{row_num}', [[new_value]], value_input_option='USER_ENTERED')
    _audit_log(bet_uuid, field, new_value)
    sync_local_csv()
    return True
