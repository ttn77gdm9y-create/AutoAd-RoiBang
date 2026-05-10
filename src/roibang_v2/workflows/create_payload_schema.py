from __future__ import annotations

from typing import Any


CREATE_PAYLOAD_SCHEMA_VERSION = "phase1.create_payload.v1"


def disabled_create_payload_schema(policy: dict[str, Any] | None = None) -> dict[str, Any]:
    live_api = policy.get("live_api") if isinstance(policy, dict) and isinstance(policy.get("live_api"), dict) else {}
    endpoints = live_api.get("endpoints") if isinstance(live_api.get("endpoints"), dict) else {}
    return {
        "version": CREATE_PAYLOAD_SCHEMA_VERSION,
        "mode": "schema_only",
        "execution_enabled": False,
        "external_api_enabled": False,
        "live_payload_generation_enabled": False,
        "endpoints": {
            "create_project": str(endpoints.get("create_project") or ""),
            "create_unit": str(endpoints.get("create_unit") or ""),
            "bind_material": str(endpoints.get("bind_material") or ""),
        },
        "required_fields": {
            "create_project": [
                "advertiser_id",
                "project_name",
                "daily_budget",
                "field_defaults.landing_type",
                "field_defaults.pricing",
                "field_defaults.inventory_type",
            ],
            "create_unit": [
                "advertiser_id",
                "project_key",
                "project_id",
                "unit_key",
                "promotion_name",
                "field_defaults.landing_type",
                "field_defaults.pricing",
                "field_defaults.inventory_type",
            ],
            "bind_material": [
                "advertiser_id",
                "project_key",
                "project_id",
                "unit_key",
                "promotion_id",
                "material_id",
                "source_video_id",
            ],
        },
        "field_sources": {
            "create_project": "create_strategy_plan.strategy.projects[]",
            "create_unit": "create_strategy_plan.strategy.projects[].units[]",
            "bind_material": "create_strategy_plan.strategy.projects[].units[].materials[]",
        },
    }


def validate_create_payload_contract(
    *,
    projects: list[dict[str, Any]],
    payload_schema: dict[str, Any],
) -> dict[str, Any]:
    required = payload_schema.get("required_fields") if isinstance(payload_schema.get("required_fields"), dict) else {}
    project_required = [str(item) for item in required.get("create_project") or []]
    unit_required = [str(item) for item in required.get("create_unit") or []]
    bind_required = [str(item) for item in required.get("bind_material") or []]
    missing_fields: list[str] = []
    checked_unit_count = 0
    checked_material_binding_count = 0
    for project in projects:
        project_key = str(project.get("project_key") or "")
        for field in project_required:
            if not _has_payload_value(project, field):
                missing_fields.append(f"create_project project {project_key} missing {field}")
        units = project.get("units") if isinstance(project.get("units"), list) else []
        for unit in [row for row in units if isinstance(row, dict)]:
            checked_unit_count += 1
            unit_key = _unit_label(project_key=project_key, unit=unit)
            unit_scope = {**project, **unit}
            for field in unit_required:
                if not _has_payload_value(unit_scope, field):
                    missing_fields.append(f"create_unit unit {unit_key} missing {field}")
            materials = unit.get("materials") if isinstance(unit.get("materials"), list) else []
            for material in [row for row in materials if isinstance(row, dict)]:
                checked_material_binding_count += 1
                bind_scope = {**project, **unit, **material}
                for field in bind_required:
                    if not _has_payload_value(bind_scope, field):
                        missing_fields.append(f"bind_material unit {unit_key} missing {field}")
    return {
        "status": "passed" if not missing_fields else "failed",
        "schema_version": str(payload_schema.get("version") or CREATE_PAYLOAD_SCHEMA_VERSION),
        "checked_project_count": len(projects),
        "checked_unit_count": checked_unit_count,
        "checked_material_binding_count": checked_material_binding_count,
        "missing_fields": missing_fields,
    }


def _has_payload_value(scope: dict[str, Any], field: str) -> bool:
    value = _payload_value(scope, field)
    if isinstance(value, dict):
        return bool(value)
    if isinstance(value, list):
        return bool(value)
    if isinstance(value, (int, float)):
        return value > 0
    return bool(str(value or "").strip())


def _payload_value(scope: dict[str, Any], field: str) -> Any:
    value: Any = scope
    for part in field.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def _unit_label(*, project_key: str, unit: dict[str, Any]) -> str:
    if str(unit.get("unit_key") or "").strip():
        return str(unit.get("unit_key") or "")
    try:
        unit_index = int(unit.get("unit_index") or 0)
    except (TypeError, ValueError):
        unit_index = 0
    if unit_index > 0:
        return f"{project_key}-u{unit_index:02d}"
    return f"{project_key}-u??"
