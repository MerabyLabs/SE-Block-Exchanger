@echo off
echo Starting Space Engineers Tactical Command...
python main.py
if %errorlevel% neq 0 (
    echo.
    echo Error starting application. Please ensure Python is installed with dependencies: pip install -r requirements.txt
    pause
)
