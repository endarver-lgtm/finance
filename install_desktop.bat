@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Finance — desktop shortcut

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\create_desktop_shortcut.ps1"
if errorlevel 1 (
  echo [ERROR] Could not create shortcut.
  pause
  exit /b 1
)

echo.
echo Done. Use the "Finance" icon on your Desktop.
echo.
pause
