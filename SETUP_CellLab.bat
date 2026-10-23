@echo off
rem CellLab one-click setup for Windows: builds CellLab.exe, adds a desktop shortcut, starts it.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-ChildItem -Recurse -File | Unblock-File" >nul 2>&1
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0packaging\install_windows.ps1"
if errorlevel 1 (
  echo.
  echo Setup failed. Please send a screenshot of this window.
)
pause
