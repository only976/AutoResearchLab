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

# Prefer the user's Miniconda install if present; otherwise fall back to conda on PATH.
CONDA_BIN=""
if [[ -x "$HOME/miniconda3/bin/conda" ]]; then
  CONDA_BIN="$HOME/miniconda3/bin/conda"
elif command -v conda >/dev/null 2>&1; then
  CONDA_BIN="conda"
fi

if [[ -n "$CONDA_BIN" ]]; then
  exec "$CONDA_BIN" run -n "$ENV_NAME" python -m uvicorn main:asgi_app \
    --host "$HOST" --port "$PORT" --loop asyncio --http h11
else
  echo "conda not found. Falling back to current python environment." >&2
  exec python -m uvicorn main:asgi_app --host "$HOST" --port "$PORT" --loop asyncio --http h11
fi
