@echo off
setlocal
cd /d "%~dp0"
py -3.12 -m venv .venv
if errorlevel 1 exit /b 1
.venv\Scripts\python -m pip install -r requirements-dev.txt
if errorlevel 1 exit /b 1
.venv\Scripts\python ..\scripts\collect_licenses.py
if errorlevel 1 exit /b 1
.venv\Scripts\python -m PyInstaller --clean --noconfirm CloudMic.spec
pause
