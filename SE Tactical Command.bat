@echo off
title Space Engineers Tactical Command
cd /d "%~dp0"

where python >nul 2>nul
if %errorlevel% equ 0 (
    set "PYTHON_EXE=python"
    goto :RUN
)

where py >nul 2>nul
if %errorlevel% equ 0 (
    set "PYTHON_EXE=py"
    goto :RUN
)

if exist "%LOCALAPPDATA%\Programs\Python\Python313\python.exe" (
    set "PYTHON_EXE=%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
    goto :RUN
)

if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
    set "PYTHON_EXE=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    goto :RUN
)

if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" (
    set "PYTHON_EXE=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    goto :RUN
)

echo [ERROR] Python was not found on your system.
echo Please install Python 3.10+ from https://www.python.org/downloads/
pause
exit /b 1

:RUN
"%PYTHON_EXE%" main.py
if %errorlevel% neq 0 (
    if %errorlevel% neq 1 (
        echo.
        echo ==========================================================
        echo Application exited with code %errorlevel%.
        echo If dependencies are missing, run:
        echo    "%PYTHON_EXE%" -m pip install -r requirements.txt
        echo ==========================================================
        pause
    )
)
