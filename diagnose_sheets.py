#!/usr/bin/env python3
"""
diagnose_sheets.py
Run this from your project directory to diagnose Google Sheets write-back.
Usage: python diagnose_sheets.py
"""
import os, sys, json
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

print("=" * 60)
print("GOOGLE SHEETS DIAGNOSTIC")
print("=" * 60)

# ── 1. Check env vars ──────────────────────────────────────────
GSHEET_ID         = os.getenv("GSHEET_ID", "")
GSHEET_TAB        = os.getenv("GSHEET_TAB", "syndicate_ledger_v3")
CREDS_PATH        = Path(os.getenv("GOOGLE_CREDENTIALS_PATH", "credentials.json"))
USE_GSHEETS_LIVE  = os.getenv("USE_GSHEETS_LIVE", "NOT SET")

print(f"\n[1] ENV VARS")
print(f"  USE_GSHEETS_LIVE      = '{USE_GSHEETS_LIVE}'")
print(f"  GSHEET_ID             = '{GSHEET_ID[:20]}...' " if len(GSHEET_ID) > 20 else f"  GSHEET_ID             = '{GSHEET_ID}'")
print(f"  GSHEET_TAB            = '{GSHEET_TAB}'")
print(f"  GOOGLE_CREDENTIALS_PATH = '{CREDS_PATH}'")

live = str(USE_GSHEETS_LIVE).lower() == "true"
if not live:
    print(f"\n  ❌ USE_GSHEETS_LIVE is '{USE_GSHEETS_LIVE}' — all writes are DRY RUN.")
    print("     Fix: add  USE_GSHEETS_LIVE=true  to your .env file")
else:
    print(f"  ✅ USE_GSHEETS_LIVE=true — writes will go live")

if not GSHEET_ID:
    print("  ❌ GSHEET_ID is empty — set it in .env")
else:
    print(f"  ✅ GSHEET_ID is set")

# ── 2. Check credentials file ──────────────────────────────────
print(f"\n[2] CREDENTIALS FILE")
if not CREDS_PATH.exists():
    # try common alternative locations
    alts = [Path("credentials.json"), Path("betbot-credentials.json"),
            Path("service_account.json"), Path("google_credentials.json")]
    found = next((p for p in alts if p.exists()), None)
    if found:
        print(f"  ⚠️  '{CREDS_PATH}' not found, but '{found}' exists.")
        print(f"     Fix: set GOOGLE_CREDENTIALS_PATH={found} in .env")
    else:
        print(f"  ❌ '{CREDS_PATH}' not found. Checked: {[str(p) for p in alts]}")
    sys.exit(1)
else:
    print(f"  ✅ '{CREDS_PATH}' found")
    try:
        creds_data = json.loads(CREDS_PATH.read_text())
        sa_email = creds_data.get("client_email", "NOT FOUND")
        proj     = creds_data.get("project_id", "NOT FOUND")
        print(f"  ✅ Service account: {sa_email}")
        print(f"  ✅ Project:         {proj}")
    except Exception as e:
        print(f"  ❌ Could not parse credentials JSON: {e}")
        sys.exit(1)

# ── 3. Try to connect ──────────────────────────────────────────
print(f"\n[3] GSPREAD CONNECTION")
try:
    import gspread
    from google.oauth2.service_account import Credentials
    creds = Credentials.from_service_account_file(
        str(CREDS_PATH),
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    gc = gspread.authorize(creds)
    print("  ✅ gspread authorised")
except ImportError as e:
    print(f"  ❌ Missing package: {e}")
    print("     Fix: pip install gspread google-auth")
    sys.exit(1)
except Exception as e:
    print(f"  ❌ Auth failed: {e}")
    sys.exit(1)

# ── 4. Try to open spreadsheet ─────────────────────────────────
print(f"\n[4] OPEN SPREADSHEET  (id={GSHEET_ID[:20]}...)")
try:
    sh = gc.open_by_key(GSHEET_ID)
    print(f"  ✅ Opened: '{sh.title}'")
    sheets = [ws.title for ws in sh.worksheets()]
    print(f"  ✅ Worksheets: {sheets}")
except gspread.exceptions.SpreadsheetNotFound:
    print(f"  ❌ Spreadsheet not found.")
    print(f"     — Double-check GSHEET_ID in .env")
    print(f"     — Make sure {sa_email} has 'Editor' access to the sheet")
    sys.exit(1)
except gspread.exceptions.APIError as e:
    print(f"  ❌ API error: {e}")
    sys.exit(1)
except Exception as e:
    print(f"  ❌ Unexpected error: {e}")
    sys.exit(1)

# ── 5. Try to open the specific tab ────────────────────────────
print(f"\n[5] OPEN TAB '{GSHEET_TAB}'")
try:
    ws = sh.worksheet(GSHEET_TAB)
    row_count = len(ws.get_all_values())
    print(f"  ✅ Tab found — {row_count} rows (including header)")
except gspread.exceptions.WorksheetNotFound:
    print(f"  ❌ Tab '{GSHEET_TAB}' not found in this spreadsheet.")
    print(f"     Available tabs: {sheets}")
    print(f"     Fix: set GSHEET_TAB=<correct tab name> in .env")
    sys.exit(1)

# ── 6. Try a test read ─────────────────────────────────────────
print(f"\n[6] TEST READ (first row)")
try:
    headers = ws.row_values(1)
    print(f"  ✅ Headers: {headers[:8]}{'...' if len(headers) > 8 else ''}")
except Exception as e:
    print(f"  ❌ Read failed: {e}")
    sys.exit(1)

# ── 7. Try a test write (appends a dummy row, then deletes it) ─
print(f"\n[7] TEST WRITE (append + delete a dummy row)")
try:
    # Append a clearly-labelled test row
    test_row = ["DIAG_TEST", "1900-01-01", "DIAGNOSTIC", "diagnostic write — safe to delete",
                "DIAG", "DIAG", 1.0, 0.0, "Void", 0.0]
    ws.append_row(test_row, value_input_option="USER_ENTERED")
    print("  ✅ append_row succeeded")

    # Find and delete it immediately
    all_uuids = ws.col_values(1)
    try:
        row_num = all_uuids.index("DIAG_TEST") + 1
        ws.delete_rows(row_num)
        print(f"  ✅ Test row deleted (was row {row_num})")
    except ValueError:
        print("  ⚠️  Test row appended but could not find it to delete — delete 'DIAG_TEST' row manually")

except gspread.exceptions.APIError as e:
    print(f"  ❌ Write failed with API error: {e}")
    print("     Most likely cause: service account does not have Editor permission.")
    print(f"     Go to the sheet → Share → add {sa_email} as Editor")
    sys.exit(1)
except Exception as e:
    print(f"  ❌ Write failed: {e}")
    sys.exit(1)

# ── 8. Check failed_writes.log ────────────────────────────────
print(f"\n[8] FAILED WRITES LOG")
log_path = Path("logs/failed_writes.log")
if not log_path.exists() or log_path.stat().st_size == 0:
    print("  ✅ No pending failed writes")
else:
    lines = [l for l in log_path.read_text().splitlines() if l.strip()]
    print(f"  ⚠️  {len(lines)} pending failed write(s):")
    for line in lines[:3]:
        try:
            rec = json.loads(line)
            print(f"     {rec.get('timestamp','')} — {rec.get('fn','')} — {str(rec.get('error',''))[:60]}")
        except Exception:
            print(f"     {line[:80]}")

print("\n" + "=" * 60)
print("ALL CHECKS PASSED — Sheets write-back should be working.")
print("=" * 60)
