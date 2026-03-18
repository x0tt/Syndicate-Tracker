@echo off
cd /d "%~dp0"
call .venv\Scripts\activate
echo Starting Streamlit app...
python -m streamlit run app.py
pause
