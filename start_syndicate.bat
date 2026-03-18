@echo off
cd /d "%~dp0"

echo Starting Syndicate Tracker v6.0...

:: Launch the Streamlit UI in a new window
:: (cmd /k keeps the window open so you can see errors if it crashes)
start "Syndicate UI (Streamlit)" cmd /k "call .venv\Scripts\activate && python -m streamlit run app.py"

:: Launch the Telegram Bot in a new window
start "Syndicate Bot (Telegram)" cmd /k "call .venv\Scripts\activate && python bot_runner.py"

echo Both services have been launched in separate windows!
echo You can close this main window now.
pause