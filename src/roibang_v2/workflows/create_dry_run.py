from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from roibang_v2.runs import write_run_artifact
from roibang_v2.workflows.create_lineage import (
    assert_same_create_plan,
    create_lineage_ref,
    create_plan_payload,
    create_ref,
)
from roibang_v2.workflows.create_payload_schema import (
    CREATE_PAYLOAD_SCHEMA_VERSION,
    disabled_create_payload_schema,
    validate_create_payload_contract,
)
from roibang_v2.workflows.create_provider_adapter import (
    build_provider_payload_drafts,
    disabled_provider_adapter,
    provider_adapter_contract,
)
from roibang_v2.workflows.create_provider_field_map import (
    load_provider_field_map,
    provider_field_map_contract,
    provider_field_map_digest,
)
from roibang_v2.workflows.create_provider_readiness import provider_readiness_contract


def _dry_run_config(request: dict[str, Any]) -> dict[str, Any]:
    value = request.get("create_dry_run")
    return dict(value) if isinstance(value, dict) else dict(request)


def _int_value(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _policy_limit(policy: dict[str, Any], key: str, default: int) -> int:
    return max(_int_value(policy.get(key), default), 0)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _projects(plan: dict[str, Any]) -> list[dict[str, Any]]:
    strategy = plan.get("strategy") if isinstance(plan.get("strategy"), dict) else {}
    rows = strategy.get("projects")
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _idempotency_key(scope: str, source_fields: dict[str, Any]) -> dict[str, Any]:
    canonical = json.dumps(source_fields, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {
        "scope": scope,
        "algorithm": "sha256",
        "value": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "source_fields": {key: str(value) for key, value in source_fields.items()},
    }


def _with_idempotency(plan: dict[str, Any], project: dict[str, Any]) -> dict[str, Any]:
    plan_fields = {
        "plan_id": str(plan.get("plan_id") or ""),
        "request_id": str(plan.get("request_id") or ""),
        "target_date": str(plan.get("target_date") or ""),
        "advertiser_id": str(project.get("advertiser_id") or ""),
        "project_key": str(project.get("project_key") or ""),
    }
    units: list[dict[str, Any]] = []
    for unit in project.get("units") if isinstance(project.get("units"), list) else []:
        if not isinstance(unit, dict):
            continue
        unit_fields = {**plan_fields, "unit_key": str(unit.get("unit_key") or "")}
        project_key = str(project.get("project_key") or "")
        unit_key = str(unit.get("unit_key") or "")
        project_id_placeholder = f"<lookup:{project_key}>"
        promotion_id_placeholder = f"<lookup:{unit_key}>"
        materials: list[dict[str, Any]] = []
        for material in unit.get("materials") if isinstance(unit.get("materials"), list) else []:
            if not isinstance(material, dict):
                continue
            material_fields = {**unit_fields, "material_id": str(material.get("material_id") or "")}
            materials.append(
                {
                    **material,
                    "project_id": project_id_placeholder,
                    "promotion_id": promotion_id_placeholder,
                    "idempotency_key": _idempotency_key("bind_material", material_fields),
                }
            )
        units.append(
            {
                **unit,
                "project_id": project_id_placeholder,
                "promotion_id": promotion_id_placeholder,
                "materials": materials,
                "idempotency_key": _idempotency_key("create_unit", unit_fields),
            }
        )
    return {
        **project,
        "units": units,
        "idempotency_key": _idempotency_key("create_project", plan_fields),
    }


def _project_task(plan: dict[str, Any], project: dict[str, Any], payload_schema: dict[str, Any]) -> dict[str, Any]:
    prepared = _with_idempotency(plan, project)
    return {
        "task_type": "create_project_candidate",
        "advertiser_id": str(prepared.get("advertiser_id") or ""),
        "project_key": str(prepared.get("project_key") or ""),
        "project_name": str(prepared.get("project_name") or ""),
        "project_type": str(prepared.get("project_type") or ""),
        "daily_budget": float(prepared.get("daily_budget") or 0),
        "field_defaults": prepared.get("field_defaults") if isinstance(prepared.get("field_defaults"), dict) else {},
        "units": prepared.get("units") if isinstance(prepared.get("units"), list) else [],
        "executable": False,
        "payload_schema_ref": CREATE_PAYLOAD_SCHEMA_VERSION,
        "idempotency_key": prepared["idempotency_key"],
        "redacted_payload_drafts": _task_payload_drafts(prepared, payload_schema=payload_schema),
        "live_api_payloads": [],
        "allowed_phase1_output": "dry_run_only",
    }


def _task_payload_drafts(project: dict[str, Any], *, payload_schema: dict[str, Any]) -> list[dict[str, Any]]:
    endpoints = payload_schema.get("endpoints") if isinstance(payload_schema.get("endpoints"), dict) else {}
    drafts = [
        {
            "operation": "create_project",
            "transport": "disabled_schema_only",
            "executable": False,
            "idempotency_key": str(project.get("idempotency_key", {}).get("value") or ""),
            "endpoint": str(endpoints.get("create_project") or ""),
            "payload": {
                "advertiser_id": str(project.get("advertiser_id") or ""),
                "project_name": str(project.get("project_name") or ""),
                "daily_budget": float(project.get("daily_budget") or 0),
                "field_defaults": project.get("field_defaults") if isinstance(project.get("field_defaults"), dict) else {},
            },
        }
    ]
    units = project.get("units") if isinstance(project.get("units"), list) else []
    for unit in [row for row in units if isinstance(row, dict)]:
        drafts.append(
            {
                "operation": "create_unit",
                "transport": "disabled_schema_only",
                "executable": False,
                "idempotency_key": str(unit.get("idempotency_key", {}).get("value") or ""),
                "endpoint": str(endpoints.get("create_unit") or ""),
                "payload": {
                    "advertiser_id": str(project.get("advertiser_id") or ""),
                    "project_key": str(project.get("project_key") or ""),
                    "project_id": str(unit.get("project_id") or ""),
                    "unit_key": str(unit.get("unit_key") or ""),
                    "promotion_name": str(unit.get("promotion_name") or ""),
                    "field_defaults": project.get("field_defaults") if isinstance(project.get("field_defaults"), dict) else {},
                },
            }
        )
    for unit in [row for row in units if isinstance(row, dict)]:
        materials = unit.get("materials") if isinstance(unit.get("materials"), list) else []
        for material in [row for row in materials if isinstance(row, dict)]:
            drafts.append(
                {
                    "operation": "bind_material",
                    "transport": "disabled_schema_only",
                    "executable": False,
                    "idempotency_key": str(material.get("idempotency_key", {}).get("value") or ""),
                    "endpoint": str(endpoints.get("bind_material") or ""),
                    "payload": {
                        "advertiser_id": str(project.get("advertiser_id") or ""),
                        "project_key": str(project.get("project_key") or ""),
                        "project_id": str(material.get("project_id") or ""),
                        "unit_key": str(unit.get("unit_key") or ""),
                        "promotion_id": str(material.get("promotion_id") or ""),
                        "material_id": str(material.get("material_id") or ""),
                        "source_video_id": str(material.get("source_video_id") or ""),
                    },
                }
            )
    return drafts


def _top_level_redacted_payload_drafts(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    drafts: list[dict[str, Any]] = []
    for task in tasks:
        material_ids = {
            str(material.get("material_id") or "")
            for unit in (task.get("units") if isinstance(task.get("units"), list) else [])
            if isinstance(unit, dict)
            for material in (unit.get("materials") if isinstance(unit.get("materials"), list) else [])
            if isinstance(material, dict) and str(material.get("material_id") or "")
        }
        drafts.append(
            {
                "operation": "create_project",
                "transport": "disabled_schema_only",
                "executable": False,
                "idempotency_key": str(task.get("idempotency_key", {}).get("value") or ""),
                "endpoint": "",
                "payload": {
                    "advertiser_id": str(task.get("advertiser_id") or ""),
                    "project_key": str(task.get("project_key") or ""),
                    "project_name": str(task.get("project_name") or ""),
                    "unit_count": len(task.get("units") if isinstance(task.get("units"), list) else []),
                    "materials": f"<redacted:{len(material_ids)} material ids>",
                },
            }
        )
    return drafts


def _payload_draft_contract(tasks: list[dict[str, Any]], redacted_payload_drafts: list[dict[str, Any]]) -> dict[str, Any]:
    task_drafts = [
        draft
        for task in tasks
        for draft in (task.get("redacted_payload_drafts") if isinstance(task.get("redacted_payload_drafts"), list) else [])
        if isinstance(draft, dict)
    ]
    return {
        "status": "passed",
        "draft_count": len(task_drafts),
        "live_payload_count": sum(
            len(task.get("live_api_payloads") if isinstance(task.get("live_api_payloads"), list) else [])
            for task in tasks
        ),
        "executable_draft_count": sum(1 for draft in task_drafts + redacted_payload_drafts if bool(draft.get("executable", False))),
        "redacted": True,
    }


def _idempotency_contract(tasks: list[dict[str, Any]]) -> dict[str, Any]:
    seen: dict[str, str] = {}
    duplicates: list[dict[str, str]] = []
    for scope, key in _iter_idempotency_keys(tasks):
        value = str(key.get("value") or "")
        if value in seen:
            duplicates.append({"scope": scope, "value": value})
        else:
            seen[value] = scope
    return {
        "status": "passed" if not duplicates else "failed",
        "checked_key_count": len(list(_iter_idempotency_keys(tasks))),
        "duplicate_keys": duplicates,
    }


def _provider_payload_draft_digest(provider_payload_drafts: list[dict[str, Any]]) -> dict[str, Any]:
    canonical = json.dumps(provider_payload_drafts, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {
        "algorithm": "sha256",
        "value": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "provider_payload_draft_count": len(provider_payload_drafts),
    }


def _unique_rows(rows: list[dict[str, str]], key_fields: tuple[str, ...]) -> list[dict[str, str]]:
    seen: set[tuple[str, ...]] = set()
    result: list[dict[str, str]] = []
    for row in rows:
        key = tuple(str(row.get(field) or "") for field in key_fields)
        if key in seen:
            continue
        seen.add(key)
        result.append(row)
    return result


def _provider_id_ledger_requirements(tasks: list[dict[str, Any]]) -> dict[str, Any]:
    produced_projects: list[dict[str, str]] = []
    produced_units: list[dict[str, str]] = []
    required_before_units: list[dict[str, str]] = []
    required_before_materials: list[dict[str, str]] = []
    for task in tasks:
        project_key = str(task.get("project_key") or "")
        if not project_key:
            continue
        produced_projects.append(
            {
                "entity_type": "project",
                "local_key": project_key,
                "provider_id_source": "create_project_response",
            }
        )
        units = task.get("units") if isinstance(task.get("units"), list) else []
        for unit in [row for row in units if isinstance(row, dict)]:
            unit_key = str(unit.get("unit_key") or "")
            project_placeholder = str(unit.get("project_id") or "")
            if project_placeholder:
                required_before_units.append(
                    {
                        "field": "project_id",
                        "entity_type": "project",
                        "local_key": project_key,
                        "placeholder": project_placeholder,
                    }
                )
            if unit_key:
                produced_units.append(
                    {
                        "entity_type": "promotion",
                        "local_key": unit_key,
                        "parent_local_key": project_key,
                        "provider_id_source": "create_unit_response",
                    }
                )
            materials = unit.get("materials") if isinstance(unit.get("materials"), list) else []
            for material in [row for row in materials if isinstance(row, dict)]:
                material_project_placeholder = str(material.get("project_id") or "")
                material_promotion_placeholder = str(material.get("promotion_id") or "")
                if material_project_placeholder:
                    required_before_materials.append(
                        {
                            "field": "project_id",
                            "entity_type": "project",
                            "local_key": project_key,
                            "placeholder": material_project_placeholder,
                        }
                    )
                if unit_key and material_promotion_placeholder:
                    required_before_materials.append(
                        {
                            "field": "promotion_id",
                            "entity_type": "promotion",
                            "local_key": unit_key,
                            "placeholder": material_promotion_placeholder,
                        }
                    )
    return {
        "status": "planned",
        "produced_by_create_project": _unique_rows(produced_projects, ("entity_type", "local_key")),
        "produced_by_create_unit": _unique_rows(produced_units, ("entity_type", "local_key")),
        "required_before_create_unit": _unique_rows(
            required_before_units,
            ("field", "entity_type", "local_key", "placeholder"),
        ),
        "required_before_bind_material": _unique_rows(
            required_before_materials,
            ("field", "entity_type", "local_key", "placeholder"),
        ),
        "execution_enabled": False,
        "external_api_calls": 0,
        "actions": [],
    }


def _provider_field_map_check_ref(artifact: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(artifact, dict):
        return {}
    summary = artifact.get("summary") if isinstance(artifact.get("summary"), dict) else {}
    return {
        "workflow": str(artifact.get("workflow") or ""),
        "phase": str(artifact.get("phase") or ""),
        "status": str(artifact.get("status") or ""),
        "provider": str(summary.get("provider") or ""),
        "field_map_path": str(summary.get("field_map_path") or ""),
    }


def _provider_field_map_check_violations(
    *,
    check_artifact: dict[str, Any] | None,
    field_map_contract: dict[str, Any],
    field_map_digest: dict[str, Any],
    readiness_contract: dict[str, Any],
) -> list[str]:
    if not isinstance(check_artifact, dict):
        return []
    violations: list[str] = []
    if str(check_artifact.get("workflow") or "") != "create_provider_field_map_check":
        violations.append("provider field map check artifact workflow must be create_provider_field_map_check")
    if bool(check_artifact.get("execution_enabled", False)):
        violations.append("provider field map check execution_enabled must be false")
    if int(check_artifact.get("external_api_calls") or 0) != 0:
        violations.append("provider field map check external_api_calls must be 0")
    if check_artifact.get("actions"):
        violations.append("provider field map check actions must be empty")
    check_contract = check_artifact.get("provider_field_map_contract")
    if not isinstance(check_contract, dict) or check_contract != field_map_contract:
        violations.append("provider field map check contract must match dry-run field map contract")
    check_digest = check_artifact.get("provider_field_map_digest")
    if not isinstance(check_digest, dict) or check_digest != field_map_digest:
        violations.append("provider field map check digest must match dry-run field map digest")
    check_readiness = check_artifact.get("provider_readiness_contract")
    if not isinstance(check_readiness, dict) or check_readiness != readiness_contract:
        violations.append("provider field map check readiness must match dry-run readiness")
    violations.extend(str(item) for item in check_artifact.get("violations") or [])
    return violations


def _iter_idempotency_keys(tasks: list[dict[str, Any]]):
    for task in tasks:
        key = task.get("idempotency_key")
        if isinstance(key, dict):
            yield str(key.get("scope") or ""), key
        units = task.get("units") if isinstance(task.get("units"), list) else []
        for unit in [row for row in units if isinstance(row, dict)]:
            unit_key = unit.get("idempotency_key")
            if isinstance(unit_key, dict):
                yield str(unit_key.get("scope") or ""), unit_key
            materials = unit.get("materials") if isinstance(unit.get("materials"), list) else []
            for material in [row for row in materials if isinstance(row, dict)]:
                material_key = material.get("idempotency_key")
                if isinstance(material_key, dict):
                    yield str(material_key.get("scope") or ""), material_key


def _record_idempotency_ledger(*, db_path: str | Path, tasks: list[dict[str, Any]]) -> dict[str, Any]:
    now = _now_iso()
    records = list(_iter_idempotency_keys(tasks))
    existing_count = 0
    with sqlite3.connect(db_path) as conn:
        for scope, key in records:
            value = str(key.get("value") or "")
            fields = key.get("source_fields") if isinstance(key.get("source_fields"), dict) else {}
            existing = conn.execute(
                "SELECT 1 FROM create_idempotency_keys WHERE idempotency_key = ?",
                (value,),
            ).fetchone()
            if existing:
                existing_count += 1
            conn.execute(
                """
                INSERT INTO create_idempotency_keys (
                  idempotency_key, scope, plan_id, request_id, target_date,
                  advertiser_id, project_key, unit_key, material_id,
                  phase, status, source_workflow, execution_enabled,
                  payload_json, first_seen_at, last_seen_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(idempotency_key) DO UPDATE SET
                  scope = excluded.scope,
                  plan_id = excluded.plan_id,
                  request_id = excluded.request_id,
                  target_date = excluded.target_date,
                  advertiser_id = excluded.advertiser_id,
                  project_key = excluded.project_key,
                  unit_key = excluded.unit_key,
                  material_id = excluded.material_id,
                  phase = excluded.phase,
                  source_workflow = excluded.source_workflow,
                  execution_enabled = excluded.execution_enabled,
                  payload_json = excluded.payload_json,
                  last_seen_at = excluded.last_seen_at
                """,
                (
                    value,
                    scope,
                    str(fields.get("plan_id") or ""),
                    str(fields.get("request_id") or ""),
                    str(fields.get("target_date") or ""),
                    str(fields.get("advertiser_id") or ""),
                    str(fields.get("project_key") or ""),
                    str(fields.get("unit_key") or ""),
                    str(fields.get("material_id") or ""),
                    "phase1",
                    "planned",
                    "create_dry_run",
                    0,
                    json.dumps(key, ensure_ascii=False, sort_keys=True),
                    now,
                    now,
                ),
            )
    return {
        "status": "recorded",
        "recorded_key_count": len(records),
        "existing_key_count": existing_count,
    }


def _violations(
    *,
    plan_ref: dict[str, Any],
    preflight: dict[str, Any],
    projects: list[dict[str, Any]],
    policy: dict[str, Any],
) -> list[str]:
    violations: list[str] = []
    preflight_ref = create_ref(workflow="create_preflight", artifact=preflight)
    preflight_plan_ref = create_lineage_ref(preflight, "create_strategy_plan")
    violations.extend(
        assert_same_create_plan(
            left_name="create strategy plan",
            left=plan_ref,
            right_name="create preflight",
            right=preflight_ref,
        )
    )
    violations.extend(
        assert_same_create_plan(
            left_name="create strategy plan",
            left=plan_ref,
            right_name="create preflight",
            right=preflight_plan_ref,
        )
    )
    if str(preflight.get("status") or "") != "passed" or not bool(preflight.get("ok", True)):
        violations.append("create preflight must pass before dry-run")
    if bool(preflight.get("approved_for_execute", False)):
        violations.append("create preflight must not approve execution in phase1")
    max_projects = _policy_limit(policy, "max_projects_per_dry_run", 50)
    max_units = _policy_limit(policy, "max_units_per_dry_run", 500)
    unit_count = sum(
        len(project.get("units") if isinstance(project.get("units"), list) else [])
        for project in projects
    )
    if len(projects) > max_projects:
        violations.append("dry-run project count exceeds policy limit")
    if unit_count > max_units:
        violations.append("dry-run unit count exceeds policy limit")
    return violations


def _summary(
    *,
    plan: dict[str, Any],
    projects: list[dict[str, Any]],
    violations: list[str],
) -> dict[str, Any]:
    units = [unit for project in projects for unit in project.get("units", []) if isinstance(unit, dict)]
    material_ids = {
        str(material.get("material_id") or "")
        for unit in units
        for material in unit.get("materials", [])
        if isinstance(material, dict) and str(material.get("material_id") or "")
    }
    return {
        "plan_id": str(plan.get("plan_id") or ""),
        "request_id": str(plan.get("request_id") or ""),
        "target_date": str(plan.get("target_date") or ""),
        "project_count": len(projects) if not violations else 0,
        "unit_count": len(units) if not violations else 0,
        "material_count": len(material_ids) if not violations else 0,
        "violation_count": len(violations),
    }


def build_create_dry_run(
    *,
    create_strategy_plan_artifact: dict[str, Any],
    create_preflight_artifact: dict[str, Any],
    create_provider_field_map_check_artifact: dict[str, Any] | None = None,
    policy: dict[str, Any],
) -> dict[str, Any]:
    plan = create_plan_payload(create_strategy_plan_artifact)
    projects = _projects(plan)
    plan_ref = create_ref(workflow="create_strategy_plan", artifact=create_strategy_plan_artifact)
    preflight_ref = create_ref(workflow="create_preflight", artifact=create_preflight_artifact)
    payload_schema = disabled_create_payload_schema(policy)
    candidate_tasks = [_project_task(plan, project, payload_schema) for project in projects]
    payload_contract = validate_create_payload_contract(projects=candidate_tasks, payload_schema=payload_schema)
    redacted_payload_drafts = _top_level_redacted_payload_drafts(candidate_tasks)
    payload_draft_contract = _payload_draft_contract(candidate_tasks, redacted_payload_drafts)
    provider_adapter = disabled_provider_adapter(policy)
    provider_field_map = load_provider_field_map(policy)
    field_map_contract = provider_field_map_contract(provider_field_map, policy)
    field_map_digest = provider_field_map_digest(provider_field_map)
    provider_payload_drafts = build_provider_payload_drafts(
        tasks=candidate_tasks,
        adapter=provider_adapter,
        provider_field_map=provider_field_map,
        provider_field_map_contract=field_map_contract,
    )
    provider_contract = provider_adapter_contract(
        adapter=provider_adapter,
        provider_payload_drafts=provider_payload_drafts,
        tasks=candidate_tasks,
    )
    provider_readiness = provider_readiness_contract(
        provider_adapter_contract=provider_contract,
        provider_field_map_contract=field_map_contract,
        payload_draft_contract=payload_draft_contract,
    )
    idempotency_contract = _idempotency_contract(candidate_tasks)
    violations = _violations(
        plan_ref=plan_ref,
        preflight=create_preflight_artifact,
        projects=projects,
        policy=policy,
    )
    violations.extend(
        _provider_field_map_check_violations(
            check_artifact=create_provider_field_map_check_artifact,
            field_map_contract=field_map_contract,
            field_map_digest=field_map_digest,
            readiness_contract=provider_readiness,
        )
    )
    violations.extend(str(item) for item in payload_contract["missing_fields"])
    violations.extend(
        f"duplicate idempotency key for {item['scope']}" for item in idempotency_contract["duplicate_keys"]
    )
    status = "simulated" if not violations else "blocked"
    emitted_provider_payload_drafts = provider_payload_drafts if not violations else []
    return {
        "ok": not violations,
        "workflow": "create_dry_run",
        "phase": "phase1",
        "execution_enabled": False,
        "external_api_calls": 0,
        "status": status,
        "summary": _summary(plan=plan, projects=projects, violations=violations),
        "lineage": {
            "create_strategy_plan": plan_ref,
            "create_preflight": preflight_ref,
            "create_provider_field_map_check": _provider_field_map_check_ref(
                create_provider_field_map_check_artifact
            ),
        },
        "policy": {
            "max_projects_per_dry_run": _policy_limit(policy, "max_projects_per_dry_run", 50),
            "max_units_per_dry_run": _policy_limit(policy, "max_units_per_dry_run", 500),
        },
        "payload_schema": payload_schema,
        "payload_contract": payload_contract,
        "payload_draft_contract": payload_draft_contract,
        "provider_adapter": provider_adapter,
        "provider_adapter_contract": provider_contract,
        "provider_field_map": provider_field_map,
        "provider_field_map_contract": field_map_contract,
        "provider_field_map_digest": field_map_digest,
        "provider_readiness_contract": provider_readiness,
        "provider_id_ledger_requirements": _provider_id_ledger_requirements(candidate_tasks),
        "provider_payload_draft_digest": _provider_payload_draft_digest(emitted_provider_payload_drafts),
        "provider_payload_drafts": emitted_provider_payload_drafts,
        "redacted_payload_drafts": redacted_payload_drafts if not violations else [],
        "idempotency_contract": idempotency_contract,
        "idempotency_ledger": {"status": "not_recorded", "recorded_key_count": 0, "existing_key_count": 0},
        "candidate_tasks": candidate_tasks if not violations else [],
        "violations": violations,
        "approved_for_execute": False,
        "actions": [],
    }


def run_create_dry_run_request(
    request: dict[str, Any],
    *,
    runs_dir: str | Path,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    cfg = _dry_run_config(request)
    plan_artifact = cfg.get("create_strategy_plan_artifact")
    preflight_artifact = cfg.get("create_preflight_artifact")
    field_map_check_artifact = cfg.get("create_provider_field_map_check_artifact")
    if not isinstance(plan_artifact, dict):
        raise ValueError("create dry-run requires create_strategy_plan_artifact")
    if not isinstance(preflight_artifact, dict):
        raise ValueError("create dry-run requires create_preflight_artifact")
    policy = cfg.get("policy") if isinstance(cfg.get("policy"), dict) else {}
    payload = build_create_dry_run(
        create_strategy_plan_artifact=plan_artifact,
        create_preflight_artifact=preflight_artifact,
        create_provider_field_map_check_artifact=field_map_check_artifact
        if isinstance(field_map_check_artifact, dict)
        else None,
        policy=policy,
    )
    payload["idempotency_ledger"] = (
        _record_idempotency_ledger(db_path=db_path, tasks=payload["candidate_tasks"])
        if db_path is not None and payload.get("candidate_tasks")
        else {"status": "not_recorded", "recorded_key_count": 0, "existing_key_count": 0}
    )
    plan_path = cfg.get("create_strategy_plan_artifact_path")
    if str(plan_path or "").strip():
        payload["lineage"]["create_strategy_plan"]["artifact_path"] = str(plan_path)
    preflight_path = cfg.get("create_preflight_artifact_path")
    if str(preflight_path or "").strip():
        payload["lineage"]["create_preflight"]["artifact_path"] = str(preflight_path)
    field_map_check_path = cfg.get("create_provider_field_map_check_artifact_path")
    if str(field_map_check_path or "").strip() and payload["lineage"].get("create_provider_field_map_check"):
        payload["lineage"]["create_provider_field_map_check"]["artifact_path"] = str(field_map_check_path)
    artifact_path = write_run_artifact(runs_dir, "create_dry_run", payload)
    return {**payload, "artifact_path": str(artifact_path)}
