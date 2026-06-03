#!/usr/bin/env bash
set -euo pipefail

ROOT="/Users/hongen/Projects/RoiBang-v2"
BACKEND_PORT=8007
FRONTEND_PORT=5180
LOG_DIR="$ROOT/data/dev-logs"

cd "$ROOT"
mkdir -p "$LOG_DIR"

echo "Stopping old local services..."
lsof -tiTCP:$BACKEND_PORT -sTCP:LISTEN | xargs kill 2>/dev/null || true
lsof -tiTCP:$FRONTEND_PORT -sTCP:LISTEN | xargs kill 2>/dev/null || true

echo "Starting backend..."
nohup env PYTHONPATH=src:. uvicorn backend.app.main:app --host 127.0.0.1 --port "$BACKEND_PORT" \
  > "$LOG_DIR/backend.log" 2>&1 &

echo "Starting frontend..."
(
  cd "$ROOT/frontend"
  nohup env VITE_API_BASE_URL=http://127.0.0.1:$BACKEND_PORT/api npm run dev -- --host 127.0.0.1 --port "$FRONTEND_PORT" \
    > "$LOG_DIR/frontend.log" 2>&1 &
)

echo "Checking backend..."
for _ in {1..30}; do
  if curl -fsS "http://127.0.0.1:$BACKEND_PORT/api/workflow-runs/catalog" >/dev/null 2>&1; then
    echo "Backend OK: http://127.0.0.1:$BACKEND_PORT"
    break
  fi
  sleep 1
done

echo "Checking frontend..."
for _ in {1..30}; do
  if curl -fsS "http://127.0.0.1:$FRONTEND_PORT/" >/dev/null 2>&1; then
    echo "Frontend OK: http://127.0.0.1:$FRONTEND_PORT"
    break
  fi
  sleep 1
done

echo "Open: http://127.0.0.1:$FRONTEND_PORT/"
echo "Logs:"
echo "  $LOG_DIR/backend.log"
echo "  $LOG_DIR/frontend.log"
