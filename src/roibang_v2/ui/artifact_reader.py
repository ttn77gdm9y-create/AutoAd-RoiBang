from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_json_file(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    try:
        value = json.loads(source.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def find_latest_artifact(runs_dir: str | Path, workflow: str) -> Path | None:
    root = Path(runs_dir) / workflow
    latest = root / "latest.json"
    if latest.exists():
        return latest
    candidates = [item for item in root.glob("*.json") if item.is_file()]
    if not candidates:
        return None
    return max(candidates, key=lambda item: (item.stat().st_mtime, item.name))


def load_latest_artifact(runs_dir: str | Path, workflow: str) -> dict[str, Any]:
    path = find_latest_artifact(runs_dir, workflow)
    if path is None:
        return {
            "ok": False,
            "workflow": workflow,
            "status": "missing",
            "artifact_path": "",
            "summary": {},
            "message": f"未找到 {workflow} 的执行结果",
        }
    payload = load_json_file(path)
    payload.setdefault("artifact_path", str(path))
    payload.setdefault("workflow", workflow)
    return payload


def compact_summary(payload: dict[str, Any]) -> dict[str, Any]:
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    return {
        "ok": payload.get("ok"),
        "workflow": payload.get("workflow"),
        "status": payload.get("status") or payload.get("phase") or "",
        "external_api_calls": payload.get("external_api_calls", 0),
        "execution_enabled": payload.get("execution_enabled", False),
        "summary": summary,
        "artifact_path": payload.get("artifact_path", ""),
    }

