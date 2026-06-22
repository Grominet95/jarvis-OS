@echo off
REM Double-cliquable : lance Jarvis (API + LiveKit + vocal). Contourne l'Execution Policy.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0jarvis.ps1" run
echo.
pause
