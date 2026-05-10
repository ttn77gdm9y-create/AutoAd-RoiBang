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
from roibang_v2.workflows.create_payload_schema import disabled_create_payload_schema
from roibang_v2.workflows.create_provider_id_ledger import resolve_provider_payload_drafts
from roibang_v2.workflows.create_provider_readiness import not_ready_provider_readiness_contract


_PAYLOAD_REVIEW_OPERATIONS = ("create_project", "bind_material", "lookup_target_material", "create_unit")


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


def _provider_id_ledger_requirements(approval: dict[str, Any]) -> dict[str, Any]:
    requirements = approval.get("provider_id_ledger_requirements")
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


def _provider_id_ledger_gate(requirements: dict[str, Any]) -> dict[str, Any]:
    required_before_create_unit = requirements.get("required_before_create_unit")
    required_before_bind_material = requirements.get("required_before_bind_material")
    return {
        "status": "hard_blocked_phase1",
        "ready_for_live_execute": False,
        "required_before_create_unit_count": len(required_before_create_unit)
        if isinstance(required_before_create_unit, list)
        else 0,
        "required_before_bind_material_count": len(required_before_bind_material)
        if isinstance(required_before_bind_material, list)
        else 0,
        "execution_enabled": False,
        "external_api_calls": 0,
        "actions": [],
    }


def _execution_plan(
    summary: dict[str, Any],
    policy: dict[str, Any],
    provider_id_ledger_gate: dict[str, Any],
) -> dict[str, Any]:
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
                "step": "bind_material",
                "order": 2,
                "planned_count": int(summary.get("material_count") or 0),
                "status": "blocked_in_phase1",
                "requires_provider_id_ledger": {
                    "status": "required",
                    "required_count": int(provider_id_ledger_gate.get("required_before_bind_material_count") or 0),
                },
            },
            {
                "step": "lookup_target_material",
                "order": 3,
                "planned_count": int(summary.get("material_count") or 0),
                "status": "blocked_in_phase1",
            },
            {
                "step": "create_unit",
                "order": 4,
                "planned_count": int(summary.get("unit_count") or 0),
                "status": "blocked_in_phase1",
                "requires_provider_id_ledger": {
                    "status": "required",
                    "required_count": int(provider_id_ledger_gate.get("required_before_create_unit_count") or 0),
                },
            },
        ],
        "failure_policy": {
            "on_project_create_error": "stop",
            "on_unit_create_error": "stop",
            "on_material_bind_error": "stop",
            "retry_enabled": False,
        },
        "payload_schema": disabled_create_payload_schema(policy),
        "provider_id_ledger_gate": provider_id_ledger_gate,
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


def _provider_payload_drafts(approval: dict[str, Any]) -> list[dict[str, Any]]:
    drafts = approval.get("provider_payload_drafts")
    return [draft for draft in drafts if isinstance(draft, dict)] if isinstance(drafts, list) else []


def _actual_provider_payload_draft_digest(drafts: list[dict[str, Any]]) -> dict[str, Any]:
    canonical = json.dumps(drafts, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {
        "algorithm": "sha256",
        "value": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "provider_payload_draft_count": len(drafts),
    }


def _provider_payload_review_summary(approval: dict[str, Any]) -> dict[str, Any]:
    summary = approval.get("provider_payload_review_summary")
    if isinstance(summary, dict):
        return summary
    drafts = _provider_payload_drafts(approval)
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


def _approval_boundary_contract(approval: dict[str, Any]) -> dict[str, Any]:
    drafts = _provider_payload_drafts(approval)
    expected_digest = _provider_payload_draft_digest(approval)
    actual_digest = _actual_provider_payload_draft_digest(drafts)
    executable_count = sum(1 for draft in drafts if bool(draft.get("executable", False)))
    live_payload_count = sum(1 for draft in drafts if bool(draft.get("live_api_payload", False)))
    candidate_summary = _provider_payload_review_summary(approval)
    return {
        "status": "passed"
        if (
            str(approval.get("status") or "") == "recorded"
            and not bool(approval.get("execute_allowed", False))
            and not bool(approval.get("approved_for_execute", False))
            and expected_digest == actual_digest
            and executable_count == 0
            and live_payload_count == 0
        )
        else "blocked",
        "approval_recorded": str(approval.get("status") or "") == "recorded",
        "execute_allowed": bool(approval.get("execute_allowed", False)),
        "approved_for_execute": bool(approval.get("approved_for_execute", False)),
        "provider_payload_digest_consistent": expected_digest == actual_digest,
        "provider_payloads_non_executable": executable_count == 0,
        "provider_payloads_without_live_payloads": live_payload_count == 0,
        "candidate_payloads_require_review": int(candidate_summary.get("candidate_unverified_field_count") or 0) > 0
        or int(candidate_summary.get("candidate_draft_count") or 0) > 0,
        "execution_enabled": False,
        "external_api_calls": 0,
        "actions": [],
    }


def _provider_payload_resolution(
    *,
    approval: dict[str, Any],
    db_path: str | Path | None,
) -> dict[str, Any]:
    drafts = _provider_payload_drafts(approval)
    if not drafts:
        return {
            "status": "no_provider_payload_drafts",
            "draft_count": 0,
            "lookup_count": 0,
            "resolved_count": 0,
            "unresolved_count": 0,
            "unresolved_placeholders": [],
            "resolved_provider_payload_drafts": [],
            "execution_enabled": False,
            "external_api_calls": 0,
            "actions": [],
        }
    if db_path is None:
        return {
            "status": "not_resolved_missing_db_path",
            "draft_count": len(drafts),
            "lookup_count": 0,
            "resolved_count": 0,
            "unresolved_count": 0,
            "unresolved_placeholders": [],
            "resolved_provider_payload_drafts": [],
            "execution_enabled": False,
            "external_api_calls": 0,
            "actions": [],
        }
    return resolve_provider_payload_drafts(db_path=db_path, provider_payload_drafts=drafts)


def _contains_lookup_placeholder(value: Any) -> bool:
    if isinstance(value, str):
        return value.startswith("<lookup:") and value.endswith(">")
    if isinstance(value, dict):
        return any(_contains_lookup_placeholder(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_lookup_placeholder(item) for item in value)
    return False


def _lookup_placeholder_count(value: Any) -> int:
    if isinstance(value, str):
        return 1 if _contains_lookup_placeholder(value) else 0
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
        "unresolved_lookup_placeholder_count": sum(
            _lookup_placeholder_count(draft.get("payload") if isinstance(draft.get("payload"), dict) else {})
            for draft in drafts
        ),
    }


def _drafts_by_operation(drafts: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    return {
        operation: [draft for draft in drafts if str(draft.get("operation") or "") == operation]
        for operation in _PAYLOAD_REVIEW_OPERATIONS
    }


def _resolved_payload_contract(
    *,
    resolved_provider_payload_drafts: list[dict[str, Any]],
    execution_plan: dict[str, Any],
) -> dict[str, Any]:
    unresolved_lookup_count = 0
    executable_draft_count = 0
    live_payload_count = len(execution_plan.get("live_api_payloads") or [])
    for draft in resolved_provider_payload_drafts:
        if not isinstance(draft, dict):
            continue
        payload = draft.get("payload") if isinstance(draft.get("payload"), dict) else {}
        unresolved_lookup_count += sum(
            1 for value in payload.values() if _contains_lookup_placeholder(value)
        )
        if bool(draft.get("executable", False)):
            executable_draft_count += 1
        if bool(draft.get("live_api_payload", False)):
            live_payload_count += 1
    violations: list[str] = []
    if unresolved_lookup_count:
        violations.append("resolved provider payload drafts must not contain lookup placeholders")
    if executable_draft_count:
        violations.append("resolved provider payload drafts must not be executable")
    if live_payload_count:
        violations.append("create execute must not contain live payloads")
    return {
        "status": "passed" if not violations else "blocked",
        "checked_draft_count": len(resolved_provider_payload_drafts),
        "unresolved_lookup_count": unresolved_lookup_count,
        "executable_draft_count": executable_draft_count,
        "live_payload_count": live_payload_count,
        "violation_count": len(violations),
        "violations": violations,
        "execution_enabled": False,
        "external_api_calls": 0,
        "actions": [],
    }


def _chain_boundary_contract(
    *,
    approval: dict[str, Any],
    approval_boundary: dict[str, Any],
    provider_id_ledger_gate: dict[str, Any],
    provider_payload_resolution: dict[str, Any],
    resolved_payload_contract: dict[str, Any],
    resolved_provider_payload_drafts: list[dict[str, Any]],
) -> dict[str, Any]:
    total_summary = _payload_operation_summary(resolved_provider_payload_drafts)
    unresolved_count = int(resolved_payload_contract.get("unresolved_lookup_count") or 0)
    return {
        "status": "hard_blocked_missing_provider_ids" if unresolved_count else "hard_blocked_review_only",
        "approval_recorded": str(approval.get("status") or "") == "recorded",
        "approval_is_record_only": not bool(approval.get("execute_allowed", False))
        and not bool(approval.get("approved_for_execute", False)),
        "execute_hard_blocked": True,
        "execution_enabled_false": True,
        "external_api_calls_zero": True,
        "actions_empty": True,
        "no_live_payloads": int(total_summary["live_payload_count"]) == 0
        and int(resolved_payload_contract.get("live_payload_count") or 0) == 0,
        "no_executable_payloads": int(total_summary["executable_true_count"]) == 0
        and int(resolved_payload_contract.get("executable_draft_count") or 0) == 0,
        "payload_digest_consistent": bool(approval_boundary.get("provider_payload_digest_consistent", False)),
        "resolved_payload_contract": str(resolved_payload_contract.get("status") or ""),
        "provider_payload_resolution": str(provider_payload_resolution.get("status") or ""),
        "provider_id_ledger_gate": str(provider_id_ledger_gate.get("status") or ""),
        "approved_for_execute": False,
        "external_api_calls": 0,
        "actions": [],
    }


def _execute_review_pack(
    *,
    approval: dict[str, Any],
    resolved_provider_payload_drafts: list[dict[str, Any]],
    resolved_payload_contract: dict[str, Any],
) -> dict[str, Any]:
    drafts_by_operation = _drafts_by_operation(resolved_provider_payload_drafts)
    by_operation = {
        operation: _payload_operation_summary(operation_drafts)
        for operation, operation_drafts in drafts_by_operation.items()
    }
    total_summary = _payload_operation_summary(resolved_provider_payload_drafts)
    payload_counts = {operation: int(summary["payload_count"]) for operation, summary in by_operation.items()}
    payload_counts["total"] = int(total_summary["payload_count"])
    unresolved_count = int(resolved_payload_contract.get("unresolved_lookup_count") or 0)
    status = "hard_blocked_missing_provider_ids" if unresolved_count else "hard_blocked_ready_for_manual_review"
    if unresolved_count:
        plain_language = (
            "execute 只是最终本地复核边界，不会执行真实创建；"
            f"{unresolved_count} 个 lookup 占位符仍未解析。"
        )
    else:
        plain_language = (
            "execute 只是最终本地复核边界，不会执行真实创建；"
            f"{int(total_summary['payload_count'])} 个 resolved payload 草稿可人工核对。"
        )
    return {
        "drafts_by_operation": drafts_by_operation,
        "manual_review_summary": {
            "status": status,
            "plain_language": plain_language,
            "payload_counts": payload_counts,
            "checks": {
                "execute_hard_blocked": True,
                "approval_is_record_only": not bool(approval.get("execute_allowed", False))
                and not bool(approval.get("approved_for_execute", False)),
                "all_payloads_executable_false": int(total_summary["executable_true_count"]) == 0,
                "live_payload_count_zero": int(total_summary["live_payload_count"]) == 0,
                "actions_empty": True,
                "external_api_calls_zero": True,
                "unresolved_lookup_placeholders_present": unresolved_count > 0,
            },
            "counts": total_summary,
            "by_operation": by_operation,
            "execution_enabled": False,
            "external_api_calls": 0,
            "actions": [],
        },
    }


def _execute_review_summary(
    *,
    summary: dict[str, Any],
    provider_id_ledger_gate: dict[str, Any],
    provider_payload_resolution: dict[str, Any],
    resolved_payload_contract: dict[str, Any],
) -> dict[str, Any]:
    unresolved_lookup_count = int(resolved_payload_contract.get("unresolved_lookup_count") or 0)
    resolved_draft_count = int(resolved_payload_contract.get("checked_draft_count") or 0)
    if unresolved_lookup_count:
        status = "blocked_missing_provider_ids"
        plain_language = (
            f"真实创建仍然硬阻断；已解析草稿仍有 {unresolved_lookup_count} 个 lookup "
            "占位未解析，需要先登记平台返回的 project_id/promotion_id。"
        )
        human_next_steps = [
            "先确认项目和单元真实创建返回的 project_id/promotion_id 已写入本地 ID 台账。",
            "重新运行 create_execute，只复核 resolved_payload_contract，不执行真实创建。",
        ]
    else:
        status = "ready_for_manual_review"
        plain_language = (
            f"真实创建仍然硬阻断；{resolved_draft_count} 个平台 payload 草稿已完成本地 ID 解析，"
            "可人工复核字段，但不会执行真实创建。"
        )
        human_next_steps = [
            "人工复核 resolved_provider_payload_drafts 的账户、项目ID、单元ID、预算和素材。",
            "继续保持 create_execute 硬阻断，等待单独批准的真实执行阶段。",
        ]
    return {
        "status": status,
        "plain_language": plain_language,
        "checks": {
            "execute_hard_blocked": True,
            "external_api_calls_zero": True,
            "provider_payload_resolution": str(provider_payload_resolution.get("status") or ""),
            "resolved_payload_contract": str(resolved_payload_contract.get("status") or ""),
            "provider_id_ledger_gate": str(provider_id_ledger_gate.get("status") or ""),
        },
        "counts": {
            "project_count": int(summary.get("project_count") or 0),
            "unit_count": int(summary.get("unit_count") or 0),
            "material_count": int(summary.get("material_count") or 0),
            "resolved_draft_count": resolved_draft_count,
            "unresolved_lookup_count": unresolved_lookup_count,
        },
        "human_next_steps": human_next_steps,
        "execution_enabled": False,
        "external_api_calls": 0,
        "actions": [],
    }


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
    approval_boundary = _approval_boundary_contract(approval)
    if str(approval_boundary.get("status") or "") != "passed":
        violations.append("create approval boundary contract must pass before execute review")
    violations.extend(str(item) for item in approval.get("violations") or [])
    return violations


def build_create_execute(
    *,
    create_approval_artifact: dict[str, Any],
    policy: dict[str, Any],
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    violations = _violations(create_approval_artifact, policy)
    summary = _summary(create_approval_artifact)
    payload_schema = disabled_create_payload_schema(policy)
    provider_id_requirements = _provider_id_ledger_requirements(create_approval_artifact)
    provider_id_gate = _provider_id_ledger_gate(provider_id_requirements)
    payload_resolution = _provider_payload_resolution(approval=create_approval_artifact, db_path=db_path)
    resolved_provider_payload_drafts = payload_resolution.get("resolved_provider_payload_drafts")
    if not isinstance(resolved_provider_payload_drafts, list):
        resolved_provider_payload_drafts = []
    execution_plan = _execution_plan(summary, policy, provider_id_gate)
    resolved_payload_contract = _resolved_payload_contract(
        resolved_provider_payload_drafts=resolved_provider_payload_drafts,
        execution_plan=execution_plan,
    )
    execute_review_summary = _execute_review_summary(
        summary=summary,
        provider_id_ledger_gate=provider_id_gate,
        provider_payload_resolution=payload_resolution,
        resolved_payload_contract=resolved_payload_contract,
    )
    approval_boundary = _approval_boundary_contract(create_approval_artifact)
    chain_boundary = _chain_boundary_contract(
        approval=create_approval_artifact,
        approval_boundary=approval_boundary,
        provider_id_ledger_gate=provider_id_gate,
        provider_payload_resolution=payload_resolution,
        resolved_payload_contract=resolved_payload_contract,
        resolved_provider_payload_drafts=resolved_provider_payload_drafts,
    )
    execute_review_pack = _execute_review_pack(
        approval=create_approval_artifact,
        resolved_provider_payload_drafts=resolved_provider_payload_drafts,
        resolved_payload_contract=resolved_payload_contract,
    )
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
        "execution_plan": execution_plan,
        "provider_field_map_digest": _provider_field_map_digest(create_approval_artifact),
        "provider_payload_draft_digest": _provider_payload_draft_digest(create_approval_artifact),
        "approval_boundary_contract": approval_boundary,
        "provider_payload_review_summary": _provider_payload_review_summary(create_approval_artifact),
        "provider_payload_resolution": {
            key: value
            for key, value in payload_resolution.items()
            if key != "resolved_provider_payload_drafts"
        },
        "resolved_provider_payload_drafts": resolved_provider_payload_drafts,
        "resolved_payload_contract": resolved_payload_contract,
        "execute_review_summary": execute_review_summary,
        "chain_boundary_contract": chain_boundary,
        "execute_review_pack": execute_review_pack,
        "provider_readiness_contract": _provider_readiness(create_approval_artifact),
        "provider_id_ledger_requirements": provider_id_requirements,
        "provider_id_ledger_gate": provider_id_gate,
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
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    cfg = _execute_config(request)
    create_approval_artifact = cfg.get("create_approval_artifact")
    if not isinstance(create_approval_artifact, dict):
        raise ValueError("create execute requires create_approval_artifact")
    policy = cfg.get("policy") if isinstance(cfg.get("policy"), dict) else {}
    payload = build_create_execute(create_approval_artifact=create_approval_artifact, policy=policy, db_path=db_path)
    approval_path = cfg.get("create_approval_artifact_path")
    if str(approval_path or "").strip():
        payload["lineage"]["create_approval"]["artifact_path"] = str(approval_path)
    artifact_path = write_run_artifact(runs_dir, "create_execute", payload)
    return {**payload, "artifact_path": str(artifact_path)}
