from __future__ import annotations

from typing import Any


PROVIDER_FIELD_MAPPING_VERSION = "phase1.oceanengine.create_payload.draft.v1"

_CREATE_PROJECT_TEMPLATE_DEFAULT_FIELDS = {
    "field_defaults.marketing_goal",
    "field_defaults.ad_type",
    "field_defaults.delivery_mode",
    "field_defaults.micro_promotion_type",
    "field_defaults.micro_app_instance_id",
    "field_defaults.aigc_dynamic_creative_switch",
    "field_defaults.external_action",
    "field_defaults.deep_external_action",
    "field_defaults.inventory_catalog",
    "field_defaults.action_track_url",
    "field_defaults.schedule_type",
    "field_defaults.deep_bid_type",
    "field_defaults.bid_type",
    "field_defaults.budget_mode",
    "field_defaults.cpa_bid",
    "field_defaults.roi_goal",
    "field_defaults.district",
    "field_defaults.gender",
    "field_defaults.audience_platform",
}


def disabled_provider_adapter(policy: dict[str, Any] | None = None) -> dict[str, Any]:
    adapter = policy.get("provider_adapter") if isinstance(policy, dict) and isinstance(policy.get("provider_adapter"), dict) else {}
    return {
        "status": "draft_verified" if bool(adapter.get("mapping_verified", False)) else "draft_unverified",
        "provider": str(adapter.get("provider") or "oceanengine"),
        "transport": "disabled_provider_adapter",
        "mapping_verified": bool(adapter.get("mapping_verified", False)),
        "executable": False,
        "field_mapping_version": str(adapter.get("field_mapping_version") or PROVIDER_FIELD_MAPPING_VERSION),
    }


def build_provider_payload_drafts(
    *,
    tasks: list[dict[str, Any]],
    adapter: dict[str, Any],
    provider_field_map: dict[str, Any] | None = None,
    provider_field_map_contract: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    field_mapping_applied = _can_apply_field_mapping(
        adapter=adapter,
        provider_field_map=provider_field_map,
        provider_field_map_contract=provider_field_map_contract,
    )
    drafts: list[dict[str, Any]] = []
    for task in tasks:
        task_drafts = task.get("redacted_payload_drafts") if isinstance(task.get("redacted_payload_drafts"), list) else []
        for draft in [row for row in task_drafts if isinstance(row, dict)]:
            operation = str(draft.get("operation") or "")
            payload = draft.get("payload") if isinstance(draft.get("payload"), dict) else {}
            unmapped_fields = _unmapped_payload_fields(
                operation=operation,
                payload=payload,
                provider_field_map=provider_field_map,
                field_mapping_requested=field_mapping_applied,
                verified_only=True,
            )
            draft_mapping_applied = field_mapping_applied and not unmapped_fields
            candidate_unmapped_fields = _unmapped_payload_fields(
                operation=operation,
                payload=payload,
                provider_field_map=provider_field_map,
                field_mapping_requested=not draft_mapping_applied,
                verified_only=False,
            )
            candidate_mapping_applied = (
                not draft_mapping_applied
                and isinstance(provider_field_map, dict)
                and bool(_operation_field_map(provider_field_map=provider_field_map, operation=operation, verified_only=False))
                and not candidate_unmapped_fields
            )
            mapping_mode = (
                "verified"
                if draft_mapping_applied
                else "candidate"
                if candidate_mapping_applied
                else "blocked_unmapped"
                if candidate_unmapped_fields
                else "none"
            )
            candidate_unverified_fields = _candidate_unverified_fields(
                operation=operation,
                payload=payload,
                provider_field_map=provider_field_map,
            ) if candidate_mapping_applied else []
            drafts.append(
                {
                    "operation": operation,
                    "provider": str(adapter.get("provider") or "oceanengine"),
                    "transport": str(adapter.get("transport") or "disabled_provider_adapter"),
                    "mapping_verified": bool(adapter.get("mapping_verified", False)),
                    "field_mapping_applied": draft_mapping_applied,
                    "candidate_field_mapping_applied": candidate_mapping_applied,
                    "field_mapping_mode": mapping_mode,
                    "unmapped_payload_fields": unmapped_fields,
                    "candidate_unmapped_payload_fields": candidate_unmapped_fields,
                    "candidate_unverified_field_count": len(candidate_unverified_fields),
                    "candidate_unverified_fields": candidate_unverified_fields,
                    "non_executable_reasons": _non_executable_reasons(
                        adapter=adapter,
                        field_mapping_applied=draft_mapping_applied,
                        candidate_mapping_applied=candidate_mapping_applied,
                        candidate_unverified_fields=candidate_unverified_fields,
                        candidate_unmapped_fields=candidate_unmapped_fields,
                    ),
                    "field_mapping_version": str(adapter.get("field_mapping_version") or PROVIDER_FIELD_MAPPING_VERSION),
                    "executable": False,
                    "idempotency_key": str(draft.get("idempotency_key") or ""),
                    "endpoint": str(draft.get("endpoint") or ""),
                    "payload": _provider_payload(
                        operation=operation,
                        payload=payload,
                        provider_field_map=provider_field_map,
                        field_mapping_applied=draft_mapping_applied or candidate_mapping_applied,
                        verified_only=draft_mapping_applied,
                    ),
                }
            )
    return drafts


def provider_adapter_contract(
    *,
    adapter: dict[str, Any],
    provider_payload_drafts: list[dict[str, Any]],
    tasks: list[dict[str, Any]],
) -> dict[str, Any]:
    live_payload_count = sum(
        len(task.get("live_api_payloads") if isinstance(task.get("live_api_payloads"), list) else [])
        for task in tasks
    )
    unmapped_payload_fields = _contract_unmapped_payload_fields(provider_payload_drafts)
    return {
        "status": "draft_verified" if bool(adapter.get("mapping_verified", False)) else "draft_unverified",
        "provider": str(adapter.get("provider") or "oceanengine"),
        "mapping_verified": bool(adapter.get("mapping_verified", False)),
        "draft_count": len(provider_payload_drafts),
        "live_payload_count": live_payload_count,
        "executable_draft_count": sum(1 for draft in provider_payload_drafts if bool(draft.get("executable", False))),
        "unmapped_payload_field_count": len(unmapped_payload_fields),
        "unmapped_payload_fields": unmapped_payload_fields,
    }


def _can_apply_field_mapping(
    *,
    adapter: dict[str, Any],
    provider_field_map: dict[str, Any] | None,
    provider_field_map_contract: dict[str, Any] | None,
) -> bool:
    return (
        bool(adapter.get("mapping_verified", False))
        and isinstance(provider_field_map, dict)
        and isinstance(provider_field_map_contract, dict)
        and str(provider_field_map_contract.get("status") or "") == "verified"
        and bool(provider_field_map.get("mapping_verified", False))
    )


def _provider_payload(
    *,
    operation: str,
    payload: dict[str, Any],
    provider_field_map: dict[str, Any] | None,
    field_mapping_applied: bool,
    verified_only: bool = True,
) -> dict[str, Any]:
    if not field_mapping_applied or not isinstance(provider_field_map, dict):
        return dict(payload)
    operation_map = _operation_field_map(
        provider_field_map=provider_field_map,
        operation=operation,
        verified_only=verified_only,
    )
    provider_payload: dict[str, Any] = {}
    for internal_field, provider_field in operation_map.items():
        value = _payload_value(payload, internal_field)
        if value is not None:
            _set_payload_value(provider_payload, provider_field, value)
    if operation == "create_project":
        _apply_create_project_template_defaults(provider_payload, payload)
    return provider_payload


def _apply_create_project_template_defaults(provider_payload: dict[str, Any], payload: dict[str, Any]) -> None:
    field_defaults = payload.get("field_defaults") if isinstance(payload.get("field_defaults"), dict) else {}
    template_fields = {
        "marketing_goal": "marketing_goal",
        "ad_type": "ad_type",
        "delivery_mode": "delivery_mode",
        "micro_promotion_type": "micro_promotion_type",
        "micro_app_instance_id": "micro_app_instance_id",
        "aigc_dynamic_creative_switch": "aigc_dynamic_creative_switch",
        "external_action": "optimize_goal.external_action",
        "deep_external_action": "optimize_goal.deep_external_action",
        "inventory_catalog": "delivery_range.inventory_catalog",
        "action_track_url": "track_url_setting.action_track_url",
        "schedule_type": "delivery_setting.schedule_type",
        "deep_bid_type": "delivery_setting.deep_bid_type",
        "bid_type": "delivery_setting.bid_type",
        "budget_mode": "delivery_setting.budget_mode",
        "cpa_bid": "delivery_setting.cpa_bid",
        "roi_goal": "delivery_setting.roi_goal",
        "district": "audience.district",
        "gender": "audience.gender",
        "audience_platform": "audience.platform",
    }
    for internal_field, provider_field in template_fields.items():
        if internal_field not in field_defaults:
            continue
        value = field_defaults.get(internal_field)
        if isinstance(value, str) and not value.strip():
            continue
        if value is None:
            continue
        _set_payload_value(provider_payload, provider_field, value)


def _unmapped_payload_fields(
    *,
    operation: str,
    payload: dict[str, Any],
    provider_field_map: dict[str, Any] | None,
    field_mapping_requested: bool,
    verified_only: bool = True,
) -> list[dict[str, str]]:
    if not field_mapping_requested or not isinstance(provider_field_map, dict):
        return []
    operation_map = _operation_field_map(
        provider_field_map=provider_field_map,
        operation=operation,
        verified_only=verified_only,
    )
    local_only_fields = _operation_local_only_fields(provider_field_map=provider_field_map, operation=operation)
    return [
        {"operation": operation, "internal_field": str(field)}
        for field in _payload_field_paths(payload)
        if not _payload_field_is_mapped(field, operation_map)
        and field not in local_only_fields
        and not _is_adapter_consumed_template_field(operation=operation, field=field)
    ]


def _payload_field_is_mapped(field: str, operation_map: dict[str, str]) -> bool:
    if field in operation_map:
        return True
    parts = field.split(".")
    return any(".".join(parts[:index]) in operation_map for index in range(1, len(parts)))


def _is_adapter_consumed_template_field(*, operation: str, field: str) -> bool:
    if operation == "create_project":
        return field in _CREATE_PROJECT_TEMPLATE_DEFAULT_FIELDS
    if operation == "create_unit":
        return field in _CREATE_PROJECT_TEMPLATE_DEFAULT_FIELDS
    return False


def _contract_unmapped_payload_fields(provider_payload_drafts: list[dict[str, Any]]) -> list[dict[str, str]]:
    fields: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for draft in provider_payload_drafts:
        if not isinstance(draft, dict):
            continue
        rows = draft.get("unmapped_payload_fields")
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            operation = str(row.get("operation") or "")
            internal_field = str(row.get("internal_field") or "")
            key = (operation, internal_field)
            if operation and internal_field and key not in seen:
                fields.append({"operation": operation, "internal_field": internal_field})
                seen.add(key)
    return fields


def _operation_field_map(
    *,
    provider_field_map: dict[str, Any],
    operation: str,
    verified_only: bool = True,
) -> dict[str, str]:
    operations = provider_field_map.get("operations") if isinstance(provider_field_map.get("operations"), dict) else {}
    rows = operations.get(operation)
    if not isinstance(rows, list):
        return {}
    mapping: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        internal_field = str(row.get("internal_field") or "").strip()
        provider_field = str(row.get("provider_field") or "").strip()
        if internal_field and provider_field and (bool(row.get("verified", False)) or not verified_only):
            mapping[internal_field] = provider_field
    return mapping


def _operation_local_only_fields(*, provider_field_map: dict[str, Any], operation: str) -> set[str]:
    operations = provider_field_map.get("operations") if isinstance(provider_field_map.get("operations"), dict) else {}
    rows = operations.get(operation)
    if not isinstance(rows, list):
        return set()
    return {
        str(row.get("internal_field") or "").strip()
        for row in rows
        if isinstance(row, dict)
        and str(row.get("internal_field") or "").strip()
        and str(row.get("mapping_kind") or "").strip() in {"local_lookup_key", "local_only"}
    }


def _operation_entries(*, provider_field_map: dict[str, Any] | None, operation: str) -> list[dict[str, Any]]:
    if not isinstance(provider_field_map, dict):
        return []
    operations = provider_field_map.get("operations") if isinstance(provider_field_map.get("operations"), dict) else {}
    rows = operations.get(operation)
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _candidate_unverified_fields(
    *,
    operation: str,
    payload: dict[str, Any],
    provider_field_map: dict[str, Any] | None,
) -> list[dict[str, str]]:
    payload_fields = set(_payload_field_paths(payload))
    rows: list[dict[str, str]] = []
    for entry in _operation_entries(provider_field_map=provider_field_map, operation=operation):
        internal_field = str(entry.get("internal_field") or "").strip()
        provider_field = str(entry.get("provider_field") or "").strip()
        if not internal_field or not provider_field or internal_field not in payload_fields:
            continue
        if bool(entry.get("verified", False)):
            continue
        rows.append(
            {
                "operation": operation,
                "internal_field": internal_field,
                "provider_field": provider_field,
                "mapping_kind": str(entry.get("mapping_kind") or ""),
            }
        )
    return rows


def _non_executable_reasons(
    *,
    adapter: dict[str, Any],
    field_mapping_applied: bool,
    candidate_mapping_applied: bool,
    candidate_unverified_fields: list[dict[str, str]],
    candidate_unmapped_fields: list[dict[str, str]],
) -> list[str]:
    reasons = ["provider payload drafts are dry-run only"]
    if not bool(adapter.get("mapping_verified", False)):
        reasons.append("provider adapter mapping is not verified")
    if candidate_mapping_applied:
        reasons.append("candidate provider fields require evidence review before execution")
    if candidate_unverified_fields:
        reasons.append("candidate provider fields are not verified")
    if candidate_unmapped_fields:
        reasons.append("provider payload contains unmapped internal fields")
    if not field_mapping_applied:
        reasons.append("verified provider field mapping is not applied")
    return reasons


def _payload_value(payload: dict[str, Any], field: str) -> Any:
    value: Any = payload
    for part in field.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def _set_payload_value(payload: dict[str, Any], field: str, value: Any) -> None:
    parts = [part for part in field.split(".") if part]
    if not parts:
        return
    value = _provider_value(field, value)
    current = payload
    for part in parts[:-1]:
        existing = current.get(part)
        if not isinstance(existing, dict):
            existing = {}
            current[part] = existing
        current = existing
    current[parts[-1]] = value
    if field == "delivery_range.inventory_type":
        current.setdefault("inventory_catalog", "UNIVERSAL_SMART")


def _provider_value(field: str, value: Any) -> Any:
    if field == "micro_app_instance_id" and isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    if field == "delivery_range.inventory_type" and isinstance(value, str):
        return [value] if value else []
    if field == "track_url_setting.action_track_url" and isinstance(value, str):
        return [value] if value else []
    return value


def _payload_field_paths(payload: dict[str, Any]) -> list[str]:
    paths: list[str] = []
    for key, value in payload.items():
        key_text = str(key)
        if isinstance(value, dict):
            for subkey in value:
                paths.append(f"{key_text}.{subkey}")
        else:
            paths.append(key_text)
    return paths
