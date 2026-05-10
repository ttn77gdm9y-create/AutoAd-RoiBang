from __future__ import annotations

from typing import Any


PROVIDER_FIELD_MAPPING_VERSION = "phase1.oceanengine.create_payload.draft.v1"


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
            )
            draft_mapping_applied = field_mapping_applied and not unmapped_fields
            drafts.append(
                {
                    "operation": operation,
                    "provider": str(adapter.get("provider") or "oceanengine"),
                    "transport": str(adapter.get("transport") or "disabled_provider_adapter"),
                    "mapping_verified": bool(adapter.get("mapping_verified", False)),
                    "field_mapping_applied": draft_mapping_applied,
                    "unmapped_payload_fields": unmapped_fields,
                    "field_mapping_version": str(adapter.get("field_mapping_version") or PROVIDER_FIELD_MAPPING_VERSION),
                    "executable": False,
                    "idempotency_key": str(draft.get("idempotency_key") or ""),
                    "endpoint": str(draft.get("endpoint") or ""),
                    "payload": _provider_payload(
                        operation=operation,
                        payload=payload,
                        provider_field_map=provider_field_map,
                        field_mapping_applied=draft_mapping_applied,
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
) -> dict[str, Any]:
    if not field_mapping_applied or not isinstance(provider_field_map, dict):
        return dict(payload)
    operation_map = _operation_field_map(provider_field_map=provider_field_map, operation=operation)
    provider_payload: dict[str, Any] = {}
    for internal_field, provider_field in operation_map.items():
        value = _payload_value(payload, internal_field)
        if value is not None:
            provider_payload[provider_field] = value
    return provider_payload


def _unmapped_payload_fields(
    *,
    operation: str,
    payload: dict[str, Any],
    provider_field_map: dict[str, Any] | None,
    field_mapping_requested: bool,
) -> list[dict[str, str]]:
    if not field_mapping_requested or not isinstance(provider_field_map, dict):
        return []
    operation_map = _operation_field_map(provider_field_map=provider_field_map, operation=operation)
    return [
        {"operation": operation, "internal_field": str(field)}
        for field in _payload_field_paths(payload)
        if field not in operation_map
    ]


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


def _operation_field_map(*, provider_field_map: dict[str, Any], operation: str) -> dict[str, str]:
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
        if internal_field and provider_field and bool(row.get("verified", False)):
            mapping[internal_field] = provider_field
    return mapping


def _payload_value(payload: dict[str, Any], field: str) -> Any:
    value: Any = payload
    for part in field.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
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
