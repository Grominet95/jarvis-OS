#!/bin/bash

# =============================================================================
# Pipecat Voice Chat - Start All Services
# =============================================================================
# This script starts both the Pipecat backend and the Electron frontend
# =============================================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PIPECAT_DIR="$(dirname "$SCRIPT_DIR")"
ELECTRON_DIR="$SCRIPT_DIR"

# Configuration
PIPECAT_PORT=7860
PIPECAT_HOST="0.0.0.0"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Pipecat Voice Chat - Starting...${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Function to cleanup on exit
cleanup() {
    echo ""
    echo -e "${YELLOW}Shutting down services...${NC}"

    # Kill background processes
    if [ ! -z "$PIPECAT_PID" ]; then
        echo -e "${YELLOW}Stopping Pipecat server (PID: $PIPECAT_PID)...${NC}"
        kill $PIPECAT_PID 2>/dev/null || true
    fi

    if [ ! -z "$ELECTRON_PID" ]; then
        echo -e "${YELLOW}Stopping Electron app (PID: $ELECTRON_PID)...${NC}"
        kill $ELECTRON_PID 2>/dev/null || true
    fi

    # Kill any remaining processes on the ports
    lsof -ti:$PIPECAT_PORT | xargs kill -9 2>/dev/null || true
    lsof -ti:5173 | xargs kill -9 2>/dev/null || true

    echo -e "${GREEN}All services stopped.${NC}"
    exit 0
}

# Set up trap for cleanup
trap cleanup SIGINT SIGTERM EXIT

# Check if ports are available
check_port() {
    if lsof -Pi :$1 -sTCP:LISTEN -t >/dev/null 2>&1; then
        echo -e "${YELLOW}Warning: Port $1 is already in use. Killing existing process...${NC}"
        lsof -ti:$1 | xargs kill -9 2>/dev/null || true
        sleep 1
    fi
}

# Check required ports
echo -e "${BLUE}[1/4]${NC} Checking ports..."
check_port $PIPECAT_PORT
check_port 5173
echo -e "${GREEN}✓ Ports available${NC}"

# Check if Pipecat directory exists
if [ ! -d "$PIPECAT_DIR" ]; then
    echo -e "${RED}Error: Pipecat directory not found at $PIPECAT_DIR${NC}"
    exit 1
fi

# Check if bot.py exists
if [ ! -f "$PIPECAT_DIR/bot.py" ]; then
    echo -e "${RED}Error: bot.py not found at $PIPECAT_DIR/bot.py${NC}"
    exit 1
fi

# Start Pipecat backend
echo -e "${BLUE}[2/4]${NC} Starting Pipecat backend on port $PIPECAT_PORT..."
cd "$PIPECAT_DIR"

# Try uv first, fall back to python
if command -v uv &> /dev/null; then
    uv run bot.py --transport webrtc --host $PIPECAT_HOST --port $PIPECAT_PORT &
    PIPECAT_PID=$!
else
    python bot.py --transport webrtc --host $PIPECAT_HOST --port $PIPECAT_PORT &
    PIPECAT_PID=$!
fi

echo -e "${GREEN}✓ Pipecat started (PID: $PIPECAT_PID)${NC}"

# Wait for Pipecat to be ready
echo -e "${BLUE}[3/4]${NC} Waiting for Pipecat to be ready..."
for i in {1..30}; do
    if curl -s "http://localhost:$PIPECAT_PORT" > /dev/null 2>&1; then
        echo -e "${GREEN}✓ Pipecat is ready${NC}"
        break
    fi
    if [ $i -eq 30 ]; then
        echo -e "${YELLOW}Warning: Pipecat may not be fully ready yet, continuing...${NC}"
    fi
    sleep 1
done

# Start Electron frontend
echo -e "${BLUE}[4/4]${NC} Starting Electron frontend..."
cd "$ELECTRON_DIR"
npm run dev &
ELECTRON_PID=$!
echo -e "${GREEN}✓ Electron started (PID: $ELECTRON_PID)${NC}"

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  All services started successfully!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "  Pipecat backend: ${BLUE}http://localhost:$PIPECAT_PORT${NC}"
echo -e "  Electron app:    ${BLUE}Running${NC}"
echo ""
echo -e "${YELLOW}Press Ctrl+C to stop all services${NC}"
echo ""

# Wait for any process to exit
wait
