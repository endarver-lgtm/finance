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

if not exist ".env" (
  echo [ERROR] File .env not found.
  echo.
  echo   copy .env.example .env
  echo   notepad .env
  echo.
  goto :fail
)

.venv\Scripts\python.exe -c "import config, os, sys; sys.exit(0 if os.environ.get('DATABASE_URL') else 1)"
if errorlevel 1 (
  echo [ERROR] DATABASE_URL is empty in .env
  goto :fail
)

set "FLASK_DEBUG=1"
set "PORT=5000"

echo.
echo   Finance tracker
echo   Open: http://127.0.0.1:%PORT%
echo   Stop: Ctrl+C
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
