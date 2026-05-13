#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _format_progress(progress: dict[str, Any]) -> str:
    if not progress:
        return "等待 create_live_execute_once（创建真实执行）进度文件..."
    operation = str(progress.get("operation") or "-")
    status = str(progress.get("status") or "-")
    done = int(progress.get("done") or 0)
    total = int(progress.get("total") or 0)
    calls = int(progress.get("external_api_calls") or progress.get("transport_call_count") or 0)
    account = str(progress.get("advertiser_id") or "")
    message = str(progress.get("message") or "")
    updated_at = str(progress.get("updated_at") or "")
    parts = [
        f"operation（操作）={operation}",
        f"status（状态）={status}",
        f"progress（进度）={done}/{total}",
        f"external_api_calls（外部接口调用）={calls}",
    ]
    if account:
        parts.append(f"account（账户）={account}")
    if message:
        parts.append(f"message（消息）={message}")
    if updated_at:
        parts.append(f"updated_at（更新时间）={updated_at}")
    return " | ".join(parts)


def _read_recent_events(path: Path, limit: int) -> list[str]:
    if limit <= 0:
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return []
    rows = []
    for line in lines[-limit:]:
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        rows.append(_format_progress(event if isinstance(event, dict) else {}))
    return rows


def _render(progress_dir: Path, *, recent_events: int = 0, clear_screen: bool = False) -> str:
    progress_path = progress_dir / "current.json"
    lines = [_format_progress(_load_json(progress_path))]
    events = _read_recent_events(progress_dir / "events.jsonl", recent_events)
    if events:
        lines.append("")
        lines.append(f"recent_events（最近事件）={len(events)}")
        lines.extend(events)
    output = "\n".join(lines)
    if clear_screen:
        return "\033[2J\033[H" + output
    return output


def run_from_args(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Watch create_live_execute_once progress in terminal.")
    parser.add_argument("--progress-dir", default="data/runs/create_live_execute_once/progress")
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument("--recent-events", type=int, default=0)
    parser.add_argument("--clear", action="store_true")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--until-done", action="store_true")
    args = parser.parse_args(argv)

    progress_dir = Path(args.progress_dir)
    last_line = ""
    while True:
        progress = _load_json(progress_dir / "current.json")
        line = _render(progress_dir, recent_events=int(args.recent_events), clear_screen=bool(args.clear))
        if line != last_line:
            print(line, flush=True)
            last_line = line
        if args.once:
            return 0
        if args.until_done and str(progress.get("status") or "") in {
            "completed",
            "failed",
            "create_http_completed",
            "create_http_failed",
            "blocked",
        }:
            return 0 if bool(progress.get("ok", False)) else 1
        if bool(args.clear) and os.environ.get("TERM", "") == "dumb":
            args.clear = False
        time.sleep(max(float(args.interval), 0.2))


def main() -> int:
    return run_from_args()


if __name__ == "__main__":
    raise SystemExit(main())
