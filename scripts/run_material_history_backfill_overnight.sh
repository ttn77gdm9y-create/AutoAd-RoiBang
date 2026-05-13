#!/usr/bin/env bash
set -u

# Temporary overnight runner for readonly material history backfill.
# It only calls preflight and readonly backfill scripts. It does not create,
# pause, delete, change budgets, change schedules, or push materials.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR" || exit 1

RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)"
OUT_DIR="${OVERNIGHT_RUN_DIR:-data/runs/material_history_backfill_overnight}"
LOG_FILE="$OUT_DIR/$RUN_ID.log"
SUMMARY_FILE="$OUT_DIR/$RUN_ID.summary.json"
mkdir -p "$OUT_DIR"

PREFLIGHT_CONFIG="${PREFLIGHT_CONFIG:-configs/runtime.example.json}"
EXECUTE_CONFIG="${EXECUTE_CONFIG:-configs/runtime.openapi-execute.local.example.json}"
REQUEST_FILE="${REQUEST_FILE:-configs/material-history-backfill-batch.disabled.example.json}"
STOP_AT="${STOP_AT:-08:00}"
MAX_ROUNDS="${MAX_ROUNDS:-20}"
SLEEP_BETWEEN_ROUNDS="${SLEEP_BETWEEN_ROUNDS:-30}"
RETRY_FAILED_ONCE="${RETRY_FAILED_ONCE:-1}"
STOP_AT_EPOCH="$(
  python3 - "$STOP_AT" <<'PY'
from datetime import datetime, time, timedelta
import sys

raw = sys.argv[1].strip()
hour, minute = [int(part) for part in raw.split(":", 1)]
now = datetime.now()
stop_at = datetime.combine(now.date(), time(hour, minute))
if stop_at <= now:
    stop_at = stop_at + timedelta(days=1)
print(int(stop_at.timestamp()))
PY
)"

log() {
  printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" | tee -a "$LOG_FILE"
}

json_value() {
  python3 - "$1" "$2" <<'PY'
import json
import sys

path, expr = sys.argv[1], sys.argv[2]
with open(path, "r", encoding="utf-8") as fh:
    data = json.load(fh)

value = data
for part in expr.split("."):
    if isinstance(value, dict):
        value = value.get(part)
    else:
        value = None
        break
print("" if value is None else value)
PY
}

selected_dates() {
  python3 - "$1" <<'PY'
import json
import sys

with open(sys.argv[1], "r", encoding="utf-8") as fh:
    data = json.load(fh)
print(",".join(data.get("selected_dates") or []))
PY
}

should_stop() {
  python3 - "$STOP_AT_EPOCH" <<'PY'
from datetime import datetime
import sys

stop_at_epoch = int(sys.argv[1])
raise SystemExit(0 if int(datetime.now().timestamp()) >= stop_at_epoch else 1)
PY
}

write_summary() {
  python3 - "$SUMMARY_FILE" "$RUN_ID" "$LOG_FILE" <<'PY'
import json
import sqlite3
import sys
from datetime import datetime, timezone

summary_path, run_id, log_file = sys.argv[1], sys.argv[2], sys.argv[3]
db_path = "data/roibang_v2.sqlite3"
with sqlite3.connect(db_path) as conn:
    status_rows = conn.execute(
        """
        SELECT status, COUNT(*)
        FROM material_sync_state
        WHERE workflow='material_history_backfill'
        GROUP BY status
        ORDER BY status
        """
    ).fetchall()
    last_rows = conn.execute(
        """
        SELECT sync_date, status, account_count, material_row_count, error_message
        FROM material_sync_state
        WHERE workflow='material_history_backfill'
        ORDER BY sync_date DESC
        LIMIT 10
        """
    ).fetchall()
    total_metrics = conn.execute(
        """
        SELECT COUNT(DISTINCT metric_date), COUNT(*), COUNT(DISTINCT material_id), ROUND(SUM(stat_cost), 2)
        FROM material_daily_metrics
        """
    ).fetchone()

payload = {
    "run_id": run_id,
    "updated_at": datetime.now(timezone.utc).isoformat(),
    "log_file": log_file,
    "status_counts": {status: count for status, count in status_rows},
    "latest_sync_state": [
        {
            "sync_date": sync_date,
            "status": status,
            "account_count": account_count,
            "material_row_count": material_row_count,
            "error_message": error_message,
        }
        for sync_date, status, account_count, material_row_count, error_message in last_rows
    ],
    "material_daily_metrics_totals": {
        "date_count": total_metrics[0] or 0,
        "row_count": total_metrics[1] or 0,
        "unique_material_count": total_metrics[2] or 0,
        "stat_cost_sum": total_metrics[3] or 0,
    },
}
with open(summary_path, "w", encoding="utf-8") as fh:
    json.dump(payload, fh, ensure_ascii=False, indent=2)
PY
}

run_preflight() {
  local path="$1"
  PYTHONPATH=src python3 scripts/run_material_history_backfill_batch.py \
    --config "$PREFLIGHT_CONFIG" \
    --request "$REQUEST_FILE" \
    --preflight >"$path" 2>>"$LOG_FILE"
}

run_execute() {
  local path="$1"
  shift
  PYTHONPATH=src python3 scripts/run_material_history_backfill_batch.py \
    --config "$EXECUTE_CONFIG" \
    --request "$REQUEST_FILE" \
    --enable-readonly "$@" >"$path" 2>>"$LOG_FILE"
}

log "overnight readonly backfill started"
log "root=$ROOT_DIR"
log "request=$REQUEST_FILE"
log "stop_at=$STOP_AT max_rounds=$MAX_ROUNDS retry_failed_once=$RETRY_FAILED_ONCE"

round=1
while [ "$round" -le "$MAX_ROUNDS" ]; do
  if should_stop; then
    log "stop time reached before round $round"
    break
  fi

  preflight_json="$OUT_DIR/$RUN_ID.round_${round}.preflight.json"
  if ! run_preflight "$preflight_json"; then
    log "preflight failed at round $round"
    break
  fi

  selected_count="$(json_value "$preflight_json" "summary.selected_date_count")"
  pending_count="$(json_value "$preflight_json" "summary.pending_date_count")"
  failed_count="$(json_value "$preflight_json" "summary.failed_date_count")"
  dates="$(selected_dates "$preflight_json")"
  log "round $round preflight selected=$selected_count pending=$pending_count failed=$failed_count dates=$dates"

  retry_needed=0
  if [ "${selected_count:-0}" = "0" ]; then
    if [ "${failed_count:-0}" = "0" ]; then
      log "nothing left to run"
      break
    fi
    retry_needed=1
  else
    execute_json="$OUT_DIR/$RUN_ID.round_${round}.execute.json"
    if run_execute "$execute_json"; then
      log "round $round execute ok"
    else
      log "round $round execute had failures; continuing after recording state"
      retry_needed=1
    fi
  fi

  if [ "$RETRY_FAILED_ONCE" = "1" ] && [ "$retry_needed" = "1" ]; then
    retry_json="$OUT_DIR/$RUN_ID.round_${round}.retry.json"
    if run_execute "$retry_json" --max-dates 1 --retry-failed; then
      retry_selected="$(selected_dates "$retry_json")"
      if [ -n "$retry_selected" ]; then
        log "round $round retry ok dates=$retry_selected"
      fi
    else
      log "round $round retry still had failures"
    fi
  fi

  write_summary
  if should_stop; then
    log "stop time reached after round $round"
    break
  fi
  round=$((round + 1))
  sleep "$SLEEP_BETWEEN_ROUNDS"
done

write_summary
log "overnight readonly backfill finished summary=$SUMMARY_FILE"
