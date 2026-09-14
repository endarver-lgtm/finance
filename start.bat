@echo off
setlocal EnableExtensions
cd /d "%~dp0"

title Finance Tracker

where py >nul 2>&1 && (set "PYLAUNCHER=py -3") || (set "PYLAUNCHER=python")
%PYLAUNCHER% --version >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Python 3 not found.
  goto :fail
)

if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment...
  %PYLAUNCHER% -m venv .venv
  call .venv\Scripts\pip install -r requirements.txt
  if errorlevel 1 goto :fail
)

REM DATABASE_URL берётся из .env (см. .env.example) при старте Python.
set "FLASK_DEBUG=1"
set "PORT=5000"
set "OPEN_BROWSER=1"
set "APP_URL=http://127.0.0.1:%PORT%/"

if not exist "%USERPROFILE%\Desktop\Finance.lnk" (
  echo Creating desktop shortcut...
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\create_desktop_shortcut.ps1" >nul 2>&1
)

echo.
echo   Finance tracker
echo   URL:  %APP_URL%
echo   DB:   Postgres ^(DATABASE_URL^)
echo   Browser opens automatically. Stop: Ctrl+C
echo.

call .venv\Scripts\python.exe app.py
if errorlevel 1 (
  echo.
  echo [ERROR] Server stopped with an error ^(see traceback above^).
  goto :fail
)

goto :eof

:fail
echo.
pause
exit /b 1
