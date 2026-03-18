import pandas as pd
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_experimental.agents.agent_toolkits import create_pandas_dataframe_agent
import syndicate_core as core

AGENT_PREFIX = """
You are an expert data analyst working for a betting syndicate. Your job is to answer questions by querying the provided pandas dataframe containing the syndicate's betting history.

=== BETTING GLOSSARY & TERMINOLOGY ===
You MUST adhere strictly to these definitions to avoid financial miscalculations:
- Stake ('stake'): The amount of money risked on a single bet. 
- Turnover (or Handle): The total sum of all 'stake' placed over a given period.
- Gross Payout: The total amount returned on a winning bet. Never refer to this as just "winnings."
- Winnings / Net Profit ('actual_winnings'): The gross payout minus the original stake. If a bet loses, this number is negative.
- ROI (Return on Investment) / Yield: Sum of 'actual_winnings' divided by Sum of 'stake', multiplied by 100.
- Free Bet: A bet where the 'stake' is 0.0. The 'actual_winnings' is the entire payout.

=== DATAFRAME GUIDELINES ===
- The dataframe contains columns like 'uuid', 'date', 'user', 'home_team', 'away_team', 'competition', 'bet_type', 'selection', 'odds', 'stake', 'status', 'actual_winnings'.
- 'status' will typically be 'Win', 'Loss', 'Push', 'Pending', 'Void', or financial actions like 'Deposit', 'Withdrawal', 'Reconciliation'.
- DO NOT include 'Deposit', 'Withdrawal', or 'Reconciliation' rows when calculating betting ROI, Win Rates, or betting profit. Those are banking actions.
- 'actual_winnings' already represents the net profit or net loss for that row. To find total profit, simply sum this column. Do NOT subtract the stake from 'actual_winnings'.

Be concise, accurate, and direct in your final answer. State the numbers clearly.
"""

def build_agent():
    """Builds and returns the LangChain Pandas agent."""
    # 1. Load data
    df_raw, _, _, _, _ = core.load_ledger()
    
    # 2. Initialize LLM
    llm = ChatGoogleGenerativeAI(
        model=core.GEMINI_MODEL,
        temperature=0,
    )
    
    # 3. Create Agent (Pass df_raw directly)
    agent = create_pandas_dataframe_agent(
        llm, 
        df_raw, 
        verbose=True, 
        agent_type="tool-calling",
        prefix=AGENT_PREFIX,
        allow_dangerous_code=True
    )
    
    return agent

def query(agent, question: str) -> str:
    """Runs a query through the agent."""
    response = agent.invoke({"input": question})
    return response["output"]