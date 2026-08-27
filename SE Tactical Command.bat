@echo off
title Space Engineers Tactical Command
cd /d "%~dp0"
python main.py
if %errorlevel% neq 0 (
    echo.
    echo ==========================================================
    echo Application exited with an error.
    echo Please make sure dependencies are installed:
    echo    pip install -r requirements.txt
    echo ==========================================================
    pause
)
