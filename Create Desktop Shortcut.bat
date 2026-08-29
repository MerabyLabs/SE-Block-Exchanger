@echo off
title Create SE Tactical Command Shortcut
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0create_desktop_shortcut.ps1"
echo.
pause
