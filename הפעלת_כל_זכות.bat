@echo off
cd /d "%~dp0"
title KolZchut Offline
echo ======================================================
echo    Starting KolZchut Offline Server...
echo ======================================================
echo.
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Python was not found on your system!
    echo Please install Python from https://www.python.org/downloads/
    echo and make sure to check 'Add Python to PATH'.
    echo.
    pause
    exit /b 1
)
python -c "import requests, bs4" >nul 2>nul
if %errorlevel% neq 0 (
    echo Installing required packages (requests, beautifulsoup4)...
    python -m pip install -r requirements.txt
    echo.
)
python kolzchut_app.py
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Server stopped unexpectedly.
    pause
)
