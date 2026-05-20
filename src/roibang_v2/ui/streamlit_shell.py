from __future__ import annotations

import json
from pathlib import Path
from typing import Any


DEFAULT_UI_CONFIG: dict[str, Any] = {
    "title": "RoiBang-v2 本地工作台",
    "project_root": ".",
    "runs_dir": "data/runs",
    "create_modes_dir": "configs/create-modes",
    "default_owner": "郭靖",
    "readonly_timeout_seconds": 900,
}


def load_ui_config(path: str | Path = "configs/ui/streamlit-v0.example.json") -> dict[str, Any]:
    source = Path(path)
    if not source.exists():
        return dict(DEFAULT_UI_CONFIG)
    value = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{source} must contain a JSON object")
    config = {**DEFAULT_UI_CONFIG, **value}
    return config


def list_create_modes(mode_dir: str | Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    path = Path(mode_dir)
    if not path.exists():
        return rows
    for item in sorted(path.glob("*.json")):
        try:
            value = json.loads(item.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if not isinstance(value, dict):
            continue
        mode_key = str(value.get("mode_key") or item.stem.replace(".example", "")).strip()
        display_name = str(value.get("display_name") or mode_key).strip()
        template_key = str(value.get("template_key") or "").strip()
        rows.append({"mode_key": mode_key, "display_name": display_name, "template_key": template_key})
    return rows


def mode_label(row: dict[str, str]) -> str:
    display_name = row.get("display_name") or row.get("mode_key") or ""
    mode_key = row.get("mode_key") or ""
    return f"{display_name} ({mode_key})"

