@echo off
REM Double-click to remove Qwik. No admin unless the dot is running elevated.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Uninstall-Qwik.ps1"
echo.
echo ---- done (if you see red errors above, send a screenshot) ----
pause
