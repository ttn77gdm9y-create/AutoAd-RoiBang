from __future__ import annotations

import json
import subprocess
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def task_paths(runs_dir: str | Path, task_id: str) -> dict[str, Path]:
    base = Path(runs_dir) / "frontend_tasks"
    return {
        "dir": base,
        "task": base / f"{task_id}.json",
        "stdout": base / f"{task_id}.stdout.log",
        "stderr": base / f"{task_id}.stderr.log",
    }


def build_task_record(
    *,
    runs_dir: str | Path,
    operation_type: str,
    command: list[str],
    cwd: str,
    request: dict[str, Any] | None = None,
    post_commands: list[list[str]] | None = None,
) -> dict[str, Any]:
    task_id = f"frontend-{datetime.now().strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:8]}"
    paths = task_paths(runs_dir, task_id)
    runs_path = Path(runs_dir)
    return {
        "task_id": task_id,
        "operation_type": operation_type,
        "status": "queued",
        "created_at": _now(),
        "updated_at": _now(),
        "cwd": cwd,
        "command": command,
        "post_commands": post_commands or [],
        "request": request or {},
        "return_code": None,
        "stdout_path": str(paths["stdout"].relative_to(runs_path)),
        "stderr_path": str(paths["stderr"].relative_to(runs_path)),
        "artifact_path": str(paths["task"].relative_to(runs_path)),
        "result": {},
        "post_results": [],
    }


def write_task_record(runs_dir: str | Path, record: dict[str, Any]) -> Path:
    task_id = str(record["task_id"])
    paths = task_paths(runs_dir, task_id)
    paths["dir"].mkdir(parents=True, exist_ok=True)
    paths["task"].write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return paths["task"]


def load_task_record(path: str | Path) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def build_runner_command(task_path: str | Path) -> list[str]:
    return ["python3", "scripts/run_frontend_task.py", "--task", str(task_path)]


def start_runner(command: list[str], *, cwd: str | Path) -> int:
    process = subprocess.Popen(
        [str(part) for part in command],
        cwd=str(cwd),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
        start_new_session=True,
    )
    return int(process.pid)
