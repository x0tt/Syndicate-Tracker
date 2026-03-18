#!/usr/bin/env python3
# coding: utf-8
"""
syndicate_core.py — Syndicate Tracker v4.4
==========================================
Pure logic layer. No UI, no Telegram, no scheduling.
Imported by app.py (Streamlit) and bot_runner.py (Telegram/scheduler).

Sections:
  C0  Config, secrets, constants
  C1  Data ingestion & cleaning  → load_ledger() → df, df_roi, df_pending, kpis
  C2  Analytics helpers          → leaderboard(), market_stats(), temporal_stats()
  C3  Grading engine             → run_grading(), grade_bet()
  C4  Wednesday Chronicler       → build_weekly_summary(), run_chronicler()
  C5  Betbot                     → betbot_query(), format_result()
  C6  Google Sheets write-back   → append_bet(), update_grade(), manual_correction()
"""

# ── C0: Config & secrets ──────────────────────────────────────────────────────
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

# ── Paths ──
PROJECT_ROOT  = Path(__file__).parent
DATA_DIR      = PROJECT_ROOT / 'data'
CACHE_DIR     = PROJECT_ROOT / 'cache'
REPORTS_DIR   = PROJECT_ROOT / 'reports'
LOGS_DIR      = PROJECT_ROOT / 'logs'

LEDGER_CSV    = DATA_DIR  / 'syndicate_ledger_v3.csv'
LAST_RUN_JSON = CACHE_DIR / 'last_run.json'
FAILED_WRITES = LOGS_DIR  / 'failed_writes.log'

for _d in [DATA_DIR, CACHE_DIR, REPORTS_DIR, LOGS_DIR]:
    _d.mkdir(parents=True, exist_ok=True)

# ── Secrets ──
GSHEET_ID          = os.getenv('GSHEET_ID', '')
GSHEET_TAB         = os.getenv('GSHEET_TAB', 'syndicate_ledger_v3')
GOOGLE_CREDS_PATH  = Path(os.getenv('GOOGLE_CREDENTIALS_PATH', 'credentials.json'))
ODDS_API_KEY       = os.getenv('ODDS_API_KEY', '')
GEMINI_API_KEY     = os.getenv('GEMINI_API_KEY', '')
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_ID   = os.getenv('TELEGRAM_CHAT_ID', '')
OPENING_BANK       = float(os.getenv('OPENING_BANK', '300.00'))

# ── Test mode — set in .env to keep reports out of the group chat while testing ──
# TEST_MODE=true       → all outbound messages go to TEST_CHAT_ID instead of TELEGRAM_CHAT_ID
# TEST_CHAT_ID         → your personal Telegram user ID (get it from @userinfobot)
TEST_MODE    = os.getenv('TEST_MODE', 'false').lower() == 'true'
TEST_CHAT_ID = os.getenv('TEST_CHAT_ID', '')

# ── Feature flags (override in .env or at runtime) ──
USE_GSHEETS_LIVE  = os.getenv('USE_GSHEETS_LIVE',  'true').lower()  == 'true'
USE_ODDS_API_LIVE = os.getenv('USE_ODDS_API_LIVE', 'true').lower()  == 'true'
GRADING_DRY_RUN   = os.getenv('GRADING_DRY_RUN',  'true').lower()  == 'true'
BETBOT_LIVE       = os.getenv('BETBOT_LIVE',       'true').lower()  == 'true'
CHRONICLER_LIVE   = os.getenv('CHRONICLER_LIVE',   'true').lower()  == 'true'

# ── Gemini ──
GEMINI_MODEL              = os.getenv('GEMINI_MODEL', 'gemini-3.1-flash-lite-preview')
BETBOT_THINKING_LEVEL     = 'minimal'
CHRONICLER_THINKING_LEVEL = 'low'
_THINKING_BUDGET          = {'minimal': 0, 'low': 512, 'medium': 1024, 'high': 2048}

# ── Grading ──
GRADING_SPORT     = 'soccer_epl'
GRADING_RETRY_MAX = 3
GRADING_BACKOFF   = 2

# ── Schema ──
VALID_STATUSES   = {'Win', 'Loss', 'Push', 'Void', 'Pending', 'manual_review', 'Deposit', 'Withdrawal', 'Reconciliation'}
SYNDICATE_MEMBERS = ['John', 'Richard', 'Xander', 'Team']

USER_ALIASES = {
    'Team'    : 'Team',
    'John'    : 'John',
    'Richard' : 'Richard',
    'Xander'  : 'Xander',
    'Xanderdu middle debut'                                          : 'Team',
    'Xanderdu middle 2 electric boogaloo'                           : 'Team',
    'Taken with the intent of cashing out at $4.80 or after 6 weeks': 'Team',
}

MARKET_ALIASES = {
    'Full Time Result'  : 'Full Time Result',
    'Asian Handicap'    : 'Asian Handicap',
    'Double Chance'     : 'Double Chance',
    'Draw No Bet'       : 'Draw No Bet',
    'Handicap'          : 'Handicap',
    'Relegation'        : 'Relegation',
    'BTTS'              : 'BTTS',
    'Goal Line'         : 'Goal Line',
    '1st Half Goal Line': 'Goal Line (1H)',
    'Total Goals'       : 'Total Goals',
    'Accumulator'       : 'Accumulator',
    'Bet Builder'       : 'Bet Builder',
    'To Score Anytime'  : 'To Score Anytime',
    'To Score'          : 'To Score Anytime',
    'To Qualify'        : 'To Qualify',
    'Winner'            : 'Winner',
    'Method of Victory' : 'Method of Victory',
    'FA Cup Multi'      : 'Multi',
    **{f'Round {n} multi': 'Multi' for n in range(10, 30)},
    **{f'Round {n} Multi': 'Multi' for n in range(10, 30)},
}

COLUMN_MAP = {
    'uuid': 'A', 'date': 'B', 'user': 'C', 'event': 'D',
    'market': 'E', 'selection': 'F', 'odds': 'G', 'stake': 'H',
    'status': 'I', 'actual_winnings': 'J',
}

CHRONICLER_WEEKDAY = 2  # Wednesday

CHRONICLER_PERSONAS = [
    {'name': 'The Statistician',
     'instruction': 'You are a dry, precise statistician. Present every result with '
                    'unnecessary decimal places and passive-voice hedging. Never show excitement.'},
    {'name': 'The Pundit',
     'instruction': 'You are an overconfident TV football pundit. Speak in clichés, '
                    'take full credit for correct predictions, and blame "the lads" for losses.'},
    {'name': 'The Accountant',
     'instruction': 'You are a deeply boring accountant who hates cheese and is mildly '
                    'offended by gambling but keeps doing the report anyway. Mention cheese '
                    'at least once. Refer to winnings as "revenue events".'},
    {'name': 'The Alien',
     'instruction': 'You are an alien anthropologist studying human gambling rituals. '
                    'You do not fully understand what "winning" means in this context. '
                    'Refer to the syndicate as "the tribe" and to money as "the tokens".'},
    {'name': 'The Victorian Gentleman',
     'instruction': 'You are a Victorian gentleman who finds the whole enterprise frightfully '
                    'vulgar but cannot stop reading the ledger. Express moral disapproval '
                    'while clearly being riveted. Use "frightful", "beastly", and "capital".'},
    {'name': 'The Cricket Commentator',
     'instruction': 'You are a cricket commentator who only knows cricket. Describe all '
                    'football results using cricket terminology. Seem confused but carry on '
                    'professionally. Refer to goals as "wickets" and matches as "overs".'},
    {'name': 'The Intern',
     'instruction': 'You are an over-enthusiastic intern presenting your very first '
                    'spreadsheet to the team. Use excessive bullet points, say "so basically" '
                    'a lot, and be visibly nervous about the negative ROI.'},
    {'name': 'The Conspiracy Theorist',
     'instruction': 'You are convinced that all draws are rigged by Big Football. '
                    'Every loss is suspicious. Every win is "despite them". '
                    'Connect unrelated results into a coherent (but wrong) narrative.'},
    {'name': 'The Pirate',
     'instruction': 'You are a pirate who desperately wants to attack Australia but keeps '
                    'getting distracted by the betting results. Nautical metaphors throughout. '
                    'End every report with a revised plan to sail east.'},
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
    'EHF Champions League Women 24/25' : None,
    "VNL Women's 25"                   : None,
}

GRADEABLE_MARKETS = {
    'Full Time Result', 'Draw No Bet', 'Handicap',
    'Asian Handicap', 'BTTS', 'Double Chance',
    'Goal Line', 'Goal Line (1H)', 'Total Goals',
}
MANUAL_REVIEW_MARKETS = {
    'Accumulator', 'Multi', 'Bet Builder', 'To Qualify',
    'Winner', 'Relegation', 'To Score Anytime', 'Method of Victory',
}

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

STRICT RULES — you must follow these exactly:
1. Every number, stat, profit figure, and result MUST come verbatim from
   the JSON summary below. Do not invent, round differently, or embellish.
2. Keep the report under 300 words.
3. Structure: opening line in persona voice, weekly results, best bet,
   worst bet (ONLY if worst_bet is not null — if null, skip it entirely,
   there were no losses this week), season standing, closing line in persona voice.
4. Address the syndicate informally — they know each other well.
5. Use the currency symbol $ for all money figures.
6. NO markdown formatting whatsoever — no **bold**, no _italics_, no #headers.
   Plain text only. Use blank lines to separate sections.
7. NEVER use JSON key names in the prose. Write naturally:
   "net profit" not "netprofit", "best bet" not "bestbet",
   "season ROI" not "seasonroipct", "free bet profit" not "freebetprofit".
8. ALWAYS mention if someone is on an active streak of 3 or more, or if a notable
   streak was broken this week. Check "streak_events" and "current_streaks" in the
   data — if either contains relevant information, weave it into the report naturally.

BALANCE FIELDS — read carefully before mentioning money:
- opening_bank: the initial deposit when the syndicate started. A baseline only.
- total_deposited: all top-up deposits made since opening (may be $0 if none yet).
- net_profit_all: total P&L from all betting (paid bets + free bets combined).
  Negative = net loss from betting.
- current_balance: the actual cash in the bank right now.
  current_balance = opening_bank + total_deposited + net_profit_all.
- season_profit: P&L from paid (staked) bets only, used for ROI calculations.
  Lower than net_profit_all because it excludes free bet winnings.
- To say whether the syndicate is UP or DOWN overall:
  If total_deposited > 0: compare current_balance to (opening_bank + total_deposited).
  If total_deposited = 0: compare current_balance to opening_bank directly.
  If current_balance > total capital deployed they are up; if less, they are down.
- NEVER compare current_balance to opening_bank alone when total_deposited > 0.

Weekly summary data:
{summary_json}
"""


# ── C1: Data ingestion & feature engineering ──────────────────────────────────

def load_ledger(csv_path: Path = LEDGER_CSV) -> tuple:
    """
    Loads, cleans, and enriches the ledger CSV.
    Returns (df, df_roi, df_free, df_pending, kpis).
    df_roi  — settled bets with stake > 0 (ROI-eligible)
    df_free — free bets (stake == 0)
    df_pending — status == 'Pending'
    kpis    — dict of pre-computed KPIs for dashboard + Chronicler
    """
    df = pd.read_csv(csv_path, parse_dates=['date'])

    # ── Cleaning ──
    df['status']     = df['status'].str.strip()
    df['user_raw']   = df['user'].copy()
    df['market_raw'] = df['market'].copy()
    df['user']       = df['user'].map(USER_ALIASES)
    df['market']     = df['market'].map(MARKET_ALIASES)
    df['is_free_bet'] = df['stake'] == 0.0

    # ── Derived columns ──
    df['profit']       = df['actual_winnings']
    df['implied_prob'] = 1 / df['odds']
    df['is_win']       = df['status'] == 'Win'
    df['is_loss']      = df['status'] == 'Loss'
    df['is_push']      = df['status'] == 'Push'

    odds_bins   = [0, 1.5, 2.0, 3.0, 999]
    odds_labels = ['<1.5', '1.5-2.0', '2.0-3.0', '3.0+']
    df['odds_band'] = pd.cut(df['odds'], bins=odds_bins, labels=odds_labels, right=False)

    df['dotw']  = df['date'].dt.day_name()
    df['month'] = df['date'].dt.to_period('M').astype(str)
    df['year']  = df['date'].dt.year
    df['week_number'] = df['date'].dt.isocalendar().week.astype(int)
    df['season'] = df['date'].apply(
        lambda d: '2024/25' if d < pd.Timestamp('2025-07-01') else '2025/26'
    )

    # ── Cumulative / rolling ──
    df_sorted        = df.sort_values('date').reset_index(drop=True)
    df_sorted['cum_profit']    = df_sorted['profit'].cumsum()
    df_sorted['balance']       = OPENING_BANK + df_sorted['cum_profit']
    df_sorted['peak_balance']  = df_sorted['balance'].cummax()
    df_sorted['drawdown']      = df_sorted['balance'] - df_sorted['peak_balance']
    df_sorted['drawdown_pct']  = df_sorted['drawdown'] / df_sorted['peak_balance'] * 100
    df_sorted['rolling_roi_10'] = (
        df_sorted['profit'].rolling(10).sum() /
        df_sorted['stake'].replace(0, np.nan).rolling(10).sum() * 100
    )
    df = df_sorted

    # ── Segmented views ──
    # Deposit/Withdrawal rows are real money events — included in balance cumsum
    # but excluded from all bet analytics (ROI, win rate, leaderboard, grading)
    df_deposits = df[df['status'].isin(['Deposit', 'Withdrawal', 'Reconciliation'])].copy()
    df_bet      = df[~df['status'].isin(['Deposit', 'Withdrawal', 'Reconciliation'])].copy()
    df_roi      = df_bet[(df_bet['status'].isin(['Win', 'Loss', 'Push'])) & (~df_bet['is_free_bet'])].copy()
    df_free     = df_bet[(df_bet['status'].isin(['Win', 'Loss', 'Push'])) & (df_bet['is_free_bet'])].copy()
    df_pending  = df_bet[df_bet['status'] == 'Pending'].copy()

    # ── KPIs ──
    total_bets    = len(df)
    total_closed  = len(df[df['status'].isin(['Win', 'Loss', 'Push', 'Void'])])
    total_wins    = int(df_roi['is_win'].sum())
    total_losses  = int(df_roi['is_loss'].sum())
    total_pushes  = int(df_roi['is_push'].sum())
    total_free    = int(df['is_free_bet'].sum())
    total_pending = len(df_pending)

    total_staked  = df_roi['stake'].sum()
    profit_all    = df[df['status'].isin(['Win','Loss','Push'])]['profit'].sum()
    free_contrib  = df_free['profit'].sum()
    profit_roi    = df_roi['profit'].sum()
    roi_pct       = profit_roi / total_staked * 100 if total_staked else 0
    current_balance = df['balance'].iloc[-1]

    win_rate   = df_roi['is_win'].mean()   if not df_roi.empty else 0.0
    avg_odds   = df_roi['odds'].mean()     if not df_roi.empty else 0.0
    avg_stake  = df_roi['stake'].mean()    if not df_roi.empty else 0.0
    avg_profit = df_roi['profit'].mean()   if not df_roi.empty else 0.0
    ev         = (win_rate * avg_odds) - 1 if avg_odds else 0.0
    avg_implied      = df_roi['implied_prob'].mean() if not df_roi.empty else 0.0
    calibration_edge = win_rate - avg_implied

    if not df_roi.empty:
        best_bet  = df_roi.loc[df_roi['profit'].idxmax()]
        worst_bet = df_roi.loc[df_roi['profit'].idxmin()]
        best_bet_kpis = {
            'best_bet_event':   best_bet['event'],
            'best_bet_user':    best_bet['user'],
            'best_bet_profit':  round(float(best_bet['profit']), 2),
            'worst_bet_event':  worst_bet['event'],
            'worst_bet_user':   worst_bet['user'],
            'worst_bet_profit': round(float(worst_bet['profit']), 2),
        }
    else:
        best_bet_kpis = {
            'best_bet_event':   'No settled bets yet',
            'best_bet_user':    '—',
            'best_bet_profit':  0.0,
            'worst_bet_event':  'No settled bets yet',
            'worst_bet_user':   '—',
            'worst_bet_profit': 0.0,
        }

    peak_balance = df['peak_balance'].max()
    max_drawdown = df['drawdown'].min()
    max_dd_pct   = df['drawdown_pct'].min()
    peak_idx     = df['balance'].idxmax()
    trough_idx   = df.loc[peak_idx:, 'balance'].idxmin()
    peak_date    = df.loc[peak_idx, 'date'].date()
    trough_date  = df.loc[trough_idx, 'date'].date()
    recovery_df  = df.loc[trough_idx:][df.loc[trough_idx:, 'balance'] >= peak_balance]
    recovery_date = recovery_df.iloc[0]['date'].date() if len(recovery_df) else 'Not yet recovered'

    if not df_roi.empty:
        streak_df = df_roi[df_roi['status'].isin(['Win', 'Loss', 'Push'])].copy()
        if not streak_df.empty:
            streak_df['streak_id'] = (streak_df['status'] != streak_df['status'].shift()).cumsum()
            streaks = streak_df.groupby(['streak_id', 'status']).size().reset_index(name='length')
            win_streaks  = streaks[streaks['status'] == 'Win']['length']
            loss_streaks = streaks[streaks['status'] == 'Loss']['length']
            max_win_streak  = int(win_streaks.max())  if len(win_streaks)  else 0
            max_loss_streak = int(loss_streaks.max()) if len(loss_streaks) else 0
            current_status  = streak_df['status'].iloc[-1]
            current_streak  = int(streaks[streaks['streak_id'] == streaks['streak_id'].max()]['length'].values[0])
        else:
            max_win_streak = max_loss_streak = current_streak = 0
            current_status = '—'
    else:
        max_win_streak = max_loss_streak = current_streak = 0
        current_status = '—'

    kpis = {
        'total_bets': total_bets, 'total_closed': total_closed,
        'roi_eligible': len(df_roi), 'total_wins': total_wins,
        'total_losses': total_losses, 'total_pushes': total_pushes,
        'total_free_bets': total_free, 'total_pending': total_pending,
        'opening_bank': round(OPENING_BANK, 2),
        'current_balance': round(current_balance, 2),
        'total_staked': round(total_staked, 2),
        'profit_all': round(profit_all, 2),
        'profit_roi': round(profit_roi, 2),
        'free_bet_contrib': round(free_contrib, 2),
        'roi_pct': round(roi_pct, 2),
        'win_rate': round(float(win_rate), 4),
        'avg_odds': round(float(avg_odds), 4),
        'avg_stake': round(float(avg_stake), 4),
        'avg_profit': round(float(avg_profit), 4),
        'max_win_streak': max_win_streak,
        'max_loss_streak': max_loss_streak,
        'current_streak': current_streak,
        'current_streak_type': current_status,
        'ev': round(ev, 4),
        'calibration_edge': round(float(calibration_edge), 4),
        'peak_balance': round(peak_balance, 2),
        'max_drawdown': round(float(max_drawdown), 2),
        'max_drawdown_pct': round(float(max_dd_pct), 1),
        'peak_date': str(peak_date),
        'trough_date': str(trough_date),
        'recovery_date': str(recovery_date),
        **best_bet_kpis,
    }

    return df, df_roi, df_free, df_pending, kpis


# ── C2: Analytics helpers ─────────────────────────────────────────────────────

def get_leaderboard(df_roi: pd.DataFrame) -> pd.DataFrame:
    lb = df_roi.groupby('user').agg(
        bets=('uuid', 'count'), wins=('is_win', 'sum'), losses=('is_loss', 'sum'),
        pushes=('is_push', 'sum'), staked=('stake', 'sum'), profit=('profit', 'sum'),
        avg_odds=('odds', 'mean'), avg_stake=('stake', 'mean'),
        implied_prob=('implied_prob', 'mean'), win_rate=('is_win', 'mean'),
    ).assign(
        roi_pct=lambda x: x['profit'] / x['staked'] * 100,
        calibration_edge=lambda x: x['win_rate'] - x['implied_prob'],
    ).sort_values('profit', ascending=False)
    for col in ['wins', 'losses', 'pushes']:
        lb[col] = lb[col].astype(int)
    return lb


def get_market_stats(df_roi: pd.DataFrame) -> pd.DataFrame:
    ms = df_roi.groupby('market').agg(
        bets=('uuid', 'count'), wins=('is_win', 'sum'), staked=('stake', 'sum'),
        profit=('profit', 'sum'), avg_odds=('odds', 'mean'),
        win_rate=('is_win', 'mean'), implied_prob=('implied_prob', 'mean'),
    ).assign(
        roi_pct=lambda x: x['profit'] / x['staked'] * 100,
        edge=lambda x: x['win_rate'] - x['implied_prob'],
    ).sort_values('bets', ascending=False)
    ms['wins'] = ms['wins'].astype(int)
    return ms


def get_dotw_stats(df_roi: pd.DataFrame) -> pd.DataFrame:
    order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    ds = df_roi.groupby('dotw').agg(
        bets=('uuid', 'count'), win_rate=('is_win', 'mean'),
        staked=('stake', 'sum'), profit=('profit', 'sum'), avg_odds=('odds', 'mean'),
    ).assign(roi_pct=lambda x: x['profit'] / x['staked'] * 100)
    return ds.reindex([d for d in order if d in ds.index])


def get_monthly_stats(df_roi: pd.DataFrame) -> pd.DataFrame:
    ms = df_roi.groupby('month').agg(
        bets=('uuid', 'count'), win_rate=('is_win', 'mean'),
        staked=('stake', 'sum'), profit=('profit', 'sum'),
    ).assign(roi_pct=lambda x: x['profit'] / x['staked'] * 100)
    ms['cum_profit'] = ms['profit'].cumsum()
    return ms


def kelly(avg_odds: float, win_rate: float) -> float:
    """Full Kelly fraction. Positive = +EV."""
    b = avg_odds - 1
    q = 1 - win_rate
    return (b * win_rate - q) / b if b else 0.0


def get_user_streak_summary(df_roi: pd.DataFrame) -> dict:
    """
    Returns rich streak info per user including Push as a valid result.

    Each entry contains:
      type     — last result (Win / Loss / Push)
      length   — consecutive run of that exact result type
      unbeaten — consecutive bets with no Loss (Wins + Pushes)
      winless  — consecutive bets with no Win  (Losses + Pushes)

    Display logic:
      Win  → "{N}-win streak"           (unbeaten == length, no need to show both)
      Loss → "{N}-loss streak"          (winless  == length, no need to show both)
      Push → "1-push ({N} unbeaten)"   if unbeaten > 1 and unbeaten >= winless
           → "1-push ({N} winless)"    if winless  > 1 and winless  > unbeaten
           → "1-push"                  if neither run is notable
    """
    result = {}
    df = df_roi[df_roi['status'].isin(['Win', 'Loss', 'Push'])].sort_values('date')
    for user, grp in df.groupby('user'):
        if grp.empty:
            continue
        statuses = grp['status'].tolist()

        # Current result streak
        current_type = statuses[-1]
        current_len = 1
        for s in reversed(statuses[:-1]):
            if s == current_type:
                current_len += 1
            else:
                break

        # Unbeaten run — walk back while result != Loss
        unbeaten = 0
        for s in reversed(statuses):
            if s != 'Loss':
                unbeaten += 1
            else:
                break

        # Winless run — walk back while result != Win
        winless = 0
        for s in reversed(statuses):
            if s != 'Win':
                winless += 1
            else:
                break

        result[user] = {
            'type'    : current_type,
            'length'  : current_len,
            'unbeaten': unbeaten,
            'winless' : winless,
        }
    return result


def get_user_streaks(df_roi: pd.DataFrame) -> dict:
    """Legacy wrapper — returns get_user_streak_summary for backward compatibility."""
    return get_user_streak_summary(df_roi)


def get_weekly_streak_breaks(df_roi: pd.DataFrame, week_start: date, week_end: date) -> list:
    """Finds streaks of 3+ that were broken by a bet settled during the report week."""
    events = []
    df = df_roi[df_roi['status'].isin(['Win', 'Loss', 'Push'])].sort_values('date').copy()
    for user, grp in df.groupby('user'):
        if len(grp) < 2:
            continue
        statuses   = grp['status'].tolist()
        dates      = [d.date() for d in grp['date'].tolist()]
        streak_len  = 1
        streak_type = statuses[0]
        for i in range(1, len(statuses)):
            if statuses[i] == streak_type:
                streak_len += 1
            else:
                if streak_len >= 3 and week_start <= dates[i] <= week_end:
                    events.append(
                        f"{user} broke a {streak_len}-{streak_type.lower()} streak."
                    )
                streak_len  = 1
                streak_type = statuses[i]
    return events


# ── C2b: Hardcoded command formatters ────────────────────────────────────────

def format_pending(df_pending: pd.DataFrame) -> str:
    """Returns a plain-text summary of all pending bets."""
    if df_pending.empty:
        return "\u23f3 No pending bets right now."
    lines = [f"\u23f3 Pending Bets ({len(df_pending)}):"]
    for _, r in df_pending.iterrows():
        lines.append(f"\u2022 {r['user']}: {r['event']} \u2014 {r['selection']} @ {r['odds']}")
    return "\n".join(lines)


def format_leaderboard(df_roi: pd.DataFrame) -> str:
    """Returns a plain-text profit/ROI leaderboard for individual members (excludes Team)."""
    lb = get_leaderboard(df_roi)
    lb = lb[lb.index != 'Team']
    lines = ["\U0001f3c6 Leaderboard:"]
    for user, row in lb.iterrows():
        lines.append(
            f"\u2022 {user}: ${row['profit']:.2f} profit "
            f"({row['roi_pct']:.1f}% ROI, {int(row['bets'])} bets)"
        )
    return "\n".join(lines)


def format_bank(df: pd.DataFrame) -> str:
    """Returns the current bank balance."""
    if df.empty:
        return "Bank: no data."
    bal    = df['balance'].iloc[-1]
    change = bal - OPENING_BANK
    sign   = "+" if change >= 0 else ""
    return (
        f"\U0001f3e6 Current Bank: ${bal:.2f}\n"
        f"Opening bank: ${OPENING_BANK:.2f}  ({sign}${change:.2f})"
    )


def _format_streak_line(user: str, s: dict) -> str:
    """Formats a single member's streak using rich display logic."""
    if s['type'] == 'Win':
        return f"• {user}: {s['length']}-win streak ✅"
    elif s['type'] == 'Loss':
        return f"• {user}: {s['length']}-loss streak ❌"
    else:  # Push
        if s['unbeaten'] > 1 and s['unbeaten'] >= s['winless']:
            return f"• {user}: 1-push ({s['unbeaten']} unbeaten) 〰️"
        elif s['winless'] > 1:
            return f"• {user}: 1-push ({s['winless']} winless) 〰️"
        else:
            return f"• {user}: 1-push 〰️"


def format_streaks(df_roi: pd.DataFrame) -> str:
    """Returns each member's current streak, Team pinned to bottom."""
    streaks = get_user_streak_summary(df_roi)
    if not streaks:
        return "No streak data yet."
    individuals    = {u: s for u, s in streaks.items() if u != 'Team'}
    team           = streaks.get('Team')
    # Sort by most notable run length
    def sort_key(item):
        s = item[1]
        return max(s['length'], s['unbeaten'], s['winless'])
    sorted_members = sorted(individuals.items(), key=sort_key, reverse=True)
    lines = ["🔥 Current Streaks:"]
    for user, s in sorted_members:
        lines.append(_format_streak_line(user, s))
    if team:
        lines.append("")
        lines.append(_format_streak_line('Team', team))
    return "\n".join(lines)


# ── C3: Grading engine ────────────────────────────────────────────────────────

def normalise_team(name: str) -> str:
    return TEAM_NAME_MAP.get(name.strip(), name.strip())


def _fetch_scores_live(sport_key: str, days_from: int = 1) -> list:
    url = f'https://api.the-odds-api.com/v4/sports/{sport_key}/scores'
    params = {'apiKey': ODDS_API_KEY, 'daysFrom': days_from, 'dateFormat': 'iso'}
    for attempt in range(GRADING_RETRY_MAX):
        try:
            r = _requests.get(url, params=params, timeout=10)
            log.info(f"Odds API [{sport_key}] status={r.status_code} "
                     f"remaining={r.headers.get('x-requests-remaining','?')}")
            r.raise_for_status()
            return r.json()
        except _requests.RequestException as e:
            if attempt == GRADING_RETRY_MAX - 1:
                raise
            _time.sleep(GRADING_BACKOFF ** attempt)


def fetch_scores_cached(sport_key: str, event_date: str) -> list:
    cache_file = CACHE_DIR / f'{sport_key}_{event_date}.json'
    if cache_file.exists():
        log.info(f"Cache hit: {cache_file.name}")
        return json.loads(cache_file.read_text())
    if not USE_ODDS_API_LIVE:
        log.warning("USE_ODDS_API_LIVE=False — cannot fetch live scores")
        return []
    scores = _fetch_scores_live(sport_key, days_from=1)
    completed = [e for e in scores if e.get('completed')]
    if completed:
        cache_file.write_text(json.dumps(completed, indent=2))
        log.info(f"Cached {len(completed)} completed events → {cache_file.name}")
    return scores


def find_event(ledger_event: str, api_events: list) -> dict | None:
    if ' vs ' not in ledger_event:
        return None
    parts = ledger_event.split(' vs ', 1)
    home_norm = normalise_team(parts[0].strip())
    away_norm = normalise_team(parts[1].strip())
    for event in api_events:
        api_home = event.get('home_team', '')
        api_away = event.get('away_team', '')
        if api_home == home_norm and api_away == away_norm:
            return event
        if home_norm.lower() in api_home.lower() and away_norm.lower() in api_away.lower():
            return event
    return None


def parse_score(event: dict) -> tuple | None:
    if not event.get('completed'):
        return None
    scores = event.get('scores')
    if not scores or len(scores) < 2:
        return None
    home_team = event['home_team']
    try:
        score_map = {s['name']: int(s['score']) for s in scores if s.get('score') is not None}
    except (ValueError, KeyError):
        return None
    if home_team not in score_map:
        return None
    away_team = event['away_team']
    return score_map.get(home_team), score_map.get(away_team)


def grade_bet(row: dict, home_score: int, away_score: int) -> tuple:
    """Returns (new_status, actual_winnings)."""
    market    = row['market']
    selection = str(row['selection']).strip()
    stake     = float(row['stake'])
    odds      = float(row['odds'])
    home_team = normalise_team(str(row.get('home_team', '')))
    away_team = normalise_team(str(row.get('away_team', '')))
    sel_norm  = normalise_team(selection)
    win_pay   = round(stake * (odds - 1), 2)

    if market in MANUAL_REVIEW_MARKETS:
        return 'manual_review', 0.0

    if market == 'Full Time Result':
        if selection.lower() == 'draw':
            won = home_score == away_score
        elif sel_norm == home_team:
            won = home_score > away_score
        elif sel_norm == away_team:
            won = away_score > home_score
        else:
            return 'manual_review', 0.0
        return ('Win', win_pay) if won else ('Loss', -stake)

    if market == 'Draw No Bet':
        if home_score == away_score:
            return 'Push', 0.0
        won = (sel_norm == home_team and home_score > away_score) or \
              (sel_norm == away_team and away_score > home_score)
        return ('Win', win_pay) if won else ('Loss', -stake)

    if market == 'BTTS':
        btts = home_score > 0 and away_score > 0
        sel_lower = selection.lower()
        if sel_lower in ('yes', 'btts yes'):
            won = btts
        elif sel_lower in ('no', 'btts no'):
            won = not btts
        else:
            return 'manual_review', 0.0
        return ('Win', win_pay) if won else ('Loss', -stake)

    if market == 'Double Chance':
        opts = [normalise_team(s.strip())
                for s in (selection.split('/') if '/' in selection else [selection])]
        actual = home_team if home_score > away_score else (
            away_team if away_score > home_score else 'Draw')
        won = actual in opts
        return ('Win', win_pay) if won else ('Loss', -stake)

    if market in ('Handicap', 'Asian Handicap'):
        m = _re.match(r'^(.+?)\s*([+-]\d+\.?\d*)$', selection)
        if not m:
            return 'manual_review', 0.0
        sel_team = normalise_team(m.group(1).strip())
        handicap = float(m.group(2))
        adj = (home_score + handicap) if sel_team == home_team else (away_score + handicap)
        opp = away_score if sel_team == home_team else home_score
        if adj > opp: return 'Win', win_pay
        if adj == opp: return 'Push', 0.0
        return 'Loss', -stake

    if market in ('Total Goals', 'Goal Line', 'Goal Line (1H)'):
        total = home_score + away_score
        m = _re.match(r'(Over|Under)\s*(\d+\.?\d*)', selection, _re.IGNORECASE)
        if not m:
            return 'manual_review', 0.0
        direction = m.group(1).lower()
        line = float(m.group(2))
        if total == line:
            return 'Push', 0.0
        won = (direction == 'over' and total > line) or (direction == 'under' and total < line)
        return ('Win', win_pay) if won else ('Loss', -stake)

    return 'manual_review', 0.0


def run_grading(df_pending_in: pd.DataFrame) -> pd.DataFrame:
    if len(df_pending_in) == 0:
        return pd.DataFrame()
    results = []
    for competition, grp in df_pending_in.groupby('competition'):
        sport_key = SPORT_KEY_MAP.get(competition)
        if sport_key is None:
            for _, row in grp.iterrows():
                results.append({'uuid': row['uuid'], 'event': row['event'],
                    'market': row['market'], 'selection': row['selection'],
                    'old_status': row['status'], 'new_status': 'manual_review',
                    'actual_winnings': 0.0, 'notes': f'No API key for: {competition}'})
            continue
        event_date = str(grp['date'].iloc[0].date())
        try:
            api_events = fetch_scores_cached(sport_key, event_date)
        except Exception as e:
            log.error(f"Score fetch failed for {competition}: {e}")
            for _, row in grp.iterrows():
                results.append({'uuid': row['uuid'], 'event': row['event'],
                    'market': row['market'], 'selection': row['selection'],
                    'old_status': row['status'], 'new_status': 'manual_review',
                    'actual_winnings': 0.0, 'notes': f'API fetch failed: {e}'})
            continue
        for _, row in grp.iterrows():
            if row['market'] in MANUAL_REVIEW_MARKETS:
                results.append({'uuid': row['uuid'], 'event': row['event'],
                    'market': row['market'], 'selection': row['selection'],
                    'old_status': row['status'], 'new_status': 'manual_review',
                    'actual_winnings': 0.0, 'notes': 'Manual market'})
                continue
            matched = find_event(row['event'], api_events)
            if matched is None:
                results.append({'uuid': row['uuid'], 'event': row['event'],
                    'market': row['market'], 'selection': row['selection'],
                    'old_status': row['status'], 'new_status': 'manual_review',
                    'actual_winnings': 0.0, 'notes': 'Event not found in API'})
                continue
            score = parse_score(matched)
            if score is None:
                results.append({'uuid': row['uuid'], 'event': row['event'],
                    'market': row['market'], 'selection': row['selection'],
                    'old_status': row['status'], 'new_status': 'manual_review',
                    'actual_winnings': 0.0, 'notes': 'Score unavailable'})
                continue
            row_dict = row.to_dict()
            row_dict['home_team'] = matched.get('home_team', '')
            row_dict['away_team'] = matched.get('away_team', '')
            new_status, winnings = grade_bet(row_dict, score[0], score[1])
            results.append({'uuid': row['uuid'], 'event': row['event'],
                'market': row['market'], 'selection': row['selection'],
                'old_status': row['status'], 'new_status': new_status,
                'actual_winnings': winnings, 'notes': f"{score[0]}-{score[1]}"})
    return pd.DataFrame(results)


# ── C4: Wednesday Chronicler ──────────────────────────────────────────────────

def get_report_window() -> tuple:
    """Returns a rolling 7-day window ending yesterday.
    Run on Wednesday 18 Mar → covers 11 Mar–17 Mar, capturing the weekend bets.
    """
    today      = date.today()
    week_end   = today - timedelta(days=1)
    week_start = today - timedelta(days=7)
    return week_start, week_end


def get_report_persona(report_date: date = None) -> dict:
    if report_date is None:
        report_date = date.today()
    week = report_date.isocalendar().week
    return CHRONICLER_PERSONAS[week % len(CHRONICLER_PERSONAS)]


def apply_persona(raw_answer: str, asker_name: str = 'mate',
                  persona: dict = None) -> str:
    """
    Takes a plain-text answer from the LangChain SQL agent and rewrites it
    in the voice of the current rotating persona.

    This is intentionally a thin wrapper — the agent already has the facts
    correct, so this call just handles style. Uses minimal tokens.
    """
    if not BETBOT_LIVE:
        return raw_answer

    if persona is None:
        persona = get_report_persona()

    prompt = (
        f"You are {persona['name']}. {persona['instruction']}\n\n"
        f"A syndicate member named {asker_name} asked a question about the betting ledger "
        f"and received this factually correct answer:\n\n"
        f"{raw_answer}\n\n"
        f"Rewrite this answer in your character's voice. "
        f"Do not change any numbers, names, or facts. Keep it concise — no more than "
        f"a short paragraph. Do not add information that wasn't in the original answer.\n\n"
        f"Formatting rules (always follow these):\n"
        f"- For profits/gains: $12.50\n"
        f"- For losses, the number is already negative in the data. Write it as -$12.50 (never $-12.50).\n"
        f"- Never say 'a loss of -$12.50' — that's a double negative. Say 'a loss of $12.50' OR '-$12.50 profit'.\n"
        f"- Use % for all percentage figures (e.g. 54.2%)\n"
        f"- Never use tables or markdown — plain text only, this is a Telegram message\n"
        f"- If listing multiple items, use a simple line break between them, not a table"
    )

    try:
        return _call_gemini(prompt, thinking_level='minimal', max_tokens=350)
    except Exception as e:
        log.warning(f"[PERSONA] Rewrite failed ({e}), returning raw answer.")
        return raw_answer  # fail safe — always return something useful


def build_weekly_summary(df: pd.DataFrame, df_roi: pd.DataFrame,
                         df_free: pd.DataFrame, week_start: date, week_end: date) -> dict:
    mask  = (df_roi['date'].dt.date >= week_start) & (df_roi['date'].dt.date <= week_end)
    week  = df_roi[mask].copy()
    closed = week[week['status'].isin(['Win', 'Loss', 'Push'])]

    free_mask = (df_free['date'].dt.date >= week_start) & (df_free['date'].dt.date <= week_end)
    free_week = df_free[free_mask]

    best_bet = worst_bet = None
    if len(closed):
        b = closed.loc[closed['profit'].idxmax()]
        best_bet  = {'event': b['event'], 'market': b['market'], 'selection': b['selection'],
                     'odds': float(b['odds']), 'profit': round(float(b['profit']), 2), 'user': b['user']}
        # Only populate worst_bet if there was an actual loss this week.
        # Avoids naming a push as "worst bet" on all-win/push weeks.
        w = closed.loc[closed['profit'].idxmin()]
        if float(w['profit']) < 0:
            worst_bet = {'event': w['event'], 'market': w['market'], 'selection': w['selection'],
                         'odds': float(w['odds']), 'profit': round(float(w['profit']), 2), 'user': w['user']}

    market_summary = {}
    if len(closed):
        for mkt, grp in closed.groupby('market'):
            if len(grp) >= 2:
                market_summary[mkt] = {'bets': len(grp), 'wins': int(grp['is_win'].sum()),
                                       'profit': round(float(grp['profit'].sum()), 2)}

    total_deposited = round(float(
        df[df['status'].isin(['Deposit', 'Withdrawal', 'Reconciliation'])]['actual_winnings'].sum()
    ), 2)
    all_bet_pl = round(float(
        df[df['status'].isin(['Win', 'Loss', 'Push'])]['actual_winnings'].sum()
    ), 2)

    return {
        'period'          : f"{week_start.strftime('%d %b')} – {week_end.strftime('%d %b %Y')}",
        'bets_placed'     : len(closed),
        'wins'            : int(closed['is_win'].sum()),
        'losses'          : int(closed['is_loss'].sum()),
        'pushes'          : int(closed['is_push'].sum()),
        'net_profit'      : round(float(closed['profit'].sum()), 2),
        'free_bet_profit' : round(float(free_week['profit'].sum()), 2),
        'best_bet'        : best_bet,
        'worst_bet'       : worst_bet,
        'market_breakdown': market_summary,
        'season_profit'   : round(float(df_roi['profit'].sum()), 2),
        'season_roi_pct'  : round(float(df_roi['profit'].sum() / df_roi['stake'].sum() * 100), 2),
        'current_balance' : round(float(df['balance'].iloc[-1]), 2),
        'opening_bank'    : round(OPENING_BANK, 2),
        'total_deposited' : total_deposited,
        'net_profit_all'  : all_bet_pl,
        'current_streaks' : get_user_streaks(df_roi),
        'streak_events'   : get_weekly_streak_breaks(df_roi, week_start, week_end),
    }


def _call_gemini(prompt: str, thinking_level: str = 'low', max_tokens: int = 1000) -> str:
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY not set")
    url     = f'https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent'
    headers = {'Content-Type': 'application/json', 'x-goog-api-key': GEMINI_API_KEY}
    budget  = _THINKING_BUDGET.get(thinking_level, 512)
    payload = {
        'contents': [{'role': 'user', 'parts': [{'text': prompt}]}],
        'generationConfig': {
            'maxOutputTokens': max_tokens,
            'thinkingConfig': {'thinkingBudget': budget},
        },
    }
    for attempt in range(GRADING_RETRY_MAX):
        try:
            r = _requests.post(url, headers=headers, json=payload, timeout=30)
            r.raise_for_status()
            response_data = r.json()
            candidate = response_data.get('candidates', [{}])[0]
            parts = candidate.get('content', {}).get('parts', [])
            # Log thinking vs text token usage if available
            usage = response_data.get('usageMetadata', {})
            thinking_tokens = usage.get('thoughtsTokenCount', 0)
            output_tokens   = usage.get('candidatesTokenCount', 0)
            if thinking_tokens:
                log.info(f"[GEMINI] thinking={thinking_tokens} output={output_tokens} tokens")
            finish_reason = candidate.get('finishReason', '')
            if finish_reason and finish_reason != 'STOP':
                log.warning(f"[GEMINI] finishReason={finish_reason}")
            return '\n'.join(p['text'] for p in parts if 'text' in p).strip()
        except _requests.RequestException as e:
            if attempt == GRADING_RETRY_MAX - 1:
                raise
            _time.sleep(GRADING_BACKOFF ** attempt)


def get_send_target(override_chat_id: str = None) -> str:
    """
    Returns the chat_id to send to, respecting TEST_MODE.

    Priority order:
      1. override_chat_id — explicit caller-supplied target (e.g. reply-to-sender)
      2. TEST_CHAT_ID     — if TEST_MODE is on and no override, redirect to private DM
      3. TELEGRAM_CHAT_ID — normal group chat (production)

    The override is used for interactive replies so the bot always replies to
    whoever sent the message, regardless of TEST_MODE. Scheduled tasks
    (Chronicler, grading notifications) pass no override, so they respect TEST_MODE.
    """
    if override_chat_id:
        return override_chat_id
    if TEST_MODE:
        if not TEST_CHAT_ID:
            log.warning("[TEST MODE] TEST_CHAT_ID not set — falling back to group chat")
            return TELEGRAM_CHAT_ID
        log.debug(f"[TEST MODE] Redirecting to TEST_CHAT_ID={TEST_CHAT_ID}")
        return TEST_CHAT_ID
    return TELEGRAM_CHAT_ID


def send_telegram(text: str, chat_id: str = None) -> bool:
    """
    Sends a Telegram message.

    chat_id — optional override. If None, get_send_target() decides destination:
      - TEST_MODE on  → your private TEST_CHAT_ID
      - TEST_MODE off → the group TELEGRAM_CHAT_ID
    Pass chat_id explicitly to reply directly to a specific user (reply-to-sender).
    """
    target = get_send_target(chat_id)
    if not TELEGRAM_BOT_TOKEN or not target:
        log.warning("Telegram credentials not set — message not sent")
        return False
    url = f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage'
    try:
        r = _requests.post(url, json={'chat_id': target, 'text': text}, timeout=10)
        r.raise_for_status()
        log.info(f"Telegram message sent → chat_id={target}")
        return True
    except _requests.RequestException as e:
        log.error(f"Telegram delivery failed: {e}")
        return False


def save_report_locally(text: str, report_date: date) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORTS_DIR / f"{report_date.strftime('%Y-%m-%d')}_report.md"
    path.write_text(text)
    log.info(f"Report saved: {path}")
    return path


def needs_report(last_run_state: dict) -> tuple:
    """Returns (should_run, report_date).
    Fires once per calendar day — uses today as the dedup key so the scheduled
    Wednesday run fires exactly once, and force=True (? report) bypasses this.
    """
    today        = date.today()
    last_report  = last_run_state.get('last_report_date')
    if last_report is None or last_report < str(today):
        return True, today
    return False, today


def run_chronicler(df: pd.DataFrame, df_roi: pd.DataFrame, df_free: pd.DataFrame,
                   force: bool = False) -> str | None:
    """
    Generates and (if CHRONICLER_LIVE) delivers the weekly report.
    Returns the report text, or None if skipped.
    """
    last_run_state = load_last_run()
    should_run, report_date = needs_report(last_run_state)
    if not should_run and not force:
        log.info(f"Report already generated for {report_date}.")
        return None

    week_start, week_end = get_report_window()
    persona = get_report_persona(report_date)
    summary = build_weekly_summary(df, df_roi, df_free, week_start, week_end)
    prompt  = CHRONICLER_SYSTEM_TEMPLATE.format(
        persona_name=persona['name'],
        persona_instruction=persona['instruction'],
        summary_json=json.dumps(summary, indent=2),
    )

    report_text = _call_gemini(prompt, thinking_level=CHRONICLER_THINKING_LEVEL)

    if CHRONICLER_LIVE:
        if TEST_MODE:
            log.info(f"[TEST MODE] Chronicler report redirected to TEST_CHAT_ID={TEST_CHAT_ID}")
        sent = send_telegram(report_text)  # get_send_target() handles the redirect
        if not sent:
            save_report_locally(report_text, report_date)
    else:
        save_report_locally(report_text, report_date)

    last_run_state['last_report_date']    = str(report_date)
    last_run_state['last_report_persona'] = persona['name']
    save_last_run(last_run_state)
    return report_text


# ── C5: Betbot ────────────────────────────────────────────────────────────────
#
# Three-stage pipeline:
#   1. classify_question()  — tiny Gemini call, returns JSON type + params
#   2. _query_*()           — pure Python/pandas, returns verified plain-text facts
#   3. _narrate_answer()    — Gemini call with facts only, no raw data, persona only

BETBOT_CLASSIFIER_PROMPT = """You are a question classifier for a betting syndicate analytics bot.

Classify the question into exactly one type and extract parameters.
Respond with JSON only — no explanation, no markdown fences.

Question: "{question}"
Asker: "{asker_name}"
Members: John, Richard, Xander, Team

Types and their parameters:
  OVERALL_STATS   — overall syndicate profit, ROI, bank, win rate, general "how are we doing"
                    params: {{}}
  BANK            — just the bank balance / how much money do we have
                    params: {{}}
  MEMBER_STATS    — one member's overall performance
                    params: {{"member": "<name>"}}
  MEMBER_MARKET   — which markets a member bets on / performs best in
                    params: {{"member": "<name>"}}
  MEMBER_TEAM     — which teams a member has bet on / performs best with
                    params: {{"member": "<name>"}}
  MARKET_STATS    — syndicate-wide performance on a specific market or all markets
                    params: {{"market": "<market name or null>"}}
  TEAM_STATS      — performance involving a specific named team (e.g. "Arsenal", "Chelsea")
                    params: {{"team": "<team name>"}}
  ALL_TEAMS       — best/worst teams overall or for a member, no specific team named
                    (e.g. "which team has been best for us", "John's best teams")
                    params: {{"member": "<name or null>"}}
  DOTW_STATS      — record on a specific day of week, or all days
                    (e.g. "how do we do on Saturdays", "what's our Friday record")
                    params: {{"day": "<day name or null for all days>"}}
  RECENT_BETS     — recent bets, last N bets, bets this week/month
                    params: {{"member": "<name or null>", "n": <int, default 10>, "days": <int or null>}}
  SEASON_STATS    — performance by season or comparing seasons
                    params: {{"season": "<'2024/25' or '2025/26' or null for both>"}}
  STREAKS         — current streaks, who's on form, win/loss runs
                    params: {{}}
  UNKNOWN         — cannot be answered from historical ledger data
                    params: {{"reason": "<why>"}}

Rules:
- "my" or "I" from the asker means member = "{asker_name}"
- "we" or "our" or "syndicate" means no specific member
- For RECENT_BETS: "last week" = days:7, "this week" = days:7, "last month" = days:30
- If genuinely ambiguous between two types, pick the more specific one
- Only use UNKNOWN for questions about future events, predictions, or things not in the ledger

Return exactly one JSON object, e.g.:
{{"type": "MEMBER_TEAM", "params": {{"member": "John"}}}}
"""

# ── Narration prompt ─────────────────────────────────────────────────────────

BETBOT_NARRATION_PROMPT = """You are {persona_name} — {persona_instruction}

Deliver the following facts in your character's voice. You are texting mates — keep it natural and punchy. Around 80-100 words, always finish your final sentence. No markdown, plain text only. Use $ for money, % for percentages.

The facts below are correct and complete. Do not add, invent, or change any numbers. Your only job is the voice.

If there is any ambiguity about what was asked, state your interpretation in one plain sentence before going into character.

Asked by {asker_name}: "{question}"

Facts to deliver:
{facts}
"""

# ── Query functions — pure Python, no AI ─────────────────────────────────────

# ── Legacy prompts (used by UNKNOWN fallback and -raw flag) ──────────────────

BETBOT_DIRECT_PROMPT = """You are {persona_name} — {persona_instruction}

You are a character who has just been handed a factual briefing about a betting syndicate and asked a question by {asker_name}. Your job is to deliver the briefing's contents in your character's voice. Think of the briefing as your script — you perform it, you don't rewrite it.

The briefing is always correct. Every number, streak, balance, and stat in it was calculated by Python. You cannot know anything the briefing doesn't tell you, and you must never invent, estimate, or recall figures from memory. If you can't find the answer in the briefing, say so in character.

Keep it natural and punchy — you're texting mates. Around 100 words, always finish your final sentence. No markdown, plain text only. Use $ for money, % for percentages.

Context: today is {today}, current season {current_season}, previous season {prev_season}. Syndicate members: John, Richard, Xander, Team (shared account). "{asker_name}" asking — "my"/"I" means their bets, "we"/"our" means the whole syndicate.

If the question is ambiguous, state your interpretation in one plain sentence before going into character.

The question from {asker_name}: "{question}"

--- BRIEFING START ---

ANCHORS — figures pre-computed by Python, too many rows to calculate reliably.
Use these verbatim. Never recalculate or derive them from the ledger below.
{stats_block}

FULL LEDGER — complete bet history. Use this for all other questions:
per-member stats, markets, teams, seasons, specific bets, trends.
Each individual member (John/Richard/Xander) has ~25-30 rows — read and reason
from these directly. For Team or syndicate-wide questions, use the ANCHORS above.
{ledger_csv}

--- BRIEFING END ---
"""

BETBOT_RAW_PROMPT = """Answer this question about a betting syndicate for {asker_name}.
Be direct and factual. Use $ for money and % for percentages. Plain text, no markdown.
Around 80 words, always finish your sentence.

Context:
- Today: {today}
- Current season: {current_season}
- The person asking is: {asker_name} — "my"/"I" refers to them, "our"/"we" is the whole syndicate.
- Syndicate members: John, Richard, Xander, Team
- event format: "Home Team vs Away Team"
- profit = actual_winnings
- IMPORTANT: use the PRE-COMPUTED STATS for any aggregate figure. Never calculate from the CSV yourself.

Question: {question}

PRE-COMPUTED STATS:
{stats_block}

RECENT BETS LOG (last 80 bets):
{ledger_csv}
"""

BETBOT_HELP_TEXT = """Betbot v4.4 — I interrogate your ledger. I can't predict the future, I have no memory between messages, I can't access the internet, and I won't make anything up. Ask me about what's already happened.

Quick commands (instant, no AI):
  ? pending           — open bets waiting for a result
  ? leaderboard       — profit & ROI ranked by member
  ? bank              — current bank balance
  ? streaks           — each member's current win/loss streak
  ? upcoming fixtures — next EPL matches

Things you can ask:
  ? what is our overall ROI?
  ? who has the best win rate?
  ? what is Xander's profit this season?
  ? which market has made us the most money?
  ? how have we done on BTTS bets?
  ? which team has been best for us?
  ? what's our record on Saturdays?
  ? show me our last 5 bets

Flags (add to any question):
  -raw       skip the persona, plain answer
  -p Pundit  use a specific persona
  -random    random persona for this message
"""

BETBOT_PERSONA_ERROR_PROMPT = """You are the syndicate's weekly persona.
Your persona this week: {persona_name}
Your character instruction: {persona_instruction}

You are responding to {asker_name}, who asked: "{question}"

This question cannot be answered from the historical ledger.
Explain in persona voice why, and suggest a related question they could ask instead.
Around 80 words. Always finish your sentence. Plain text only, no markdown.
"""


def parse_betbot_flags(text: str) -> tuple:
    """
    Parses inline flags from a Betbot message. Returns (clean_question, flags_dict).
    Flags: -raw, -p <PersonaName>, -random
    """
    import random as _random

    flags = {'raw': False, 'persona': None}

    if _re.search(r'\s-raw\b', text, _re.IGNORECASE):
        flags['raw'] = True
        text = _re.sub(r'\s-raw\b', '', text, flags=_re.IGNORECASE).strip()

    if _re.search(r'\s-random\b', text, _re.IGNORECASE):
        flags['persona'] = _random.choice(CHRONICLER_PERSONAS)
        text = _re.sub(r'\s-random\b', '', text, flags=_re.IGNORECASE).strip()

    p_match = _re.search(r'\s-p\s+([\w ]+?)(?=\s+-|$)', text, _re.IGNORECASE)
    if p_match:
        requested = p_match.group(1).strip().lower()
        matched_persona = next(
            (p for p in CHRONICLER_PERSONAS
             if p['name'].lower() == requested
             or p['name'].lower().replace('the ', '') == requested),
            None
        )
        if matched_persona:
            flags['persona'] = matched_persona
        text = _re.sub(r'\s-p\s+[\w ]+?(\s+-|$)', r'\1', text, flags=_re.IGNORECASE).strip()

    return text.strip(), flags


def _get_ledger_csv(df_roi: pd.DataFrame) -> str:
    """Returns the full ledger as CSV for injection into fallback prompts."""
    cols = ['date', 'user', 'event', 'market', 'selection', 'odds',
            'stake', 'status', 'profit', 'season']
    available = [c for c in cols if c in df_roi.columns]
    return df_roi.sort_values('date')[available].to_csv(index=False)






# ── Orchestration ─────────────────────────────────────────────────────────────

def build_betbot_stats(df_roi: pd.DataFrame, df_free: pd.DataFrame = None,
                       df: pd.DataFrame = None) -> str:
    """
    Pre-computed anchor figures in natural sentence format.
    Used by the UNKNOWN fallback path and injected into all prompts.

    Written as sentences because models read and reproduce natural language
    more reliably than custom table/header formats during text generation.
    The bank figure is on the first line, stated unambiguously, so the model
    encounters it before generating any prose.
    """
    if df_roi.empty:
        return "No settled bets on record yet."
    if df_free is None:
        df_free = pd.DataFrame(columns=df_roi.columns)

    # ── Bank balance — must come from the full df (includes deposits/recon) ──
    # Never fall back to df_roi for this — df_roi's last balance row is not
    # the final balance; reconciliation rows come after the last bet.
    if df is not None and 'balance' in df.columns and not df.empty:
        current_bank = float(df['balance'].iloc[-1])
    else:
        # True fallback only if df genuinely not available
        current_bank = (300.0
                        + float(df_roi['profit'].sum())
                        + float(df_free['profit'].sum() if not df_free.empty else 0))

    # ── Compute all figures ───────────────────────────────────────────────────
    staked      = float(df_roi['stake'].sum())
    paid_profit = float(df_roi['profit'].sum())
    roi         = paid_profit / staked * 100 if staked else 0
    wins        = int(df_roi['is_win'].sum())
    losses      = int(df_roi['is_loss'].sum())
    pushes      = int(df_roi['is_push'].sum())
    total       = len(df_roi)
    win_rate    = wins / total * 100 if total else 0
    free_profit = float(df_free['profit'].sum()) if not df_free.empty else 0.0
    free_wins   = int(df_free['is_win'].sum()) if not df_free.empty else 0
    free_losses = int(df_free['is_loss'].sum()) if not df_free.empty else 0
    free_count  = len(df_free)
    net_betting = paid_profit + free_profit

    dep_total = 0.0
    if df is not None:
        dep_total = float(df[df['status'].isin(
            ['Deposit', 'Withdrawal', 'Reconciliation'])]['actual_winnings'].sum())

    team       = df_roi[df_roi['user'] == 'Team']
    t_staked   = float(team['stake'].sum())   if not team.empty else 0.0
    t_profit   = float(team['profit'].sum())  if not team.empty else 0.0
    t_roi      = t_profit / t_staked * 100    if t_staked else 0
    t_wins     = int(team['is_win'].sum())    if not team.empty else 0
    t_losses   = int(team['is_loss'].sum())   if not team.empty else 0
    t_pushes   = int(team['is_push'].sum())   if not team.empty else 0
    t_total    = len(team)
    t_wr       = t_wins / t_total * 100       if t_total else 0

    streaks    = get_user_streak_summary(df_roi)

    def _streak_str(user, s):
        if s['type'] == 'Win':
            return f"{user} is on a {s['length']}-win streak"
        if s['type'] == 'Loss':
            return f"{user} is on a {s['length']}-loss streak"
        if s['unbeaten'] > 1 and s['unbeaten'] >= s['winless']:
            return f"{user} last result was a push ({s['unbeaten']} unbeaten)"
        if s['winless'] > 1:
            return f"{user} last result was a push ({s['winless']} winless)"
        return f"{user} last result was a push"

    # ── Build natural-sentence output ─────────────────────────────────────────
    lines = []

    # Bank — first, unambiguous, nothing else nearby
    lines.append(f"The current bank balance is ${current_bank:.2f}. "
                 f"This is the only correct balance figure — use it exactly as written.")
    lines.append("")

    # Syndicate-wide totals
    lines.append(
        f"Across all {total} paid bets the syndicate has {wins} wins, {losses} losses, "
        f"and {pushes} pushes — a {win_rate:.1f}% win rate. "
        f"Total staked is ${staked:.2f}. "
        f"Profit from paid bets is ${paid_profit:.2f}, giving an ROI of {roi:.2f}%."
    )
    if free_count:
        lines.append(
            f"The syndicate also had {free_count} free bets (zero stake): "
            f"{free_wins} wins and {free_losses} losses, contributing ${free_profit:.2f} "
            f"in pure windfall profit."
        )
    lines.append(
        f"Net profit from all betting combined is ${net_betting:.2f}."
    )
    if dep_total:
        lines.append(
            f"The bank also received ${dep_total:.2f} from deposits and top-ups "
            f"(not betting profit)."
        )
    lines.append("")

    # Team account
    if not team.empty:
        lines.append(
            f"The shared Team account has placed {t_total} bets: "
            f"{t_wins} wins, {t_losses} losses, {t_pushes} pushes — "
            f"{t_wr:.1f}% win rate. "
            f"Staked ${t_staked:.2f}, profit ${t_profit:.2f}, ROI {t_roi:.2f}%."
        )
        lines.append("")

    # Streaks
    if streaks:
        streak_parts = [_streak_str(u, s) for u, s in streaks.items()]
        lines.append("Current form: " + "; ".join(streak_parts) + ".")

    return '\n'.join(lines)


# ── Betbot v2: hybrid aggregate/retrieve pipeline ────────────────────────────
#
# Two-category approach:
#   AGGREGATE — Python computes full answer, model only narrates
#   RETRIEVE  — model defines filters, Python applies them, model narrates
#   UNKNOWN   — falls back to single-call with slim stats block + full CSV
#
# One classifier call (tiny), one narration call (no raw data for aggregate,
# filtered rows for retrieve). Total: 2 Gemini calls per question.

# ── Prompts ───────────────────────────────────────────────────────────────────

BETBOT_CLASSIFIER_V2 = """Classify this betting syndicate question. Respond with JSON only.

Question: "{question}"
Asker: "{asker_name}"
Members: John, Richard, Xander, Team
Today: {today}

== CATEGORY: AGGREGATE ==
Question requires stats computation. Return:
{{"category": "AGGREGATE", "subtype": "<see below>",
  "params": {{
    "group_by": "<team|market|dotw|member|season — what to break the answer down by>",
    "filters": {{
      "member":  "<John|Richard|Xander|Team|null>",
      "market":  "<market name or null>",
      "team":    "<team name or null>",
      "day":     "<Monday..Sunday or null>",
      "season":  "<2024/25|2025/26|null>"
    }},
    "sort_by": "<profit|roi|win_rate|bets — default profit>"
  }}
}}

Subtypes:
  OVERALL   — no breakdown, just totals. params: {{}}
  BANK      — just the balance. params: {{}}
  MEMBER    — one member's overall stats. params: {{"member":"<name>"}}
  STREAKS   — current streaks. params: {{}}
  BREAKDOWN — any grouped breakdown (by team, market, day, season, member).
              Set group_by to what the question asks about.
              Set filters to any pre-filters mentioned.
              Set sort_by to what "best"/"worst"/"most" refers to.

== CATEGORY: RETRIEVE ==
Question asks to show specific bets. Return:
{{"category": "RETRIEVE", "params": {{
    "user": "<name or null>",
    "market": "<or null>",
    "team": "<or null>",
    "days": <int or null>,
    "date_from": "<YYYY-MM-DD or null>",
    "date_to":   "<YYYY-MM-DD or null>",
    "n": <int, default 10>
}}}}

== CATEGORY: COMPARE ==
Question compares two filter sets. Return:
{{"category": "COMPARE",
  "query_a": {{"group_by":"<dim>","filters":{{...}},"sort_by":"profit","label":"<short label>"}},
  "query_b": {{"group_by":"<dim>","filters":{{...}},"sort_by":"profit","label":"<short label>"}},
  "label_a": "<label>", "label_b": "<label>"
}}

== CATEGORY: UNKNOWN ==
Future events or predictions only. Return:
{{"category": "UNKNOWN", "reason": "<why>"}}

== RULES ==
- "my"/"I" from asker = member "{asker_name}"
- "we"/"our" = no member filter (null)
- "last week" = days:7, "this week" = days:7, "this month" = days:30
- "best" without qualifier = sort_by:profit
- "most wins"/"win rate" = sort_by:win_rate
- "most bets"/"most used" = sort_by:bets
- "vs" or "compared to" or "better than" = COMPARE

== EXAMPLES ==
"What's our overall ROI?" -> {{"category":"AGGREGATE","subtype":"OVERALL","params":{{}}}}
"What's the bank?" -> {{"category":"AGGREGATE","subtype":"BANK","params":{{}}}}
"How is John doing?" -> {{"category":"AGGREGATE","subtype":"MEMBER","params":{{"member":"John"}}}}
"Current streaks?" -> {{"category":"AGGREGATE","subtype":"STREAKS","params":{{}}}}
"Best markets by profit" -> {{"category":"AGGREGATE","subtype":"BREAKDOWN","params":{{"group_by":"market","filters":{{}},"sort_by":"profit"}}}}
"Best BTTS teams by ROI" -> {{"category":"AGGREGATE","subtype":"BREAKDOWN","params":{{"group_by":"team","filters":{{"market":"BTTS"}},"sort_by":"roi"}}}}
"Best markets for Chelsea" -> {{"category":"AGGREGATE","subtype":"BREAKDOWN","params":{{"group_by":"market","filters":{{"team":"Chelsea"}},"sort_by":"profit"}}}}
"John's best markets on Saturdays" -> {{"category":"AGGREGATE","subtype":"BREAKDOWN","params":{{"group_by":"market","filters":{{"member":"John","day":"Saturday"}},"sort_by":"profit"}}}}
"Which day is best for Draw No Bet?" -> {{"category":"AGGREGATE","subtype":"BREAKDOWN","params":{{"group_by":"dotw","filters":{{"market":"Draw No Bet"}},"sort_by":"profit"}}}}
"How do we do on Saturdays?" -> {{"category":"AGGREGATE","subtype":"BREAKDOWN","params":{{"group_by":"dotw","filters":{{"day":"Saturday"}},"sort_by":"profit"}}}}
"Xander's record on BTTS this season" -> {{"category":"AGGREGATE","subtype":"BREAKDOWN","params":{{"group_by":"market","filters":{{"member":"Xander","market":"BTTS","season":"2025/26"}},"sort_by":"profit"}}}}
"Show me my last 5 bets" -> {{"category":"RETRIEVE","params":{{"user":"{asker_name}","n":5}}}}
"John's bets this week" -> {{"category":"RETRIEVE","params":{{"user":"John","days":7}}}}
"John's BTTS vs Richard's DNB" -> {{"category":"COMPARE","query_a":{{"group_by":"market","filters":{{"member":"John","market":"BTTS"}},"sort_by":"profit","label":"John BTTS"}},"query_b":{{"group_by":"market","filters":{{"member":"Richard","market":"Draw No Bet"}},"sort_by":"profit","label":"Richard DNB"}},"label_a":"John BTTS","label_b":"Richard DNB"}}
"Saturdays vs Sundays" -> {{"category":"COMPARE","query_a":{{"group_by":"dotw","filters":{{"day":"Saturday"}},"sort_by":"profit","label":"Saturdays"}},"query_b":{{"group_by":"dotw","filters":{{"day":"Sunday"}},"sort_by":"profit","label":"Sundays"}},"label_a":"Saturdays","label_b":"Sundays"}}
"Who will win the Premier League?" -> {{"category":"UNKNOWN","reason":"future prediction"}}
"""

BETBOT_NARRATION_V2 = """You are {persona_name} — {persona_instruction}

Deliver these facts in your character's voice. Texting mates — natural and punchy.
Around 80-100 words. Always finish your sentence. No markdown. $ for money, % for percentages.

Every number below was calculated by Python and is correct. Do not change, add, or invent any figures.
If the question is ambiguous, say your interpretation in one plain sentence before going into character.

{asker_name} asked: "{question}"

Facts:
{facts}
"""

# ── Aggregate query functions — pure Python, all verified ────────────────────

def _pf(v: float) -> str: return f"${v:.2f}"
def _pct(n, d) -> str: return f"{n/d*100:.1f}%" if d else "n/a"

def _q_overall(df_roi: pd.DataFrame, df_free: pd.DataFrame, df: pd.DataFrame) -> str:
    bank    = float(df['balance'].iloc[-1]) if 'balance' in df.columns else 0.0
    staked  = float(df_roi['stake'].sum())
    paid_p  = float(df_roi['profit'].sum())
    roi     = paid_p / staked * 100 if staked else 0
    w       = int(df_roi['is_win'].sum())
    l       = int(df_roi['is_loss'].sum())
    p       = int(df_roi['is_push'].sum())
    total   = len(df_roi)
    free_p  = float(df_free['profit'].sum()) if not df_free.empty else 0.0
    return (f"Bank: {_pf(bank)}\n"
            f"Paid bets: {total} | W:{w} L:{l} P:{p} | Win rate: {_pct(w, total)}\n"
            f"Staked: {_pf(staked)} | Paid P&L: {_pf(paid_p)} | ROI: {roi:.2f}%\n"
            f"Free bet P&L: {_pf(free_p)} (stake $0 — pure windfall)\n"
            f"Net from all betting: {_pf(paid_p + free_p)}")


def _q_bank(df: pd.DataFrame) -> str:
    bank = float(df['balance'].iloc[-1]) if 'balance' in df.columns else 0.0
    return f"Current bank: {_pf(bank)}"


def _q_member(df_roi: pd.DataFrame, df_free: pd.DataFrame,
              member: str, scope: str = 'overall') -> str:
    m = df_roi[df_roi['user'] == member]
    if m.empty:
        return f"No settled bets found for {member}."

    if scope == 'market':
        mkt = m.groupby('market').agg(
            bets=('profit', 'count'), wins=('is_win', 'sum'),
            staked=('stake', 'sum'), profit=('profit', 'sum'),
        ).assign(wr=lambda x: x['wins'] / x['bets'] * 100,
                 roi=lambda x: x['profit'] / x['staked'] * 100
        ).sort_values('profit', ascending=False)
        lines = [f"{member}'s markets (by profit):"]
        for mkt_name, r in mkt.iterrows():
            lines.append(f"  {mkt_name}: {int(r['bets'])} bets | "
                         f"win rate {r['wr']:.1f}% | P&L {_pf(r['profit'])} | ROI {r['roi']:.1f}%")
        return '\n'.join(lines)

    if scope == 'team':
        home = m.copy()
        home['team'] = home['event'].str.extract(r'^(.+?) vs ')[0].str.strip()
        away = m.copy()
        away['team'] = away['event'].str.extract(r' vs (.+)$')[0].str.strip()
        teams = pd.concat([home, away]).groupby('team').agg(
            bets=('profit', 'count'), wins=('is_win', 'sum'), profit=('profit', 'sum'),
        ).assign(wr=lambda x: x['wins'] / x['bets'] * 100
        ).sort_values('profit', ascending=False)
        lines = [f"{member}'s best teams (by profit):"]
        for team, r in teams.head(12).iterrows():
            lines.append(f"  {team}: {int(r['bets'])} bets | "
                         f"win rate {r['wr']:.1f}% | P&L {_pf(r['profit'])}")
        return '\n'.join(lines)

    # overall
    staked = float(m['stake'].sum())
    profit = float(m['profit'].sum())
    roi    = profit / staked * 100 if staked else 0
    w = int(m['is_win'].sum()); l = int(m['is_loss'].sum()); p = int(m['is_push'].sum())
    total = len(m)
    mf     = df_free[df_free['user'] == member] if not df_free.empty else pd.DataFrame()
    free_p = float(mf['profit'].sum()) if not mf.empty else 0.0
    lines  = [f"{member}'s stats:",
              f"Bets: {total} | W:{w} L:{l} P:{p} | Win rate: {_pct(w, total)}",
              f"Staked: {_pf(staked)} | P&L: {_pf(profit)} | ROI: {roi:.2f}%"]
    if free_p:
        lines.append(f"Free bet P&L: {_pf(free_p)}")
    return '\n'.join(lines)


def _q_aggregate(df_roi: pd.DataFrame, group_by: str = 'market',
                 filters: dict = None, sort_by: str = 'profit') -> str:
    """
    Universal aggregate query — replaces _q_market, _q_team, _q_dotw,
    _q_member, _q_season, _q_filtered.

    group_by — what to break down by: team | market | dotw | member | season
    filters  — any combination of member/market/team/day/season (all optional)
    sort_by  — profit | roi | win_rate | bets
    """
    _DOTW = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']
    filters = filters or {}
    m = df_roi.copy()

    # ── Apply filters ────────────────────────────────────────────────────────
    if filters.get('member'):
        m = m[m['user'] == filters['member']]
    if filters.get('market'):
        m = m[m['market'].str.contains(filters['market'], case=False, na=False)]
    if filters.get('team'):
        m = m[m['event'].str.contains(filters['team'], case=False, na=False)]
    if filters.get('day'):
        matches = [d for d in _DOTW if d.lower().startswith(filters['day'].lower()[:3])]
        if matches:
            m = m[m['dotw'] == matches[0]]
    if filters.get('season'):
        m = m[m['season'] == filters['season']]

    if m.empty:
        f_desc = ', '.join(f'{k}={v}' for k, v in filters.items() if v)
        return f"No bets found{' for ' + f_desc if f_desc else ''}."

    # ── Group ────────────────────────────────────────────────────────────────
    if group_by == 'team':
        home = m.copy()
        home['_grp'] = home['event'].str.extract(r'^(.+?) vs ')[0].str.strip()
        away = m.copy()
        away['_grp'] = away['event'].str.extract(r' vs (.+)$')[0].str.strip()
        grouped_df = pd.concat([home, away])
    else:
        col_map = {'market': 'market', 'dotw': 'dotw',
                   'member': 'user',   'season': 'season'}
        m = m.copy()
        m['_grp'] = m[col_map.get(group_by, 'market')]
        grouped_df = m

    agg = grouped_df.groupby('_grp').agg(
        bets=('profit', 'count'),
        wins=('is_win', 'sum'),
        staked=('stake', 'sum'),
        profit=('profit', 'sum'),
    ).assign(
        win_rate=lambda x: x['wins'] / x['bets'] * 100,
        roi=lambda x: x['profit'] / x['staked'] * 100,
    )

    # ── Sort ─────────────────────────────────────────────────────────────────
    sort_col = {'profit': 'profit', 'roi': 'roi',
                'win_rate': 'win_rate', 'bets': 'bets'}.get(sort_by, 'profit')
    agg = agg.sort_values(sort_col, ascending=False)

    # For dotw, re-sort by day order if no explicit sort requested
    if group_by == 'dotw' and sort_by == 'profit':
        pass  # profit sort is informative, keep it

    # Minimum bets threshold for team (otherwise single-bet flukes dominate)
    if group_by == 'team':
        qualified = agg[agg['bets'] >= 2]
        agg = qualified if not qualified.empty else agg

    # ── Format output ────────────────────────────────────────────────────────
    filter_parts = [v for v in [
        filters.get('member'), filters.get('market'),
        filters.get('team'),   filters.get('day'), filters.get('season'),
    ] if v]
    filter_desc  = ' | '.join(filter_parts)
    group_label  = {'team': 'teams', 'market': 'markets', 'dotw': 'days',
                    'member': 'members', 'season': 'seasons'}.get(group_by, group_by)
    sort_label   = {'profit': 'profit', 'roi': 'ROI',
                    'win_rate': 'win rate', 'bets': 'volume'}.get(sort_by, sort_by)
    header = (f"Best {group_label}"
              f"{' for ' + filter_desc if filter_desc else ''}"
              f" by {sort_label}:")

    lines = [header]
    for name, r in agg.head(12).iterrows():
        lines.append(
            f"  {name}: {int(r['bets'])} bets | "
            f"win rate {r['win_rate']:.1f}% | "
            f"P&L {_pf(r['profit'])} | ROI {r['roi']:.1f}%"
        )
    return '\n'.join(lines)


def _q_streaks(df_roi: pd.DataFrame) -> str:
    streaks = get_user_streak_summary(df_roi)
    if not streaks:
        return "No streak data yet."
    order = [u for u in streaks if u != 'Team'] + (['Team'] if 'Team' in streaks else [])
    lines = ["Current streaks:"]
    for user in order:
        s = streaks[user]
        if s['type'] == 'Win':
            lines.append(f"  {user}: {s['length']}-win streak")
        elif s['type'] == 'Loss':
            lines.append(f"  {user}: {s['length']}-loss streak")
        else:
            if s['unbeaten'] > 1 and s['unbeaten'] >= s['winless']:
                lines.append(f"  {user}: 1-push ({s['unbeaten']} unbeaten)")
            elif s['winless'] > 1:
                lines.append(f"  {user}: 1-push ({s['winless']} winless)")
            else:
                lines.append(f"  {user}: 1-push")
    return '\n'.join(lines)


def _q_retrieve(df: pd.DataFrame, user: str = None, market: str = None,
                team: str = None, days: int = None, date_from: str = None,
                date_to: str = None, n: int = 10) -> str:
    from datetime import date as _date_, timedelta
    rows = df[~df['status'].isin(['Deposit', 'Withdrawal', 'Reconciliation'])].copy()
    if user:
        rows = rows[rows['user'] == user]
    if market:
        rows = rows[rows['market'].str.contains(market, case=False, na=False)]
    if team:
        rows = rows[rows['event'].str.contains(team, case=False, na=False)]
    if days:
        cutoff = pd.Timestamp(_date_.today() - timedelta(days=int(days)))
        rows = rows[rows['date'] >= cutoff]
    if date_from:
        rows = rows[rows['date'] >= pd.Timestamp(date_from)]
    if date_to:
        rows = rows[rows['date'] <= pd.Timestamp(date_to)]
    recent = rows.sort_values('date').tail(int(n))
    if recent.empty:
        return "No bets found matching those filters."
    lines = [f"Bets ({len(recent)} shown):"]
    for _, r in recent.iterrows():
        lines.append(
            f"  {r['date'].date()} | {r['user']} | {r['event']} | "
            f"{r['market']} | {r['selection']} @ {r['odds']} | "
            f"{r['status']} | {_pf(float(r['profit']))}"
        )
    return '\n'.join(lines)


# ── Classifier ────────────────────────────────────────────────────────────────

def _classify_v2(question: str, asker_name: str, today: str) -> dict:
    prompt = BETBOT_CLASSIFIER_V2.format(
        question=question,
        asker_name=asker_name,
        today=today,
    )
    try:
        raw = _call_gemini(prompt, thinking_level='minimal', max_tokens=300)
        raw = raw.strip().strip('`').strip()
        if raw.startswith('json'):
            raw = raw[4:].strip()
        result = json.loads(raw)
        log.info(f"[BETBOT] category={result.get('category')} "
                 f"subtype={result.get('subtype','—')} "
                 f"params={result.get('params', result.get('reason',''))}")
        return result
    except Exception as e:
        log.warning(f"[BETBOT] classifier failed ({e}), falling back to UNKNOWN")
        return {'category': 'UNKNOWN', 'reason': str(e)}


# ── Router ────────────────────────────────────────────────────────────────────

def _route_v2(classified: dict, df_roi: pd.DataFrame, df_free: pd.DataFrame,
              df: pd.DataFrame) -> str | None:
    """Routes to the correct query function. Returns plain-text facts or None for UNKNOWN."""
    cat    = classified.get('category', 'UNKNOWN')
    params = classified.get('params', {})

    if cat == 'RETRIEVE':
        return _q_retrieve(
            df,
            user      = params.get('user'),
            market    = params.get('market'),
            team      = params.get('team'),
            days      = params.get('days'),
            date_from = params.get('date_from'),
            date_to   = params.get('date_to'),
            n         = params.get('n', 10),
        )

    if cat == 'AGGREGATE':
        sub = classified.get('subtype', 'OVERALL')

        if sub == 'OVERALL':
            return _q_overall(df_roi, df_free, df)

        if sub == 'BANK':
            return _q_bank(df)

        if sub == 'MEMBER':
            member = params.get('member') or 'mate'
            # If extra filters supplied (e.g. market, day), use _q_aggregate
            # to give a filtered breakdown rather than bare overall stats
            extra = params.get('filters', {})
            if not extra:
                # Also check flat params for legacy classifier output
                extra = {k: params.get(k) for k in ('market','team','day','season') if params.get(k)}
            if extra:
                extra['member'] = member
                return _q_aggregate(df_roi,
                                    group_by = extra.pop('group_by', 'market'),
                                    filters  = extra,
                                    sort_by  = params.get('sort_by', 'profit'))
            return _q_member(df_roi, df_free, member)

        if sub == 'STREAKS':
            return _q_streaks(df_roi)

        # All breakdown subtypes route through _q_aggregate
        # group_by tells us what dimension to break down by
        # filters carries any pre-filters (market, team, member, day, season)
        # sort_by controls ranking
        # BREAKDOWN handles all grouped questions via _q_aggregate
        # Legacy subtypes (MARKET/TEAM/DOTW/SEASON/FILTERED) also route here
        legacy_group = {
            'MARKET' : 'market', 'TEAM': 'team',
            'DOTW'   : 'dotw',   'SEASON': 'season', 'FILTERED': 'market',
        }
        if sub == 'BREAKDOWN' or sub in legacy_group:
            group_by = (params.get('group_by') or
                        legacy_group.get(sub, 'market'))
            filters  = {k: v for k, v in
                        (params.get('filters') or params).items()
                        if k in ('member','market','team','day','season') and v}
            sort_by  = params.get('sort_by', 'profit')
            return _q_aggregate(df_roi, group_by=group_by,
                                filters=filters, sort_by=sort_by)

        log.warning(f"[BETBOT] unrecognised subtype: {sub}")
        return None

    if cat == 'COMPARE':
        qa = classified.get('query_a', {})
        qb = classified.get('query_b', {})
        la = classified.get('label_a', 'A')
        lb = classified.get('label_b', 'B')
        # Each side is a filtered aggregate — default group_by to the dimension
        # that differs between the two queries
        def _compare_side(q):
            filters = {k: q.get(k) for k in ('member','market','team','day','season') if q.get(k)}
            group_by = q.get('group_by', 'market')
            sort_by  = q.get('sort_by', 'profit')
            return _q_aggregate(df_roi, group_by=group_by,
                                filters=filters, sort_by=sort_by)
        facts_a = _compare_side(qa)
        facts_b = _compare_side(qb)
        return f"{la}:\n{facts_a}\n\n{lb}:\n{facts_b}"

    return None  # UNKNOWN


# ── Main betbot_query ─────────────────────────────────────────────────────────

def betbot_query(question: str, df_roi: pd.DataFrame,
                 df_free: pd.DataFrame = None,
                 df: pd.DataFrame = None,
                 asker_name: str = "mate") -> str:
    """
    Hybrid aggregate/retrieve pipeline.

    AGGREGATE questions: Python computes full answer, model narrates only.
    RETRIEVE questions: model defines filters, Python applies them, model narrates.
    UNKNOWN: falls back to single-call with slim stats block + full CSV.

    Two Gemini calls for AGGREGATE/RETRIEVE (classify + narrate).
    One Gemini call for UNKNOWN (full context single-call).
    """
    question, flags = parse_betbot_flags(question)

    if flags['persona'] is not None:
        persona = flags['persona']
    else:
        persona = get_report_persona()

    log.info(f"[BETBOT] persona={persona['name']} raw={flags['raw']} asker={asker_name}")

    if not BETBOT_LIVE:
        return f"(offline) {asker_name}, question received: {question}"

    if question.strip().lower() in ('help', '?', 'commands', 'what can you do'):
        return BETBOT_HELP_TEXT

    from datetime import date as _d
    today          = str(_d.today())
    current_season = '2024/25' if _d.today() < _d(2025, 7, 1) else '2025/26'
    prev_season    = '2024/25' if current_season == '2025/26' else '2023/24'

    if df_free is None:
        df_free = pd.DataFrame()
    # Never fall back to df_roi for df — df_roi's last balance row is not the
    # final balance (reconciliation rows come after the last bet).
    # If df genuinely wasn't passed, build_betbot_stats handles it gracefully.

    try:
        # ── Stage 1: classify ──────────────────────────────────────────────
        classified = _classify_v2(question, asker_name, today)

        # ── Stage 2: compute facts ─────────────────────────────────────────
        facts = _route_v2(classified, df_roi, df_free, df)

        # ── UNKNOWN fallback: single-call with full ledger ─────────────────
        if facts is None:
            log.info(f"[BETBOT] UNKNOWN — falling back to single-call")
            stats_block = build_betbot_stats(df_roi, df_free, df)
            ledger_csv  = _get_ledger_csv(df_roi)
            if flags['raw']:
                prompt = BETBOT_RAW_PROMPT.format(
                    asker_name=asker_name, question=question,
                    today=today, current_season=current_season,
                    stats_block=stats_block, ledger_csv=ledger_csv,
                )
            else:
                prompt = BETBOT_DIRECT_PROMPT.format(
                    asker_name=asker_name, question=question,
                    persona_name=persona['name'],
                    persona_instruction=persona['instruction'],
                    today=today, current_season=current_season,
                    prev_season=prev_season,
                    stats_block=stats_block, ledger_csv=ledger_csv,
                )
            return _call_gemini(prompt, thinking_level='minimal', max_tokens=500)

        # ── Stage 3: narrate verified facts ───────────────────────────────
        if flags['raw']:
            return facts  # raw mode: skip persona

        narration = BETBOT_NARRATION_V2.format(
            persona_name        = persona['name'],
            persona_instruction = persona['instruction'],
            asker_name          = asker_name,
            question            = question,
            facts               = facts,
        )
        return _call_gemini(narration, thinking_level='minimal', max_tokens=400)

    except Exception as e:
        log.error(f"[BETBOT] pipeline failed: {e}")
        try:
            return _call_gemini(
                BETBOT_PERSONA_ERROR_PROMPT.format(
                    persona_name        = persona['name'],
                    persona_instruction = persona['instruction'],
                    asker_name          = asker_name,
                    question            = question,
                ),
                thinking_level='low', max_tokens=350,
            )
        except Exception:
            return f"Sorry {asker_name}, something went wrong — try rephrasing."


# ── Fixtures helpers (called from bot_runner._handle_fixtures) ───────────────

def fetch_upcoming_fixtures(sport_key: str = 'soccer_epl', days: int = 7) -> list:
    """Fetches upcoming fixtures from the Odds API."""
    if not ODDS_API_KEY:
        return []
    url    = f'https://api.the-odds-api.com/v4/sports/{sport_key}/events'
    params = {'apiKey': ODDS_API_KEY, 'dateFormat': 'iso'}
    try:
        r = _requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        events  = r.json()
        from datetime import timezone as _tz
        cutoff  = datetime.now(_tz.utc) + timedelta(days=days)
        upcoming = [
            e for e in events
            if datetime.fromisoformat(e['commence_time'].replace('Z', '+00:00')) <= cutoff
        ]
        return upcoming[:10]
    except Exception as e:
        log.error(f"fetch_upcoming_fixtures failed: {e}")
        return []


def format_fixtures_message(fixtures: list, sport_label: str = 'EPL') -> str:
    """Formats upcoming fixtures as a plain-text Telegram message."""
    if not fixtures:
        return f"No upcoming {sport_label} fixtures found (or ODDS_API_KEY not set)."
    lines = [f"\U0001f4c5 Upcoming {sport_label} fixtures:"]
    for f in fixtures:
        try:
            dt       = datetime.fromisoformat(f['commence_time'].replace('Z', '+00:00'))
            date_str = dt.strftime('%a %d %b %H:%M UTC')
            lines.append(f"\u2022 {f.get('home_team','?')} vs {f.get('away_team','?')} — {date_str}")
        except Exception:
            lines.append(f"\u2022 {f.get('home_team','?')} vs {f.get('away_team','?')}")
    return '\n'.join(lines)


# ── C6: Google Sheets write-back ──────────────────────────────────────────────

def load_last_run() -> dict:
    if LAST_RUN_JSON.exists():
        return json.loads(LAST_RUN_JSON.read_text())
    return {}


def save_last_run(state: dict):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    LAST_RUN_JSON.write_text(json.dumps(state, indent=2))


def get_worksheet():
    import gspread
    from google.oauth2.service_account import Credentials
    creds = Credentials.from_service_account_file(
        str(GOOGLE_CREDS_PATH),
        scopes=['https://www.googleapis.com/auth/spreadsheets'],
    )
    return gspread.authorize(creds).open_by_key(GSHEET_ID).worksheet(GSHEET_TAB)


def _log_failed_write(record: dict):
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    with open(FAILED_WRITES, 'a') as f:
        f.write(json.dumps(record) + '\n')
    log.error(f"Write failed and logged: {record.get('fn')} — {str(record.get('error',''))[:80]}")


def write_with_retry(fn, *args, max_retries=3, backoff_base=2, **kwargs):
    for attempt in range(max_retries):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            if attempt == max_retries - 1:
                _log_failed_write({
                    'fn': fn.__name__, 'args': str(args)[:200],
                    'kwargs': str(kwargs)[:200], 'error': str(e),
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                })
                raise
            wait = backoff_base ** attempt
            log.warning(f"Write attempt {attempt+1} failed ({e}), retrying in {wait}s")
            _time.sleep(wait)


def replay_failed_writes() -> int:
    if not FAILED_WRITES.exists():
        return 0
    lines = FAILED_WRITES.read_text().strip().splitlines()
    if not lines:
        return 0
    log.info(f"Replaying {len(lines)} failed write(s)...")
    still_pending = []
    for line in lines:
        try:
            record = json.loads(line)
            log.warning(f"Pending write: {record['fn']} at {record['timestamp']}")
            still_pending.append(line)
        except Exception as e:
            log.error(f"Could not parse failed_write record: {e}")
            still_pending.append(line)
    if still_pending:
        FAILED_WRITES.write_text('\n'.join(still_pending) + '\n')
    else:
        FAILED_WRITES.write_text('')
    return len(still_pending)


def sync_local_csv() -> bool:
    if not USE_GSHEETS_LIVE:
        log.info("[DRY RUN] sync_local_csv: skipped")
        return True
    try:
        ws = get_worksheet()
        records = ws.get_all_records()
        df_sync = pd.DataFrame(records)
        df_sync.columns = [c.lower().replace(' ', '_') for c in df_sync.columns]
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        df_sync.to_csv(LEDGER_CSV, index=False)
        log.info(f"Local CSV synced: {len(df_sync)} rows")
        return True
    except Exception as e:
        log.error(f"sync_local_csv failed: {e}")
        return False


def _audit_log(bet_uuid: str, field: str, new_value):
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    record = {
        'uuid': bet_uuid, 'field': field, 'new_value': str(new_value),
        'timestamp': datetime.now(timezone.utc).isoformat(), 'operator': 'manual',
    }
    with open(LOGS_DIR / 'audit.log', 'a') as f:
        f.write(json.dumps(record) + '\n')


def append_bet(user: str, event: str, market: str, selection: str,
               odds: float, stake: float, bet_date: _date = None,
               status: str = 'Pending', actual_winnings: float = 0.0) -> str:
    new_uuid = _uuid.uuid4().hex[:8]
    bet_date = bet_date or _date.today()
    row = [new_uuid, str(bet_date), user, event, market, selection,
           round(float(odds), 3), round(float(stake), 2), status, round(float(actual_winnings), 2)]
    if not USE_GSHEETS_LIVE:
        log.info(f"[DRY RUN] append_bet: {new_uuid} | {event} | {market} @ {odds} | ${stake}")
        return new_uuid
    ws = get_worksheet()
    write_with_retry(ws.append_row, row, value_input_option='USER_ENTERED')
    sync_local_csv()
    log.info(f"Bet appended: {new_uuid} | {event} | {market}")
    return new_uuid


def update_grade(bet_uuid: str, new_status: str, actual_winnings: float) -> bool:
    if not USE_GSHEETS_LIVE:
        log.info(f"[DRY RUN] update_grade: {bet_uuid} → {new_status} ${actual_winnings:.2f}")
        return True
    ws = get_worksheet()
    uuids = ws.col_values(1)
    try:
        row_num = uuids.index(bet_uuid) + 1
    except ValueError:
        log.error(f"update_grade: UUID {bet_uuid} not found")
        return False
    updates = [
        {'range': f'I{row_num}', 'values': [[new_status]]},
        {'range': f'J{row_num}', 'values': [[round(float(actual_winnings), 2)]]},
    ]
    write_with_retry(ws.batch_update, updates, value_input_option='USER_ENTERED')
    sync_local_csv()
    log.info(f"Grade updated: {bet_uuid} → {new_status} ${actual_winnings:.2f}")
    return True


def manual_correction(bet_uuid: str, field: str, new_value) -> bool:
    if field not in COLUMN_MAP:
        raise ValueError(f"Invalid field: {field}. Must be one of {list(COLUMN_MAP.keys())}")
    col_letter = COLUMN_MAP[field]
    if not USE_GSHEETS_LIVE:
        log.info(f"[DRY RUN] manual_correction: {bet_uuid} | {field}={new_value}")
        _audit_log(bet_uuid, field, new_value)
        return True
    ws = get_worksheet()
    uuids = ws.col_values(1)
    try:
        row_num = uuids.index(bet_uuid) + 1
    except ValueError:
        log.error(f"manual_correction: UUID {bet_uuid} not found")
        return False
    write_with_retry(ws.update, f'{col_letter}{row_num}', [[new_value]],
                     value_input_option='USER_ENTERED')
    _audit_log(bet_uuid, field, new_value)
    sync_local_csv()
    log.info(f"Manual correction: {bet_uuid} | {field} = {new_value}")
    return True
