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


_WORKFLOW_KEYS = {
    "create_request": "create_request_artifact",
    "create_strategy_plan": "create_strategy_plan_artifact",
    "create_preflight": "create_preflight_artifact",
    "create_dry_run": "create_dry_run_artifact",
    "create_approval": "create_approval_artifact",
    "create_plan_snapshot": "create_plan_snapshot_artifact",
    "create_execute": "create_execute_artifact",
}

_EXPECTED_STATUSES = {
    "create_preflight": "passed",
    "create_dry_run": "simulated",
    "create_approval": "recorded",
    "create_execute": "blocked",
}


def _replay_config(request: dict[str, Any]) -> dict[str, Any]:
    value = request.get("create_chain_replay")
    return dict(value) if isinstance(value, dict) else dict(request)


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


def _digest(artifact: dict[str, Any], key: str) -> dict[str, Any]:
    value = artifact.get(key)
    return dict(value) if isinstance(value, dict) else {}


def _digest_values(rows: list[tuple[str, dict[str, Any]]]) -> list[str]:
    return [str(row.get("value") or "") for _, row in rows if isinstance(row, dict)]


def _same_digest(rows: list[tuple[str, dict[str, Any]]]) -> bool:
    values = _digest_values(rows)
    return bool(values) and len(set(values)) == 1 and all(values)


def _digest_check(name: str, rows: list[tuple[str, dict[str, Any]]], violation: str) -> tuple[dict[str, Any], list[str]]:
    status = "passed" if _same_digest(rows) else "failed"
    check = {
        "status": status,
        "sources": {source: digest for source, digest in rows},
    }
    return check, [] if status == "passed" else [violation]


def _lineage(
    *,
    request: dict[str, Any],
    plan: dict[str, Any],
    preflight: dict[str, Any],
    dry_run: dict[str, Any],
    approval: dict[str, Any],
    snapshot: dict[str, Any],
    execute: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    return {
        "create_request": create_ref(workflow="create_request", artifact=request),
        "create_strategy_plan": create_ref(workflow="create_strategy_plan", artifact=plan),
        "create_preflight": create_ref(workflow="create_preflight", artifact=preflight),
        "create_dry_run": create_ref(workflow="create_dry_run", artifact=dry_run),
        "create_approval": create_ref(workflow="create_approval", artifact=approval),
        "create_plan_snapshot": create_ref(workflow="create_plan_snapshot", artifact=snapshot),
        "create_execute": create_ref(workflow="create_execute", artifact=execute),
    }


def _lineage_violations(lineage: dict[str, dict[str, Any]], artifacts: dict[str, dict[str, Any]]) -> list[str]:
    violations: list[str] = []
    request_ref = lineage["create_request"]
    plan_ref = lineage["create_strategy_plan"]
    if str(request_ref.get("request_id") or "") != str(plan_ref.get("request_id") or ""):
        violations.append("create request request_id must match create strategy plan request_id")
    if str(request_ref.get("target_date") or "") != str(plan_ref.get("target_date") or ""):
        violations.append("create request target_date must match create strategy plan target_date")
    for workflow in ("create_strategy_plan", "create_preflight", "create_dry_run", "create_approval", "create_plan_snapshot", "create_execute"):
        violations.extend(require_create_ref_fields(workflow.replace("_", " "), lineage[workflow]))
    for workflow in ("create_preflight", "create_dry_run", "create_approval", "create_plan_snapshot", "create_execute"):
        violations.extend(
            assert_same_create_plan(
                left_name="create strategy plan",
                left=plan_ref,
                right_name=workflow.replace("_", " "),
                right=lineage[workflow],
            )
        )
    dry_run_lineage = create_lineage_ref(artifacts["create_approval"], "create_dry_run")
    if dry_run_lineage:
        violations.extend(
            assert_same_create_plan(
                left_name="create dry-run",
                left=lineage["create_dry_run"],
                right_name="create approval lineage",
                right=dry_run_lineage,
            )
        )
    return violations


def _phase1_safety_contract(artifacts: dict[str, dict[str, Any]]) -> tuple[dict[str, Any], list[str]]:
    execution_enabled_false = all(not bool(artifact.get("execution_enabled", False)) for artifact in artifacts.values())
    external_api_calls_zero = all(int(artifact.get("external_api_calls") or 0) == 0 for artifact in artifacts.values())
    actions_empty = all(artifact.get("actions") in (None, [], {}) for artifact in artifacts.values())
    violations: list[str] = []
    if not execution_enabled_false:
        violations.append("all create chain artifacts must keep execution_enabled=false")
    if not external_api_calls_zero:
        violations.append("all create chain artifacts must keep external_api_calls=0")
    if not actions_empty:
        violations.append("all create chain artifacts must keep actions empty")
    return {
        "status": "passed" if not violations else "failed",
        "execution_enabled_false": execution_enabled_false,
        "external_api_calls_zero": external_api_calls_zero,
        "actions_empty": actions_empty,
    }, violations


def _artifact_identity_contract(artifacts: dict[str, dict[str, Any]]) -> tuple[dict[str, Any], list[str]]:
    workflow_checks: dict[str, dict[str, Any]] = {}
    status_checks: dict[str, dict[str, Any]] = {}
    violations: list[str] = []
    for workflow, artifact in artifacts.items():
        actual_workflow = str(artifact.get("workflow") or "")
        workflow_ok = actual_workflow == workflow
        workflow_checks[workflow] = {
            "expected": workflow,
            "actual": actual_workflow,
            "ok": workflow_ok,
        }
        if not workflow_ok:
            violations.append(f"{workflow} artifact workflow must be {workflow}")
        expected_status = _EXPECTED_STATUSES.get(workflow)
        if expected_status is not None:
            actual_status = str(artifact.get("status") or "")
            status_ok = actual_status == expected_status
            status_checks[workflow] = {
                "expected": expected_status,
                "actual": actual_status,
                "ok": status_ok,
            }
            if not status_ok:
                violations.append(f"{workflow} artifact status must be {expected_status}")
    return {
        "status": "passed" if not violations else "failed",
        "workflow_checks": workflow_checks,
        "status_checks": status_checks,
    }, violations


def _summary(lineage: dict[str, dict[str, Any]], *, violations: list[str]) -> dict[str, Any]:
    plan_ref = lineage["create_strategy_plan"]
    return {
        "plan_id": str(plan_ref.get("plan_id") or ""),
        "request_id": str(plan_ref.get("request_id") or ""),
        "target_date": str(plan_ref.get("target_date") or ""),
        "checked_workflow_count": len(_WORKFLOW_KEYS),
        "violation_count": len(violations),
    }


def build_create_chain_replay(
    *,
    create_request_artifact: dict[str, Any],
    create_strategy_plan_artifact: dict[str, Any],
    create_preflight_artifact: dict[str, Any],
    create_dry_run_artifact: dict[str, Any],
    create_approval_artifact: dict[str, Any],
    create_plan_snapshot_artifact: dict[str, Any],
    create_execute_artifact: dict[str, Any],
) -> dict[str, Any]:
    artifacts = {
        "create_request": create_request_artifact,
        "create_strategy_plan": create_strategy_plan_artifact,
        "create_preflight": create_preflight_artifact,
        "create_dry_run": create_dry_run_artifact,
        "create_approval": create_approval_artifact,
        "create_plan_snapshot": create_plan_snapshot_artifact,
        "create_execute": create_execute_artifact,
    }
    lineage = _lineage(
        request=create_request_artifact,
        plan=create_strategy_plan_artifact,
        preflight=create_preflight_artifact,
        dry_run=create_dry_run_artifact,
        approval=create_approval_artifact,
        snapshot=create_plan_snapshot_artifact,
        execute=create_execute_artifact,
    )
    candidate_check, candidate_violations = _digest_check(
        "candidate_task_digest",
        [
            ("dry_run_computed", _candidate_task_digest(create_dry_run_artifact)),
            ("approval", _digest(create_approval_artifact, "candidate_task_digest")),
            ("snapshot", _digest(create_plan_snapshot_artifact, "candidate_task_digest")),
            ("execute", _digest(create_execute_artifact, "candidate_task_digest")),
        ],
        "candidate task digest must match across dry-run, approval, snapshot, and execute",
    )
    field_map_check, field_map_violations = _digest_check(
        "provider_field_map_digest",
        [
            ("dry_run", _digest(create_dry_run_artifact, "provider_field_map_digest")),
            ("approval", _digest(create_approval_artifact, "provider_field_map_digest")),
            ("snapshot", _digest(create_plan_snapshot_artifact, "provider_field_map_digest")),
            ("execute", _digest(create_execute_artifact, "provider_field_map_digest")),
        ],
        "provider field map digest must match across dry-run, approval, snapshot, and execute",
    )
    payload_check, payload_violations = _digest_check(
        "provider_payload_draft_digest",
        [
            ("dry_run", _digest(create_dry_run_artifact, "provider_payload_draft_digest")),
            ("approval", _digest(create_approval_artifact, "provider_payload_draft_digest")),
            ("snapshot", _digest(create_plan_snapshot_artifact, "provider_payload_draft_digest")),
            ("execute", _digest(create_execute_artifact, "provider_payload_draft_digest")),
        ],
        "provider payload draft digest must match across dry-run, approval, snapshot, and execute",
    )
    safety_contract, safety_violations = _phase1_safety_contract(artifacts)
    identity_contract, identity_violations = _artifact_identity_contract(artifacts)
    violations = (
        identity_violations
        + _lineage_violations(lineage, artifacts)
        + candidate_violations
        + field_map_violations
        + payload_violations
        + safety_violations
    )
    status = "passed" if not violations else "blocked"
    return {
        "ok": not violations,
        "workflow": "create_chain_replay",
        "phase": "phase1",
        "execution_enabled": False,
        "external_api_calls": 0,
        "status": status,
        "summary": _summary(lineage, violations=violations),
        "lineage": lineage,
        "digest_consistency": {
            "candidate_task_digest": candidate_check,
            "provider_field_map_digest": field_map_check,
            "provider_payload_draft_digest": payload_check,
        },
        "artifact_identity_contract": identity_contract,
        "phase1_safety_contract": safety_contract,
        "violations": violations,
        "actions": [],
    }


def run_create_chain_replay_request(
    request: dict[str, Any],
    *,
    runs_dir: str | Path,
) -> dict[str, Any]:
    cfg = _replay_config(request)
    missing = [key for key in _WORKFLOW_KEYS.values() if not isinstance(cfg.get(key), dict)]
    if missing:
        raise ValueError(f"create chain replay requires artifacts: {', '.join(missing)}")
    payload = build_create_chain_replay(
        create_request_artifact=cfg["create_request_artifact"],
        create_strategy_plan_artifact=cfg["create_strategy_plan_artifact"],
        create_preflight_artifact=cfg["create_preflight_artifact"],
        create_dry_run_artifact=cfg["create_dry_run_artifact"],
        create_approval_artifact=cfg["create_approval_artifact"],
        create_plan_snapshot_artifact=cfg["create_plan_snapshot_artifact"],
        create_execute_artifact=cfg["create_execute_artifact"],
    )
    artifact_path = write_run_artifact(runs_dir, "create_chain_replay", payload)
    return {**payload, "artifact_path": str(artifact_path)}
