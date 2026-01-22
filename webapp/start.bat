@echo off

cd /d "%~dp0"

echo ============================================================
echo Jarvis - Starting Electron App
echo ============================================================
echo.

where node >nul 2>&1
if errorlevel 1 (
    echo Error: Node.js not found. Please install Node.js first.
    echo Download from: https://nodejs.org/
    pause
    exit /b 1
)

where python >nul 2>&1
if errorlevel 1 (
    echo Error: Python not found. Please install Python 3.10+ first.
    echo Download from: https://www.python.org/downloads/
    pause
    exit /b 1
)

where uv >nul 2>&1
if errorlevel 1 (
    echo uv not found. Installing uv...
    call python -m pip install uv
    if errorlevel 1 (
        echo Error: Failed to install uv. Please install manually:
        echo   pip install uv
        echo Or visit: https://docs.astral.sh/uv/getting-started/installation/
        pause
        exit /b 1
    )
)

if not exist "package.json" (
    echo Error: package.json not found. Running setup...
    if exist "setup.bat" (
        call setup.bat
    ) else (
        echo Error: setup.bat not found. Please run setup manually.
        pause
        exit /b 1
    )
)

if not exist ".venv" (
    echo Python virtual environment not found. Running setup...
    if exist "setup.bat" (
        call setup.bat
    )
)

if not exist "node_modules" (
    echo Installing Electron dependencies...
    call npm install
    if errorlevel 1 (
        echo Error: Failed to install Node.js dependencies.
        pause
        exit /b 1
    )
)

echo Starting Electron app...
call npm start
