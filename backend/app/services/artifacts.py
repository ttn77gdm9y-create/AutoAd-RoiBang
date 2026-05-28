from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def find_latest_artifact(runs_dir: str | Path, workflow: str) -> Path | None:
    base = Path(runs_dir) / workflow
    if not base.exists():
        return None
    candidates = sorted(path for path in base.glob("*.json") if path.name != "latest.json")
    if candidates:
        return candidates[-1]
    latest = base / "latest.json"
    return latest if latest.exists() else None


def read_json(path: str | Path) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}
