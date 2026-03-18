"""
migrate_to_enriched_csv.py
==========================
One-time script to build the enriched syndicate_ledger.csv from the Excel source.

Run once:
    python migrate_to_enriched_csv.py

Output: syndicate_ledger.csv  (replaces syndicate_ledger_v3.csv as source of truth)
"""

import pandas as pd
import uuid as uuid_lib
from pathlib import Path

EXCEL_PATH  = Path('data/EPL_2024_5.xlsx')
OUTPUT_PATH = Path('data/syndicate_ledger.csv')

# ── Load ──────────────────────────────────────────────────────────────────────

df = pd.read_excel(EXCEL_PATH, sheet_name='Bets')
df.columns = df.columns.str.strip()
df = df[[c for c in df.columns if not c.startswith('Unnamed')]]

print(f"Loaded {len(df)} rows from Excel.")

# ── 1. User — Notes column → user ─────────────────────────────────────────────
# Named members stay as-is. Everything else (NaN or freeform notes) → Team.

VALID_USERS = {'Xander', 'John', 'Richard'}

def resolve_user(note):
    if pd.isna(note):
        return 'Team'
    note = str(note).strip()
    if note in VALID_USERS:
        return note
    return 'Team'

df['user'] = df['Notes'].apply(resolve_user)

# ── 2. Bet type — normalise all multi variants to 'Multi' ─────────────────────

MULTI_PATTERNS = (
    'accumulator', 'multi', 'parlay'
)

def normalise_bet_type(bt):
    if pd.isna(bt):
        return bt
    bt_lower = str(bt).strip().lower()
    if any(p in bt_lower for p in MULTI_PATTERNS):
        return 'Multi'
    return str(bt).strip()

df['bet_type'] = df['Bet Type'].apply(normalise_bet_type)

# ── 3. Selection — multis → 'Multiple' ───────────────────────────────────────

def normalise_selection(row):
    if row['bet_type'] == 'Multi':
        return 'Multiple'
    val = row['Betting Option']
    return str(val).strip() if not pd.isna(val) else ''

df['selection'] = df.apply(normalise_selection, axis=1)

# ── 4. Status — strip whitespace, map W/L/P → Win/Loss/Push ──────────────────

STATUS_MAP = {'W': 'Win', 'L': 'Loss', 'P': 'Push'}

df['status'] = df['Result'].astype(str).str.strip().map(STATUS_MAP).fillna(df['Result'].astype(str).str.strip())

# ── 5. Matchday — keep integers only, everything else → NaN ──────────────────

def normalise_matchday(val):
    if pd.isna(val):
        return None
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return None  # catches 'Null' strings and anything else

df['matchday'] = df['Matchday'].apply(normalise_matchday)

# ── 6. UUID — use existing Index as seed for deterministic UUIDs ──────────────
# This gives stable UUIDs so re-running the script produces the same IDs.

df['uuid'] = df['Index'].apply(
    lambda i: str(uuid_lib.uuid5(uuid_lib.NAMESPACE_DNS, f"syndicate-bet-{int(i)}"))
)

# ── 7. Rename/select final columns ───────────────────────────────────────────

df['home_team']    = df['Home Team'].str.strip()
df['away_team']    = df['Away Team'].str.strip()
df['competition']  = df['Market'].str.strip()
df['sport']        = df['Sport'].str.strip()
df['odds']         = df['Odds']
df['stake']        = df['Stake']
df['actual_winnings'] = df['Winnings']
df['date']         = pd.to_datetime(df['Date']).dt.strftime('%Y-%m-%d')

FINAL_COLS = [
    'uuid', 'date', 'user', 'home_team', 'away_team',
    'competition', 'bet_type', 'selection',
    'odds', 'stake', 'status', 'actual_winnings',
    'matchday', 'sport',
]

out = df[FINAL_COLS].copy()

# ── 8. Sanity checks ──────────────────────────────────────────────────────────

print()
print('=== USER distribution ===')
print(out['user'].value_counts().to_string())

print()
print('=== BET TYPE distribution ===')
print(out['bet_type'].value_counts().to_string())

print()
print('=== STATUS distribution ===')
print(out['status'].value_counts().to_string())

print()
print('=== COMPETITION distribution ===')
print(out['competition'].value_counts().to_string())

print()
print('=== SPORT distribution ===')
print(out['sport'].value_counts().to_string())

print()
print('=== MATCHDAY nulls ===')
print(f"  With matchday: {out['matchday'].notna().sum()}")
print(f"  Without:       {out['matchday'].isna().sum()}")

print()
print('=== Sample rows ===')
print(out.head(5).to_string())

print()
print('=== Multi sample ===')
print(out[out['bet_type'] == 'Multi'][['home_team','away_team','bet_type','selection','user']].head(5).to_string())

# ── Write ─────────────────────────────────────────────────────────────────────

out.to_csv(OUTPUT_PATH, index=False)
print()
print(f"✅ Written {len(out)} rows to {OUTPUT_PATH}")
