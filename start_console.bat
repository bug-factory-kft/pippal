@echo off
setlocal
set "APP_DIR=%~dp0"
cd /d "%APP_DIR%"

where python >nul 2>nul
if errorlevel 1 (
    echo Python 3.11+ was not found on PATH.
    echo Install Python and re-run setup.ps1.
    pause
    exit /b 1
)

python reader_app.py
pause
