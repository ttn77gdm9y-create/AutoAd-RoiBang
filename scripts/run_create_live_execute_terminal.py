#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from _repo_bootstrap import bootstrap_project_root

PROJECT_ROOT = bootstrap_project_root()

from watch_create_live_progress import _render
from open_create_live_progress_terminal import open_progress_terminal


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _progress_dir(policy_path: Path) -> Path:
    policy = _load_json(policy_path)
    runner = policy.get("create_live_execute_once") if isinstance(policy.get("create_live_execute_once"), dict) else {}
    progress = runner.get("progress") if isinstance(runner.get("progress"), dict) else {}
    return Path(str(progress.get("dir") or "data/runs/create_live_execute_once/progress"))


def _write_terminal_progress(progress_dir: Path, payload: dict[str, Any]) -> None:
    progress_dir.mkdir(parents=True, exist_ok=True)
    payload.setdefault("workflow", "create_live_execute_once")
    payload.setdefault("updated_at", datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))
    (progress_dir / "current.json").write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _reset_terminal_progress(progress_dir: Path) -> None:
    progress_dir.mkdir(parents=True, exist_ok=True)
    for name in ("current.json", "events.jsonl"):
        path = progress_dir / name
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def _print_final_json(stdout_log: Path) -> None:
    text = stdout_log.read_text(encoding="utf-8").strip() if stdout_log.exists() else ""
    if not text:
        return
    print("")
    print("final_result（最终结果）:")
    print(text)


def run_from_args(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run live create and show terminal progress.")
    parser.add_argument("--config", default="configs/runtime.create-live.local.json")
    parser.add_argument("--policy", default="policies/create-live-execute.local.json")
    parser.add_argument("--plan", required=True)
    parser.add_argument("--create-execute-artifact", default="")
    parser.add_argument("--check-config-only", action="store_true")
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument("--recent-events", type=int, default=5)
    parser.add_argument("--clear", action="store_true")
    parser.add_argument("--open-progress-window", action="store_true")
    args = parser.parse_args(argv)

    progress_dir = _progress_dir(Path(args.policy))
    run_stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    stdout_log = progress_dir / f"terminal_{run_stamp}.stdout.log"
    stderr_log = progress_dir / f"terminal_{run_stamp}.stderr.log"
    command = [
        sys.executable,
        "scripts/run_create_live_execute_once.py",
        "--config",
        args.config,
        "--policy",
        args.policy,
        "--plan",
        args.plan,
    ]
    if str(args.create_execute_artifact or "").strip():
        command.extend(["--create-execute-artifact", args.create_execute_artifact])
    if args.check_config_only:
        command.append("--check-config-only")

    _reset_terminal_progress(progress_dir)
    _write_terminal_progress(
        progress_dir,
        {
            "ok": True,
            "status": "starting",
            "operation": "create_live_execute_once",
            "done": 0,
            "total": 0,
            "external_api_calls": 0,
            "transport_call_count": 0,
            "message": "starting fixed execute script",
        },
    )
    progress_dir.mkdir(parents=True, exist_ok=True)
    print("terminal_runner（终端执行器）=started", flush=True)
    print(f"stdout_log（标准输出日志）={stdout_log}", flush=True)
    print(f"stderr_log（标准错误日志）={stderr_log}", flush=True)
    print("")
    if args.open_progress_window and not args.check_config_only:
        try:
            open_progress_terminal(
                cwd=PROJECT_ROOT,
                progress_dir=progress_dir,
                interval=float(args.interval),
                recent_events=int(args.recent_events),
                clear=bool(args.clear),
            )
            print("progress_window（进度窗口）=opened", flush=True)
        except Exception as exc:
            print(f"progress_window（进度窗口）=failed reason（原因）={exc}", flush=True)

    with stdout_log.open("w", encoding="utf-8") as stdout_handle, stderr_log.open("w", encoding="utf-8") as stderr_handle:
        process = subprocess.Popen(command, stdout=stdout_handle, stderr=stderr_handle)
        last_render = ""
        try:
            while process.poll() is None:
                rendered = _render(progress_dir, recent_events=int(args.recent_events), clear_screen=bool(args.clear))
                if rendered != last_render:
                    print(rendered, flush=True)
                    last_render = rendered
                time.sleep(max(float(args.interval), 0.2))
        except KeyboardInterrupt:
            process.terminate()
            _write_terminal_progress(
                progress_dir,
                {
                    "ok": False,
                    "status": "interrupted",
                    "operation": "create_live_execute_once",
                    "done": 0,
                    "total": 0,
                    "external_api_calls": 0,
                    "transport_call_count": 0,
                    "message": "user interrupted terminal runner",
                },
            )
            raise
        return_code = int(process.wait())

    rendered = _render(progress_dir, recent_events=int(args.recent_events), clear_screen=bool(args.clear))
    if rendered != last_render:
        print(rendered, flush=True)
    print("")
    print(f"terminal_runner（终端执行器）=finished exit_code（退出码）={return_code}", flush=True)
    _print_final_json(stdout_log)
    if return_code != 0:
        print("")
        print(f"stderr_log（标准错误日志）={stderr_log}", flush=True)
    return return_code


def main() -> int:
    return run_from_args()


if __name__ == "__main__":
    raise SystemExit(main())
