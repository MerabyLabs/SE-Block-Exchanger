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

set "PYTHON_EXE=python"

:RUN
"%PYTHON_EXE%" main.py
