#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shlex
import subprocess
from pathlib import Path


def _shell_command(*, cwd: Path, progress_dir: Path, interval: float, recent_events: int, clear: bool) -> str:
    command = [
        "PYTHONPATH=src",
        "python3",
        "scripts/watch_create_live_progress.py",
        "--progress-dir",
        str(progress_dir),
        "--interval",
        str(interval),
        "--recent-events",
        str(recent_events),
        "--until-done",
    ]
    if clear:
        command.append("--clear")
    return "cd " + shlex.quote(str(cwd)) + " && " + " ".join(shlex.quote(part) for part in command)


def open_progress_terminal(
    *,
    cwd: str | Path,
    progress_dir: str | Path,
    interval: float = 1.0,
    recent_events: int = 5,
    clear: bool = True,
) -> None:
    shell_command = _shell_command(
        cwd=Path(cwd),
        progress_dir=Path(progress_dir),
        interval=interval,
        recent_events=recent_events,
        clear=clear,
    )
    script = "\n".join(
        [
            'tell application "Terminal"',
            "  activate",
            f"  do script {json.dumps(shell_command)}",
            "end tell",
        ]
    )
    subprocess.run(["osascript", "-e", script], check=True)


def run_from_args(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Open Terminal.app to watch create_live_execute_once progress.")
    parser.add_argument("--cwd", default=str(Path.cwd()))
    parser.add_argument("--progress-dir", default="data/runs/create_live_execute_once/progress")
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument("--recent-events", type=int, default=5)
    parser.add_argument("--no-clear", action="store_true")
    args = parser.parse_args(argv)
    open_progress_terminal(
        cwd=args.cwd,
        progress_dir=args.progress_dir,
        interval=float(args.interval),
        recent_events=int(args.recent_events),
        clear=not bool(args.no_clear),
    )
    return 0


def main() -> int:
    return run_from_args()


if __name__ == "__main__":
    raise SystemExit(main())
