#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND_PORT="${BACKEND_PORT:-8010}"
FRONTEND_PORT="${FRONTEND_PORT:-3030}"

# Define commands
BACKEND_CMD="source ~/miniconda3/etc/profile.d/conda.sh && conda activate AutoResearchLab && uvicorn backend.main:app --reload --port ${BACKEND_PORT}"
FRONTEND_CMD="cd \"$ROOT_DIR/web\" && API_BASE_URL=\"http://localhost:${BACKEND_PORT}\" npm run dev -- --port ${FRONTEND_PORT}"

# Kill existing processes on ports
echo "Checking ports..."
lsof -ti :$BACKEND_PORT | xargs kill -9 2>/dev/null || true
lsof -ti :$FRONTEND_PORT | xargs kill -9 2>/dev/null || true

# Start Backend
echo "Starting Backend on port $BACKEND_PORT..."
nohup bash -lc "$BACKEND_CMD" > "$ROOT_DIR/backend.log" 2>&1 &
BACKEND_PID=$!
echo "Backend started with PID $BACKEND_PID"

# Start Frontend
echo "Starting Frontend on port $FRONTEND_PORT..."
nohup bash -lc "$FRONTEND_CMD" > "$ROOT_DIR/frontend.log" 2>&1 &
FRONTEND_PID=$!
echo "Frontend started with PID $FRONTEND_PID"

echo "Services are running in background."
echo "Backend logs: $ROOT_DIR/backend.log"
echo "Frontend logs: $ROOT_DIR/frontend.log"
