@echo off

echo ============================================================
echo Jarvis - Project Setup
echo ============================================================
echo.

python setup.py
if errorlevel 1 (
    echo.
    echo Error: Setup failed. Make sure Python 3.10+ is installed.
    pause
    exit /b 1
)

pause
