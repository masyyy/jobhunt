#!/bin/bash
# Start both frontend and backend, clean up on exit
# Usage: ./start.sh [--seed]

set -m  # Enable job control so children get their own process groups

SEED=0
for arg in "$@"; do
  [[ "$arg" == "--seed" ]] && SEED=1
done

cleanup() {
  # Kill entire process groups (negative PID), not just the direct children
  kill -- -$BACKEND_PID -$FRONTEND_PID 2>/dev/null
  # Give processes a moment to exit gracefully
  sleep 0.5
  # Force-kill any stragglers
  kill -9 -- -$BACKEND_PID -$FRONTEND_PID 2>/dev/null
  wait 2>/dev/null
  docker compose down db
}
trap cleanup EXIT INT TERM

docker compose up db -d || exit 1
uv run alembic upgrade head || exit 1
uv run python scripts/apply_delta_migrations.py || exit 1
[[ "$SEED" == "1" ]] && { uv run python scripts/seed.py || exit 1; }

uv run main.py &
BACKEND_PID=$!

(cd frontend && npm run dev) < /dev/null &
FRONTEND_PID=$!

wait
