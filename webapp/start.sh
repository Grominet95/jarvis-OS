#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "============================================================"
echo "Jarvis - Starting Electron App"
echo "============================================================"
echo ""

if ! command -v node &> /dev/null; then
    echo "Error: Node.js not found. Please install Node.js first."
    echo "Download from: https://nodejs.org/"
    exit 1
fi

if ! command -v python3 &> /dev/null && ! command -v python &> /dev/null; then
    echo "Error: Python not found. Please install Python 3.10+ first."
    echo "Download from: https://www.python.org/downloads/"
    exit 1
fi

if ! command -v uv &> /dev/null; then
    echo "uv not found. Installing uv..."
    if command -v pip3 &> /dev/null; then
        pip3 install uv
    elif command -v pip &> /dev/null; then
        pip install uv
    else
        echo "Error: pip not found. Installing uv via curl..."
        curl -LsSf https://astral.sh/uv/install.sh | sh
        export PATH="$HOME/.cargo/bin:$PATH"
    fi
    
    if ! command -v uv &> /dev/null; then
        echo "Error: Failed to install uv. Please install manually:"
        echo "  pip install uv"
        echo "Or visit: https://docs.astral.sh/uv/getting-started/installation/"
        exit 1
    fi
fi

if [ ! -f "package.json" ]; then
    echo "Error: package.json not found. Running setup..."
    if [ -f "setup.sh" ]; then
        bash setup.sh
    else
        echo "Error: setup.sh not found. Please run setup manually."
        exit 1
    fi
fi

if [ ! -d ".venv" ]; then
    echo "Python virtual environment not found. Running setup..."
    if [ -f "setup.sh" ]; then
        bash setup.sh
    fi
fi

if [ ! -d "node_modules" ]; then
    echo "Installing Electron dependencies..."
    npm install
    if [ $? -ne 0 ]; then
        echo "Error: Failed to install Node.js dependencies."
        exit 1
    fi
fi

echo "Starting Electron app..."
npm start
