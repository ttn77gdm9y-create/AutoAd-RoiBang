#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
ROIBANG_API_RELOAD=1 PYTHONPATH=.:src python3 scripts/run_fastapi_backend.py &
BACKEND_PID="$!"
trap 'kill "$BACKEND_PID" 2>/dev/null || true' EXIT
cd "$ROOT/frontend"
npm run dev -- --port 5173
