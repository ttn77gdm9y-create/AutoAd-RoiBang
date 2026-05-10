from __future__ import annotations

from pathlib import Path
from typing import Any

from roibang_v2.runs import write_run_artifact


def _runbook_config(request: dict[str, Any]) -> dict[str, Any]:
    value = request.get("create_first_live_runbook")
    return dict(value) if isinstance(value, dict) else dict(request)


def _first_live_policy(policy: dict[str, Any]) -> dict[str, Any]:
    value = policy.get("first_live_run")
    return dict(value) if isinstance(value, dict) else {}


def _mock_summary(mock_execute: dict[str, Any]) -> dict[str, Any]:
    value = mock_execute.get("summary") if isinstance(mock_execute.get("summary"), dict) else {}
    return {
        "project_count": int(value.get("project_count") or 0),
        "unit_count": int(value.get("unit_count") or 0),
        "material_count": int(value.get("material_count") or 0),
    }


def _scope(*, mock_execute: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    summary = _mock_summary(mock_execute)
    first_live = _first_live_policy(policy)
    return {
        "advertiser_id": str(first_live.get("advertiser_id") or ""),
        "project_count": int(summary["project_count"]),
        "unit_count": int(summary["unit_count"]),
        "material_count": int(summary["material_count"]),
        "max_project_count": int(first_live.get("max_project_count") or 1),
        "max_unit_count": int(first_live.get("max_unit_count") or 2),
        "max_material_count": int(first_live.get("max_material_count") or 4),
    }


def _scope_violations(scope: dict[str, Any]) -> list[str]:
    violations: list[str] = []
    if not str(scope.get("advertiser_id") or ""):
        violations.append("first live run advertiser_id is required")
    if int(scope.get("project_count") or 0) > int(scope.get("max_project_count") or 0):
        violations.append("first live run project count exceeds max_project_count")
    if int(scope.get("unit_count") or 0) > int(scope.get("max_unit_count") or 0):
        violations.append("first live run unit count exceeds max_unit_count")
    if int(scope.get("material_count") or 0) > int(scope.get("max_material_count") or 0):
        violations.append("first live run material count exceeds max_material_count")
    return violations


def build_create_first_live_runbook(
    *,
    create_mock_execute_artifact: dict[str, Any],
    create_live_payload_adapter_scaffold_artifact: dict[str, Any],
    policy: dict[str, Any],
) -> dict[str, Any]:
    scope = _scope(mock_execute=create_mock_execute_artifact, policy=policy)
    violations = _scope_violations(scope)
    if str(create_mock_execute_artifact.get("status") or "") != "simulated":
        violations.append("create mock execute must be simulated before first live runbook")
    if bool(create_live_payload_adapter_scaffold_artifact.get("execution_enabled", False)):
        violations.append("live payload adapter scaffold execution_enabled must be false")
    if int(create_live_payload_adapter_scaffold_artifact.get("external_api_calls") or 0) != 0:
        violations.append("live payload adapter scaffold external_api_calls must be 0")
    return {
        "ok": not violations,
        "workflow": "create_first_live_runbook",
        "phase": "phase2_preparation",
        "execution_enabled": False,
        "external_api_calls": 0,
        "status": "ready_for_human_approval" if not violations else "blocked",
        "live_execute_enabled": False,
        "scope": scope,
        "approval_requirements": [
            "你明确批准首单真实创建",
            "runtime.execution_enabled=true",
            "runtime.external_api_enabled=true",
            "policy.create_execute.live_api.enabled=true",
            "policy.create_execute.payload_schema.live_payload_generation_enabled=true",
            "create_live_execute_phase_gate.live_execute_allowed=true",
        ],
        "runbook_steps": [
            "运行 create_request 到 create_execute 的完整本地链路",
            "运行 create_mock_execute 验证 project_id 和 promotion_id 台账解析",
            "人工复核 execute_review_pack 的 create_project/create_unit/bind_material payload",
            "确认首单 scope 没有超过 1 个项目、2 个单元、4 个素材",
            "你单独批准后，才允许进入真实创建执行阶段",
        ],
        "rollback_policy": {
            "on_create_project_error": "stop_without_create_unit",
            "on_create_unit_error": "stop_without_bind_material",
            "on_bind_material_error": "stop_and_keep_created_ids_for_manual_review",
            "auto_retry_enabled": False,
        },
        "source_workflows": [
            str(create_mock_execute_artifact.get("workflow") or ""),
            str(create_live_payload_adapter_scaffold_artifact.get("workflow") or ""),
        ],
        "violations": violations,
        "actions": [],
    }


def run_create_first_live_runbook_request(
    request: dict[str, Any],
    *,
    runs_dir: str | Path,
) -> dict[str, Any]:
    cfg = _runbook_config(request)
    mock_execute = cfg.get("create_mock_execute_artifact")
    adapter_scaffold = cfg.get("create_live_payload_adapter_scaffold_artifact")
    if not isinstance(mock_execute, dict):
        raise ValueError("create first live runbook requires create_mock_execute_artifact")
    if not isinstance(adapter_scaffold, dict):
        raise ValueError("create first live runbook requires create_live_payload_adapter_scaffold_artifact")
    policy = cfg.get("policy") if isinstance(cfg.get("policy"), dict) else {}
    payload = build_create_first_live_runbook(
        create_mock_execute_artifact=mock_execute,
        create_live_payload_adapter_scaffold_artifact=adapter_scaffold,
        policy=policy,
    )
    artifact_path = write_run_artifact(runs_dir, "create_first_live_runbook", payload)
    return {**payload, "artifact_path": str(artifact_path)}
