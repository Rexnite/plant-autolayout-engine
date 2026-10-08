@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -m streamlit run app.py
  exit /b
)
python --version >nul 2>&1
if %errorlevel% equ 0 (
  python -m streamlit run app.py
  exit /b
)
echo Python was not found. Install Python and run: python -m pip install -r requirements.txt
exit /b 1
