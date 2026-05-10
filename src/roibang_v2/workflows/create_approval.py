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


_PAYLOAD_REVIEW_OPERATIONS = ("create_project", "create_unit", "bind_material")


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


def _lookup_placeholder_count(value: Any) -> int:
    if isinstance(value, str):
        return 1 if value.startswith("<lookup:") and value.endswith(">") else 0
    if isinstance(value, dict):
        return sum(_lookup_placeholder_count(item) for item in value.values())
    if isinstance(value, list):
        return sum(_lookup_placeholder_count(item) for item in value)
    return 0


def _draft_live_payload_count(draft: dict[str, Any]) -> int:
    return 1 if bool(draft.get("live_api_payload", False)) or bool(draft.get("live_payload", False)) else 0


def _payload_operation_summary(drafts: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "payload_count": len(drafts),
        "executable_true_count": sum(1 for draft in drafts if bool(draft.get("executable", False))),
        "live_payload_count": sum(_draft_live_payload_count(draft) for draft in drafts),
        "candidate_draft_count": sum(1 for draft in drafts if str(draft.get("field_mapping_mode") or "") == "candidate"),
        "candidate_unverified_field_count": sum(int(draft.get("candidate_unverified_field_count") or 0) for draft in drafts),
        "unresolved_lookup_placeholder_count": sum(
            _lookup_placeholder_count(draft.get("payload") if isinstance(draft.get("payload"), dict) else {})
            for draft in drafts
        ),
    }


def _payload_review(dry_run: dict[str, Any]) -> dict[str, Any]:
    drafts = _provider_payload_drafts(dry_run)
    drafts_by_operation = {
        operation: [draft for draft in drafts if str(draft.get("operation") or "") == operation]
        for operation in _PAYLOAD_REVIEW_OPERATIONS
    }
    by_operation = {
        operation: _payload_operation_summary(operation_drafts)
        for operation, operation_drafts in drafts_by_operation.items()
    }
    total_summary = _payload_operation_summary(drafts)
    payload_counts = {operation: int(summary["payload_count"]) for operation, summary in by_operation.items()}
    payload_counts["total"] = int(total_summary["payload_count"])
    return {
        "drafts_by_operation": drafts_by_operation,
        "manual_review_summary": {
            "status": "record_only_not_execute_switch",
            "plain_language": "approve 只是批准记录，不是执行开关；create_execute 仍然 hard-block。",
            "payload_counts": payload_counts,
            "checks": {
                "all_payloads_executable_false": int(total_summary["executable_true_count"]) == 0,
                "live_payload_count_zero": int(total_summary["live_payload_count"]) == 0,
                "candidate_payloads_present": int(total_summary["candidate_draft_count"])
                + int(total_summary["candidate_unverified_field_count"])
                > 0,
                "unresolved_lookup_placeholders_present": int(total_summary["unresolved_lookup_placeholder_count"]) > 0,
                "create_execute_hard_block_required": True,
                "approve_is_execute_switch": False,
                "external_api_calls_zero": True,
            },
            "counts": total_summary,
            "by_operation": by_operation,
            "execution_enabled": False,
            "external_api_calls": 0,
            "actions": [],
        },
    }


def _actual_provider_payload_draft_digest(drafts: list[dict[str, Any]]) -> dict[str, Any]:
    canonical = json.dumps(drafts, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {
        "algorithm": "sha256",
        "value": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "provider_payload_draft_count": len(drafts),
    }


def _payload_digest_contract(dry_run: dict[str, Any]) -> dict[str, Any]:
    drafts = _provider_payload_drafts(dry_run)
    expected = _provider_payload_draft_digest(dry_run)
    actual = _actual_provider_payload_draft_digest(drafts)
    status = "passed" if expected == actual else "failed"
    return {
        "status": status,
        "expected_digest": expected,
        "actual_digest": actual,
        "draft_count": len(drafts),
    }


def _provider_payload_review_summary(dry_run: dict[str, Any]) -> dict[str, Any]:
    drafts = _provider_payload_drafts(dry_run)
    readiness = _provider_readiness(dry_run)
    candidate_unverified_count = sum(int(draft.get("candidate_unverified_field_count") or 0) for draft in drafts)
    candidate_draft_count = sum(1 for draft in drafts if str(draft.get("field_mapping_mode") or "") == "candidate")
    executable_count = sum(1 for draft in drafts if bool(draft.get("executable", False)))
    live_payload_count = sum(1 for draft in drafts if bool(draft.get("live_api_payload", False)))
    unmapped_count = sum(len(draft.get("unmapped_payload_fields") or []) for draft in drafts)
    blocking_reasons: list[str] = []
    if candidate_draft_count or candidate_unverified_count:
        blocking_reasons.append("candidate provider fields require evidence review")
    if executable_count:
        blocking_reasons.append("provider payload drafts must not be executable")
    if live_payload_count:
        blocking_reasons.append("provider payload drafts must not contain live payloads")
    if unmapped_count:
        blocking_reasons.append("provider payload drafts contain unmapped internal fields")
    for reason in readiness.get("blocking_reasons") if isinstance(readiness.get("blocking_reasons"), list) else []:
        reason_text = str(reason)
        if reason_text and reason_text not in blocking_reasons:
            blocking_reasons.append(reason_text)
    return {
        "draft_count": len(drafts),
        "candidate_draft_count": candidate_draft_count,
        "verified_draft_count": sum(1 for draft in drafts if str(draft.get("field_mapping_mode") or "") == "verified"),
        "executable_draft_count": executable_count,
        "live_payload_count": live_payload_count,
        "candidate_unverified_field_count": candidate_unverified_count,
        "unmapped_payload_field_count": unmapped_count,
        "ready_for_execute": False,
        "blocking_reasons": blocking_reasons,
    }


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
    payload_digest_contract = _payload_digest_contract(dry_run)
    if str(payload_digest_contract.get("status") or "") != "passed":
        violations.append("provider payload draft digest must match approval payload drafts")
    payload_summary = _provider_payload_review_summary(dry_run)
    if int(payload_summary.get("executable_draft_count") or 0):
        violations.append("provider payload drafts must not be executable before approval")
    if int(payload_summary.get("live_payload_count") or 0):
        violations.append("provider payload drafts must not contain live payloads before approval")
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
        "payload_digest_contract": _payload_digest_contract(create_dry_run_artifact),
        "provider_payload_review_summary": _provider_payload_review_summary(create_dry_run_artifact),
        "payload_review": _payload_review(create_dry_run_artifact),
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
