@echo off
chcp 65001 >nul
title כל-זכות אופליין
echo ======================================================
echo    מפעיל את ארכיון כל-זכות אופליין וממשק הסנכרון...
echo ======================================================
echo.

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [שגיאה] לא נמצא Python מותקן במחשב!
    echo נא להתקין Python מ-https://www.python.org/downloads/
    echo ולוודא שמסומנת האפשרות "Add Python to PATH".
    echo.
    pause
    exit /b
)

python kolzchut_app.py
pause
