#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from _repo_bootstrap import bootstrap_project_root

PROJECT_ROOT = bootstrap_project_root()


def _find_streamlit_pids(port: str) -> list[int]:
    result = subprocess.run(
        ["ps", "-ef"],
        text=True,
        capture_output=True,
        check=False,
    )
    pids: list[int] = []
    if result.returncode != 0:
        return pids
    for line in result.stdout.splitlines():
        if "streamlit_app.py" not in line and "run_streamlit_ui.py" not in line:
            continue
        if f"--port {port}" not in line and f"--server.port {port}" not in line:
            continue
        parts = line.split()
        if len(parts) > 1:
            try:
                pid = int(parts[1])
            except ValueError:
                continue
            if pid != os.getpid():
                pids.append(pid)
    return sorted(set(pids))


def _stop_pids(pids: list[int], *, wait_seconds: float) -> list[int]:
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    deadline = time.time() + wait_seconds
    remaining = list(pids)
    while time.time() < deadline:
        remaining = []
        for pid in pids:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                continue
            remaining.append(pid)
        if not remaining:
            return []
        time.sleep(0.2)
    for pid in remaining:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    return remaining


def _healthcheck(url: str, *, timeout_seconds: float, attempts: int) -> bool:
    for _ in range(attempts):
        try:
            with urllib.request.urlopen(url, timeout=timeout_seconds) as response:
                if int(response.status) < 500:
                    return True
        except (OSError, urllib.error.URLError):
            time.sleep(0.5)
    return False


def run_from_args(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Restart RoiBang-v2 Streamlit local UI by port.")
    parser.add_argument("--ui-config", default="configs/ui/streamlit-v0.example.json")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default="8502")
    parser.add_argument("--wait-seconds", type=float, default=3.0)
    parser.add_argument("--health-attempts", type=int, default=20)
    args = parser.parse_args(argv)

    before_pids = _find_streamlit_pids(str(args.port))
    killed_pids = _stop_pids(before_pids, wait_seconds=float(args.wait_seconds))
    command = [
        sys.executable,
        "scripts/run_streamlit_ui.py",
        "--host",
        str(args.host),
        "--port",
        str(args.port),
        "--ui-config",
        str(args.ui_config),
    ]
    process = subprocess.Popen(
        command,
        cwd=str(PROJECT_ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    url = f"http://{args.host}:{args.port}"
    ok = _healthcheck(url, timeout_seconds=2, attempts=int(args.health_attempts))
    summary = {
        "ok": ok,
        "workflow": "streamlit_ui_restart",
        "status": "running" if ok else "healthcheck_failed",
        "url": url,
        "stopped_pids": before_pids,
        "force_killed_pids": killed_pids,
        "started_pid": process.pid,
        "command": command,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if ok else 1


def main() -> int:
    return run_from_args()


if __name__ == "__main__":
    raise SystemExit(main())
