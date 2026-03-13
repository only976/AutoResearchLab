#!/usr/bin/env bash
set -euo pipefail

# MAARS start script (macOS/Linux)
# Mirrors start.bat:
#   cd backend
#   python -m uvicorn main:asgi_app --host 0.0.0.0 --port 3001 --loop asyncio --http h11

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/backend"

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-3001}"
ENV_NAME="${ENV_NAME:-AutoResearchLab}"
LOG_DIR="${LOG_DIR:-$SCRIPT_DIR/logs}"
LOG_FILE="${MAARS_START_LOG_FILE:-$LOG_DIR/backend.log}"
PID_FILE="${MAARS_START_PID_FILE:-$SCRIPT_DIR/.maars_backend.pid}"

# Kill any existing process listening on $PORT before starting.
# This prevents the common "old process still running" issue.
# Set MAARS_START_KILL_OLD=0 to disable.
MAARS_START_KILL_OLD="${MAARS_START_KILL_OLD:-1}"
MAARS_START_KILL_TIMEOUT_S="${MAARS_START_KILL_TIMEOUT_S:-2}"
MAARS_START_BOOT_TIMEOUT_S="${MAARS_START_BOOT_TIMEOUT_S:-12}"

kill_listeners_on_port() {
  local port="$1"

  if [[ "$MAARS_START_KILL_OLD" != "1" ]]; then
    return 0
  fi
  if ! command -v lsof >/dev/null 2>&1; then
    echo "WARN: lsof not found; cannot auto-kill processes on port $port" >&2
    return 0
  fi

  local pids
  pids="$(lsof -ti tcp:"$port" -sTCP:LISTEN 2>/dev/null || true)"
  if [[ -z "$pids" ]]; then
    return 0
  fi

  echo "INFO: Detected existing listener(s) on port $port: $pids" >&2
  echo "$pids" | xargs -r kill -TERM 2>/dev/null || true

  local deadline=$(( $(date +%s) + MAARS_START_KILL_TIMEOUT_S ))
  while [[ $(date +%s) -lt $deadline ]]; do
    if ! lsof -ti tcp:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
      echo "INFO: Port $port is free" >&2
      return 0
    fi
    sleep 0.2
  done

  pids="$(lsof -ti tcp:"$port" -sTCP:LISTEN 2>/dev/null || true)"
  if [[ -n "$pids" ]]; then
    echo "WARN: Listener(s) still on port $port after ${MAARS_START_KILL_TIMEOUT_S}s; forcing kill: $pids" >&2
    echo "$pids" | xargs -r kill -KILL 2>/dev/null || true
  fi
}

kill_pid_file_process() {
  if [[ "$MAARS_START_KILL_OLD" != "1" ]]; then
    return 0
  fi
  if [[ ! -f "$PID_FILE" ]]; then
    return 0
  fi

  local old_pid
  old_pid="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [[ -z "$old_pid" ]]; then
    rm -f "$PID_FILE" || true
    return 0
  fi

  if kill -0 "$old_pid" >/dev/null 2>&1; then
    echo "INFO: Found existing backend pid from $PID_FILE: $old_pid" >&2
    kill -TERM "$old_pid" 2>/dev/null || true
    local deadline=$(( $(date +%s) + MAARS_START_KILL_TIMEOUT_S ))
    while [[ $(date +%s) -lt $deadline ]]; do
      if ! kill -0 "$old_pid" >/dev/null 2>&1; then
        break
      fi
      sleep 0.2
    done
    if kill -0 "$old_pid" >/dev/null 2>&1; then
      echo "WARN: Old backend pid still alive; force killing: $old_pid" >&2
      kill -KILL "$old_pid" 2>/dev/null || true
    fi
  fi

  rm -f "$PID_FILE" || true
}

mkdir -p "$LOG_DIR"
kill_pid_file_process
kill_listeners_on_port "$PORT"

# Prefer the user's Miniconda install if present; otherwise fall back to conda on PATH.
CONDA_BIN=""
if [[ -x "$HOME/miniconda3/bin/conda" ]]; then
  CONDA_BIN="$HOME/miniconda3/bin/conda"
elif command -v conda >/dev/null 2>&1; then
  CONDA_BIN="conda"
fi

start_server() {
  : > "$LOG_FILE"
  if [[ -n "$CONDA_BIN" ]]; then
    nohup "$CONDA_BIN" run -n "$ENV_NAME" python -m uvicorn main:asgi_app \
      --host "$HOST" --port "$PORT" --loop asyncio --http h11 \
      >>"$LOG_FILE" 2>&1 &
  else
    echo "conda not found. Falling back to current python environment." >&2
    nohup python -m uvicorn main:asgi_app --host "$HOST" --port "$PORT" --loop asyncio --http h11 \
      >>"$LOG_FILE" 2>&1 &
  fi
  echo $!
}

SERVER_PID="$(start_server)"
echo "$SERVER_PID" > "$PID_FILE"
disown "$SERVER_PID" 2>/dev/null || true
echo "INFO: Starting backend (pid=$SERVER_PID) on http://localhost:$PORT" >&2
echo "INFO: Logs: $LOG_FILE" >&2

deadline=$(( $(date +%s) + MAARS_START_BOOT_TIMEOUT_S ))
started=0
while [[ $(date +%s) -lt $deadline ]]; do
  if command -v curl >/dev/null 2>&1 && curl -fsS "http://127.0.0.1:$PORT/api/status" >/dev/null 2>&1; then
    started=1
    break
  fi

  if lsof -ti tcp:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
    started=1
    break
  fi

  if ! kill -0 "$SERVER_PID" >/dev/null 2>&1; then
    break
  fi
  sleep 0.2
done

if [[ "$started" == "1" ]]; then
  echo "INFO: Backend started successfully on http://localhost:$PORT (pid=$SERVER_PID)" >&2
  echo "INFO: Server is running in background. Use 'lsof -ti tcp:$PORT' or cat '$PID_FILE' to get PID." >&2
  echo "INFO: Stop with: kill \"$(cat "$PID_FILE" 2>/dev/null || echo "$SERVER_PID")\"" >&2
  tail -n 5 "$LOG_FILE" 2>/dev/null || true
  exit 0
else
  echo "ERROR: Backend failed to start within ${MAARS_START_BOOT_TIMEOUT_S}s (pid=$SERVER_PID, port=$PORT)" >&2
  echo "ERROR: Recent logs:" >&2
  tail -n 40 "$LOG_FILE" >&2 || true
  if ! kill -0 "$SERVER_PID" >/dev/null 2>&1; then
    wait "$SERVER_PID" || true
  else
    kill -TERM "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" || true
  fi
  rm -f "$PID_FILE" || true
  exit 1
fi

