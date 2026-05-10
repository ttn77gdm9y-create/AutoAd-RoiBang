from __future__ import annotations

from pathlib import Path
from typing import Any

from roibang_v2.runs import write_run_artifact


def _prepare_config(request: dict[str, Any]) -> dict[str, Any]:
    value = request.get("create_first_live_prepare_pack")
    return dict(value) if isinstance(value, dict) else dict(request)


def _final_preflight(execution_pack_artifact: dict[str, Any]) -> dict[str, Any]:
    value = execution_pack_artifact.get("final_preflight")
    return dict(value) if isinstance(value, dict) else {}


def _execution_pack(execution_pack_artifact: dict[str, Any]) -> dict[str, Any]:
    value = execution_pack_artifact.get("execution_pack")
    return dict(value) if isinstance(value, dict) else {}


def _payload_counts(execution_pack: dict[str, Any]) -> dict[str, int]:
    value = execution_pack.get("payload_counts")
    data = value if isinstance(value, dict) else {}
    return {
        "create_project": int(data.get("create_project") or 0),
        "create_unit": int(data.get("create_unit") or 0),
        "bind_material": int(data.get("bind_material") or 0),
        "lookup_target_material": int(data.get("lookup_target_material") or 0),
        "total": int(data.get("total") or 0),
    }


def _checks(final_preflight: dict[str, Any]) -> dict[str, bool]:
    value = final_preflight.get("checks")
    data = value if isinstance(value, dict) else {}
    return {str(key): bool(val) for key, val in data.items()}


def _required_enablement(checks: dict[str, bool]) -> dict[str, Any]:
    return {
        "runtime": {
            "execution_enabled": True,
            "external_api_enabled": True,
        },
        "policy": {
            "create_execute.live_api.enabled": True,
            "create_execute.payload_schema.live_payload_generation_enabled": True,
            "create_live_execute_runner.allow_create_http_transport": True,
        },
        "current_missing_checks": [
            key
            for key in (
                "runtime_execution_enabled",
                "runtime_external_api_enabled",
                "policy_live_api_enabled",
                "policy_live_payload_generation_enabled",
                "create_http_transport_allowed",
            )
            if not bool(checks.get(key, False))
        ],
    }


def build_create_first_live_prepare_pack(
    *,
    create_live_execution_pack_artifact: dict[str, Any],
) -> dict[str, Any]:
    final_preflight = _final_preflight(create_live_execution_pack_artifact)
    execution_pack = _execution_pack(create_live_execution_pack_artifact)
    checks = _checks(final_preflight)
    local_boundary_ready = bool(final_preflight.get("ready_for_live_enablement", False))
    ready_for_live_execute = bool(final_preflight.get("ready_for_live_execute", False))
    blocking_reasons = [str(item) for item in final_preflight.get("blocking_reasons") or []]
    status = "ready_for_live_execute" if ready_for_live_execute else "ready_for_human_live_enablement"
    if not local_boundary_ready:
        status = "blocked"
    return {
        "ok": local_boundary_ready,
        "workflow": "create_first_live_prepare_pack",
        "phase": "phase2_preparation",
        "execution_enabled": False,
        "live_execute_enabled": False,
        "external_api_calls": 0,
        "status": status,
        "readiness": {
            "local_boundary_ready": local_boundary_ready,
            "ready_for_live_execute": ready_for_live_execute,
            "requires_human_switch_enablement": not ready_for_live_execute,
            "requires_explicit_user_approval": True,
        },
        "payload_review": {
            "summary": execution_pack.get("summary") if isinstance(execution_pack.get("summary"), dict) else {},
            "scope": execution_pack.get("scope") if isinstance(execution_pack.get("scope"), dict) else {},
            "payload_counts": _payload_counts(execution_pack),
            "ordered_operations": list(execution_pack.get("ordered_operations") or []),
        },
        "required_enablement": _required_enablement(checks),
        "human_review_checklist": [
            "核对 create_project 请求体里的账户、项目名、预算和投放目标。",
            "核对 create_unit 请求体里的项目 ID、出价、定向和素材数量。",
            "核对 bind_material 请求体里的源素材账户、目标账户和源视频 ID。",
            "确认 create_live_execute_once 固定脚本仍是唯一真实执行入口。",
            "你明确批准后，才允许打开 runtime 和 policy 的真实执行开关。",
        ],
        "fixed_scripts": {
            "execution_pack": "scripts/run_create_live_execution_pack.py",
            "execute_once": "scripts/run_create_live_execute_once.py",
        },
        "blocking_reasons": [] if local_boundary_ready else blocking_reasons,
        "actions": [],
    }


def run_create_first_live_prepare_pack_request(
    request: dict[str, Any],
    *,
    runs_dir: str | Path,
) -> dict[str, Any]:
    cfg = _prepare_config(request)
    execution_pack = cfg.get("create_live_execution_pack_artifact")
    if not isinstance(execution_pack, dict):
        raise ValueError("create first live prepare pack requires create_live_execution_pack_artifact")
    payload = build_create_first_live_prepare_pack(create_live_execution_pack_artifact=execution_pack)
    artifact_path = write_run_artifact(runs_dir, "create_first_live_prepare_pack", payload)
    return {**payload, "artifact_path": str(artifact_path)}
