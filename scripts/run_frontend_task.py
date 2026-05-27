from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _parse_stdout(stdout: str) -> dict[str, Any]:
    for line in reversed(stdout.splitlines()):
        text = line.strip()
        if not text.startswith("{"):
            continue
        try:
            value = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return {}


def _run_command(command: list[Any], *, cwd: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(part) for part in command],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )


def _expand_placeholders(command: list[Any], *, result: dict[str, Any]) -> list[str]:
    artifact_path = str(result.get("artifact_path") or "")
    return [
        str(part).replace("{result.artifact_path}", artifact_path)
        for part in command
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", required=True)
    args = parser.parse_args()
    task_path = Path(args.task)
    runs_dir = task_path.parent.parent
    task = _read_json(task_path)
    if not task:
        return 2

    task["status"] = "running"
    task["started_at"] = _now()
    task["updated_at"] = _now()
    _write_json(task_path, task)

    stdout_path = runs_dir / str(task.get("stdout_path") or "")
    stderr_path = runs_dir / str(task.get("stderr_path") or "")
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    cwd = str(task.get("cwd") or ".")
    completed = _run_command(task.get("command") or [], cwd=cwd)
    stdout_path.write_text(completed.stdout or "", encoding="utf-8")
    stderr_path.write_text(completed.stderr or "", encoding="utf-8")

    parsed = _parse_stdout(completed.stdout or "")
    post_results: list[dict[str, Any]] = []
    post_return_codes: list[int] = []
    main_ok = completed.returncode == 0 and bool(parsed.get("ok", True))
    if main_ok:
        for index, post_command in enumerate(task.get("post_commands") or []):
            task["status"] = f"running_post_{index + 1}"
            task["updated_at"] = _now()
            _write_json(task_path, task)
            expanded_post_command = _expand_placeholders(post_command, result=parsed)
            post_completed = _run_command(expanded_post_command, cwd=cwd)
            post_stdout_path = stdout_path.with_name(f"{task_path.stem}.post{index + 1}.stdout.log")
            post_stderr_path = stderr_path.with_name(f"{task_path.stem}.post{index + 1}.stderr.log")
            post_stdout_path.write_text(post_completed.stdout or "", encoding="utf-8")
            post_stderr_path.write_text(post_completed.stderr or "", encoding="utf-8")
            post_payload = _parse_stdout(post_completed.stdout or "")
            post_payload.setdefault("return_code", post_completed.returncode)
            post_payload.setdefault("stdout_path", str(post_stdout_path.relative_to(runs_dir)))
            post_payload.setdefault("stderr_path", str(post_stderr_path.relative_to(runs_dir)))
            post_payload.setdefault("command", expanded_post_command)
            post_results.append(post_payload)
            post_return_codes.append(post_completed.returncode)
            if post_completed.returncode != 0:
                break

    ok = main_ok and all(code == 0 for code in post_return_codes)
    task["status"] = "completed" if ok else "failed"
    task["return_code"] = completed.returncode
    task["post_return_codes"] = post_return_codes
    task["result"] = parsed
    task["post_results"] = post_results
    task["finished_at"] = _now()
    task["updated_at"] = _now()
    _write_json(task_path, task)
    if completed.returncode != 0:
        return completed.returncode
    if not main_ok:
        return 1
    for code in post_return_codes:
        if code != 0:
            return code
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
