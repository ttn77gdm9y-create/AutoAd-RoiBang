from __future__ import annotations

from pathlib import Path
from typing import Any

from roibang_v2.runs import write_run_artifact
from roibang_v2.workflows.create_lineage import (
    assert_same_create_plan,
    create_lineage_ref,
    create_plan_payload,
    create_ref,
)
from roibang_v2.workflows.create_provider_readiness import not_ready_provider_readiness_contract


def _snapshot_config(request: dict[str, Any]) -> dict[str, Any]:
    value = request.get("create_plan_snapshot")
    return dict(value) if isinstance(value, dict) else dict(request)


def _projects(plan: dict[str, Any]) -> list[dict[str, Any]]:
    strategy = plan.get("strategy") if isinstance(plan.get("strategy"), dict) else {}
    rows = strategy.get("projects")
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _units(project: dict[str, Any]) -> list[dict[str, Any]]:
    rows = project.get("units")
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _material_ids_from_project(project: dict[str, Any]) -> list[str]:
    material_ids = {
        str(material.get("material_id") or "")
        for unit in _units(project)
        for material in (unit.get("materials") if isinstance(unit.get("materials"), list) else [])
        if isinstance(material, dict) and str(material.get("material_id") or "")
    }
    return sorted(material_ids)


def _accounts(projects: list[dict[str, Any]], *, idempotency_by_project: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for project in projects:
        grouped.setdefault(str(project.get("advertiser_id") or ""), []).append(project)

    accounts: list[dict[str, Any]] = []
    for advertiser_id in sorted(grouped):
        account_projects = grouped[advertiser_id]
        account_material_ids = sorted(
            {
                material_id
                for project in account_projects
                for material_id in _material_ids_from_project(project)
            }
        )
        project_summaries = [
            {
                "project_key": str(project.get("project_key") or ""),
                "project_name": str(project.get("project_name") or ""),
                "idempotency_key": idempotency_by_project.get(str(project.get("project_key") or ""), {}),
                "unit_count": len(_units(project)),
                "material_ids": _material_ids_from_project(project),
            }
            for project in account_projects
        ]
        accounts.append(
            {
                "advertiser_id": advertiser_id,
                "project_count": len(account_projects),
                "unit_count": sum(len(_units(project)) for project in account_projects),
                "material_count": len(account_material_ids),
                "material_ids": account_material_ids,
                "projects": project_summaries,
            }
        )
    return accounts


def _summary(
    *,
    plan: dict[str, Any],
    accounts: list[dict[str, Any]],
    preflight: dict[str, Any],
    dry_run: dict[str, Any],
    approval: dict[str, Any],
    violations: list[str],
) -> dict[str, Any]:
    material_ids = {
        material_id
        for account in accounts
        for material_id in (account.get("material_ids") if isinstance(account.get("material_ids"), list) else [])
    }
    return {
        "plan_id": str(plan.get("plan_id") or ""),
        "request_id": str(plan.get("request_id") or ""),
        "target_date": str(plan.get("target_date") or ""),
        "account_count": len(accounts),
        "project_count": sum(int(account.get("project_count") or 0) for account in accounts),
        "unit_count": sum(int(account.get("unit_count") or 0) for account in accounts),
        "material_count": len(material_ids),
        "preflight_status": str(preflight.get("status") or ""),
        "dry_run_status": str(dry_run.get("status") or ""),
        "approval_status": str(approval.get("status") or ""),
        "policy_decision": str(approval.get("policy_decision") or ""),
        "violation_count": len(violations),
    }


def _violations(
    *,
    plan_ref: dict[str, Any],
    preflight: dict[str, Any],
    dry_run: dict[str, Any],
    approval: dict[str, Any],
) -> list[str]:
    violations: list[str] = []
    for name, ref in [
        ("create preflight", create_ref(workflow="create_preflight", artifact=preflight)),
        ("create dry-run", create_ref(workflow="create_dry_run", artifact=dry_run)),
        ("create approval", create_ref(workflow="create_approval", artifact=approval)),
        ("create dry-run lineage", create_lineage_ref(approval, "create_dry_run")),
    ]:
        violations.extend(
            assert_same_create_plan(
                left_name="create strategy plan",
                left=plan_ref,
                right_name=name,
                right=ref,
            )
        )
    violations.extend(str(item) for item in preflight.get("violations") or [])
    violations.extend(str(item) for item in dry_run.get("violations") or [])
    violations.extend(str(item) for item in approval.get("violations") or [])
    return violations


def _idempotency_by_project(dry_run: dict[str, Any]) -> dict[str, dict[str, Any]]:
    tasks = dry_run.get("candidate_tasks") if isinstance(dry_run.get("candidate_tasks"), list) else []
    result: dict[str, dict[str, Any]] = {}
    for task in tasks:
        if not isinstance(task, dict):
            continue
        project_key = str(task.get("project_key") or "")
        idempotency_key = task.get("idempotency_key")
        if project_key and isinstance(idempotency_key, dict):
            result[project_key] = idempotency_key
    return result


def build_create_plan_snapshot(
    *,
    create_strategy_plan_artifact: dict[str, Any],
    create_preflight_artifact: dict[str, Any],
    create_dry_run_artifact: dict[str, Any],
    create_approval_artifact: dict[str, Any],
) -> dict[str, Any]:
    plan = create_plan_payload(create_strategy_plan_artifact)
    plan_ref = create_ref(workflow="create_strategy_plan", artifact=create_strategy_plan_artifact)
    projects = _projects(plan)
    violations = _violations(
        plan_ref=plan_ref,
        preflight=create_preflight_artifact,
        dry_run=create_dry_run_artifact,
        approval=create_approval_artifact,
    )
    accounts = _accounts(projects, idempotency_by_project=_idempotency_by_project(create_dry_run_artifact))
    return {
        "ok": not violations,
        "workflow": "create_plan_snapshot",
        "phase": "phase1",
        "execution_enabled": False,
        "external_api_calls": 0,
        "summary": _summary(
            plan=plan,
            accounts=accounts,
            preflight=create_preflight_artifact,
            dry_run=create_dry_run_artifact,
            approval=create_approval_artifact,
            violations=violations,
        ),
        "lineage": {
            "create_strategy_plan": plan_ref,
            "create_preflight": create_ref(workflow="create_preflight", artifact=create_preflight_artifact),
            "create_dry_run": create_ref(workflow="create_dry_run", artifact=create_dry_run_artifact),
            "create_approval": create_ref(workflow="create_approval", artifact=create_approval_artifact),
            "create_provider_field_map_check": create_lineage_ref(
                create_dry_run_artifact,
                "create_provider_field_map_check",
            ),
        },
        "candidate_task_digest": create_approval_artifact.get("candidate_task_digest")
        if isinstance(create_approval_artifact.get("candidate_task_digest"), dict)
        else {"algorithm": "sha256", "value": "", "candidate_task_count": 0},
        "payload_contract": create_dry_run_artifact.get("payload_contract")
        if isinstance(create_dry_run_artifact.get("payload_contract"), dict)
        else {"status": "unknown", "missing_fields": []},
        "payload_draft_contract": create_dry_run_artifact.get("payload_draft_contract")
        if isinstance(create_dry_run_artifact.get("payload_draft_contract"), dict)
        else {"status": "unknown", "draft_count": 0, "live_payload_count": 0},
        "provider_adapter_contract": create_dry_run_artifact.get("provider_adapter_contract")
        if isinstance(create_dry_run_artifact.get("provider_adapter_contract"), dict)
        else {"status": "unknown", "draft_count": 0, "live_payload_count": 0},
        "provider_field_map_contract": create_dry_run_artifact.get("provider_field_map_contract")
        if isinstance(create_dry_run_artifact.get("provider_field_map_contract"), dict)
        else {"status": "unknown", "field_count": 0, "verified_field_count": 0},
        "provider_field_map_digest": create_dry_run_artifact.get("provider_field_map_digest")
        if isinstance(create_dry_run_artifact.get("provider_field_map_digest"), dict)
        else {"algorithm": "sha256", "value": ""},
        "provider_payload_draft_digest": create_approval_artifact.get("provider_payload_draft_digest")
        if isinstance(create_approval_artifact.get("provider_payload_draft_digest"), dict)
        else {"algorithm": "sha256", "value": "", "provider_payload_draft_count": 0},
        "provider_readiness_contract": create_dry_run_artifact.get("provider_readiness_contract")
        if isinstance(create_dry_run_artifact.get("provider_readiness_contract"), dict)
        else not_ready_provider_readiness_contract(),
        "idempotency_contract": create_dry_run_artifact.get("idempotency_contract")
        if isinstance(create_dry_run_artifact.get("idempotency_contract"), dict)
        else {"status": "unknown", "duplicate_keys": []},
        "idempotency_ledger": create_dry_run_artifact.get("idempotency_ledger")
        if isinstance(create_dry_run_artifact.get("idempotency_ledger"), dict)
        else {"status": "unknown", "recorded_key_count": 0, "existing_key_count": 0},
        "accounts": accounts,
        "review_notes": [
            "phase1 snapshot is review-only",
            "no live API payloads or actions are included",
        ],
        "violations": violations,
        "actions": [],
    }


def run_create_plan_snapshot_request(
    request: dict[str, Any],
    *,
    runs_dir: str | Path,
) -> dict[str, Any]:
    cfg = _snapshot_config(request)
    plan = cfg.get("create_strategy_plan_artifact")
    preflight = cfg.get("create_preflight_artifact")
    dry_run = cfg.get("create_dry_run_artifact")
    approval = cfg.get("create_approval_artifact")
    if not isinstance(plan, dict):
        raise ValueError("create plan snapshot requires create_strategy_plan_artifact")
    if not isinstance(preflight, dict):
        raise ValueError("create plan snapshot requires create_preflight_artifact")
    if not isinstance(dry_run, dict):
        raise ValueError("create plan snapshot requires create_dry_run_artifact")
    if not isinstance(approval, dict):
        raise ValueError("create plan snapshot requires create_approval_artifact")
    payload = build_create_plan_snapshot(
        create_strategy_plan_artifact=plan,
        create_preflight_artifact=preflight,
        create_dry_run_artifact=dry_run,
        create_approval_artifact=approval,
    )
    artifact_path = write_run_artifact(runs_dir, "create_plan_snapshot", payload)
    return {**payload, "artifact_path": str(artifact_path)}
