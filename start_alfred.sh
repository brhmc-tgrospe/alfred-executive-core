#!/usr/bin/env bash
set -e

echo "====================================================================="
echo "          A.L.F.R.E.D. - Autonomous Logistics Functional"
echo "                Response & Executive Director"
echo "====================================================================="

# 0. Clean up any stale processes on port 8765 or Electron
if command -v lsof >/dev/null 2>&1; then
    lsof -ti:8765 | xargs kill -9 2>/dev/null || true
fi
pkill -f electron 2>/dev/null || true

# 1. Check Python Virtual Environment
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
elif [ -f ".venv/Scripts/activate" ]; then
    source .venv/Scripts/activate
else
    echo "[ERROR] Virtual environment (.venv) not found."
    exit 1
fi

# 2. Check HUD Build
if [ ! -f "hud/dist/index.html" ]; then
    echo "[INFO] Compiling HUD production assets..."
    cd hud
    npm run build
    cd ..
fi

# 3. Start Backend in background
echo "[STARTING] A.L.F.R.E.D. Backend Coordinator on ws://127.0.0.1:8765..."
python -m backend.main &
BACKEND_PID=$!

# Trap cleanup to terminate backend on exit
cleanup() {
    echo ""
    echo "[SHUTTING DOWN] Stopping background backend (PID: $BACKEND_PID)..."
    kill "$BACKEND_PID" 2>/dev/null || true
    pkill -f electron 2>/dev/null || true
    echo "Systems offline. Goodbye, Sir."
}
trap cleanup EXIT INT TERM

sleep 2

# 4. Start Electron HUD
echo "[STARTING] A.L.F.R.E.D. Desktop HUD Overlay..."
cd hud
npm run electron:start
