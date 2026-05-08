from __future__ import annotations

from pathlib import Path
from typing import Any

from roibang_v2.runs import write_run_artifact
from roibang_v2.workflows.create_lineage import (
    assert_same_create_plan,
    create_lineage_ref,
    create_ref,
    require_create_ref_fields,
)
from roibang_v2.workflows.create_payload_schema import disabled_create_payload_schema
from roibang_v2.workflows.create_provider_readiness import not_ready_provider_readiness_contract


def _execute_config(request: dict[str, Any]) -> dict[str, Any]:
    value = request.get("create_execute")
    return dict(value) if isinstance(value, dict) else dict(request)


def _summary(approval: dict[str, Any]) -> dict[str, Any]:
    summary = approval.get("summary") if isinstance(approval.get("summary"), dict) else {}
    return {
        "plan_id": str(summary.get("plan_id") or ""),
        "request_id": str(summary.get("request_id") or ""),
        "target_date": str(summary.get("target_date") or ""),
        "project_count": int(summary.get("project_count") or 0),
        "unit_count": int(summary.get("unit_count") or 0),
        "material_count": int(summary.get("material_count") or 0),
        "approval_status": str(approval.get("status") or ""),
        "policy_decision": str(approval.get("policy_decision") or ""),
        "execute_allowed": bool(approval.get("execute_allowed", False)),
    }


def _execution_plan(summary: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    return {
        "mode": "phase1_skeleton_only",
        "steps": [
            {
                "step": "create_project",
                "order": 1,
                "planned_count": int(summary.get("project_count") or 0),
                "status": "blocked_in_phase1",
            },
            {
                "step": "create_unit",
                "order": 2,
                "planned_count": int(summary.get("unit_count") or 0),
                "status": "blocked_in_phase1",
            },
            {
                "step": "bind_material",
                "order": 3,
                "planned_count": int(summary.get("material_count") or 0),
                "status": "blocked_in_phase1",
            },
        ],
        "failure_policy": {
            "on_project_create_error": "stop",
            "on_unit_create_error": "stop",
            "on_material_bind_error": "stop",
            "retry_enabled": False,
        },
        "payload_schema": disabled_create_payload_schema(policy),
        "live_api_payloads": [],
    }


def _audit_config(policy: dict[str, Any]) -> dict[str, Any]:
    audit = policy.get("audit") if isinstance(policy.get("audit"), dict) else {}
    return {
        "enabled": False,
        "format": str(audit.get("format") or "jsonl"),
        "path": str(audit.get("path") or "data/runs/create_execute/audit"),
        "redact_fields": list(audit.get("redact_fields") or ["Access-Token", "Cookie", "x-csrftoken"]),
    }


def _candidate_task_digest(approval: dict[str, Any]) -> dict[str, Any]:
    digest = approval.get("candidate_task_digest")
    if isinstance(digest, dict):
        return {
            "algorithm": str(digest.get("algorithm") or ""),
            "value": str(digest.get("value") or ""),
            "candidate_task_count": int(digest.get("candidate_task_count") or 0),
        }
    return {"algorithm": "sha256", "value": "", "candidate_task_count": 0}


def _provider_readiness(approval: dict[str, Any]) -> dict[str, Any]:
    contract = approval.get("provider_readiness_contract")
    if isinstance(contract, dict):
        return contract
    return not_ready_provider_readiness_contract()


def _provider_field_map_digest(approval: dict[str, Any]) -> dict[str, Any]:
    digest = approval.get("provider_field_map_digest")
    if isinstance(digest, dict):
        return {
            "algorithm": str(digest.get("algorithm") or ""),
            "value": str(digest.get("value") or ""),
        }
    return {"algorithm": "sha256", "value": ""}


def _provider_payload_draft_digest(approval: dict[str, Any]) -> dict[str, Any]:
    digest = approval.get("provider_payload_draft_digest")
    if isinstance(digest, dict):
        return {
            "algorithm": str(digest.get("algorithm") or ""),
            "value": str(digest.get("value") or ""),
            "provider_payload_draft_count": int(digest.get("provider_payload_draft_count") or 0),
        }
    return {"algorithm": "sha256", "value": "", "provider_payload_draft_count": 0}


def _policy_violations(policy: dict[str, Any]) -> list[str]:
    violations: list[str] = []
    if bool(policy.get("allow_execute_phase1", False)):
        violations.append("create execute policy allow_execute_phase1 must be false in phase1")
    if bool(policy.get("allow_live_api_payloads", False)):
        violations.append("create execute policy allow_live_api_payloads must be false in phase1")
    live_api = policy.get("live_api") if isinstance(policy.get("live_api"), dict) else {}
    if bool(live_api.get("enabled", False)):
        violations.append("create execute live_api.enabled must be false in phase1")
    if bool(live_api.get("allow_live_api_payloads", False)):
        violations.append("create execute live_api.allow_live_api_payloads must be false in phase1")
    execution = policy.get("execution") if isinstance(policy.get("execution"), dict) else {}
    if str(execution.get("status") or "") == "execute":
        violations.append("create execute request execution.status must not be execute in phase1")
    if bool(execution.get("execution_enabled", False)):
        violations.append("create execute request execution_enabled must be false in phase1")
    if bool(execution.get("external_api_enabled", False)):
        violations.append("create execute request external_api_enabled must be false in phase1")
    payload_schema = policy.get("payload_schema") if isinstance(policy.get("payload_schema"), dict) else {}
    if str(payload_schema.get("mode") or "") == "live_payloads":
        violations.append("create execute payload_schema.mode must not be live_payloads in phase1")
    if bool(payload_schema.get("live_payload_generation_enabled", False)):
        violations.append("create execute payload_schema.live_payload_generation_enabled must be false in phase1")
    return violations


def _violations(approval: dict[str, Any], policy: dict[str, Any]) -> list[str]:
    violations: list[str] = []
    violations.extend(_policy_violations(policy))
    approval_ref = create_ref(workflow="create_approval", artifact=approval)
    violations.extend(require_create_ref_fields("create approval", approval_ref))
    dry_run_ref = create_lineage_ref(approval, "create_dry_run")
    violations.extend(require_create_ref_fields("create dry-run", dry_run_ref))
    if dry_run_ref:
        violations.extend(
            assert_same_create_plan(
                left_name="create approval",
                left=approval_ref,
                right_name="create dry-run",
                right=dry_run_ref,
            )
        )
    plan_ref = create_lineage_ref(approval, "create_strategy_plan")
    violations.extend(require_create_ref_fields("create strategy plan", plan_ref))
    if plan_ref:
        violations.extend(
            assert_same_create_plan(
                left_name="create approval",
                left=approval_ref,
                right_name="create strategy plan",
                right=plan_ref,
            )
        )
    if str(approval.get("status") or "") != "recorded" or not bool(approval.get("ok", True)):
        violations.append("create approval must be recorded before execute")
    if bool(approval.get("execution_enabled", False)):
        violations.append("create approval execution_enabled must be false")
    if int(approval.get("external_api_calls") or 0) != 0:
        violations.append("create approval external_api_calls must be 0")
    if bool(approval.get("execute_allowed", False)):
        violations.append("create approval execute_allowed must be false in phase1")
    if bool(approval.get("approved_for_execute", False)):
        violations.append("create approval approved_for_execute must be false in phase1")
    if approval.get("actions"):
        violations.append("create approval actions must be empty in phase1")
    violations.extend(str(item) for item in approval.get("violations") or [])
    return violations


def build_create_execute(
    *,
    create_approval_artifact: dict[str, Any],
    policy: dict[str, Any],
) -> dict[str, Any]:
    violations = _violations(create_approval_artifact, policy)
    summary = _summary(create_approval_artifact)
    payload_schema = disabled_create_payload_schema(policy)
    return {
        "ok": not violations,
        "workflow": "create_execute",
        "phase": "phase1",
        "execution_enabled": False,
        "external_api_calls": 0,
        "status": "blocked",
        "reason": "phase1_execute_disabled",
        "summary": summary,
        "lineage": {
            "create_approval": create_ref(workflow="create_approval", artifact=create_approval_artifact),
            "create_dry_run": create_lineage_ref(create_approval_artifact, "create_dry_run"),
            "create_strategy_plan": create_lineage_ref(create_approval_artifact, "create_strategy_plan"),
            "create_preflight": create_lineage_ref(create_approval_artifact, "create_preflight"),
            "create_provider_field_map_check": create_lineage_ref(
                create_approval_artifact,
                "create_provider_field_map_check",
            ),
        },
        "candidate_task_digest": _candidate_task_digest(create_approval_artifact),
        "payload_schema": payload_schema,
        "execution_plan": _execution_plan(summary, policy),
        "provider_field_map_digest": _provider_field_map_digest(create_approval_artifact),
        "provider_payload_draft_digest": _provider_payload_draft_digest(create_approval_artifact),
        "provider_readiness_contract": _provider_readiness(create_approval_artifact),
        "audit": _audit_config(policy),
        "violations": violations,
        "approved_for_execute": False,
        "executed_task_count": 0,
        "actions": [],
    }


def run_create_execute_request(
    request: dict[str, Any],
    *,
    runs_dir: str | Path,
) -> dict[str, Any]:
    cfg = _execute_config(request)
    create_approval_artifact = cfg.get("create_approval_artifact")
    if not isinstance(create_approval_artifact, dict):
        raise ValueError("create execute requires create_approval_artifact")
    policy = cfg.get("policy") if isinstance(cfg.get("policy"), dict) else {}
    payload = build_create_execute(create_approval_artifact=create_approval_artifact, policy=policy)
    approval_path = cfg.get("create_approval_artifact_path")
    if str(approval_path or "").strip():
        payload["lineage"]["create_approval"]["artifact_path"] = str(approval_path)
    artifact_path = write_run_artifact(runs_dir, "create_execute", payload)
    return {**payload, "artifact_path": str(artifact_path)}
