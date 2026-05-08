from __future__ import annotations

from pathlib import Path
from typing import Any

from roibang_v2.reports.snapshot import import_report_snapshot_file
from roibang_v2.runs import write_run_artifact


def _data_sync_config(request: dict[str, Any]) -> dict[str, Any]:
    value = request.get("data_sync")
    return dict(value) if isinstance(value, dict) else dict(request)


def run_data_sync_request(
    request: dict[str, Any],
    *,
    db_path: str | Path,
    runs_dir: str | Path,
) -> dict[str, Any]:
    cfg = _data_sync_config(request)
    kind = str(cfg.get("kind") or "local_report_snapshot")
    if kind != "local_report_snapshot":
        raise ValueError(f"unsupported data sync kind in phase1: {kind}")

    imported = import_report_snapshot_file(cfg["snapshot_file"], db_path=db_path)
    payload = {
        "ok": True,
        "workflow": "data_sync",
        "phase": "phase1",
        "kind": kind,
        "execution_enabled": False,
        "external_api_calls": 0,
        "import": imported,
    }
    artifact = write_run_artifact(runs_dir, "data_sync", payload)
    return {**payload, "artifact_path": str(artifact)}
