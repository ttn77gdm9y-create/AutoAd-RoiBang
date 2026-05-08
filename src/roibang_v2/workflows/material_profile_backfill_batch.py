from __future__ import annotations

import sqlite3
from copy import deepcopy
from pathlib import Path
from typing import Any

from roibang_v2.fetch.openapi_executor import Transport
from roibang_v2.runs import write_run_artifact
from roibang_v2.workflows.material_duplicate_analysis import run_material_duplicate_analysis_request
from roibang_v2.workflows.material_profile_sync import build_material_profile_sync_preflight
from roibang_v2.workflows.material_profile_sync import run_material_profile_sync_request


def _config(request: dict[str, Any]) -> dict[str, Any]:
    value = request.get("material_profile_backfill_batch")
    return dict(value) if isinstance(value, dict) else dict(request)


def _max_batches(cfg: dict[str, Any]) -> int:
    value = int(cfg.get("max_batches") or 1)
    if value < 1:
        raise ValueError("material_profile_backfill_batch.max_batches must be positive")
    return value


def _profile_sync_config(cfg: dict[str, Any]) -> dict[str, Any]:
    value = cfg.get("material_profile_sync")
    if not isinstance(value, dict):
        raise ValueError("material_profile_backfill_batch requires material_profile_sync")
    profile_cfg = deepcopy(value)
    if str(profile_cfg.get("kind") or "") != "openapi_video_materials":
        raise ValueError("material_profile_backfill_batch only supports openapi_video_materials")
    return profile_cfg


def _missing_material_count(*, db_path: str | Path, profile_cfg: dict[str, Any]) -> int:
    preflight = build_material_profile_sync_preflight({"material_profile_sync": profile_cfg}, db_path=db_path)
    return int(preflight["summary"]["missing_material_count"])


def _profile_count(db_path: str | Path) -> int:
    with sqlite3.connect(db_path) as conn:
        return int(conn.execute("SELECT COUNT(*) FROM material_profiles").fetchone()[0] or 0)


def run_material_profile_backfill_batch_request(
    request: dict[str, Any],
    *,
    db_path: str | Path,
    runs_dir: str | Path,
    transport: Transport | None = None,
) -> dict[str, Any]:
    cfg = _config(request)
    profile_cfg = _profile_sync_config(cfg)
    max_batches = _max_batches(cfg)
    stop_on_no_progress = bool(cfg.get("stop_on_no_progress", True))
    run_duplicate_analysis = bool(cfg.get("run_duplicate_analysis", True))

    if bool(profile_cfg.get("enabled", False)) and transport is None:
        raise RuntimeError("material profile backfill batch requires an explicit readonly transport when enabled")

    missing_before = _missing_material_count(db_path=db_path, profile_cfg=profile_cfg)
    profile_count_before = _profile_count(db_path)
    batches: list[dict[str, Any]] = []
    total_profiles_imported = 0
    total_attributes_imported = 0
    total_external_api_calls = 0
    stop_reason = "max_batches_reached"

    for batch_index in range(1, max_batches + 1):
        preflight = build_material_profile_sync_preflight({"material_profile_sync": profile_cfg}, db_path=db_path)
        missing_before_batch = int(preflight["summary"]["missing_material_count"])
        source_account_count = int(preflight["summary"]["source_account_count"])
        if missing_before_batch <= 0:
            stop_reason = "no_missing_materials"
            break
        if source_account_count <= 0:
            stop_reason = "no_source_accounts"
            break

        result = run_material_profile_sync_request(
            {"material_profile_sync": profile_cfg},
            db_path=db_path,
            runs_dir=runs_dir,
            transport=transport,
        )
        profiles_imported = int(result["summary"].get("profiles_imported") or 0)
        attributes_imported = int(result["summary"].get("attributes_imported") or 0)
        total_profiles_imported += profiles_imported
        total_attributes_imported += attributes_imported
        total_external_api_calls += int(result.get("external_api_calls") or 0)
        missing_after_batch = _missing_material_count(db_path=db_path, profile_cfg=profile_cfg)
        batches.append(
            {
                "batch_index": batch_index,
                "missing_material_count_before": missing_before_batch,
                "missing_material_count_after": missing_after_batch,
                "source_account_count": source_account_count,
                "profiles_imported": profiles_imported,
                "attributes_imported": attributes_imported,
                "external_api_calls": int(result.get("external_api_calls") or 0),
                "stages": result["summary"].get("stages") or [],
                "artifact_path": result.get("artifact_path", ""),
            }
        )
        if stop_on_no_progress and missing_after_batch >= missing_before_batch and profiles_imported <= 0 and attributes_imported <= 0:
            stop_reason = "no_import_progress"
            break
        if batch_index == max_batches:
            stop_reason = "max_batches_reached"

    duplicate_result: dict[str, Any] | None = None
    if run_duplicate_analysis:
        duplicate_cfg = cfg.get("material_duplicate_analysis")
        duplicate_request = (
            {"material_duplicate_analysis": duplicate_cfg}
            if isinstance(duplicate_cfg, dict)
            else {"material_duplicate_analysis": {"rules": ["signature"], "min_group_size": 2}}
        )
        duplicate_result = run_material_duplicate_analysis_request(duplicate_request, db_path=db_path, runs_dir=runs_dir)

    missing_after = _missing_material_count(db_path=db_path, profile_cfg=profile_cfg)
    profile_count_after = _profile_count(db_path)
    payload = {
        "ok": True,
        "workflow": "material_profile_backfill_batch",
        "phase": "phase1",
        "execution_enabled": False,
        "external_api_calls": total_external_api_calls,
        "summary": {
            "max_batches": max_batches,
            "batches_run": len(batches),
            "profiles_imported": total_profiles_imported,
            "attributes_imported": total_attributes_imported,
            "profile_count_before": profile_count_before,
            "profile_count_after": profile_count_after,
            "missing_material_count_before": missing_before,
            "missing_material_count_after": missing_after,
            "stop_reason": stop_reason,
        },
        "batches": batches,
        "duplicate_analysis": duplicate_result,
        "guardrails": {
            "business_actions": [],
            "writes": [
                "material_profiles",
                "materials",
                "material_attribute_snapshots",
                "material_duplicate_candidates",
                "run_artifact",
            ],
            "external_api_calls": total_external_api_calls,
        },
    }
    artifact_path = write_run_artifact(runs_dir, "material_profile_backfill_batch", payload)
    payload["artifact_path"] = str(artifact_path)
    return payload
