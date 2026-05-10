from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from roibang_v2.runs import write_run_artifact
from roibang_v2.workflows.create_lineage import (
    assert_same_create_plan,
    create_lineage_ref,
    create_ref,
    require_create_ref_fields,
)
from roibang_v2.workflows.create_provider_readiness import not_ready_provider_readiness_contract


def _approval_config(request: dict[str, Any]) -> dict[str, Any]:
    value = request.get("create_approval")
    return dict(value) if isinstance(value, dict) else dict(request)


def _policy_limit(policy: dict[str, Any], key: str, default: int) -> int:
    try:
        value = int(policy.get(key) or default)
    except (TypeError, ValueError):
        value = default
    return max(value, 0)


def _summary(dry_run: dict[str, Any]) -> dict[str, int | str]:
    summary = dry_run.get("summary") if isinstance(dry_run.get("summary"), dict) else {}
    return {
        "plan_id": str(summary.get("plan_id") or ""),
        "request_id": str(summary.get("request_id") or ""),
        "target_date": str(summary.get("target_date") or ""),
        "project_count": int(summary.get("project_count") or 0),
        "unit_count": int(summary.get("unit_count") or 0),
        "material_count": int(summary.get("material_count") or 0),
        "violation_count": int(summary.get("violation_count") or 0),
    }


def _candidate_tasks(dry_run: dict[str, Any]) -> list[dict[str, Any]]:
    tasks = dry_run.get("candidate_tasks")
    return [task for task in tasks if isinstance(task, dict)] if isinstance(tasks, list) else []


def _candidate_task_digest(dry_run: dict[str, Any]) -> dict[str, Any]:
    tasks = _candidate_tasks(dry_run)
    canonical = json.dumps(tasks, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {
        "algorithm": "sha256",
        "value": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "candidate_task_count": len(tasks),
    }


def _provider_readiness(dry_run: dict[str, Any]) -> dict[str, Any]:
    contract = dry_run.get("provider_readiness_contract")
    if isinstance(contract, dict):
        return contract
    return not_ready_provider_readiness_contract()


def _provider_field_map_digest(dry_run: dict[str, Any]) -> dict[str, Any]:
    digest = dry_run.get("provider_field_map_digest")
    if isinstance(digest, dict):
        return {
            "algorithm": str(digest.get("algorithm") or ""),
            "value": str(digest.get("value") or ""),
        }
    return {"algorithm": "sha256", "value": ""}


def _provider_payload_draft_digest(dry_run: dict[str, Any]) -> dict[str, Any]:
    digest = dry_run.get("provider_payload_draft_digest")
    if isinstance(digest, dict):
        return {
            "algorithm": str(digest.get("algorithm") or ""),
            "value": str(digest.get("value") or ""),
            "provider_payload_draft_count": int(digest.get("provider_payload_draft_count") or 0),
        }
    return {"algorithm": "sha256", "value": "", "provider_payload_draft_count": 0}


def _provider_id_ledger_requirements(dry_run: dict[str, Any]) -> dict[str, Any]:
    requirements = dry_run.get("provider_id_ledger_requirements")
    if isinstance(requirements, dict):
        return requirements
    return {
        "status": "missing",
        "produced_by_create_project": [],
        "produced_by_create_unit": [],
        "required_before_create_unit": [],
        "required_before_bind_material": [],
        "execution_enabled": False,
        "external_api_calls": 0,
        "actions": [],
    }


def _provider_payload_drafts(dry_run: dict[str, Any]) -> list[dict[str, Any]]:
    drafts = dry_run.get("provider_payload_drafts")
    return [draft for draft in drafts if isinstance(draft, dict)] if isinstance(drafts, list) else []


def _violations(dry_run: dict[str, Any], policy: dict[str, Any]) -> list[str]:
    violations: list[str] = []
    dry_run_ref = create_ref(workflow="create_dry_run", artifact=dry_run)
    violations.extend(require_create_ref_fields("create dry-run", dry_run_ref))
    plan_ref = create_lineage_ref(dry_run, "create_strategy_plan")
    violations.extend(require_create_ref_fields("create strategy plan", plan_ref))
    if plan_ref:
        violations.extend(
            assert_same_create_plan(
                left_name="create dry-run",
                left=dry_run_ref,
                right_name="create strategy plan",
                right=plan_ref,
            )
        )
    preflight_ref = create_lineage_ref(dry_run, "create_preflight")
    violations.extend(require_create_ref_fields("create preflight", preflight_ref))
    if preflight_ref:
        violations.extend(
            assert_same_create_plan(
                left_name="create dry-run",
                left=dry_run_ref,
                right_name="create preflight",
                right=preflight_ref,
            )
        )
    if str(dry_run.get("status") or "") != "simulated" or not bool(dry_run.get("ok", True)):
        violations.append("create dry-run must be simulated before approval")
    if bool(dry_run.get("execution_enabled", False)):
        violations.append("create dry-run execution_enabled must be false")
    if int(dry_run.get("external_api_calls") or 0) != 0:
        violations.append("create dry-run external_api_calls must be 0")
    if bool(dry_run.get("approved_for_execute", False)):
        violations.append("create dry-run must not already be approved for execute")
    if dry_run.get("actions"):
        violations.append("create dry-run actions must be empty in phase1")
    summary = _summary(dry_run)
    if int(summary["project_count"]) > _policy_limit(policy, "max_projects_per_approval", 50):
        violations.append("approval project count exceeds policy limit")
    if int(summary["unit_count"]) > _policy_limit(policy, "max_units_per_approval", 500):
        violations.append("approval unit count exceeds policy limit")
    if int(summary["material_count"]) > _policy_limit(policy, "max_materials_per_approval", 1000):
        violations.append("approval material count exceeds policy limit")
    for task in _candidate_tasks(dry_run):
        if bool(task.get("executable", False)):
            violations.append("approval candidate tasks must not be executable in phase1")
        if task.get("live_api_payloads"):
            violations.append("approval candidate tasks must not contain live_api_payloads in phase1")
    violations.extend(str(item) for item in dry_run.get("violations") or [])
    return violations


def build_create_approval(
    *,
    create_dry_run_artifact: dict[str, Any],
    policy: dict[str, Any],
) -> dict[str, Any]:
    violations = _violations(create_dry_run_artifact, policy)
    summary = _summary(create_dry_run_artifact)
    if violations:
        status = "blocked"
        policy_decision = "reject"
    elif bool(policy.get("auto_approve_phase1", False)):
        status = "recorded"
        policy_decision = "would_approve"
    else:
        status = "recorded"
        policy_decision = "record_only"
    return {
        "ok": not violations,
        "workflow": "create_approval",
        "phase": "phase1",
        "execution_enabled": False,
        "external_api_calls": 0,
        "status": status,
        "approval_mode": "phase1_record_only",
        "policy_decision": policy_decision,
        "approved": False,
        "execute_allowed": False,
        "approved_for_execute": False,
        "summary": summary,
        "lineage": {
            "create_dry_run": create_ref(workflow="create_dry_run", artifact=create_dry_run_artifact),
            "create_strategy_plan": create_lineage_ref(create_dry_run_artifact, "create_strategy_plan"),
            "create_preflight": create_lineage_ref(create_dry_run_artifact, "create_preflight"),
            "create_provider_field_map_check": create_lineage_ref(
                create_dry_run_artifact,
                "create_provider_field_map_check",
            ),
        },
        "candidate_task_digest": _candidate_task_digest(create_dry_run_artifact),
        "provider_field_map_digest": _provider_field_map_digest(create_dry_run_artifact),
        "provider_payload_draft_digest": _provider_payload_draft_digest(create_dry_run_artifact),
        "provider_payload_drafts": _provider_payload_drafts(create_dry_run_artifact),
        "provider_readiness_contract": _provider_readiness(create_dry_run_artifact),
        "provider_id_ledger_requirements": _provider_id_ledger_requirements(create_dry_run_artifact),
        "policy": {
            "auto_approve_phase1": bool(policy.get("auto_approve_phase1", False)),
            "max_projects_per_approval": _policy_limit(policy, "max_projects_per_approval", 50),
            "max_units_per_approval": _policy_limit(policy, "max_units_per_approval", 500),
            "max_materials_per_approval": _policy_limit(policy, "max_materials_per_approval", 1000),
        },
        "violations": violations,
        "actions": [],
    }


def run_create_approval_request(
    request: dict[str, Any],
    *,
    runs_dir: str | Path,
) -> dict[str, Any]:
    cfg = _approval_config(request)
    create_dry_run_artifact = cfg.get("create_dry_run_artifact")
    if not isinstance(create_dry_run_artifact, dict):
        raise ValueError("create approval requires create_dry_run_artifact")
    policy = cfg.get("policy") if isinstance(cfg.get("policy"), dict) else {}
    payload = build_create_approval(create_dry_run_artifact=create_dry_run_artifact, policy=policy)
    dry_run_path = cfg.get("create_dry_run_artifact_path")
    if str(dry_run_path or "").strip():
        payload["lineage"]["create_dry_run"]["artifact_path"] = str(dry_run_path)
    artifact_path = write_run_artifact(runs_dir, "create_approval", payload)
    return {**payload, "artifact_path": str(artifact_path)}
