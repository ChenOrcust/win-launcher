@echo off
chcp 65001 >nul
title WinLauncher Builder

echo ============================================
echo  WinLauncher - Build Script
echo ============================================
echo.

setlocal enabledelayedexpansion

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH.
    echo Please install Python 3.10+ from https://www.python.org/
    pause
    exit /b 1
)

:: Get script directory and cd to it
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

echo [1/5] Creating virtual environment...
if not exist "venv\" (
    python -m venv venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
) else (
    echo Virtual environment already exists, skipping.
)

echo [2/5] Activating virtual environment and installing dependencies...
call venv\Scripts\activate.bat
if errorlevel 1 (
    echo [ERROR] Failed to activate virtual environment.
    pause
    exit /b 1
)

pip install --upgrade pip -q
pip install -r requirements.txt -q
if errorlevel 1 (
    echo [ERROR] Failed to install dependencies.
    pause
    exit /b 1
)

pip install pyinstaller -q

echo [3/5] Generating application icon...
python build_icon.py 2>nul

if not exist "icon.ico" (
    echo [INFO] Could not generate icon, proceeding without custom icon.
)

echo [4/5] Building executable with PyInstaller...
if exist "icon.ico" (
    pyinstaller --onefile --windowed --name "WinLauncher" --icon "icon.ico" --hidden-import "win32com" --hidden-import "pythoncom" main.py
) else (
    pyinstaller --onefile --windowed --name "WinLauncher" --hidden-import "win32com" --hidden-import "pythoncom" main.py
)

if errorlevel 1 (
    echo [ERROR] PyInstaller build failed.
    pause
    exit /b 1
)

echo [5/5] Build complete!
echo.
echo Output: dist\WinLauncher.exe
echo.
echo You can now:
echo   1. Run dist\WinLauncher.exe directly
echo   2. Run installer.iss with Inno Setup to create an installer
echo.
echo Press any key to test run, or close this window.
pause >nul

:: Test run
start "" "dist\WinLauncher.exe"

pause
