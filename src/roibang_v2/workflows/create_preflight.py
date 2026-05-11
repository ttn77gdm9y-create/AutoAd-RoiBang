from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Any

from roibang_v2.runs import write_run_artifact
from roibang_v2.workflows.create_lineage import create_plan_payload, create_ref


def _preflight_config(request: dict[str, Any]) -> dict[str, Any]:
    value = request.get("create_preflight")
    return dict(value) if isinstance(value, dict) else dict(request)


def _int_value(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _request(plan: dict[str, Any]) -> dict[str, Any]:
    value = plan.get("request")
    return value if isinstance(value, dict) else {}


def _projects(plan: dict[str, Any]) -> list[dict[str, Any]]:
    strategy = plan.get("strategy") if isinstance(plan.get("strategy"), dict) else {}
    rows = strategy.get("projects")
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _account_pool_contains(
    *,
    db_path: str | Path,
    advertiser_id: str,
    product: str,
    platform: str,
) -> bool:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT 1
            FROM account_pool
            WHERE advertiser_id = ?
              AND product = ?
              AND platform = ?
            LIMIT 1
            """,
            (advertiser_id, product, platform),
        ).fetchone()
    return row is not None


def _existing_project_names(
    *,
    db_path: str | Path,
    advertiser_id: str,
) -> set[str]:
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT name
            FROM projects
            WHERE advertiser_id = ?
            """,
            (advertiser_id,),
        ).fetchall()
    return {str(row[0]) for row in rows if str(row[0] or "").strip()}


def _shape_violations(plan: dict[str, Any]) -> list[str]:
    violations: list[str] = []
    if str(plan.get("phase") or "") != "phase1":
        violations.append("create strategy plan phase must be phase1")
    if bool(plan.get("execution_enabled", False)):
        violations.append("create strategy plan execution_enabled must be false")
    if int(plan.get("external_api_calls") or 0) != 0:
        violations.append("create strategy plan external_api_calls must be 0")
    if plan.get("actions"):
        violations.append("create strategy plan actions must be empty")
    if plan.get("live_api_payloads"):
        violations.append("create strategy plan live_api_payloads must be empty")
    return violations


def _required_field_defaults(policy: dict[str, Any]) -> list[str]:
    value = policy.get("required_field_defaults")
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _candidate_rows(*, db_path: str | Path, request: dict[str, Any]) -> dict[str, dict[str, Any]]:
    selected_materials = request.get("selected_materials")
    if isinstance(selected_materials, list) and selected_materials:
        rows = [dict(row) for row in selected_materials if isinstance(row, dict)]
        return {str(row.get("material_id") or ""): row for row in rows if str(row.get("material_id") or "").strip()}
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT material_id, material_type, review_status
            FROM product_source_material_candidates
            WHERE pool_key = ?
              AND product = ?
              AND source_advertiser_id = ?
            """,
            (
                str(request.get("pool_key") or ""),
                str(request.get("product") or ""),
                str(request.get("source_advertiser_id") or ""),
            ),
        ).fetchall()
    return {str(row["material_id"]): dict(row) for row in rows}


def _allowed_review_statuses(policy: dict[str, Any]) -> set[str]:
    filters = policy.get("candidate_filters") if isinstance(policy.get("candidate_filters"), dict) else {}
    value = filters.get("allowed_review_statuses")
    if not isinstance(value, list):
        return set()
    return {str(item).strip() for item in value if str(item).strip()}


def _expected_material_type(*, request: dict[str, Any], policy: dict[str, Any]) -> str:
    if str(policy.get("material_type") or "").strip():
        return str(policy.get("material_type") or "").strip()
    requirements = request.get("material_requirements") if isinstance(request.get("material_requirements"), dict) else {}
    return str(requirements.get("material_type") or "video")


def _dedupe_scope(*, request: dict[str, Any], policy: dict[str, Any]) -> str:
    if str(policy.get("dedupe_scope") or "").strip():
        return str(policy.get("dedupe_scope") or "").strip()
    requirements = request.get("material_requirements") if isinstance(request.get("material_requirements"), dict) else {}
    return str(requirements.get("dedupe_scope") or "request")


def _material_violations(*, request: dict[str, Any], projects: list[dict[str, Any]], policy: dict[str, Any]) -> list[str]:
    violations: list[str] = []
    candidates = _candidate_rows(db_path=policy["_db_path"], request=request)
    pool_key = str(request.get("pool_key") or "")
    expected_material_type = _expected_material_type(request=request, policy=policy)
    allowed_statuses = _allowed_review_statuses(policy)
    dedupe_scope = _dedupe_scope(request=request, policy=policy)
    seen_request_material_ids: set[str] = set()
    for project in projects:
        advertiser_id = str(project.get("advertiser_id") or "")
        seen_account_material_ids: set[str] = set()
        for unit in project.get("units") or []:
            if not isinstance(unit, dict):
                continue
            for material in unit.get("materials") or []:
                if not isinstance(material, dict):
                    continue
                material_id = str(material.get("material_id") or "")
                material_type = str(material.get("material_type") or "")
                if material_type != expected_material_type:
                    violations.append(f"material {material_id} type must be {expected_material_type}, got {material_type}")
                candidate = candidates.get(material_id)
                if not candidate:
                    violations.append(f"material {material_id} is not in candidate pool {pool_key}")
                elif allowed_statuses and str(candidate.get("review_status") or "") not in allowed_statuses:
                    violations.append(f"material {material_id} review_status is not allowed")
                if dedupe_scope == "request":
                    if material_id in seen_request_material_ids:
                        violations.append(f"material {material_id} is duplicated in request scope")
                    seen_request_material_ids.add(material_id)
                elif dedupe_scope == "account":
                    key = f"{advertiser_id}:{material_id}"
                    if key in seen_account_material_ids:
                        violations.append(f"material {material_id} is duplicated in account scope for {advertiser_id}")
                    seen_account_material_ids.add(key)
    return violations


def _project_violations(*, request: dict[str, Any], projects: list[dict[str, Any]], policy: dict[str, Any]) -> list[str]:
    violations: list[str] = []
    min_budget = float(policy.get("min_daily_budget") or 0)
    max_budget = float(policy.get("max_daily_budget") or 0)
    max_name_length = _int_value(policy.get("max_project_name_length"), 80)
    project_name_pattern = str(policy.get("project_name_pattern") or "").strip()
    required_defaults = _required_field_defaults(policy)
    expected_material_count = max(
        _int_value(
            (request.get("material_requirements") if isinstance(request.get("material_requirements"), dict) else {}).get(
                "materials_per_unit"
            ),
            1,
        ),
        0,
    )
    product = str(request.get("product") or "")
    platform = str(request.get("platform") or "")
    seen_project_names_by_account: dict[str, set[str]] = {}
    for project in projects:
        advertiser_id = str(project.get("advertiser_id") or "")
        budget = float(project.get("daily_budget") or 0)
        if min_budget and budget < min_budget:
            violations.append(f"daily budget for {advertiser_id} must be at least {int(min_budget)}")
        if max_budget and budget > max_budget:
            violations.append(f"daily budget for {advertiser_id} must be at most {int(max_budget)}")
        project_name = str(project.get("project_name") or "")
        if not project_name:
            violations.append(f"project name for {advertiser_id} is required")
        if len(project_name) > max_name_length:
            violations.append(f"project name for {advertiser_id} exceeds {max_name_length} characters")
        if project_name and project_name_pattern:
            try:
                matches_pattern = re.fullmatch(project_name_pattern, project_name) is not None
            except re.error:
                matches_pattern = False
                if "project_name_pattern is invalid" not in violations:
                    violations.append("project_name_pattern is invalid")
            if not matches_pattern:
                violations.append(f"project name {project_name} does not match required pattern")
        seen_names = seen_project_names_by_account.setdefault(advertiser_id, set())
        if project_name and project_name in seen_names:
            violations.append(f"project name {project_name} is duplicated in plan for advertiser {advertiser_id}")
        seen_names.add(project_name)
        if bool(policy.get("reject_existing_project_names", False)) and project_name in _existing_project_names(
            db_path=policy["_db_path"],
            advertiser_id=advertiser_id,
        ):
            violations.append(f"project name {project_name} already exists for advertiser {advertiser_id}")
        defaults = project.get("field_defaults") if isinstance(project.get("field_defaults"), dict) else {}
        for field in required_defaults:
            if not str(defaults.get(field) or "").strip():
                violations.append(f"field_defaults missing {field}")
        if bool(policy.get("require_account_pool", True)) and not _account_pool_contains(
            db_path=policy["_db_path"],
            advertiser_id=advertiser_id,
            product=product,
            platform=platform,
        ):
            violations.append(f"target account {advertiser_id} is not in account_pool for {product}/{platform}")
        for unit in project.get("units") or []:
            if not isinstance(unit, dict):
                continue
            materials = unit.get("materials") if isinstance(unit.get("materials"), list) else []
            if len(materials) != expected_material_count:
                violations.append(
                    f"unit {unit.get('unit_key')} has {len(materials)} materials, expected {expected_material_count}"
                )
    return violations


def build_create_preflight(
    *,
    create_strategy_plan_artifact: dict[str, Any],
    db_path: str | Path,
    policy: dict[str, Any],
) -> dict[str, Any]:
    plan = create_plan_payload(create_strategy_plan_artifact)
    request = _request(plan)
    projects = _projects(plan)
    policy_with_db = {**policy, "_db_path": db_path}
    violations = _shape_violations(plan)
    violations.extend(str(item) for item in plan.get("violations") or [])
    violations.extend(_project_violations(request=request, projects=projects, policy=policy_with_db))
    violations.extend(_material_violations(request=request, projects=projects, policy=policy_with_db))
    status = "passed" if not violations else "failed"
    units = [unit for project in projects for unit in project.get("units", []) if isinstance(unit, dict)]
    return {
        "ok": not violations,
        "workflow": "create_preflight",
        "phase": "phase1",
        "execution_enabled": False,
        "external_api_calls": 0,
        "status": status,
        "summary": {
            "plan_id": str(plan.get("plan_id") or ""),
            "request_id": str(plan.get("request_id") or ""),
            "target_date": str(plan.get("target_date") or ""),
            "project_count": len(projects),
            "unit_count": len(units),
            "violation_count": len(violations),
        },
        "lineage": {
            "create_strategy_plan": create_ref(
                workflow="create_strategy_plan",
                artifact=create_strategy_plan_artifact,
            ),
        },
        "checks": [
            "validate_phase1_plan_only",
            "validate_account_pool_membership",
            "validate_material_counts",
            "validate_budget_limits",
            "validate_project_names",
            "validate_field_defaults",
            "validate_material_candidate_source",
            "validate_material_type_and_review_status",
            "validate_material_dedupe_scope",
        ],
        "violations": violations,
        "approved_for_execute": False,
        "actions": [],
    }


def run_create_preflight_request(
    request: dict[str, Any],
    *,
    db_path: str | Path,
    runs_dir: str | Path,
) -> dict[str, Any]:
    cfg = _preflight_config(request)
    artifact = cfg.get("create_strategy_plan_artifact")
    if not isinstance(artifact, dict):
        raise ValueError("create preflight requires create_strategy_plan_artifact")
    policy = cfg.get("policy") if isinstance(cfg.get("policy"), dict) else {}
    payload = build_create_preflight(create_strategy_plan_artifact=artifact, db_path=db_path, policy=policy)
    plan_path = cfg.get("create_strategy_plan_artifact_path")
    if str(plan_path or "").strip():
        payload["lineage"]["create_strategy_plan"]["artifact_path"] = str(plan_path)
    artifact_path = write_run_artifact(runs_dir, "create_preflight", payload)
    return {**payload, "artifact_path": str(artifact_path)}
