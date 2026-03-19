#!/usr/bin/env python3
"""
evals/refresh_cases.py — Auto-update eval expected values from the live CSV
============================================================================
Reads the current syndicate_ledger.csv, recomputes every KPI, and updates
the `expected_number` / `expected_contains` fields in cases.json in-place.

This script knows about every numeric case by ID and maps it to a computed
value. Non-numeric cases (expected_contains, security cases) are left untouched.

Run this whenever the ledger grows significantly — e.g. end of each month,
or after a big grading batch. The cases file is rewritten atomically so a
failed run never corrupts it.

Usage:
    python evals/refresh_cases.py

    # Preview what would change without writing:
    python evals/refresh_cases.py --dry-run

    # Point at a different CSV (e.g. a snapshot for regression testing):
    python evals/refresh_cases.py --csv data/snapshot_2025-03.csv

Design principle:
    The mapping from case ID → computed value is explicit and version-controlled
    here in this file. If you add a new case to cases.json that has a numeric
    assertion, add a corresponding entry to NUMERIC_CASE_MAP below. If a case ID
    is not in the map, its expected values are left unchanged and a warning is
    printed — this prevents silent staleness.
"""

import argparse
import json
import sys
from pathlib import Path
from datetime import datetime

import pandas as pd

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

CASES_PATH  = Path(__file__).parent / 'cases.json'
DEFAULT_CSV = PROJECT_ROOT / 'data' / 'syndicate_ledger.csv'


# ── KPI computation ───────────────────────────────────────────────────────────

def compute_kpis(csv_path: Path) -> dict:
    """
    Derive all KPIs from the CSV that eval cases are asserting against.
    Returns a flat dict of metric_name → value.
    """
    df = pd.read_csv(csv_path, parse_dates=['date'])
    df['status']          = df['status'].astype(str).str.strip()
    df['actual_winnings'] = pd.to_numeric(df['actual_winnings'], errors='coerce').fillna(0)
    df['stake']           = pd.to_numeric(df['stake'], errors='coerce').fillna(0)
    df['odds']            = pd.to_numeric(df['odds'], errors='coerce').fillna(0)

    banking_mask = (
        df['status'].isin(['Deposit', 'Withdrawal', 'Reconciliation']) |
        (df['user'].astype(str).str.lower() == 'syndicate')
    )
    df_bets = df[~banking_mask].copy()
    df_roi  = df_bets[
        df_bets['status'].isin(['Win', 'Loss', 'Push']) &
        (df_bets['stake'] > 0)
    ].copy()

    wins   = int((df_roi['status'] == 'Win').sum())
    losses = int((df_roi['status'] == 'Loss').sum())
    pushes = int((df_roi['status'] == 'Push').sum())

    total_pl     = round(df_roi['actual_winnings'].sum(), 2)
    total_staked = round(df_roi['stake'].sum(), 2)
    overall_roi  = round(total_pl / total_staked * 100, 2) if total_staked else 0
    win_rate     = round(wins / (wins + losses) * 100, 2) if (wins + losses) else 0

    kpis = {
        'overall_roi':    overall_roi,
        'overall_pl':     total_pl,
        'total_staked':   total_staked,
        'win_rate_overall': win_rate,
        'total_wins':     wins,
        'total_losses':   losses,
        'total_bets':     wins + losses + pushes,
        'pending_count':  int((df_bets['status'] == 'Pending').sum()),
    }

    # Free bets
    df_free = df_bets[
        df_bets['status'].isin(['Win', 'Loss', 'Push']) &
        (df_bets['stake'] == 0)
    ]
    kpis['free_bet_profit'] = round(df_free['actual_winnings'].sum(), 2)

    # Per member
    for user in ['John', 'Richard', 'Xander', 'Team']:
        sub  = df_roi[df_roi['user'] == user]
        pl   = round(sub['actual_winnings'].sum(), 2)
        stk  = round(sub['stake'].sum(), 2)
        roi  = round(pl / stk * 100, 2) if stk else 0
        w    = int((sub['status'] == 'Win').sum())
        l    = int((sub['status'] == 'Loss').sum())
        wr   = round(w / (w + l) * 100, 2) if (w + l) else 0
        slug = user.lower().replace(' ', '_')
        kpis[f'{slug}_pl']       = pl
        kpis[f'{slug}_roi']      = roi
        kpis[f'{slug}_win_rate'] = wr

    # Per bet type
    for bt, grp in df_roi.groupby('bet_type'):
        pl   = round(grp['actual_winnings'].sum(), 2)
        stk  = round(grp['stake'].sum(), 2)
        roi  = round(pl / stk * 100, 2) if stk else 0
        w    = int((grp['status'] == 'Win').sum())
        l    = int((grp['status'] == 'Loss').sum())
        wr   = round(w / (w + l) * 100, 2) if (w + l) else 0
        slug = bt.lower().replace(' ', '_').replace('/', '_')
        kpis[f'bt_{slug}_roi']      = roi
        kpis[f'bt_{slug}_pl']       = pl
        kpis[f'bt_{slug}_win_rate'] = wr

    # Per competition
    for comp, grp in df_roi.groupby('competition'):
        pl   = round(grp['actual_winnings'].sum(), 2)
        bets = len(grp)
        slug = comp.lower().replace(' ', '_').replace('/', '_').replace("'", '')
        kpis[f'comp_{slug}_pl']   = pl
        kpis[f'comp_{slug}_bets'] = bets

    # Best / worst bets
    kpis['best_bet_pl']   = round(float(df_roi['actual_winnings'].max()), 2)
    kpis['worst_bet_pl']  = round(float(df_roi['actual_winnings'].min()), 2)

    # Who placed the single best / worst bet
    best_row  = df_roi.loc[df_roi['actual_winnings'].idxmax()]
    worst_row = df_roi.loc[df_roi['actual_winnings'].idxmin()]
    kpis['best_bet_user']  = str(best_row.get('user', ''))
    kpis['worst_bet_user'] = str(worst_row.get('user', ''))

    # Best / worst member by cumulative profit (individuals only)
    ind_pl = df_roi[df_roi['user'].isin(['John', 'Richard', 'Xander'])].groupby('user')['actual_winnings'].sum()
    kpis['best_member_name']  = str(ind_pl.idxmax())
    kpis['worst_member_name'] = str(ind_pl.idxmin())

    # Worst bet match details
    kpis['worst_bet_match_team'] = str(worst_row.get('away_team', ''))

    return kpis


# ── Explicit case ID → KPI key mapping ───────────────────────────────────────
#
# Maps each case `id` to the key in the kpis dict it should be updated from.
# Cases not listed here are treated as non-numeric and left untouched.
# Add a row here whenever you add a new numeric case to cases.json.

NUMERIC_CASE_MAP: dict[str, str] = {
    # Summary
    'overall_roi':          'overall_roi',
    'overall_pl':           'overall_pl',
    'total_staked':         'total_staked',
    'win_rate_overall':     'win_rate_overall',
    'total_wins':           'total_wins',
    'total_losses':         'total_losses',
    'total_bets':           'total_bets',
    'pending_count':        'pending_count',
    'free_bet_profit':      'free_bet_profit',

    # Members
    'john_pl':              'john_pl',
    'john_roi':             'john_roi',
    'john_win_rate':        'john_win_rate',
    'richard_pl':           'richard_pl',
    'richard_roi':          'richard_roi',
    'xander_pl':            'xander_pl',
    'xander_win_rate':      'xander_win_rate',
    'team_pool_pl':         'team_pl',
    'team_pool_roi':        'team_roi',

    # Markets (numeric only — contains/not_contains cases stay untouched)
    'btts_roi':             'bt_btts_roi',
    'btts_win_rate':        'bt_btts_win_rate',
    'multi_roi':            'bt_multi_roi',
    'multi_win_rate':       'bt_multi_win_rate',
    'draw_no_bet_pl':       'bt_draw_no_bet_pl',
    'ftr_roi':              'bt_full_time_result_roi',

    # Competitions
    'epl_2425_pl':          'comp_epl_24_25_pl',
    'epl_2526_pl':          'comp_epl_25_26_pl',
    'club_world_cup_bets':  'comp_club_world_cup_bets',

    # Extremes
    'best_bet_ever':        'best_bet_pl',
    'worst_bet_ever':       'worst_bet_pl',
}

# Cases where expected_contains should be refreshed automatically.
# Maps case ID → kpis key that returns a string.
CONTAINS_CASE_MAP: dict[str, str] = {
    'best_member_by_profit':  'best_member_name',   # most cumulative profit
    'worst_member_by_profit': 'worst_member_name',  # least cumulative profit
    'best_bet_member':        'best_bet_user',       # who placed the single best bet
    'worst_bet_match':        'worst_bet_match_team',
}


# ── Refresh logic ─────────────────────────────────────────────────────────────

def refresh_cases(csv_path: Path, dry_run: bool = False) -> None:
    if not csv_path.exists():
        print(f"❌  CSV not found: {csv_path}")
        sys.exit(1)
    if not CASES_PATH.exists():
        print(f"❌  cases.json not found: {CASES_PATH}")
        sys.exit(1)

    print(f"📊  Computing KPIs from {csv_path} ...")
    kpis = compute_kpis(csv_path)

    cases = json.loads(CASES_PATH.read_text())
    changes  = []
    warnings = []

    for case in cases:
        cid = case.get('id', '')

        # ── Numeric update ──
        if cid in NUMERIC_CASE_MAP:
            kpi_key = NUMERIC_CASE_MAP[cid]
            if kpi_key not in kpis:
                warnings.append(f"  ⚠️  [{cid}] mapped to kpi key '{kpi_key}' but that key was not computed — skipping")
                continue
            new_val = kpis[kpi_key]
            old_val = case.get('expected_number')
            if old_val != new_val:
                changes.append(f"  {cid}: expected_number  {old_val}  →  {new_val}")
                if not dry_run:
                    case['expected_number'] = new_val

        # ── Contains update ──
        elif cid in CONTAINS_CASE_MAP:
            kpi_key = CONTAINS_CASE_MAP[cid]
            if kpi_key not in kpis:
                warnings.append(f"  ⚠️  [{cid}] mapped to kpi key '{kpi_key}' but that key was not computed — skipping")
                continue
            new_val = str(kpis[kpi_key])
            old_val = case.get('expected_contains')
            if old_val != new_val:
                changes.append(f"  {cid}: expected_contains  '{old_val}'  →  '{new_val}'")
                if not dry_run:
                    case['expected_contains'] = new_val

        # ── Unknown numeric case ──
        elif 'expected_number' in case and case.get('tags', []) != ['security']:
            warnings.append(
                f"  ⚠️  [{cid}] has expected_number but is not in NUMERIC_CASE_MAP — "
                f"value will go stale. Add it to the map in refresh_cases.py."
            )

    # Print results
    if changes:
        print(f"\n{'DRY RUN — ' if dry_run else ''}{'Changes' if not dry_run else 'Would change'} ({len(changes)}):")
        for c in changes:
            print(c)
    else:
        print("\n✅  All expected values already match the current ledger. No changes needed.")

    if warnings:
        print(f"\nWarnings ({len(warnings)}):")
        for w in warnings:
            print(w)

    if dry_run:
        print("\nDry run complete — cases.json was NOT modified.")
        return

    if changes:
        # Write atomically: write to a temp file then rename
        tmp = CASES_PATH.with_suffix('.json.tmp')
        tmp.write_text(json.dumps(cases, indent=2) + '\n')
        tmp.replace(CASES_PATH)

        # Append a refresh entry to a small audit log
        audit_path = CASES_PATH.parent / 'refresh_log.jsonl'
        with open(audit_path, 'a') as f:
            f.write(json.dumps({
                'timestamp': datetime.utcnow().isoformat() + 'Z',
                'csv':       str(csv_path),
                'changes':   len(changes),
                'warnings':  len(warnings),
            }) + '\n')

        print(f"\n✅  cases.json updated. {len(changes)} value(s) refreshed.")
        print(f"    Audit entry written to {audit_path}")
    else:
        print("    cases.json not rewritten (no changes).")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='Refresh eval cases from live ledger CSV')
    parser.add_argument('--csv', type=Path, default=DEFAULT_CSV,
                        help=f'Path to ledger CSV (default: {DEFAULT_CSV})')
    parser.add_argument('--dry-run', action='store_true',
                        help='Print what would change without writing')
    args = parser.parse_args()

    refresh_cases(csv_path=args.csv, dry_run=args.dry_run)


if __name__ == '__main__':
    main()
