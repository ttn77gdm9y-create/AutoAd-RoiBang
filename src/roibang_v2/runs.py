from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def write_run_artifact(runs_dir: str | Path, workflow: str, payload: dict[str, Any]) -> Path:
    target_dir = Path(runs_dir) / workflow
    target_dir.mkdir(parents=True, exist_ok=True)
    timestamp = utc_timestamp()
    content = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    for index in range(1000):
        suffix = "" if index == 0 else f"-{index:03d}"
        target = target_dir / f"{timestamp}{suffix}.json"
        try:
            with target.open("x", encoding="utf-8") as handle:
                handle.write(content)
            return target
        except FileExistsError:
            continue
    raise RuntimeError(f"cannot allocate run artifact path for workflow {workflow}: {timestamp}")


def write_latest_artifact(runs_dir: str | Path, workflow: str, payload: dict[str, Any]) -> Path:
    target_dir = Path(runs_dir) / workflow
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / "latest.json"
    tmp = target_dir / f".latest.{uuid4().hex}.json.tmp"
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(target)
    return target


def write_snapshot_artifact(runs_dir: str | Path, workflow: str, payload: dict[str, Any]) -> Path:
    target_dir = Path(runs_dir) / workflow
    target_dir.mkdir(parents=True, exist_ok=True)
    timestamp = utc_timestamp()
    for index in range(1000):
        suffix = "" if index == 0 else f"-{index:03d}"
        target = target_dir / f"{timestamp}{suffix}.json"
        snapshot_payload = {**payload, "artifact_path": str(target)}
        content = json.dumps(snapshot_payload, ensure_ascii=False, indent=2) + "\n"
        try:
            with target.open("x", encoding="utf-8") as handle:
                handle.write(content)
        except FileExistsError:
            continue
        write_latest_artifact(runs_dir, workflow, snapshot_payload)
        return target
    raise RuntimeError(f"cannot allocate snapshot artifact path for workflow {workflow}: {timestamp}")
