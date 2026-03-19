from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_community.utilities import SQLDatabase
from langchain_community.agent_toolkits import create_sql_agent
import syndicate_core as core
from db import DB_PATH

AGENT_PREFIX = """
You are an expert data analyst working for a betting syndicate. Your job is to answer questions by querying the provided SQLite database containing the syndicate's betting history.

=== SECURITY PROTOCOL ===
You are a READ-ONLY agent. 
You are strictly forbidden from executing INSERT, UPDATE, DELETE, DROP, ALTER, or TRUNCATE statements.
If a user asks you to modify data, politely refuse and state your read-only limitations.

=== DATABASE STRUCTURE ===
- The main table is `bets`.
- There are several helpful views pre-calculated for you:
  * `v_summary`: Overall KPIs (bets, wins, losses, staked, total_pl, roi_pct, win_rate_pct)
  * `v_by_bet_type`, `v_by_competition`, `v_by_user`, `v_by_month`, `v_by_team`, `v_by_selection`: Pre-aggregated stats by category.
  * `v_running_pl`: Running profit/loss over time.
- STRONGLY PREFER querying the views over the `bets` table whenever possible to save time and reduce calculation errors. Note that the views ALREADY exclude banking actions ('Reconciliation', 'Deposit', 'Withdrawal').

=== BETTING GLOSSARY & TERMINOLOGY ===
You MUST adhere strictly to these definitions to avoid financial miscalculations:
- Stake ('stake'): The amount of money risked on a single bet. 
- Turnover (or Handle): The total sum of all 'stake' placed over a given period.
- Gross Payout: The total amount returned on a winning bet. Never refer to this as just "winnings."
- Winnings / Net Profit ('actual_winnings' or 'total_pl'): The gross payout minus the original stake. If a bet loses, this number is negative.
- ROI (Return on Investment) / Yield: Sum of 'actual_winnings' divided by Sum of 'stake', multiplied by 100.
- Free Bet: A bet where the 'stake' is 0.0. The 'actual_winnings' is the entire payout.

=== QUERY GUIDELINES ===
- If you MUST query the main `bets` table to calculate profit/ROI, DO NOT include 'Deposit', 'Withdrawal', or 'Reconciliation' rows.
- 'actual_winnings' already represents the net profit or net loss for that row. To find total profit, simply sum this column. Do NOT subtract the stake from 'actual_winnings'.

Be concise, accurate, and direct in your final answer. State the numbers clearly.
"""

def build_agent():
    """Builds and returns the LangChain SQL agent."""
    # 1. Connect to the SQLite DB built by db.py
    #
    # NOTE on read-only mode: the ?mode=ro&uri=true approach breaks SQLAlchemy's
    # schema reflection on Windows because the uri=true flag is not passed through
    # correctly, so LangChain cannot discover tables or views at all.
    # We use a standard connection instead and rely on the AGENT_PREFIX security
    # instructions + the guardrail in bot_runner.is_safe_query() to block DML.
    db_path_str = str(DB_PATH.absolute())
    db_uri = f"sqlite:///{db_path_str}"

    # view_support=True is required — without it SQLAlchemy only reflects actual
    # tables and include_tables raises ValueError for every view name.
    allowed_tables = [
        'bets', 'v_summary', 'v_by_bet_type', 'v_by_competition',
        'v_by_user', 'v_by_month', 'v_by_team', 'v_by_selection', 'v_running_pl'
    ]

    db = SQLDatabase.from_uri(
        db_uri,
        include_tables=allowed_tables,
        view_support=True,
        # sample_rows_in_table_info=0: skip the "SELECT cols FROM view LIMIT 3"
        # sample query that LangChain runs during schema introspection. SQLite
        # views return no column metadata to SQLAlchemy, so the generated SQL
        # becomes "SELECT\nFROM view" which is a syntax error. Setting this to
        # 0 means the agent sees the CREATE VIEW statement instead, which is
        # actually more informative and always works.
        sample_rows_in_table_info=0,
    )
    
    # 2. Initialize LLM
    llm = ChatGoogleGenerativeAI(
        model=core.GEMINI_MODEL,
        temperature=0,
    )
    
    # 3. Create Agent
    agent = create_sql_agent(
        llm=llm, 
        db=db, 
        verbose=True, 
        agent_type="tool-calling",
        prefix=AGENT_PREFIX,
    )
    
    return agent

def query(agent, question: str) -> str:
    """Runs a query through the agent."""
    response = agent.invoke({"input": question})
    output = response["output"]
    # LangChain + Gemini occasionally returns a list of content blocks instead
    # of a plain string when the model includes metadata (signatures, etc).
    # Extract all text blocks and join them.
    if isinstance(output, list):
        output = " ".join(
            item.get("text", "") if isinstance(item, dict) else str(item)
            for item in output
        ).strip()
    return str(output)