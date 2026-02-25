#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"

cleanup() {
    echo ""
    echo "Shutting down..."
    kill "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || true
    wait "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || true
    echo "Done."
}
trap cleanup EXIT INT TERM

# --- Backend ---
echo "==> Installing backend dependencies..."
cd "$ROOT_DIR/backend"
uv sync

echo "==> Starting backend on http://localhost:8001"
uv run uvicorn app.main:app --reload --port 8001 &
BACKEND_PID=$!

# --- Frontend ---
echo "==> Installing frontend dependencies..."
cd "$ROOT_DIR/frontend"
npm install --silent

echo "==> Starting frontend on http://localhost:3000"
npm run dev &
FRONTEND_PID=$!

echo ""
echo "========================================="
echo "  Backend:  http://localhost:8001"
echo "  Frontend: http://localhost:3000"
echo "  Press Ctrl+C to stop both servers"
echo "========================================="

wait
