@echo off
setlocal
cd /d "%~dp0"
python -m pip install -r requirements.txt pyinstaller
if errorlevel 1 exit /b 1
python -m PyInstaller --noconfirm --clean SE_Tactical_Command.spec
if errorlevel 1 exit /b 1
python package_release.py
if errorlevel 1 exit /b 1
echo Candidate artifacts built in dist. Publication still requires release acceptance.
endlocal
