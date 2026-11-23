@echo off
REM Qwik installer launcher: bypasses ExecutionPolicy and keeps the window
REM open so errors stay visible. Double-click this file.
cd /d "%~dp0"
if not exist "Qwik\Qwik.exe" if exist "Qwik.zip" tar -xf Qwik.zip
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Install-Qwik.ps1"
echo.
echo ---- done (if you see red errors above, send a screenshot) ----
pause
