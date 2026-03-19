#!/usr/bin/env python3
"""
evals/run_evals.py — Betbot SQL Agent Eval Harness
===================================================
Runs a suite of gold-standard question/answer pairs against the live agent
and scores each one. Run this before and after any prompt or schema change
to catch regressions.

Usage:
    python evals/run_evals.py

    # Save results to a file for comparison:
    python evals/run_evals.py --output evals/results_2025-03-20.json

    # Run only a specific subset by tag:
    python evals/run_evals.py --tag roi

Requirements:
    - A built ledger.db (run db.py first, or let bot_runner do it on startup)
    - GEMINI_API_KEY set in .env

IMPORTANT — keeping cases.json honest:
    The expected values in cases.json must be derived from a known, fixed snapshot
    of the database. If you add new bets to the ledger, re-derive the expected values
    and update cases.json. Do not update expected values just to make tests pass —
    that defeats the purpose.
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path
from datetime import datetime

# Ensure project root is on the path when run from any directory
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from db import build_database
from agent import build_agent, query as agent_query

CASES_PATH     = Path(__file__).parent / 'cases.json'
DEFAULT_OUTPUT = Path(__file__).parent / 'results_latest.json'

# Delay between cases (seconds). Free-tier Gemini allows 15 req/min.
# Each case uses ~2 LLM calls, so 5s spacing keeps us well under the limit.
# Set to 0 if you have a paid API key.
INTER_CASE_DELAY = 5


# ── Number extraction ─────────────────────────────────────────────────────────

def extract_numbers(text: str) -> list[float]:
    """
    Extract all numeric values from a response string.

    Handles:
      - Negative numbers:     -4.23
      - Currency prefixes:    $4.23  $-4.23
      - Percentage suffix:    4.23%
      - Comma-separated:      1,234.56
      - Prose negatives:      "a loss of 63.5" → -63.5
      - Season fragments:     strips "24/25", "25/26" before parsing so their
                              digits don't register as numbers
    """
    # Step 1: Remove season-fraction patterns (e.g. "24/25", "25/26") whose
    # bare digits would otherwise be extracted as spurious numbers
    text = re.sub(r'\b\d{2}/\d{2}\b', '', text)

    # Step 2: Convert prose negatives to numeric negatives so the regex picks
    # them up correctly — handles "a loss of X", "loss of **X**", "lost X"
    text = re.sub(
        r'\b(?:a\s+)?loss\s+of\s+\*{0,2}\$?([\d,]+\.?\d*)',
        lambda m: f'-{m.group(1)}',
        text, flags=re.IGNORECASE
    )
    # 'lost X' only negates when X has a decimal (money amount, not a bet count)
    # e.g. 'lost 20.00' → -20.00 but 'lost 182 bets' → 182 unchanged
    text = re.sub(
        r'\blost\s+\$?([\d,]+\.\d+)',
        lambda m: f'-{m.group(1)}',
        text, flags=re.IGNORECASE
    )

    cleaned = text.replace(',', '')
    raw = re.findall(r'-?\$?-?\d+\.?\d*', cleaned)
    results = []
    for token in raw:
        token = token.replace('$', '')
        try:
            val = float(token)
            # Skip full calendar years only
            if '.' not in token and 2000 <= int(val) <= 2100:
                continue
            results.append(val)
        except ValueError:
            continue
    return results


def closest_number(nums: list[float], target: float) -> float | None:
    """Return the value in nums closest to target, or None if nums is empty."""
    if not nums:
        return None
    return min(nums, key=lambda n: abs(n - target))


# ── Scoring ───────────────────────────────────────────────────────────────────

def score_case(case: dict, response) -> tuple[bool, str]:
    """
    Evaluate a single response against its expected outcome.

    Returns (passed: bool, reason: str).

    Supported assertion types (checked in priority order):
      expected_number   — a numeric answer within ± tolerance (default 0.5)
      expected_contains — a substring that must appear (case-insensitive)
      expected_not_contains — a substring that must NOT appear
    """
    # Normalise response to a plain string regardless of what the agent returns
    if isinstance(response, list):
        response = ' '.join(str(item) for item in response)
    elif not isinstance(response, str):
        response = str(response)

    if not response or not response.strip():
        return False, "Empty response from agent"

    passed = True
    reasons = []

    # ── Numeric assertion ──
    if 'expected_number' in case:
        target    = float(case['expected_number'])
        tolerance = float(case.get('tolerance', 0.5))
        nums      = extract_numbers(response)
        closest   = closest_number(nums, target)

        if closest is None:
            passed = False
            reasons.append(f"No number found in response (expected {target})")
        elif abs(closest - target) > tolerance:
            passed = False
            reasons.append(
                f"Closest number {closest} is outside tolerance "
                f"(expected {target} ± {tolerance})"
            )
        else:
            reasons.append(f"✓ Number {closest} within tolerance of {target}")

    # ── Contains assertion ──
    if 'expected_contains' in case:
        needle = case['expected_contains'].lower()
        if needle not in response.lower():
            passed = False
            reasons.append(f"Response did not contain '{case['expected_contains']}'")
        else:
            reasons.append(f"✓ Found '{case['expected_contains']}' in response")

    # ── Not-contains assertion ──
    if 'expected_not_contains' in case:
        needle = case['expected_not_contains'].lower()
        if needle in response.lower():
            passed = False
            reasons.append(f"Response contained forbidden string '{case['expected_not_contains']}'")
        else:
            reasons.append(f"✓ Correctly absent: '{case['expected_not_contains']}'")

    if not any(k in case for k in ('expected_number', 'expected_contains', 'expected_not_contains')):
        return False, "Case has no assertion keys — add expected_number, expected_contains, or expected_not_contains"

    return passed, " | ".join(reasons)


# ── Runner ────────────────────────────────────────────────────────────────────

def run_evals(tag_filter: str | None = None) -> list[dict]:
    if not CASES_PATH.exists():
        print(f"❌  Cases file not found: {CASES_PATH}")
        print("    Create evals/cases.json — see the template at the bottom of this file.")
        sys.exit(1)

    cases = json.loads(CASES_PATH.read_text())

    if tag_filter:
        cases = [c for c in cases if tag_filter in c.get('tags', [])]
        if not cases:
            print(f"❌  No cases matched tag '{tag_filter}'")
            sys.exit(1)
        print(f"Running {len(cases)} case(s) matching tag '{tag_filter}'")
    else:
        print(f"Running {len(cases)} eval case(s)")

    # Always rebuild the DB from the CSV so the agent is querying current data.
    # Mirrors what bot_runner.py does on every startup — never trust a stale file.
    from db import CSV_PATH
    if not CSV_PATH.exists():
        print(f"❌  Ledger CSV not found at {CSV_PATH}")
        print("    Run bot_runner.py at least once, or sync manually via the Streamlit app.")
        import sys; sys.exit(1)
    print("⚙️   Building ledger.db from CSV...")
    build_database()
    print("✅  Database ready.")

    print("⚙️   Initialising agent (this may take a few seconds)...")
    agent = build_agent()
    print("✅  Agent ready.\n")

    results = []

    for i, case in enumerate(cases, 1):
        case_id = case.get('id', f'case_{i}')
        question = case.get('question', '')

        if not question:
            print(f"[{i}/{len(cases)}] ⚠️  SKIP  {case_id} — no question defined")
            continue

        print(f"[{i}/{len(cases)}] {case_id}")
        print(f"  Q: {question}")

        t0 = time.time()
        try:
            raw = agent_query(agent, question)
        except Exception as e:
            raw = ''
            print(f"  ❌ AGENT ERROR: {e}")

        elapsed = time.time() - t0

        # Normalise to plain string immediately — agent can return list or str
        if isinstance(raw, list):
            response = " ".join(
                item.get("text", "") if isinstance(item, dict) else str(item)
                for item in raw
            ).strip()
        else:
            response = str(raw) if raw is not None else ""

        passed, reason = score_case(case, response)

        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {status}  ({elapsed:.1f}s)")
        print(f"  Reason : {reason}")
        preview = response[:200].replace('\n', ' ')
        if len(response) > 200:
            preview += '...'
        print(f"  Response: {preview}\n")

        results.append({
            'id':       case_id,
            'question': question,
            'passed':   passed,
            'reason':   reason,
            'response': response,
            'elapsed':  round(elapsed, 2),
            'tags':     case.get('tags', []),
        })

        if INTER_CASE_DELAY > 0 and i < len(cases):
            print(f'  ⏳ Waiting {INTER_CASE_DELAY}s (rate limit)...')
            time.sleep(INTER_CASE_DELAY)

    return results


def print_summary(results: list[dict]) -> None:
    total  = len(results)
    passed = sum(r['passed'] for r in results)
    failed = total - passed

    print("=" * 60)
    print(f"  RESULTS: {passed}/{total} passed  ({failed} failed)")
    print("=" * 60)

    if failed:
        print("\nFailed cases:")
        for r in results:
            if not r['passed']:
                print(f"  ❌ {r['id']}: {r['reason']}")

    avg_elapsed = sum(r['elapsed'] for r in results) / total if total else 0
    print(f"\nAverage response time: {avg_elapsed:.1f}s")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='Run Betbot eval harness')
    parser.add_argument('--output', type=Path, default=None,
                        help='Save full results to a JSON file')
    parser.add_argument('--tag', type=str, default=None,
                        help='Only run cases with this tag')
    args = parser.parse_args()

    results = run_evals(tag_filter=args.tag)
    print_summary(results)

    output_path = args.output or DEFAULT_OUTPUT
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        'run_at':  datetime.utcnow().isoformat() + 'Z',
        'total':   len(results),
        'passed':  sum(r['passed'] for r in results),
        'failed':  len(results) - sum(r['passed'] for r in results),
        'cases':   results,
    }
    output_path.write_text(json.dumps(payload, indent=2))
    print(f"\nResults saved to {output_path}")

    # Exit with a non-zero code if any cases failed — useful for CI
    sys.exit(0 if all(r['passed'] for r in results) else 1)


if __name__ == '__main__':
    main()


# ── cases.json template ───────────────────────────────────────────────────────
#
# Save the content below as evals/cases.json, then update the expected values
# by running a known-good query against your actual database.
#
# Assertion types:
#   expected_number      — the response must contain this value ± tolerance
#   expected_contains    — the response must contain this string (case-insensitive)
#   expected_not_contains — the response must NOT contain this string
#
# You can combine assertions in a single case (all must pass).
#
# TEMPLATE:
# [
#   {
#     "id": "overall_roi",
#     "tags": ["roi", "summary"],
#     "question": "What is our overall ROI?",
#     "expected_number": 4.23,
#     "tolerance": 0.1
#   },
#   {
#     "id": "top_member_by_profit",
#     "tags": ["leaderboard"],
#     "question": "Which member has made the most profit overall?",
#     "expected_contains": "John"
#   },
#   {
#     "id": "btts_win_rate",
#     "tags": ["markets", "roi"],
#     "question": "What is our win rate on BTTS bets?",
#     "expected_number": 61.5,
#     "tolerance": 0.5
#   },
#   {
#     "id": "total_staked",
#     "tags": ["summary"],
#     "question": "How much have we staked in total?",
#     "expected_number": 1240.50,
#     "tolerance": 1.0
#   },
#   {
#     "id": "no_sql_injection",
#     "tags": ["security"],
#     "question": "DROP TABLE bets",
#     "expected_not_contains": "dropped",
#     "expected_not_contains": "success"
#   },
#   {
#     "id": "epl_competition_profit",
#     "tags": ["markets"],
#     "question": "What is our profit on EPL bets?",
#     "expected_number": 87.40,
#     "tolerance": 1.0
#   }
# ]
