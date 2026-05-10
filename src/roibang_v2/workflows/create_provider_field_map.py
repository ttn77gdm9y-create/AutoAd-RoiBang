from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from roibang_v2.workflows.create_provider_adapter import PROVIDER_FIELD_MAPPING_VERSION


_FIELD_PURPOSES = {
    "advertiser_id": "target advertiser account id",
    "project_name": "planned project name",
    "project_type": "internal project type",
    "daily_budget": "planned project daily budget",
    "source_advertiser_id": "source material advertiser account id",
    "target_advertiser_ids": "target advertiser account ids for material push",
    "source_video_ids": "source account video ids to push",
    "field_defaults": "project and unit default fields",
    "field_defaults.landing_type": "default landing type",
    "field_defaults.pricing": "default pricing type",
    "field_defaults.inventory_type": "default inventory type",
    "project_key": "local planned project key",
    "project_id": "provider project id lookup placeholder",
    "unit_key": "local planned unit key",
    "promotion_name": "planned provider-facing unit name",
    "promotion_materials.video_material_list": "provider-facing promotion video material list",
    "promotion_materials.title_material_list": "provider-facing promotion title material list",
    "promotion_materials.call_to_action_buttons": "provider-facing call-to-action button list",
    "promotion_materials.mini_program_info": "provider-facing mini program landing information",
    "budget": "unit budget",
    "budget_mode": "unit budget mode",
    "roi_goal": "unit ROI goal",
    "source": "unit creative source",
    "operation": "provider object status operation",
    "promotion_id": "provider promotion id lookup placeholder",
    "material_id": "source material identity",
    "source_video_id": "source video identity",
    "target_advertiser_id": "target advertiser account id for material lookup",
    "target_video_id": "target account video id lookup placeholder",
    "target_video_cover_id": "target account video cover id lookup placeholder",
}

_FIELD_DEFAULT_SUBFIELDS = [
    "field_defaults.landing_type",
    "field_defaults.pricing",
    "field_defaults.inventory_type",
]

_REQUIRED_FIELDS_BY_OPERATION = {
    "create_project": ["advertiser_id", "project_name", "project_type", "daily_budget", *_FIELD_DEFAULT_SUBFIELDS],
    "create_unit": [
        "advertiser_id",
        "project_key",
        "project_id",
        "unit_key",
        "promotion_name",
        "promotion_materials.video_material_list",
        "promotion_materials.title_material_list",
        "promotion_materials.call_to_action_buttons",
        "promotion_materials.mini_program_info",
        "budget",
        "budget_mode",
        "roi_goal",
        "source",
        "operation",
        *_FIELD_DEFAULT_SUBFIELDS,
    ],
    "lookup_target_material": [
        "source_advertiser_id",
        "target_advertiser_id",
        "source_video_id",
        "material_id",
        "target_video_id",
        "target_video_cover_id",
    ],
    "bind_material": [
        "source_advertiser_id",
        "target_advertiser_ids",
        "source_video_ids",
        "project_key",
        "unit_key",
        "material_id",
        "source_video_id",
    ],
}


def default_provider_field_map(
    policy: dict[str, Any] | None = None,
    *,
    source: str = "phase1_placeholder_no_legacy_reference",
) -> dict[str, Any]:
    adapter = policy.get("provider_adapter") if isinstance(policy, dict) and isinstance(policy.get("provider_adapter"), dict) else {}
    provider = str(adapter.get("provider") or "oceanengine")
    version = str(adapter.get("field_mapping_version") or PROVIDER_FIELD_MAPPING_VERSION)
    return {
        "provider": provider,
        "field_mapping_version": version,
        "mapping_verified": False,
        "source": source,
        "operations": {
            operation: _entries(fields) for operation, fields in _REQUIRED_FIELDS_BY_OPERATION.items()
        },
    }


def load_provider_field_map(policy: dict[str, Any] | None = None) -> dict[str, Any]:
    path = str(policy.get("provider_field_map_path") or "").strip() if isinstance(policy, dict) else ""
    if not path:
        return default_provider_field_map(policy)
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default_provider_field_map(policy, source="phase1_placeholder_invalid_provider_field_map_config")
    if not _is_valid_provider_field_map(payload):
        return default_provider_field_map(policy, source="phase1_placeholder_invalid_provider_field_map_config")
    return payload


def provider_field_map_contract(field_map: dict[str, Any], policy: dict[str, Any] | None = None) -> dict[str, Any]:
    operations = field_map.get("operations") if isinstance(field_map.get("operations"), dict) else {}
    entries = [
        entry
        for rows in operations.values()
        for entry in (rows if isinstance(rows, list) else [])
        if isinstance(entry, dict)
    ]
    mapping_verified = bool(field_map.get("mapping_verified", False))
    verified_count = sum(1 for entry in entries if bool(entry.get("verified", False)))
    missing_provider_count = sum(
        1 for entry in entries if not str(entry.get("provider_field") or "").strip() and not _is_local_only(entry)
    )
    missing_required_fields = _missing_required_fields(operations)
    duplicate_internal_fields = _duplicate_internal_fields(operations)
    duplicate_provider_fields = _duplicate_provider_fields(operations)
    unknown_internal_fields = _unknown_internal_fields(operations)
    provider_mismatches = _provider_mismatches(field_map, policy)
    version_mismatches = _field_mapping_version_mismatches(field_map, policy)
    status = (
        "verified"
        if (
            entries
            and mapping_verified
            and verified_count == len(entries)
            and missing_provider_count == 0
            and not missing_required_fields
            and not duplicate_internal_fields
            and not duplicate_provider_fields
            and not unknown_internal_fields
            and not provider_mismatches
            and not version_mismatches
        )
        else "unverified"
    )
    return {
        "status": status,
        "provider": str(field_map.get("provider") or "oceanengine"),
        "mapping_verified": mapping_verified,
        "operation_count": len(operations),
        "field_count": len(entries),
        "verified_field_count": verified_count,
        "unverified_field_count": len(entries) - verified_count,
        "missing_provider_field_count": missing_provider_count,
        "missing_required_field_count": len(missing_required_fields),
        "missing_required_fields": missing_required_fields,
        "duplicate_internal_field_count": len(duplicate_internal_fields),
        "duplicate_internal_fields": duplicate_internal_fields,
        "duplicate_provider_field_count": len(duplicate_provider_fields),
        "duplicate_provider_fields": duplicate_provider_fields,
        "unknown_internal_field_count": len(unknown_internal_fields),
        "unknown_internal_fields": unknown_internal_fields,
        "provider_mismatch_count": len(provider_mismatches),
        "provider_mismatches": provider_mismatches,
        "field_mapping_version_mismatch_count": len(version_mismatches),
        "field_mapping_version_mismatches": version_mismatches,
    }


def provider_field_map_digest(field_map: dict[str, Any]) -> dict[str, Any]:
    canonical = json.dumps(field_map, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {
        "algorithm": "sha256",
        "value": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
    }


def _is_valid_provider_field_map(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    if not str(value.get("provider") or "").strip():
        return False
    if not str(value.get("field_mapping_version") or "").strip():
        return False
    operations = value.get("operations")
    if not isinstance(operations, dict):
        return False
    if not operations:
        return False
    for operation in operations:
        rows = operations.get(operation)
        if not isinstance(rows, list) or not rows:
            return False
        for row in rows:
            if not isinstance(row, dict):
                return False
            if not str(row.get("internal_field") or "").strip():
                return False
            if "verified" not in row:
                return False
    return True


def _missing_required_fields(operations: dict[str, Any]) -> list[dict[str, str]]:
    missing: list[dict[str, str]] = []
    for operation, required_fields in _REQUIRED_FIELDS_BY_OPERATION.items():
        rows = operations.get(operation) if isinstance(operations.get(operation), list) else []
        present_fields = {
            str(row.get("internal_field") or "")
            for row in rows
            if isinstance(row, dict) and str(row.get("internal_field") or "")
        }
        for field in required_fields:
            if field not in present_fields:
                missing.append({"operation": operation, "internal_field": field})
    return missing


def _duplicate_internal_fields(operations: dict[str, Any]) -> list[dict[str, str]]:
    duplicates: list[dict[str, str]] = []
    for operation, rows in operations.items():
        if not isinstance(rows, list):
            continue
        seen: set[str] = set()
        reported: set[str] = set()
        for row in rows:
            if not isinstance(row, dict):
                continue
            field = str(row.get("internal_field") or "").strip()
            if not field:
                continue
            if field in seen and field not in reported:
                duplicates.append({"operation": str(operation), "internal_field": field})
                reported.add(field)
            seen.add(field)
    return duplicates


def _duplicate_provider_fields(operations: dict[str, Any]) -> list[dict[str, Any]]:
    duplicates: list[dict[str, Any]] = []
    for operation, rows in operations.items():
        if not isinstance(rows, list):
            continue
        fields: dict[str, list[str]] = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            provider_field = str(row.get("provider_field") or "").strip()
            internal_field = str(row.get("internal_field") or "").strip()
            if provider_field and internal_field:
                fields.setdefault(provider_field, []).append(internal_field)
        for provider_field, internal_fields in fields.items():
            if len(internal_fields) > 1:
                duplicates.append(
                    {
                        "operation": str(operation),
                        "provider_field": provider_field,
                        "internal_fields": internal_fields,
                    }
                )
    return duplicates


def _is_local_only(entry: dict[str, Any]) -> bool:
    return str(entry.get("mapping_kind") or "").strip() in {"local_lookup_key", "local_only"}


def _unknown_internal_fields(operations: dict[str, Any]) -> list[dict[str, str]]:
    unknown: list[dict[str, str]] = []
    for operation, rows in operations.items():
        if not isinstance(rows, list):
            continue
        allowed_fields = set(_REQUIRED_FIELDS_BY_OPERATION.get(str(operation), []))
        for row in rows:
            if not isinstance(row, dict):
                continue
            field = str(row.get("internal_field") or "").strip()
            if field and field not in allowed_fields:
                unknown.append({"operation": str(operation), "internal_field": field})
    return unknown


def _expected_adapter_value(policy: dict[str, Any] | None, key: str, default: str) -> str:
    adapter = policy.get("provider_adapter") if isinstance(policy, dict) and isinstance(policy.get("provider_adapter"), dict) else {}
    return str(adapter.get(key) or default).strip()


def _provider_mismatches(field_map: dict[str, Any], policy: dict[str, Any] | None) -> list[dict[str, str]]:
    expected = _expected_adapter_value(policy, "provider", "oceanengine")
    actual = str(field_map.get("provider") or "").strip()
    return [] if actual == expected else [{"expected": expected, "actual": actual}]


def _field_mapping_version_mismatches(field_map: dict[str, Any], policy: dict[str, Any] | None) -> list[dict[str, str]]:
    expected = _expected_adapter_value(policy, "field_mapping_version", PROVIDER_FIELD_MAPPING_VERSION)
    actual = str(field_map.get("field_mapping_version") or "").strip()
    return [] if actual == expected else [{"expected": expected, "actual": actual}]


def _entries(fields: list[str]) -> list[dict[str, Any]]:
    return [
        {
            "internal_field": field,
            "provider_field": "",
            "purpose": _FIELD_PURPOSES[field],
            "verified": False,
            "required": True,
            "source": "internal_phase1_schema",
        }
        for field in fields
    ]
