# 🏆 Syndicate Tracker (Xanderdu)

An advanced, full-stack betting syndicate management suite. This project combines a highly visual Streamlit dashboard with an always-on Telegram background worker, powered by Google's Gemini AI and LangChain. 

The system automatically syncs with a Google Sheets ledger, auto-grades pending matches using The Odds API, and features an AI "Betbot" capable of answering complex SQL queries about betting performance in natural language.

---

## ✨ Core Features

* **📊 Mobile-Optimized Dashboard:** A comprehensive Streamlit UI featuring Plotly visualizations like Bankroll Splines, Flow of Money Sankeys, Odds Beeswarms, and Member Radar charts.
* **🤖 Betbot (LangChain SQL Agent):** An integrated Gemini-powered AI agent that interrogates the local SQLite database to answer natural language questions about syndicate performance.
* **⚙️ Automated Grading Engine:** Background polling automatically grades pending bets as Wins, Losses, or Pushes using live data from The Odds API.
* **📝 The Chronicler:** An automated weekly scheduled task that generates and broadcasts a persona-based syndicate performance report to Telegram (e.g., "The Statistician", "The Pirate", "The Pundit").
* **📱 Telegram Integration:** A long-polling Telegram bot that routes messages, provides instant on-demand commands (e.g., `? pending`, `? bank`), and delivers scheduled grading updates.

---

## 🏗️ Architecture & Data Flow

1.  **Source of Truth:** Google Sheets acts as the live entry point for the ledger.
2.  **Local Sync:** The app pulls the Google Sheet into a local CSV (`data/syndicate_ledger.csv`).
3.  **Database Build:** The CSV is ingested into a local SQLite database (`data/ledger.db`), automatically generating pre-calculated analytical views (`v_summary`, `v_by_bet_type`, etc.) for optimal AI querying.
4.  **Dual Execution:** The frontend (`app.py`) and background worker (`bot_runner.py`) operate independently on this synchronized local data.

---

## 🚀 Installation & Setup

### 1. Prerequisites
* Python 3.10+
* Google Cloud Service Account credentials (`credentials.json`).
* API Keys: Gemini, Telegram Bot, and The Odds API.

### 2. Clone & Install
```bash
git clone https://github.com/yourusername/syndicate-tracker.git
cd syndicate-tracker
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Environment Configuration (`.env`)
Create a `.env` file in the root directory and configure the following variables:

```env
# APIs
GEMINI_API_KEY=your_gemini_api_key
ODDS_API_KEY=your_odds_api_key
TELEGRAM_BOT_TOKEN=your_telegram_bot_token

# Telegram Routing
TELEGRAM_CHAT_ID=your_primary_group_chat_id
TEST_CHAT_ID=your_personal_dm_chat_id

# Google Sheets
GSHEET_ID=your_google_sheet_id
GSHEET_TAB=syndicate_ledger_v3
GOOGLE_CREDENTIALS_PATH=credentials.json

# Core App Settings
OPENING_BANK=0.00
GEMINI_MODEL=gemini-3.1-flash-lite-preview

# Feature Flags (Set to 'true' or 'false')
TEST_MODE=false
USE_GSHEETS_LIVE=true
USE_ODDS_API_LIVE=true
GRADING_DRY_RUN=false
BETBOT_LIVE=true
CHRONICLER_LIVE=true
```

### 4. Database Schema Requirements
The Google Sheet must contain the following exact column headers to parse correctly:
`uuid`, `date`, `user`, `home_team`, `away_team`, `competition`, `bet_type`, `selection`, `odds`, `stake`, `status`, `actual_winnings`, `matchday`, `sport`.

### 5. Telegram User Mapping
To ensure the bot accurately recognizes syndicate members via Telegram DMs, update the `TELEGRAM_USER_MAP` dictionary in `bot_runner.py` with the specific Telegram User IDs of your members (obtainable via `@userinfobot`).

---

## 🏃‍♂️ Running the Ecosystem

Because this project consists of a UI and a background worker, you must run both processes, ideally in separate terminal windows.

**Start the Web Dashboard:**
```bash
streamlit run app.py
```

**Start the Background Worker (Grading & Telegram Bot):**
```bash
python bot_runner.py
```

***