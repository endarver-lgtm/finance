@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Сначала запустите start.bat один раз.
  pause
  exit /b 1
)
echo.
echo   Очистка базы данных...
echo.
.venv\Scripts\python.exe manage.py reset
echo.
pause
