"""
db.py
Loads the enriched ledger CSV into SQLite and creates analytical views.
Call build_database() on startup to (re)build from the CSV.

CSV source of truth: data/syndicate_ledger.csv
Schema: uuid, date, user, home_team, away_team, competition, bet_type,
        selection, odds, stake, status, actual_winnings, matchday, sport
"""

import sqlite3
import pandas as pd
from pathlib import Path

DB_PATH  = Path(__file__).parent / "data" / "ledger.db"
CSV_PATH = Path(__file__).parent / "data" / "syndicate_ledger.csv"

VIEWS = [
    (
        "v_summary",
        """
        CREATE VIEW IF NOT EXISTS v_summary AS
        SELECT
            COUNT(*)                                                AS total_bets,
            SUM(CASE WHEN status = 'Win'  THEN 1 ELSE 0 END)       AS wins,
            SUM(CASE WHEN status = 'Loss' THEN 1 ELSE 0 END)       AS losses,
            SUM(CASE WHEN status = 'Push' THEN 1 ELSE 0 END)       AS pushes,
            ROUND(SUM(stake), 2)                                    AS total_staked,
            ROUND(SUM(actual_winnings), 2)                         AS total_pl,
            ROUND(SUM(actual_winnings) / NULLIF(SUM(stake),0)*100, 2) AS roi_pct,
            ROUND(
                100.0 * SUM(CASE WHEN status='Win' THEN 1 ELSE 0 END)
                / NULLIF(SUM(CASE WHEN status IN ('Win','Loss') THEN 1 ELSE 0 END),0),
                2
            )                                                       AS win_rate_pct
        FROM bets
        WHERE status IN ('Win', 'Loss', 'Push')
        AND stake > 0
        AND LOWER(COALESCE(user,'')) != 'syndicate'
        """,
    ),
    (
        "v_by_bet_type",
        """
        CREATE VIEW IF NOT EXISTS v_by_bet_type AS
        SELECT
            bet_type,
            COUNT(*)                                                AS total_bets,
            SUM(CASE WHEN status='Win'  THEN 1 ELSE 0 END)         AS wins,
            SUM(CASE WHEN status='Loss' THEN 1 ELSE 0 END)         AS losses,
            ROUND(SUM(stake), 2)                                    AS total_staked,
            ROUND(SUM(actual_winnings), 2)                         AS total_pl,
            ROUND(SUM(actual_winnings) / NULLIF(SUM(stake),0)*100, 2) AS roi_pct,
            ROUND(
                100.0 * SUM(CASE WHEN status='Win' THEN 1 ELSE 0 END)
                / NULLIF(SUM(CASE WHEN status IN ('Win','Loss') THEN 1 ELSE 0 END),0),
                2
            )                                                       AS win_rate_pct
        FROM bets
        WHERE status IN ('Win', 'Loss', 'Push')
        AND stake > 0
        AND LOWER(COALESCE(user,'')) != 'syndicate'
        GROUP BY bet_type
        ORDER BY total_pl DESC
        """,
    ),
    (
        "v_by_competition",
        """
        CREATE VIEW IF NOT EXISTS v_by_competition AS
        SELECT
            competition,
            COUNT(*)                                                AS total_bets,
            SUM(CASE WHEN status='Win'  THEN 1 ELSE 0 END)         AS wins,
            SUM(CASE WHEN status='Loss' THEN 1 ELSE 0 END)         AS losses,
            ROUND(SUM(stake), 2)                                    AS total_staked,
            ROUND(SUM(actual_winnings), 2)                         AS total_pl,
            ROUND(SUM(actual_winnings) / NULLIF(SUM(stake),0)*100, 2) AS roi_pct,
            ROUND(
                100.0 * SUM(CASE WHEN status='Win' THEN 1 ELSE 0 END)
                / NULLIF(SUM(CASE WHEN status IN ('Win','Loss') THEN 1 ELSE 0 END),0),
                2
            )                                                       AS win_rate_pct
        FROM bets
        WHERE status IN ('Win', 'Loss', 'Push')
        AND stake > 0
        AND LOWER(COALESCE(user,'')) != 'syndicate'
        GROUP BY competition
        ORDER BY total_pl DESC
        """,
    ),
    (
        "v_by_user",
        """
        CREATE VIEW IF NOT EXISTS v_by_user AS
        SELECT
            user,
            COUNT(*)                                                AS total_bets,
            SUM(CASE WHEN status='Win'  THEN 1 ELSE 0 END)         AS wins,
            SUM(CASE WHEN status='Loss' THEN 1 ELSE 0 END)         AS losses,
            ROUND(SUM(stake), 2)                                    AS total_staked,
            ROUND(SUM(actual_winnings), 2)                         AS total_pl,
            ROUND(SUM(actual_winnings) / NULLIF(SUM(stake),0)*100, 2) AS roi_pct,
            ROUND(
                100.0 * SUM(CASE WHEN status='Win' THEN 1 ELSE 0 END)
                / NULLIF(SUM(CASE WHEN status IN ('Win','Loss') THEN 1 ELSE 0 END),0),
                2
            )                                                       AS win_rate_pct
        FROM bets
        WHERE status IN ('Win', 'Loss', 'Push')
        AND stake > 0
        AND LOWER(COALESCE(user,'')) != 'syndicate'
        GROUP BY user
        ORDER BY total_pl DESC
        """,
    ),
    (
        "v_by_month",
        """
        CREATE VIEW IF NOT EXISTS v_by_month AS
        SELECT
            strftime('%Y-%m', date)                                 AS month,
            COUNT(*)                                                AS total_bets,
            SUM(CASE WHEN status='Win'  THEN 1 ELSE 0 END)         AS wins,
            SUM(CASE WHEN status='Loss' THEN 1 ELSE 0 END)         AS losses,
            ROUND(SUM(stake), 2)                                    AS total_staked,
            ROUND(SUM(actual_winnings), 2)                         AS monthly_pl,
            ROUND(SUM(actual_winnings) / NULLIF(SUM(stake),0)*100, 2) AS roi_pct
        FROM bets
        WHERE status IN ('Win', 'Loss', 'Push')
        AND stake > 0
        AND LOWER(COALESCE(user,'')) != 'syndicate'
        GROUP BY month
        ORDER BY month
        """,
    ),
    (
        "v_by_team",
        """
        CREATE VIEW IF NOT EXISTS v_by_team AS
        SELECT
            team,
            COUNT(*)                                                AS total_bets,
            SUM(CASE WHEN status='Win'  THEN 1 ELSE 0 END)         AS wins,
            SUM(CASE WHEN status='Loss' THEN 1 ELSE 0 END)         AS losses,
            ROUND(SUM(stake), 2)                                    AS total_staked,
            ROUND(SUM(actual_winnings), 2)                         AS total_pl,
            ROUND(SUM(actual_winnings) / NULLIF(SUM(stake),0)*100, 2) AS roi_pct,
            ROUND(
                100.0 * SUM(CASE WHEN status='Win' THEN 1 ELSE 0 END)
                / NULLIF(SUM(CASE WHEN status IN ('Win','Loss') THEN 1 ELSE 0 END),0),
                2
            )                                                       AS win_rate_pct
        FROM (
            SELECT home_team AS team, status, stake, actual_winnings FROM bets
            WHERE home_team != 'Multiple' AND status IN ('Win','Loss','Push') AND stake > 0 AND LOWER(COALESCE(user,'')) != 'syndicate'
            UNION ALL
            SELECT away_team AS team, status, stake, actual_winnings FROM bets
            WHERE away_team != 'Multiple' AND status IN ('Win','Loss','Push') AND stake > 0 AND LOWER(COALESCE(user,'')) != 'syndicate'
        )
        GROUP BY team
        ORDER BY total_pl DESC
        """,
    ),
    (
        "v_by_selection",
        """
        CREATE VIEW IF NOT EXISTS v_by_selection AS
        SELECT
            selection,
            COUNT(*)                                                AS total_bets,
            SUM(CASE WHEN status='Win'  THEN 1 ELSE 0 END)         AS wins,
            SUM(CASE WHEN status='Loss' THEN 1 ELSE 0 END)         AS losses,
            ROUND(SUM(stake), 2)                                    AS total_staked,
            ROUND(SUM(actual_winnings), 2)                         AS total_pl,
            ROUND(SUM(actual_winnings) / NULLIF(SUM(stake),0)*100, 2) AS roi_pct
        FROM bets
        WHERE status IN ('Win', 'Loss', 'Push')
        AND stake > 0
        AND LOWER(COALESCE(user,'')) != 'syndicate'
          AND selection != 'Multiple'
        GROUP BY selection
        ORDER BY total_pl DESC
        """,
    ),
    (
        "v_running_pl",
        """
        CREATE VIEW IF NOT EXISTS v_running_pl AS
        SELECT
            uuid, date, user, home_team, away_team,
            actual_winnings,
            ROUND(SUM(actual_winnings) OVER (ORDER BY date, rowid), 2) AS running_pl
        FROM bets
        WHERE status IN ('Win', 'Loss', 'Push')
        AND LOWER(COALESCE(user,'')) != 'syndicate'
        ORDER BY date, rowid
        """,
    ),
]


def build_database(csv_path: Path = CSV_PATH, db_path: Path = DB_PATH) -> None:
    """Rebuild SQLite DB from CSV. Safe to call on every startup."""
    db_path.parent.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(csv_path)
    df.columns = df.columns.str.strip()
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")

    conn = sqlite3.connect(db_path)
    try:
        df.to_sql("bets", conn, if_exists="replace", index=False)
        for view_name, view_sql in VIEWS:
            conn.execute(f"DROP VIEW IF EXISTS {view_name}")
            conn.execute(view_sql)
        conn.commit()
        print(f"✅ Database built: {len(df)} rows, {len(VIEWS)} views.")
    finally:
        conn.close()


def get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    """Return a read-only SQLite connection."""
    uri = f"file:{db_path}?mode=ro"
    return sqlite3.connect(uri, uri=True, check_same_thread=False)


if __name__ == "__main__":
    build_database()
