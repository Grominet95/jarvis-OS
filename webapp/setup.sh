#!/bin/bash

set -e

echo "============================================================"
echo "Jarvis - Project Setup"
echo "============================================================"
echo ""

if command -v python3 &> /dev/null; then
    python3 setup.py
elif command -v python &> /dev/null; then
    python setup.py
else
    echo "Error: Python not found. Please install Python 3.10+ first."
    exit 1
fi
