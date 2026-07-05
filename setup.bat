@echo off
setlocal enabledelayedexpansion
REM Sets up the project on plain Windows (no Git Bash/WSL needed): creates a
REM venv if missing, installs requirements, and downloads the default Vosk
REM model if it isn't already present. Double-click this file, or run it
REM from Command Prompt.
REM
REM Usage:
REM   setup.bat            normal setup (requirements.txt)
REM   setup.bat --dev      also installs requirements-dev.txt (pytest)

cd /d "%~dp0"

set VENV_DIR=.venv
set DEV_MODE=0
if "%~1"=="--dev" set DEV_MODE=1

REM --- Find a Python interpreter -----------------------------------------
set PYTHON=
where py >nul 2>nul
if %errorlevel%==0 (
    set PYTHON=py -3
) else (
    where python >nul 2>nul
    if %errorlevel%==0 (
        set PYTHON=python
    )
)

if "%PYTHON%"=="" (
    echo Error: no Python interpreter found on PATH.
    echo Install Python from https://www.python.org/downloads/ ^(check "Add
    echo python.exe to PATH" during install^), then run this again.
    pause
    exit /b 1
)

REM --- Create the venv if it doesn't exist yet ----------------------------
if exist "%VENV_DIR%\Scripts\activate.bat" (
    echo Virtual environment already exists at .\%VENV_DIR%, skipping creation.
) else (
    echo Creating virtual environment at .\%VENV_DIR% ...
    %PYTHON% -m venv %VENV_DIR%
    if not exist "%VENV_DIR%\Scripts\activate.bat" (
        echo Error: failed to create the virtual environment.
        pause
        exit /b 1
    )
)

call "%VENV_DIR%\Scripts\activate.bat"
echo Using:
python --version

REM --- Install requirements ------------------------------------------------
python -m pip install --upgrade pip
if %DEV_MODE%==1 (
    echo Installing requirements-dev.txt ...
    pip install -r requirements-dev.txt
) else (
    echo Installing requirements.txt ...
    pip install -r requirements.txt
)
if errorlevel 1 (
    echo Error: pip install failed - see above for details.
    pause
    exit /b 1
)

REM --- Download the Vosk model if needed -----------------------------------
REM download_vosk_model.py already no-ops if the model directory exists, so
REM it's safe to call unconditionally.
echo Checking Vosk model...
python scripts\download_vosk_model.py

echo.
echo Setup complete. Start the app by double-clicking:
echo   Start Speech To Keyboard.vbs
echo.
pause
