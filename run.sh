#!/usr/bin/env bash
# Start the backend (uvicorn) and frontend (vite) in parallel.
# Ctrl+C stops both.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"

# Pick a python: prefer venv if it exists.
if [[ -x "$BACKEND_DIR/.venv/bin/python" ]]; then
  PYTHON="$BACKEND_DIR/.venv/bin/python"
else
  PYTHON="${PYTHON:-python3}"
fi

echo "[backend] uvicorn on http://localhost:8000"
(
  cd "$BACKEND_DIR"
  "$PYTHON" -m uvicorn main:app \
    --host 0.0.0.0 --port 8000 \
    --reload \
    --reload-dir routers --reload-dir services --reload-dir models \
    --reload-include 'main.py'
) &
BACKEND_PID=$!

echo "[frontend] vite on http://localhost:5173"
(
  cd "$FRONTEND_DIR"
  npm run dev
) &
FRONTEND_PID=$!

cleanup() {
  echo
  echo "shutting down…"
  kill "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || true
  wait 2>/dev/null || true
}
trap cleanup INT TERM

wait
