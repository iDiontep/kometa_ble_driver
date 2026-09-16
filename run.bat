@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Creating .venv ...
  py -3 -m venv .venv 2>nul || python -m venv .venv
)

".venv\Scripts\python.exe" -m pip install -e . -q
if errorlevel 1 (
  echo Install failed. Open this folder in PowerShell and run:
  echo   .\.venv\Scripts\python.exe -m pip install -e ".[dev]"
  pause
  exit /b 1
)

".venv\Scripts\python.exe" -m kometa
