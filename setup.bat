@echo off
REM Double-cliquable : configure Jarvis (assistant web). Contourne l'Execution Policy.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0jarvis.ps1" setup
echo.
pause
