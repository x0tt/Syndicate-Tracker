#!/usr/bin/env python3
"""
upload_csv_to_sheets.py  —  ONE-TIME migration tool
====================================================
Uploads your local syndicate_ledger_v3.csv into the Google Sheet,
replacing whatever is there (currently just the header row).

Safe to re-run: clears the sheet first, then writes fresh.

Usage:
    python upload_csv_to_sheets.py
    python upload_csv_to_sheets.py --dry-run     # preview only, no writes
    python upload_csv_to_sheets.py --csv path/to/other.csv
"""

import argparse
import sys
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

load_dotenv()

import syndicate_core as core   # loads env vars and paths

BATCH_SIZE = 500  # rows per API call — stays well inside gspread limits


def upload(csv_path: Path, dry_run: bool = False) -> None:
    print(f"\n{'[DRY RUN] ' if dry_run else ''}Uploading {csv_path} → Sheet '{core.GSHEET_TAB}'")

    # ── Load CSV ──────────────────────────────────────────────────────────────
    if not csv_path.exists():
        print(f"❌ CSV not found: {csv_path}")
        sys.exit(1)

    df = pd.read_csv(csv_path)
    df.columns = df.columns.str.strip()          # remove any trailing spaces from headers
    df = df.where(pd.notnull(df), "")            # replace NaN with empty string for Sheets

    print(f"   Loaded {len(df)} rows × {len(df.columns)} columns")
    print(f"   Columns: {df.columns.tolist()}")

    if dry_run:
        print("\n[DRY RUN] Would write the above to Google Sheets. Exiting without writing.")
        return

    # ── Connect ───────────────────────────────────────────────────────────────
    try:
        ws = core.get_worksheet()
        print(f"   ✅ Connected to sheet")
    except Exception as e:
        print(f"   ❌ Could not connect: {e}")
        sys.exit(1)

    # ── Clear existing content ────────────────────────────────────────────────
    print("   Clearing existing sheet content...")
    try:
        ws.clear()
        print("   ✅ Sheet cleared")
    except Exception as e:
        print(f"   ❌ Clear failed: {e}")
        sys.exit(1)

    # ── Write header ──────────────────────────────────────────────────────────
    headers = df.columns.tolist()
    try:
        ws.append_row(headers, value_input_option="USER_ENTERED")
        print(f"   ✅ Header written: {headers[:8]}{'...' if len(headers) > 8 else ''}")
    except Exception as e:
        print(f"   ❌ Header write failed: {e}")
        sys.exit(1)

    # ── Write data in batches ─────────────────────────────────────────────────
    rows = df.values.tolist()
    total = len(rows)
    written = 0

    for start in range(0, total, BATCH_SIZE):
        batch = rows[start : start + BATCH_SIZE]
        # Convert every value to string/int/float — Sheets doesn't accept numpy types
        clean = []
        for row in batch:
            clean_row = []
            for val in row:
                if pd.isna(val) if not isinstance(val, str) else False:
                    clean_row.append("")
                elif hasattr(val, 'item'):   # numpy scalar
                    clean_row.append(val.item())
                else:
                    clean_row.append(val)
            clean.append(clean_row)

        try:
            ws.append_rows(clean, value_input_option="USER_ENTERED")
            written += len(batch)
            print(f"   ✅ Written {written}/{total} rows...")
        except Exception as e:
            print(f"   ❌ Batch write failed at row {start}: {e}")
            sys.exit(1)

    print(f"\n✅ Upload complete — {written} data rows + 1 header row in Sheet.")

    # ── Verify round-trip ─────────────────────────────────────────────────────
    print("\nVerifying round-trip read-back...")
    try:
        records = ws.get_all_records()
        print(f"   ✅ Sheet now has {len(records)} data rows (matches CSV: {len(records) == total})")
        if len(records) != total:
            print(f"   ⚠️  Count mismatch: CSV={total}, Sheet={len(records)}")
    except Exception as e:
        print(f"   ⚠️  Verification read failed: {e}")

    print("\nNext steps:")
    print("  1. Open your Google Sheet and confirm data looks correct")
    print("  2. The Sheet is now the source of truth")
    print("  3. All future bets entered via the Streamlit Inbox or bot will write here automatically")
    print("  4. sync_local_csv() pulls the Sheet back to CSV after every write")


def main():
    parser = argparse.ArgumentParser(description="Upload local CSV to Google Sheets")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview only — no writes to Google Sheets")
    parser.add_argument("--csv", type=str, default=None,
                        help=f"Path to CSV (default: {core.LEDGER_CSV})")
    args = parser.parse_args()

    csv_path = Path(args.csv) if args.csv else core.LEDGER_CSV
    upload(csv_path, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
