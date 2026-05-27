from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _read_jsonl_tail(path: Path, limit: int) -> list[dict[str, Any]]:
    if limit <= 0:
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return []
    rows: list[dict[str, Any]] = []
    for line in lines[-limit:]:
        text = line.strip()
        if not text:
            continue
        try:
            value = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            rows.append(value)
    return rows


def _text(value: Any) -> str:
    return str(value or "").strip()


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def progress_percent(current: dict[str, Any]) -> int:
    done = _int(current.get("done"))
    total = _int(current.get("total"))
    if total <= 0 or done <= 0:
        return 0
    return max(0, min(100, int(done * 100 / total)))


def task_run_from_operation_artifact(payload: dict[str, Any], artifact_path: str | Path) -> dict[str, Any]:
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
    return {
        "task_id": _text(payload.get("task_id")) or _text(payload.get("created_at")) or _text(artifact_path),
        "operation_type": _text(payload.get("operation_type")),
        "status": _text(payload.get("status")),
        "product": _text(summary.get("product")),
        "actor": _text(payload.get("actor")),
        "created_at": _text(payload.get("created_at")),
        "account_count": _int(summary.get("account_count")),
        "material_assignment_count": _int(summary.get("material_assignment_count")),
        "unique_material_count": _int(summary.get("unique_material_count")),
        "result_status": _text(result.get("status")),
        "review_status": _text(summary.get("review_status")),
        "review_blocking_reason_count": _int(summary.get("review_blocking_reason_count")),
        "review_warning_count": _int(summary.get("review_warning_count")),
        "artifact_path": str(artifact_path),
        "execute_artifact_path": _text(result.get("execute_artifact_path")),
        "report_artifact_path": _text(result.get("report_artifact_path")),
    }


def load_recent_task_runs(runs_dir: str | Path, *, limit: int = 50) -> list[dict[str, Any]]:
    log_dir = Path(runs_dir) / "frontend_operation_log"
    paths = sorted(log_dir.glob("*.json"), key=lambda path: path.name, reverse=True)
    rows: list[dict[str, Any]] = []
    for path in paths:
        payload = _read_json(path)
        if not payload:
            continue
        rows.append(task_run_from_operation_artifact(payload, path))
        if len(rows) >= limit:
            break
    return rows


def load_frontend_task_rows(runs_dir: str | Path, *, limit: int = 100) -> list[dict[str, Any]]:
    task_dir = Path(runs_dir) / "frontend_tasks"
    paths = sorted(task_dir.glob("*.json"), key=lambda path: path.name, reverse=True)
    rows: list[dict[str, Any]] = []
    for path in paths:
        payload = _read_json(path)
        if not payload:
            continue
        result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
        post_results = payload.get("post_results") if isinstance(payload.get("post_results"), list) else []
        report_artifact_path = ""
        if post_results and isinstance(post_results[0], dict):
            report_artifact_path = _text(post_results[0].get("artifact_path"))
        rows.append(
            {
                "task_id": _text(payload.get("task_id")) or path.stem,
                "operation_type": _text(payload.get("operation_type")),
                "status": _text(payload.get("status")),
                "created_at": _text(payload.get("created_at")),
                "updated_at": _text(payload.get("updated_at")),
                "return_code": payload.get("return_code"),
                "execute_artifact_path": _text(result.get("execute_artifact_path") or result.get("artifact_path")),
                "report_artifact_path": report_artifact_path,
                "stdout_path": _text(payload.get("stdout_path")),
                "stderr_path": _text(payload.get("stderr_path")),
                "artifact_path": _text(payload.get("artifact_path")) or str(path),
                "command": payload.get("command") if isinstance(payload.get("command"), list) else [],
                "post_commands": payload.get("post_commands") if isinstance(payload.get("post_commands"), list) else [],
                "result": result,
                "post_results": post_results,
            }
        )
        if len(rows) >= limit:
            break
    return rows


def read_create_live_progress(runs_dir: str | Path, *, recent_events: int = 12) -> dict[str, Any]:
    progress_dir = Path(runs_dir) / "create_live_execute_once" / "progress"
    current = _read_json(progress_dir / "current.json")
    events = _read_jsonl_tail(progress_dir / "events.jsonl", recent_events)
    return {
        "progress_dir": str(progress_dir),
        "current": current,
        "percent": progress_percent(current),
        "events": events,
    }


def load_task_detail(runs_dir: str | Path, task_id: str) -> dict[str, Any]:
    for row in load_recent_task_runs(runs_dir, limit=500):
        if row.get("task_id") != task_id:
            continue
        artifact = _read_json(Path(str(row.get("artifact_path") or "")))
        detail = {
            "task": row,
            "artifact": artifact,
            "progress": {},
        }
        if row.get("operation_type") == "create_live_execute":
            detail["progress"] = read_create_live_progress(runs_dir)
        return detail
    return {"task": {}, "artifact": {}, "progress": {}}
