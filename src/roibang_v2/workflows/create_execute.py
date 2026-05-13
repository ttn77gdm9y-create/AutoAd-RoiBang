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


def _execute_config(request: dict[str, Any]) -> dict[str, Any]:
    value = request.get("create_execute")
    return dict(value) if isinstance(value, dict) else dict(request)


def _dry_run_summary(dry_run: dict[str, Any]) -> dict[str, Any]:
    summary = dry_run.get("summary") if isinstance(dry_run.get("summary"), dict) else {}
    return {
        "plan_id": str(summary.get("plan_id") or ""),
        "request_id": str(summary.get("request_id") or ""),
        "target_date": str(summary.get("target_date") or ""),
        "project_count": int(summary.get("project_count") or 0),
        "unit_count": int(summary.get("unit_count") or 0),
        "material_count": int(summary.get("material_count") or 0),
        "source_status": str(dry_run.get("status") or ""),
    }


def _provider_id_ledger_requirements(source: dict[str, Any]) -> dict[str, Any]:
    requirements = source.get("provider_id_ledger_requirements")
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


def _candidate_task_digest_from_dry_run(dry_run: dict[str, Any]) -> dict[str, Any]:
    tasks = dry_run.get("candidate_tasks")
    rows = [task for task in tasks if isinstance(task, dict)] if isinstance(tasks, list) else []
    canonical = json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {
        "algorithm": "sha256",
        "value": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "candidate_task_count": len(rows),
    }


def _provider_readiness(source: dict[str, Any]) -> dict[str, Any]:
    contract = source.get("provider_readiness_contract")
    if isinstance(contract, dict):
        return contract
    return not_ready_provider_readiness_contract()


def _provider_field_map_digest(source: dict[str, Any]) -> dict[str, Any]:
    digest = source.get("provider_field_map_digest")
    if isinstance(digest, dict):
        return {
            "algorithm": str(digest.get("algorithm") or ""),
            "value": str(digest.get("value") or ""),
        }
    return {"algorithm": "sha256", "value": ""}


def _provider_payload_draft_digest(source: dict[str, Any]) -> dict[str, Any]:
    digest = source.get("provider_payload_draft_digest")
    if isinstance(digest, dict):
        return {
            "algorithm": str(digest.get("algorithm") or ""),
            "value": str(digest.get("value") or ""),
            "provider_payload_draft_count": int(digest.get("provider_payload_draft_count") or 0),
        }
    return {"algorithm": "sha256", "value": "", "provider_payload_draft_count": 0}


def _provider_payload_drafts(source: dict[str, Any]) -> list[dict[str, Any]]:
    drafts = source.get("provider_payload_drafts")
    return [draft for draft in drafts if isinstance(draft, dict)] if isinstance(drafts, list) else []


def _actual_provider_payload_draft_digest(drafts: list[dict[str, Any]]) -> dict[str, Any]:
    canonical = json.dumps(drafts, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {
        "algorithm": "sha256",
        "value": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "provider_payload_draft_count": len(drafts),
    }


def _provider_payload_review_summary(source: dict[str, Any]) -> dict[str, Any]:
    summary = source.get("provider_payload_review_summary")
    if isinstance(summary, dict):
        return summary
    drafts = _provider_payload_drafts(source)
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


def _provider_payload_resolution(
    *,
    source: dict[str, Any],
    db_path: str | Path | None,
) -> dict[str, Any]:
    drafts = _provider_payload_drafts(source)
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


def _dry_run_boundary_contract(dry_run: dict[str, Any]) -> dict[str, Any]:
    drafts = _provider_payload_drafts(dry_run)
    expected_digest = _provider_payload_draft_digest(dry_run)
    actual_digest = _actual_provider_payload_draft_digest(drafts)
    executable_count = sum(1 for draft in drafts if bool(draft.get("executable", False)))
    live_payload_count = sum(1 for draft in drafts if bool(draft.get("live_api_payload", False)))
    return {
        "status": "passed"
        if (
            str(dry_run.get("status") or "") == "simulated"
            and bool(dry_run.get("ok", True))
            and expected_digest == actual_digest
            and executable_count == 0
            and live_payload_count == 0
        )
        else "blocked",
        "dry_run_simulated": str(dry_run.get("status") or "") == "simulated",
        "provider_payload_digest_consistent": expected_digest == actual_digest,
        "provider_payloads_non_executable": executable_count == 0,
        "provider_payloads_without_live_payloads": live_payload_count == 0,
        "execution_enabled": False,
        "external_api_calls": 0,
        "actions": [],
    }


def _dry_run_violations(dry_run: dict[str, Any], policy: dict[str, Any]) -> list[str]:
    violations: list[str] = []
    violations.extend(_policy_violations(policy))
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
        violations.append("create dry-run must be simulated before execute review")
    if bool(dry_run.get("execution_enabled", False)):
        violations.append("create dry-run execution_enabled must be false")
    if int(dry_run.get("external_api_calls") or 0) != 0:
        violations.append("create dry-run external_api_calls must be 0")
    if dry_run.get("actions"):
        violations.append("create dry-run actions must be empty")
    if str(_dry_run_boundary_contract(dry_run).get("status") or "") != "passed":
        violations.append("create dry-run boundary contract must pass before execute review")
    violations.extend(str(item) for item in dry_run.get("violations") or [])
    return violations


def build_create_execute_from_dry_run(
    *,
    create_dry_run_artifact: dict[str, Any],
    policy: dict[str, Any],
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    violations = _dry_run_violations(create_dry_run_artifact, policy)
    summary = _dry_run_summary(create_dry_run_artifact)
    payload_schema = disabled_create_payload_schema(policy)
    provider_id_requirements = _provider_id_ledger_requirements(create_dry_run_artifact)
    provider_id_gate = _provider_id_ledger_gate(provider_id_requirements)
    payload_resolution = _provider_payload_resolution(source=create_dry_run_artifact, db_path=db_path)
    resolved_provider_payload_drafts = payload_resolution.get("resolved_provider_payload_drafts")
    if not isinstance(resolved_provider_payload_drafts, list):
        resolved_provider_payload_drafts = []
    execution_plan = _execution_plan(summary, policy, provider_id_gate)
    resolved_payload_contract = _resolved_payload_contract(
        resolved_provider_payload_drafts=resolved_provider_payload_drafts,
        execution_plan=execution_plan,
    )
    dry_run_boundary = _dry_run_boundary_contract(create_dry_run_artifact)
    execute_review_summary = _execute_review_summary(
        summary=summary,
        provider_id_ledger_gate=provider_id_gate,
        provider_payload_resolution=payload_resolution,
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
            "create_dry_run": create_ref(workflow="create_dry_run", artifact=create_dry_run_artifact),
            "create_strategy_plan": create_lineage_ref(create_dry_run_artifact, "create_strategy_plan"),
            "create_preflight": create_lineage_ref(create_dry_run_artifact, "create_preflight"),
            "create_provider_field_map_check": create_lineage_ref(
                create_dry_run_artifact,
                "create_provider_field_map_check",
            ),
        },
        "candidate_task_digest": _candidate_task_digest_from_dry_run(create_dry_run_artifact),
        "payload_schema": payload_schema,
        "execution_plan": execution_plan,
        "provider_field_map_digest": _provider_field_map_digest(create_dry_run_artifact),
        "provider_payload_draft_digest": _provider_payload_draft_digest(create_dry_run_artifact),
        "dry_run_boundary_contract": dry_run_boundary,
        "provider_payload_review_summary": _provider_payload_review_summary(create_dry_run_artifact),
        "provider_payload_resolution": {
            key: value
            for key, value in payload_resolution.items()
            if key != "resolved_provider_payload_drafts"
        },
        "resolved_provider_payload_drafts": resolved_provider_payload_drafts,
        "resolved_payload_contract": resolved_payload_contract,
        "execute_review_summary": execute_review_summary,
        "provider_readiness_contract": _provider_readiness(create_dry_run_artifact),
        "provider_id_ledger_requirements": provider_id_requirements,
        "provider_id_ledger_gate": provider_id_gate,
        "audit": _audit_config(policy),
        "violations": violations,
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
    create_dry_run_artifact = cfg.get("create_dry_run_artifact")
    if not isinstance(create_dry_run_artifact, dict):
        raise ValueError("create execute requires create_dry_run_artifact")
    policy = cfg.get("policy") if isinstance(cfg.get("policy"), dict) else {}
    payload = build_create_execute_from_dry_run(
        create_dry_run_artifact=create_dry_run_artifact,
        policy=policy,
        db_path=db_path,
    )
    dry_run_path = cfg.get("create_dry_run_artifact_path")
    if str(dry_run_path or "").strip():
        payload["lineage"]["create_dry_run"]["artifact_path"] = str(dry_run_path)
    artifact_path = write_run_artifact(runs_dir, "create_execute", payload)
    return {**payload, "artifact_path": str(artifact_path)}
