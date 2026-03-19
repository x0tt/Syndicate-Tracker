@echo off
:: run_evals.bat
:: Runs the Betbot eval harness from the project root.
:: Place this file in your project root (same level as bot_runner.py).
::
:: Usage:
::   run_evals.bat              — full suite
::   run_evals.bat roi          — only cases tagged 'roi'
::   run_evals.bat security     — only cases tagged 'security'

cd /d "%~dp0"

:: Activate virtual environment if one exists
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
) else if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
)

:: Timestamp for the output filename
for /f "tokens=1-4 delims=/-: " %%a in ("%date% %time%") do (
    set DATESTAMP=%%a%%b%%c_%%d
)
set OUTFILE=evals\results_%DATESTAMP%.json

if "%~1"=="" (
    echo Running full eval suite...
    python evals\run_evals.py --output "%OUTFILE%"
) else (
    echo Running eval suite with tag: %~1
    python evals\run_evals.py --tag %~1 --output "%OUTFILE%"
)

echo.
echo Results saved to %OUTFILE%
pause
