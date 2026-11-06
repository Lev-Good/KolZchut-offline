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
python kolzchut_app.py
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Server stopped unexpectedly.
    pause
)
