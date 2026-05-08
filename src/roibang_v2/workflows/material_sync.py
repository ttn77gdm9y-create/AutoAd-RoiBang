from __future__ import annotations

from pathlib import Path
from typing import Any

from roibang_v2.materials.library import import_material_cache_file
from roibang_v2.materials.library import count_available_materials
from roibang_v2.runs import write_run_artifact


def build_material_supplement_plan(
    *,
    db_path: str | Path,
    advertiser_id: str,
    policy: dict[str, Any],
) -> dict[str, Any]:
    material_type = str(policy.get("material_type") or "video")
    statuses = [str(item) for item in policy.get("available_statuses", ["APPROVED"]) if str(item)]
    if not statuses:
        raise ValueError("available_statuses must not be empty")
    target_count = int(policy.get("target_available_count") or 0)
    if target_count < 1:
        raise ValueError("target_available_count must be greater than 0")

    available_count = count_available_materials(
        db_path=db_path,
        advertiser_id=advertiser_id,
        material_type=material_type,
        review_statuses=statuses,
    )
    supplement_needed = max(target_count - available_count, 0)
    status = "needs_supplement" if supplement_needed else "sufficient"

    return {
        "workflow": "material_sync",
        "phase": "phase1",
        "status": status,
        "advertiser_id": advertiser_id,
        "material_type": material_type,
        "available_statuses": statuses,
        "target_available_count": target_count,
        "available_count": available_count,
        "supplement_needed": supplement_needed,
        "execution_enabled": False,
        "external_api_calls": 0,
        "actions": [],
    }


def _material_sync_config(request: dict[str, Any]) -> dict[str, Any]:
    value = request.get("material_sync")
    return dict(value) if isinstance(value, dict) else dict(request)


def run_material_sync_request(
    request: dict[str, Any],
    *,
    db_path: str | Path,
    runs_dir: str | Path,
) -> dict[str, Any]:
    cfg = _material_sync_config(request)
    kind = str(cfg.get("kind") or "local_cache")
    if kind != "local_cache":
        raise ValueError(f"unsupported material sync kind in phase1: {kind}")

    advertiser_id = str(cfg.get("advertiser_id") or "").strip()
    if not advertiser_id:
        raise ValueError("advertiser_id must not be empty")

    imported = import_material_cache_file(cfg["cache_file"], db_path=db_path)
    if imported["advertiser_id"] != advertiser_id:
        raise ValueError("request advertiser_id does not match material cache advertiser_id")

    policy = cfg.get("policy") if isinstance(cfg.get("policy"), dict) else {}
    plan = build_material_supplement_plan(
        db_path=db_path,
        advertiser_id=advertiser_id,
        policy=policy,
    )
    payload = {
        "ok": True,
        "workflow": "material_sync",
        "phase": "phase1",
        "execution_enabled": False,
        "external_api_calls": 0,
        "import": imported,
        "plan": plan,
    }
    artifact = write_run_artifact(runs_dir, "material_sync", payload)
    return {**payload, "artifact_path": str(artifact)}
