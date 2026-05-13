from __future__ import annotations

from pathlib import Path
from typing import Any

from roibang_v2.runs import write_run_artifact
from roibang_v2.workflows.create_phase2_yzt_create_preview import build_create_phase2_yzt_create_preview
from roibang_v2.workflows.create_strategy_plan import (
    _candidate_filters,
    _candidate_rows,
    _material_requirements,
    _required_material_slots,
    _target_existing_material_ids_by_account,
    _usable_source_material_count,
)


def _check_config(request: dict[str, Any]) -> dict[str, Any]:
    value = request.get("create_phase2_yzt_material_pool_check")
    return dict(value) if isinstance(value, dict) else dict(request)


def _strategy_policy(policy: dict[str, Any]) -> dict[str, Any]:
    value = policy.get("create_strategy_plan")
    return dict(value) if isinstance(value, dict) else {}


def _allowed_statuses(policy: dict[str, Any]) -> list[str]:
    value = _candidate_filters(policy).get("allowed_review_statuses")
    return [str(item) for item in value if str(item)] if isinstance(value, list) else []


def build_create_phase2_yzt_material_pool_check(
    *,
    preview_config: dict[str, Any],
    policy: dict[str, Any],
    db_path: str | Path,
) -> dict[str, Any]:
    preview = build_create_phase2_yzt_create_preview(preview_config=preview_config, policy=policy)
    standard_request = preview.get("standard_create_request") if isinstance(preview.get("standard_create_request"), dict) else {}
    strategy_policy = _strategy_policy(policy)
    candidates = _candidate_rows(db_path=db_path, request=standard_request, policy=strategy_policy)
    existing_by_account = _target_existing_material_ids_by_account(
        db_path=db_path,
        request=standard_request,
        policy=strategy_policy,
    )
    usable_count = _usable_source_material_count(
        request=standard_request,
        candidates=candidates,
        existing_by_account=existing_by_account,
    )
    required_count = _required_material_slots(standard_request)
    missing_count = max(required_count - usable_count, 0)
    requirements = _material_requirements(standard_request)
    violations = (
        [f"源素材账户可用素材 {usable_count} 个，不够本次预演需要的 {required_count} 个，缺 {missing_count} 个"]
        if missing_count
        else []
    )
    ok = bool(preview.get("ok")) and not violations
    product = str(standard_request.get("product") or "")
    source_advertiser_id = str(standard_request.get("source_advertiser_id") or "")
    return {
        "ok": ok,
        "workflow": "create_phase2_yzt_material_pool_check",
        "phase": "phase2_preparation",
        "execution_enabled": False,
        "external_api_calls": 0,
        "status": "passed" if ok else "needs_source_material_account_sync",
        "summary": {
            "product": product,
            "source_advertiser_id": source_advertiser_id,
            "required_material_count": required_count,
            "usable_material_count": usable_count,
            "missing_material_count": missing_count,
            "ready_for_dry_chain": ok,
        },
        "source_material_account": {
            "material_type": str(requirements.get("material_type") or "video"),
            "materials_per_unit": int(requirements.get("materials_per_unit") or 0),
            "dedupe_scope": str(requirements.get("dedupe_scope") or "request"),
            "candidate_filter_statuses": _allowed_statuses(strategy_policy),
        },
        "violations": list(preview.get("violations") or []) + violations,
        "human_next_steps": (
            ["源素材账户素材数量够用；下一步可以跑完整预演。"]
            if ok
            else ["先同步源素材账户，或减少本次项目数、单元数、每单元素材数。"]
        ),
        "actions": [],
    }


def run_create_phase2_yzt_material_pool_check_request(
    request: dict[str, Any],
    *,
    db_path: str | Path,
    runs_dir: str | Path,
) -> dict[str, Any]:
    cfg = _check_config(request)
    payload = build_create_phase2_yzt_material_pool_check(
        preview_config=cfg.get("preview_config") if isinstance(cfg.get("preview_config"), dict) else {},
        policy=cfg.get("policy") if isinstance(cfg.get("policy"), dict) else {},
        db_path=db_path,
    )
    artifact_path = write_run_artifact(runs_dir, "create_phase2_yzt_material_pool_check", payload)
    return {**payload, "artifact_path": str(artifact_path)}
