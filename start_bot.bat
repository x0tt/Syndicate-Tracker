@echo off
cd /d "%~dp0"
call .venv\Scripts\activate
echo Starting Telegram bot runner...
py -3.13 bot_runner.py
pause
