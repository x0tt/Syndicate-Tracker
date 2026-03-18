@echo off
:: Move into the folder where this batch file lives
cd /d "%~dp0"

echo [SYSTEM] Activating Virtual Environment...
:: We point directly to the python.exe inside your .venv
set PYTHON_PATH=%~dp0.venv\Scripts\python.exe

echo [SYSTEM] Starting Syndicate Bot Runner...
echo ------------------------------------------------------------

:: Run the bot using the specific environment's python
"%PYTHON_PATH%" bot_runner.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Bot crashed or stopped with an error.
    pause
)