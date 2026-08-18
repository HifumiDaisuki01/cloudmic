@echo off
REM ============================================================
REM CloudMic - Windows build script (pure ASCII)
REM One-click: create venv -> install deps -> build exe
REM Output: dist\CloudMic.exe
REM Usage: double click build.bat
REM ============================================================
setlocal enabledelayedexpansion

set "APP_NAME=CloudMic"
set "SRC=gamesay.py"
set "VENV=.build-venv"
set "MIRROR=https://mirrors.cloud.tencent.com/pypi/simple"

echo ============================================
echo  CloudMic Build (Windows x64)
echo ============================================

REM ---------- 0. check python ----------
echo [0/5] Check Python...
where python >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found in PATH.
    echo Install Python 3.10+ from https://www.python.org/downloads/
    echo IMPORTANT: check "Add python.exe to PATH" during install.
    pause
    exit /b 1
)
for /f "delims=" %%v in ('python -c "import sys;print(sys.version.split()[0])"') do set "PYVER=%%v"
echo       Python %PYVER%

REM ---------- 1. create venv ----------
echo [1/5] Create venv...
if not exist "%VENV%" (
    python -m venv "%VENV%"
    if errorlevel 1 (
        echo ERROR: venv creation failed.
        pause
        exit /b 1
    )
)
set "PY=%CD%\%VENV%\Scripts\python.exe"
set "PIP=%CD%\%VENV%\Scripts\pip.exe"

REM ---------- 2. install deps ----------
echo [2/5] Install dependencies (mirror: tencent cloud)...
"%PIP%" install --upgrade pip -q -i %MIRROR%
"%PIP%" install -r requirements.txt -i %MIRROR%
if errorlevel 1 (
    echo ERROR: pip install failed. Try again or check network.
    pause
    exit /b 1
)

REM ---------- 3. install pyinstaller ----------
echo [3/5] Install PyInstaller...
"%PIP%" install -q pyinstaller -i %MIRROR%
if errorlevel 1 (
    echo ERROR: PyInstaller install failed.
    pause
    exit /b 1
)

REM ---------- 4. build ----------
echo [4/5] Build exe (this may take 2-5 minutes)...
"%PY%" -m PyInstaller --noconfirm --clean --onefile --noconsole --name %APP_NAME% ^
    --collect-all edge_tts ^
    --collect-all miniaudio ^
    --collect-all sounddevice ^
    --add-data "vbcable;vbcable" ^
    --icon icon.png ^
    --hidden-import win32com.client ^
    --hidden-import win32timezone ^
    --exclude-module tkinter ^
    %SRC%
if errorlevel 1 (
    echo ERROR: PyInstaller build failed. Check messages above.
    pause
    exit /b 1
)

REM ---------- 5. done ----------
echo [5/5] Done!
if exist "dist\%APP_NAME%.exe" (
    echo Output: %CD%\dist\%APP_NAME%.exe
    explorer dist
) else (
    echo ERROR: exe not found after build.
)
pause
