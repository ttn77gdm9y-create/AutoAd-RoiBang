from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Callable

from roibang_v2.runs import write_run_artifact
from roibang_v2.workflows.create_material_bind_ledger import (
    existing_material_bind_result,
    record_create_material_bind_from_payload,
)
from roibang_v2.workflows.create_provider_id_ledger import (
    record_create_provider_id,
    resolve_provider_payload_drafts,
)

Transport = Callable[[dict[str, Any]], dict[str, Any]]
OPERATION_ORDER = ["create_project", "bind_material", "lookup_target_material", "create_unit"]
RECOVERY_ENDPOINTS = {
    "lookup_existing_project": "/open_api/v3.0/project/list/",
    "lookup_existing_unit": "/open_api/v3.0/promotion/list/",
}
PROJECT_CAP_CLEANUP_ENDPOINTS = {
    "lookup_disabled_projects": "/open_api/v3.0/project/list/",
    "delete_project": "/open_api/2/project/delete/",
}
ACTIVE_STATUS_VALUES = {
    "ACTIVE",
    "ENABLE",
    "ENABLED",
    "ON",
    "RUNNING",
    "START",
    "STARTED",
    "CAMPAIGN_STATUS_ENABLE",
    "PROJECT_STATUS_ENABLE",
    "PROMOTION_STATUS_ENABLE",
}
CLOSED_PROJECT_STATUS_VALUES = {
    "DISABLE",
    "DISABLED",
    "OFF",
    "STOP",
    "STOPPED",
    "PROJECT_STATUS_DISABLE",
    "PROJECT_STATUS_DISABLED",
    "PROJECT_STATUS_STOP",
}
LAUNCH_FIELD_NAMES = {
    "status",
    "delivery_status",
    "marketing_status",
    "project_status",
    "promotion_status",
    "operation",
    "enable",
    "enabled",
    "is_enabled",
}


def _once_config(request: dict[str, Any]) -> dict[str, Any]:
    value = request.get("create_live_execute_once")
    return dict(value) if isinstance(value, dict) else dict(request)


def _pre_transport_blocking_reasons(runtime: dict[str, Any], transport: Transport | None) -> list[str]:
    reasons: list[str] = []
    if not bool(runtime.get("execution_enabled", False)):
        reasons.append("runtime.execution_enabled is false")
    if not bool(runtime.get("external_api_enabled", False)):
        reasons.append("runtime.external_api_enabled is false")
    if transport is None and not reasons:
        reasons.append("create_http transport is not constructed")
    return reasons


def _blocked_result(
    *,
    reason: str,
    blocking_reasons: list[str],
) -> dict[str, Any]:
    return {
        "ok": False,
        "workflow": "create_live_execute_once",
        "phase": "phase2_preparation",
        "execution_enabled": False,
        "live_execute_enabled": False,
        "external_api_calls": 0,
        "status": "blocked",
        "reason": reason,
        "blocking_reasons": blocking_reasons,
        "ordered_steps": [],
        "provider_id_records": [],
        "transport_call_count": 0,
        "idempotency": {
            "status": "not_checked",
            "skipped_existing_provider_id_count": 0,
            "skipped_provider_id_records": [],
            "skipped_existing_material_bind_count": 0,
            "skipped_material_bind_records": [],
        },
        "material_bind_records": [],
        "project_cap_cleanup": _project_cap_cleanup_summary([]),
        "runner_result": None,
        "failure": None,
        "actions": [],
    }


def _rows(value: Any) -> list[dict[str, Any]]:
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def _create_execute_policy(policy: dict[str, Any]) -> dict[str, Any]:
    value = policy.get("create_execute")
    return dict(value) if isinstance(value, dict) else {}


def _live_api_policy(policy: dict[str, Any]) -> dict[str, Any]:
    value = _create_execute_policy(policy).get("live_api")
    return dict(value) if isinstance(value, dict) else {}


def _payload_schema_policy(policy: dict[str, Any]) -> dict[str, Any]:
    value = _create_execute_policy(policy).get("payload_schema")
    return dict(value) if isinstance(value, dict) else {}


def _runner_policy(policy: dict[str, Any]) -> dict[str, Any]:
    value = policy.get("create_live_execute_once")
    return dict(value) if isinstance(value, dict) else {}


def _project_cap_cleanup_policy(policy: dict[str, Any]) -> dict[str, Any]:
    value = _runner_policy(policy).get("project_cap_cleanup")
    data = dict(value) if isinstance(value, dict) else {}
    disabled_status_values = data.get("disabled_status_values")
    statuses = (
        {str(item).strip().upper() for item in disabled_status_values if str(item).strip()}
        if isinstance(disabled_status_values, list)
        else set(CLOSED_PROJECT_STATUS_VALUES)
    )
    delete_count = int(data.get("delete_count") or 10)
    return {
        "enabled": bool(data.get("enabled", True)),
        "delete_count": max(0, delete_count),
        "page_size": max(int(data.get("page_size") or 100), delete_count, 1),
        "disabled_status_values": statuses,
    }


def _endpoints(policy: dict[str, Any]) -> dict[str, str]:
    policy_endpoints = _live_api_policy(policy).get("endpoints")
    data = policy_endpoints if isinstance(policy_endpoints, dict) else {}
    endpoints = {operation: str(data.get(operation) or "") for operation in OPERATION_ORDER}
    for operation, endpoint in RECOVERY_ENDPOINTS.items():
        endpoints[operation] = str(data.get(operation) or endpoint)
    for operation, endpoint in PROJECT_CAP_CLEANUP_ENDPOINTS.items():
        endpoints[operation] = str(data.get(operation) or endpoint)
    return endpoints


def _provider_payload_drafts(create_execute: dict[str, Any]) -> list[dict[str, Any]]:
    drafts = _rows(create_execute.get("provider_payload_drafts"))
    if drafts:
        return drafts
    return _rows(create_execute.get("resolved_provider_payload_drafts"))


def _create_execute_payload_safety(create_execute: dict[str, Any]) -> dict[str, Any]:
    drafts = _provider_payload_drafts(create_execute)
    executable_count = sum(1 for draft in drafts if bool(draft.get("executable", False)))
    live_payload_count = sum(
        1
        for draft in drafts
        if bool(draft.get("live_api_payload", False)) or bool(draft.get("live_payload", False))
    )
    contract = create_execute.get("resolved_payload_contract")
    unresolved_lookup_count = int(contract.get("unresolved_lookup_count") or 0) if isinstance(contract, dict) else 0
    chain_lookup = _chain_lookup_contract(create_execute)
    return {
        "payloads_non_executable": executable_count == 0,
        "live_payload_count_zero": live_payload_count == 0,
        "lookup_placeholders_chain_resolvable": bool(chain_lookup["ok"]),
        "executable_count": executable_count,
        "live_payload_count": live_payload_count,
        "unresolved_lookup_count": unresolved_lookup_count,
        "unresolvable_lookup_placeholders": chain_lookup["unresolvable_lookup_placeholders"],
    }


def _lookup_key(value: Any) -> str:
    text = str(value) if isinstance(value, str) else ""
    if text.startswith("<lookup:") and text.endswith(">"):
        return text[len("<lookup:") : -1]
    return ""


def _lookup_keys(value: Any) -> list[str]:
    key = _lookup_key(value)
    if key:
        return [key]
    if isinstance(value, dict):
        return [row for item in value.values() for row in _lookup_keys(item)]
    if isinstance(value, list):
        return [row for item in value for row in _lookup_keys(item)]
    return []


def _chain_lookup_contract(create_execute: dict[str, Any]) -> dict[str, Any]:
    requirements = _provider_id_requirements(create_execute)
    allowed_create_unit_keys = {
        str(row.get("local_key") or "")
        for row in [
            *_rows(requirements.get("produced_by_create_project")),
            *_rows(requirements.get("required_before_create_unit")),
        ]
    }
    unresolvable: list[dict[str, str]] = []
    for draft in _provider_payload_drafts(create_execute):
        operation = str(draft.get("operation") or "")
        payload = draft.get("payload") if isinstance(draft.get("payload"), dict) else {}
        for key in _lookup_keys(payload):
            if operation == "create_unit" and key in allowed_create_unit_keys:
                continue
            unresolvable.append({"operation": operation, "local_key": key})
    return {
        "ok": not unresolvable,
        "unresolvable_lookup_placeholders": unresolvable,
    }


def _provider_payload_mapping_contract(create_execute: dict[str, Any]) -> dict[str, Any]:
    drafts = _provider_payload_drafts(create_execute)
    unmapped_count = 0
    unverified_count = 0
    for draft in drafts:
        if not bool(draft.get("field_mapping_applied", False)):
            unverified_count += 1
            continue
        if str(draft.get("field_mapping_mode") or "") != "verified":
            unverified_count += 1
        if draft.get("unmapped_payload_fields"):
            unmapped_count += 1
    return {
        "status": "passed" if drafts and unverified_count == 0 and unmapped_count == 0 else "blocked",
        "checked_draft_count": len(drafts),
        "unverified_draft_count": unverified_count,
        "unmapped_draft_count": unmapped_count,
    }


def _payload_launch_fields(value: Any, path: str = "") -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if isinstance(value, dict):
        for key, item in value.items():
            key_text = str(key)
            next_path = f"{path}.{key_text}" if path else key_text
            if key_text.lower() in LAUNCH_FIELD_NAMES:
                rows.append({"path": next_path, "value": item})
            rows.extend(_payload_launch_fields(item, next_path))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            rows.extend(_payload_launch_fields(item, f"{path}[{index}]"))
    return rows


def _active_launch_violations(create_execute: dict[str, Any]) -> list[str]:
    violations: list[str] = []
    for draft in _provider_payload_drafts(create_execute):
        operation = str(draft.get("operation") or "")
        payload = draft.get("payload") if isinstance(draft.get("payload"), dict) else {}
        for field in _payload_launch_fields(payload):
            value = field.get("value")
            path = str(field.get("path") or "")
            if isinstance(value, bool) and value:
                violations.append(f"{operation}.{path} must not enable live delivery during create")
                continue
            if isinstance(value, str) and value.strip().upper() in ACTIVE_STATUS_VALUES:
                violations.append(f"{operation}.{path} must not be {value.strip()} during create")
    return violations


def _drafts_for_operation(create_execute: dict[str, Any], operation: str) -> list[dict[str, Any]]:
    return [draft for draft in _provider_payload_drafts(create_execute) if str(draft.get("operation") or "") == operation]


def _provider_id_requirements(create_execute: dict[str, Any]) -> dict[str, Any]:
    value = create_execute.get("provider_id_ledger_requirements")
    return dict(value) if isinstance(value, dict) else {}


def _project_records(create_execute: dict[str, Any]) -> list[dict[str, Any]]:
    return _rows(_provider_id_requirements(create_execute).get("produced_by_create_project"))


def _unit_records(create_execute: dict[str, Any]) -> list[dict[str, Any]]:
    return _rows(_provider_id_requirements(create_execute).get("produced_by_create_unit"))


def _target_material_records(create_execute: dict[str, Any]) -> list[dict[str, Any]]:
    requirements = _rows(_provider_id_requirements(create_execute).get("required_before_create_unit"))
    return [
        row
        for row in requirements
        if str(row.get("entity_type") or "") in {"target_video", "target_video_cover"}
    ]


def _summary(create_execute: dict[str, Any]) -> dict[str, Any]:
    value = create_execute.get("summary")
    return dict(value) if isinstance(value, dict) else {}


def _existing_provider_id(*, db_path: str | Path, entity_type: str, local_key: str) -> str:
    if not str(local_key or "").strip():
        return ""
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT provider_id
            FROM create_provider_id_ledger
            WHERE entity_type = ? AND local_key = ? AND status = 'active'
              AND provider_id NOT LIKE 'mock_%'
              AND source_workflow != 'create_mock_execute'
            LIMIT 1
            """,
            (entity_type, local_key),
        ).fetchone()
    return str(row[0]) if row else ""


def _record_for_operation(create_execute: dict[str, Any], operation: str, index: int) -> dict[str, Any]:
    if operation == "create_project":
        records = _project_records(create_execute)
    elif operation == "create_unit":
        records = _unit_records(create_execute)
    else:
        records = []
    return records[index] if index < len(records) else {}


def _entity_type(operation: str) -> str:
    if operation == "create_project":
        return "project"
    if operation == "create_unit":
        return "promotion"
    return ""


def _response_code(response: dict[str, Any]) -> int:
    value = response.get("code", 0)
    try:
        return int(value)
    except (TypeError, ValueError):
        return -1


def _response_message(response: dict[str, Any]) -> str:
    return str(response.get("message") or response.get("msg") or "")


def _advertiser_id_from_payload(payload: dict[str, Any]) -> str:
    target_ids = payload.get("target_advertiser_ids")
    if isinstance(target_ids, list) and target_ids:
        return str(target_ids[0] or "")
    return str(payload.get("advertiser_id") or payload.get("target_advertiser_id") or "")


def _is_skip_account_create_project_failure(operation: str, response: dict[str, Any]) -> bool:
    return _is_project_cap_failure(operation, response)


def _is_project_cap_failure(operation: str, response: dict[str, Any]) -> bool:
    if operation != "create_project":
        return False
    message = _response_message(response)
    return _response_code(response) == 40000 and "已创建30个项目" in message


def _response_data(response: dict[str, Any]) -> dict[str, Any]:
    value = response.get("data")
    return dict(value) if isinstance(value, dict) else {}


def _first_response_item(response: dict[str, Any]) -> dict[str, Any]:
    data = _response_data(response)
    rows = data.get("list")
    if isinstance(rows, list):
        for row in rows:
            if isinstance(row, dict):
                return row
    rows = response.get("list")
    if isinstance(rows, list):
        for row in rows:
            if isinstance(row, dict):
                return row
    return {}


def _project_status_values(row: dict[str, Any]) -> set[str]:
    values: set[str] = set()
    for key in ("project_status", "status", "opt_status", "delivery_status", "marketing_status"):
        value = row.get(key)
        if isinstance(value, list):
            values.update(str(item).strip().upper() for item in value if str(item).strip())
        elif str(value or "").strip():
            values.add(str(value).strip().upper())
    return values


def _project_id_from_row(row: dict[str, Any]) -> str:
    for key in ("project_id", "id"):
        value = row.get(key)
        if str(value or "").strip():
            return str(value).strip()
    return ""


def _disabled_project_candidates(response: dict[str, Any], disabled_status_values: set[str]) -> list[str]:
    project_ids: list[str] = []
    seen: set[str] = set()
    for row in _response_items(response):
        project_id = _project_id_from_row(row)
        if not project_id or project_id in seen:
            continue
        if _project_status_values(row) & disabled_status_values:
            project_ids.append(project_id)
            seen.add(project_id)
    return project_ids


def _project_cap_lookup_payload(advertiser_id: str, page_size: int) -> dict[str, Any]:
    return {
        "advertiser_id": advertiser_id,
        "filtering": {"project_status": ["PROJECT_STATUS_DISABLE"]},
        "page": 1,
        "page_size": page_size,
    }


def _project_delete_payload(advertiser_id: str, project_id: str) -> dict[str, Any]:
    return {"advertiser_id": advertiser_id, "project_id": project_id}


def _project_cap_cleanup_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "status": "checked" if records else "not_triggered",
        "attempted_count": len(records),
        "deleted_count": sum(int(record.get("deleted_count") or 0) for record in records),
        "records": records,
    }


def _cleanup_closed_projects_for_project_cap(
    *,
    advertiser_id: str,
    endpoints: dict[str, str],
    policy: dict[str, Any],
    transport: Transport,
    sequence: int,
) -> tuple[dict[str, Any], int, int]:
    cleanup_policy = _project_cap_cleanup_policy(policy)
    result: dict[str, Any] = {
        "advertiser_id": advertiser_id,
        "status": "not_run",
        "deleted_count": 0,
        "deleted_project_ids": [],
        "failed_project_ids": [],
    }
    if not advertiser_id:
        result["status"] = "missing_advertiser_id"
        return result, sequence, 0
    if not bool(cleanup_policy["enabled"]) or int(cleanup_policy["delete_count"]) <= 0:
        result["status"] = "disabled"
        return result, sequence, 0

    call_count = 0
    lookup_call = {
        "sequence": sequence,
        "operation": "lookup_disabled_projects",
        "endpoint": endpoints.get("lookup_disabled_projects", ""),
        "payload": _project_cap_lookup_payload(advertiser_id, int(cleanup_policy["page_size"])),
        "transport_mode": "create_http",
    }
    try:
        lookup_response = transport(lookup_call)
    except RuntimeError as exc:
        result["status"] = "lookup_failed"
        result["message"] = str(exc)
        return result, sequence + 1, call_count + 1
    sequence += 1
    call_count += 1
    result["lookup_response_code"] = _response_code(lookup_response)
    if _response_code(lookup_response) != 0:
        result["status"] = "lookup_failed"
        result["message"] = _response_message(lookup_response)
        return result, sequence, call_count

    candidates = _disabled_project_candidates(
        lookup_response,
        set(cleanup_policy["disabled_status_values"]),
    )
    delete_project_ids = candidates[: int(cleanup_policy["delete_count"])]
    result["candidate_count"] = len(candidates)
    result["target_delete_count"] = len(delete_project_ids)
    if not delete_project_ids:
        result["status"] = "no_closed_projects"
        return result, sequence, call_count

    deleted_ids: list[str] = []
    failed_ids: list[str] = []
    for project_id in delete_project_ids:
        delete_call = {
            "sequence": sequence,
            "operation": "delete_project",
            "endpoint": endpoints.get("delete_project", ""),
            "payload": _project_delete_payload(advertiser_id, project_id),
            "transport_mode": "create_http",
        }
        try:
            delete_response = transport(delete_call)
        except RuntimeError:
            sequence += 1
            call_count += 1
            failed_ids.append(project_id)
            continue
        sequence += 1
        call_count += 1
        if _response_code(delete_response) == 0:
            deleted_ids.append(project_id)
        else:
            failed_ids.append(project_id)
    result["deleted_project_ids"] = deleted_ids
    result["failed_project_ids"] = failed_ids
    result["deleted_count"] = len(deleted_ids)
    result["status"] = "deleted" if deleted_ids else "delete_failed"
    return result, sequence, call_count


def _response_items(response: dict[str, Any]) -> list[dict[str, Any]]:
    data = _response_data(response)
    for key in ("list", "rows", "data"):
        rows = data.get(key)
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
    rows = response.get("list")
    if isinstance(rows, list):
        return [row for row in rows if isinstance(row, dict)]
    return []


def _project_id(response: dict[str, Any]) -> str:
    data = _response_data(response)
    return str(data.get("project_id") or response.get("project_id") or "")


def _promotion_id(response: dict[str, Any]) -> str:
    data = _response_data(response)
    return str(data.get("promotion_id") or response.get("promotion_id") or "")


def _target_video_id(response: dict[str, Any]) -> str:
    data = _response_data(response)
    item = _first_response_item(response)
    return str(
        data.get("target_video_id")
        or data.get("video_id")
        or item.get("target_video_id")
        or item.get("video_id")
        or item.get("id")
        or response.get("target_video_id")
        or response.get("video_id")
        or ""
    )


def _target_video_cover_id(response: dict[str, Any]) -> str:
    data = _response_data(response)
    item = _first_response_item(response)
    return str(
        data.get("target_video_cover_id")
        or data.get("video_cover_id")
        or data.get("cover_id")
        or item.get("target_video_cover_id")
        or item.get("video_cover_id")
        or item.get("cover_id")
        or item.get("image_id")
        or response.get("target_video_cover_id")
        or response.get("video_cover_id")
        or response.get("cover_id")
        or ""
    )


def _target_material_item_for_lookup(response: dict[str, Any], lookup_item: dict[str, Any]) -> dict[str, Any]:
    rows = _response_items(response)
    if not rows:
        return _response_data(response)
    material_id = str(lookup_item.get("material_id") or "")
    source_video_id = str(lookup_item.get("source_video_id") or "")
    for row in rows:
        row_material_id = str(row.get("material_id") or row.get("id") or "")
        row_video_id = str(row.get("video_id") or row.get("source_video_id") or row.get("id") or "")
        if material_id and row_material_id == material_id:
            return row
        if source_video_id and row_video_id == source_video_id:
            return row
    return rows[0]


def _target_video_id_from_item(item: dict[str, Any]) -> str:
    return str(item.get("target_video_id") or item.get("video_id") or item.get("id") or "")


def _target_video_cover_id_from_item(item: dict[str, Any]) -> str:
    return str(
        item.get("target_video_cover_id")
        or item.get("video_cover_id")
        or item.get("cover_id")
        or item.get("image_id")
        or ""
    )


def _material_bind_task_id(response: dict[str, Any]) -> str:
    data = _response_data(response)
    return str(
        data.get("task_id")
        or data.get("bind_task_id")
        or response.get("task_id")
        or response.get("bind_task_id")
        or ""
    )


def _safe_response(response: dict[str, Any]) -> dict[str, Any]:
    return {
        "code": _response_code(response),
        "message": _response_message(response),
        "data_keys": sorted(str(key) for key in _response_data(response).keys()),
    }


def _failure(operation: str, index: int, response: dict[str, Any]) -> dict[str, Any]:
    return {
        "operation": operation,
        "index": index,
        "message": _response_message(response),
        "code": _response_code(response),
    }


def _is_recoverable_create_failure(operation: str, failure: dict[str, Any]) -> bool:
    if operation not in {"create_project", "create_unit"}:
        return False
    message = _response_message(failure) or str(failure.get("error") or "")
    if any(fragment in message for fragment in ("transient network error", "Connection reset", "网络异常", "timed out", "timeout")):
        return True
    return _response_code(failure) in {-1}


def _recovery_lookup_operation(operation: str) -> str:
    if operation == "create_project":
        return "lookup_existing_project"
    if operation == "create_unit":
        return "lookup_existing_unit"
    return ""


def _recovery_lookup_payload(operation: str, payload: dict[str, Any]) -> dict[str, Any]:
    if operation == "create_project":
        return {
            "advertiser_id": str(payload.get("advertiser_id") or ""),
            "name": str(payload.get("name") or ""),
        }
    if operation == "create_unit":
        return {
            "advertiser_id": str(payload.get("advertiser_id") or ""),
            "project_id": str(payload.get("project_id") or ""),
            "name": str(payload.get("name") or ""),
        }
    return {}


def _row_name(row: dict[str, Any], operation: str) -> str:
    if operation == "create_project":
        return str(row.get("project_name") or row.get("name") or "")
    if operation == "create_unit":
        return str(row.get("promotion_name") or row.get("name") or "")
    return ""


def _row_provider_id(row: dict[str, Any], operation: str) -> str:
    if operation == "create_project":
        return str(row.get("project_id") or row.get("id") or "")
    if operation == "create_unit":
        return str(row.get("promotion_id") or row.get("id") or "")
    return ""


def _existing_create_response(operation: str, lookup_response: dict[str, Any], expected_name: str) -> dict[str, Any]:
    for row in _response_items(lookup_response):
        if _row_name(row, operation) != expected_name:
            continue
        provider_id = _row_provider_id(row, operation)
        if not provider_id:
            continue
        if operation == "create_project":
            return {"code": 0, "message": "recovered_existing_project", "data": {"project_id": provider_id}}
        if operation == "create_unit":
            return {"code": 0, "message": "recovered_existing_unit", "data": {"promotion_id": provider_id}}
    return {}


def _runner_failure_result(
    *,
    operation: str,
    index: int,
    message: str,
    code: int,
    ordered_steps: list[dict[str, Any]],
    provider_id_records: list[dict[str, Any]],
    material_bind_records: list[dict[str, Any]],
    transport_call_count: int,
    skipped_provider_id_records: list[dict[str, Any]],
    skipped_material_bind_records: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "ok": False,
        "status": "create_http_failed",
        "blocking_reasons": [],
        "ordered_steps": ordered_steps,
        "provider_id_records": provider_id_records,
        "material_bind_records": material_bind_records,
        "transport_call_count": transport_call_count,
        "external_api_calls": transport_call_count,
        "failure": {
            "operation": operation,
            "index": index,
            "message": message,
            "code": code,
        },
        "idempotency": _idempotency_summary(
            skipped_provider_id_records=skipped_provider_id_records,
            skipped_material_bind_records=skipped_material_bind_records,
        ),
    }


def _record_provider_id(
    *,
    db_path: str | Path,
    create_execute_artifact: dict[str, Any],
    operation: str,
    index: int,
    response: dict[str, Any],
    request_payload: dict[str, Any] | None = None,
) -> dict[str, Any] | list[dict[str, Any]] | None:
    summary = _summary(create_execute_artifact)
    if operation == "lookup_target_material":
        payload = request_payload if isinstance(request_payload, dict) else {}
        lookup_items = payload.get("lookup_items") if isinstance(payload.get("lookup_items"), list) else []
        if not lookup_items:
            lookup_items = [
                {
                    "target_advertiser_id": str(payload.get("target_advertiser_id") or payload.get("advertiser_id") or ""),
                    "source_video_id": str(payload.get("source_video_id") or ""),
                    "material_id": str(payload.get("material_id") or ""),
                }
            ]
        records = _target_material_records(create_execute_artifact)
        results: list[dict[str, Any]] = []
        for lookup_item in lookup_items:
            source_video_id = str(lookup_item.get("source_video_id") or "")
            target_advertiser_id = str(
                lookup_item.get("target_advertiser_id") or lookup_item.get("advertiser_id") or payload.get("target_advertiser_id") or payload.get("advertiser_id") or ""
            )
            expected_local_keys = {
                "target_video": f"target_video:{target_advertiser_id}:{source_video_id}",
                "target_video_cover": f"target_video_cover:{target_advertiser_id}:{source_video_id}",
            }
            item = _target_material_item_for_lookup(response, lookup_item)
            provider_ids = {
                "target_video": _target_video_id_from_item(item),
                "target_video_cover": _target_video_cover_id_from_item(item),
            }
            matching_records = [
                row
                for row in records
                if str(row.get("local_key") or "") == expected_local_keys.get(str(row.get("entity_type") or ""), "")
            ]
            for row in matching_records:
                entity_type = str(row.get("entity_type") or "")
                local_key = str(row.get("local_key") or "")
                provider_id = provider_ids.get(entity_type, "")
                if not local_key or not provider_id:
                    results.append(
                        {
                            "status": "missing_provider_id",
                            "entity_type": entity_type,
                            "local_key": local_key,
                            "provider_id": provider_id,
                            "execution_enabled": False,
                            "external_api_calls": 0,
                            "actions": [],
                        }
                    )
                    continue
                results.append(
                    record_create_provider_id(
                        db_path=db_path,
                        entity_type=entity_type,
                        local_key=local_key,
                        provider_id=provider_id,
                        plan_id=str(summary.get("plan_id") or ""),
                        request_id=str(summary.get("request_id") or ""),
                        advertiser_id="",
                        parent_local_key="",
                        source_workflow="create_live_execute_once",
                        response_payload=_safe_response(response),
                    )
                )
        return results
    if operation == "create_project":
        provider_id = _project_id(response)
        entity_type = "project"
    elif operation == "create_unit":
        provider_id = _promotion_id(response)
        entity_type = "promotion"
    else:
        return None
    row = _record_for_operation(create_execute_artifact, operation, index)
    local_key = str(row.get("local_key") or "")
    if not local_key or not provider_id:
        return {
            "status": "missing_provider_id",
            "entity_type": entity_type,
            "local_key": local_key,
            "provider_id": provider_id,
            "execution_enabled": False,
            "external_api_calls": 0,
            "actions": [],
        }
    return record_create_provider_id(
        db_path=db_path,
        entity_type=entity_type,
        local_key=local_key,
        provider_id=provider_id,
        plan_id=str(summary.get("plan_id") or ""),
        request_id=str(summary.get("request_id") or ""),
        advertiser_id=str(row.get("advertiser_id") or ""),
        parent_local_key=str(row.get("parent_local_key") or ""),
        source_workflow="create_live_execute_once",
        response_payload=_safe_response(response),
    )


def _split_existing_provider_ids(
    *,
    db_path: str | Path,
    create_execute_artifact: dict[str, Any],
    operation: str,
    drafts: list[dict[str, Any]],
) -> tuple[list[tuple[int, dict[str, Any]]], list[dict[str, Any]]]:
    entity_type = _entity_type(operation)
    if not entity_type:
        return [(index, draft) for index, draft in enumerate(drafts)], []
    pending: list[tuple[int, dict[str, Any]]] = []
    skipped: list[dict[str, Any]] = []
    for index, draft in enumerate(drafts):
        record = _record_for_operation(create_execute_artifact, operation, index)
        local_key = str(record.get("local_key") or "")
        provider_id = _existing_provider_id(db_path=db_path, entity_type=entity_type, local_key=local_key)
        if provider_id:
            skipped.append(
                {
                    "operation": operation,
                    "index": index,
                    "entity_type": entity_type,
                    "local_key": local_key,
                    "provider_id": provider_id,
                    "status": "skipped_existing_provider_id",
                }
            )
        else:
            pending.append((index, draft))
    return pending, skipped


def _split_existing_material_binds(
    *,
    db_path: str | Path,
    drafts: list[dict[str, Any]],
) -> tuple[list[tuple[int, dict[str, Any]]], list[dict[str, Any]]]:
    pending: list[tuple[int, dict[str, Any]]] = []
    skipped: list[dict[str, Any]] = []
    for index, draft in enumerate(drafts):
        payload = draft.get("payload") if isinstance(draft.get("payload"), dict) else {}
        existing = existing_material_bind_result(db_path=db_path, payload=payload)
        if existing is None:
            pending.append((index, draft))
            continue
        skipped.append(
            {
                "operation": "bind_material",
                "index": index,
                "bind_key": str(existing.get("bind_key") or ""),
                "provider_task_id": str(existing.get("provider_task_id") or ""),
                "status": "skipped_existing_material_bind",
            }
        )
    return pending, skipped


def _split_existing_target_materials(
    *,
    db_path: str | Path,
    create_execute_artifact: dict[str, Any],
    drafts: list[dict[str, Any]],
) -> tuple[list[tuple[int, dict[str, Any]]], list[dict[str, Any]]]:
    records = _target_material_records(create_execute_artifact)
    pending: list[tuple[int, dict[str, Any]]] = []
    skipped: list[dict[str, Any]] = []
    for index, draft in enumerate(drafts):
        payload = draft.get("payload") if isinstance(draft.get("payload"), dict) else {}
        source_video_id = str(payload.get("source_video_id") or "")
        target_advertiser_id = str(payload.get("target_advertiser_id") or payload.get("advertiser_id") or "")
        expected_local_keys = {
            "target_video": f"target_video:{target_advertiser_id}:{source_video_id}",
            "target_video_cover": f"target_video_cover:{target_advertiser_id}:{source_video_id}",
        }
        record_pair = [
            row
            for row in records
            if str(row.get("local_key") or "") == expected_local_keys.get(str(row.get("entity_type") or ""), "")
        ]
        existing_rows: list[dict[str, Any]] = []
        for row in record_pair:
            entity_type = str(row.get("entity_type") or "")
            local_key = str(row.get("local_key") or "")
            provider_id = _existing_provider_id(db_path=db_path, entity_type=entity_type, local_key=local_key)
            if provider_id:
                existing_rows.append(
                    {
                        "operation": "lookup_target_material",
                        "index": index,
                        "entity_type": entity_type,
                        "local_key": local_key,
                        "provider_id": provider_id,
                        "status": "skipped_existing_provider_id",
                    }
                )
        if record_pair and len(existing_rows) == len(record_pair):
            skipped.extend(existing_rows)
        else:
            pending.append((index, draft))
    return pending, skipped


def _record_material_bind(
    *,
    db_path: str | Path,
    create_execute_artifact: dict[str, Any],
    payload: dict[str, Any],
    response: dict[str, Any],
) -> dict[str, Any]:
    summary = _summary(create_execute_artifact)
    return record_create_material_bind_from_payload(
        db_path=db_path,
        payload=payload,
        provider_task_id=_material_bind_task_id(response),
        plan_id=str(summary.get("plan_id") or ""),
        request_id=str(summary.get("request_id") or ""),
        source_workflow="create_live_execute_once",
        response_payload=_safe_response(response),
    )


def _idempotency_summary(
    *,
    skipped_provider_id_records: list[dict[str, Any]],
    skipped_material_bind_records: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "status": "checked",
        "skipped_existing_provider_id_count": len(skipped_provider_id_records),
        "skipped_provider_id_records": skipped_provider_id_records,
        "skipped_existing_material_bind_count": len(skipped_material_bind_records),
        "skipped_material_bind_records": skipped_material_bind_records,
    }


def _batch_target_material_lookup_drafts(
    pending: list[tuple[int, dict[str, Any]]],
    resolved_drafts: list[dict[str, Any]],
    *,
    batch_size: int = 20,
) -> tuple[list[tuple[int, dict[str, Any]]], list[dict[str, Any]]]:
    batches: list[tuple[int, dict[str, Any]]] = []
    batch_drafts: list[dict[str, Any]] = []
    current_key = ""
    current: list[dict[str, Any]] = []
    current_first_index = 0

    def flush() -> None:
        nonlocal current, current_key, current_first_index
        if not current:
            return
        target_advertiser_id = current_key
        material_ids = [str(item.get("material_id") or "") for item in current if str(item.get("material_id") or "")]
        source_video_ids = [
            str(item.get("source_video_id") or "") for item in current if str(item.get("source_video_id") or "")
        ]
        payload: dict[str, Any] = {
            "target_advertiser_id": target_advertiser_id,
            "advertiser_id": target_advertiser_id,
            "lookup_items": list(current),
        }
        if material_ids:
            payload["material_ids"] = material_ids
        if source_video_ids:
            payload["source_video_ids"] = source_video_ids
        batches.append((current_first_index, {"operation": "lookup_target_material", "payload": payload}))
        batch_drafts.append({"operation": "lookup_target_material", "payload": payload})
        current = []
        current_key = ""

    for offset, draft in enumerate(resolved_drafts):
        payload = draft.get("payload") if isinstance(draft.get("payload"), dict) else {}
        target_advertiser_id = str(payload.get("target_advertiser_id") or payload.get("advertiser_id") or "")
        item = {
            "target_advertiser_id": target_advertiser_id,
            "source_video_id": str(payload.get("source_video_id") or ""),
            "material_id": str(payload.get("material_id") or ""),
        }
        if not current or current_key != target_advertiser_id or len(current) >= batch_size:
            flush()
            current_key = target_advertiser_id
            current_first_index = pending[offset][0]
        current.append(item)
    flush()
    return batches, batch_drafts


def _resumable_create_http_run(
    *,
    create_execute_artifact: dict[str, Any],
    policy: dict[str, Any],
    db_path: str | Path,
    transport: Transport,
) -> dict[str, Any]:
    endpoints = _endpoints(policy)
    provider_id_records: list[dict[str, Any]] = []
    material_bind_records: list[dict[str, Any]] = []
    skipped_provider_id_records: list[dict[str, Any]] = []
    skipped_material_bind_records: list[dict[str, Any]] = []
    skipped_account_records: list[dict[str, Any]] = []
    skipped_account_ids: set[str] = set()
    project_cap_cleanup_records: list[dict[str, Any]] = []
    ordered_steps: list[dict[str, Any]] = []
    transport_call_count = 0
    sequence = 0

    for operation in OPERATION_ORDER:
        drafts = _drafts_for_operation(create_execute_artifact, operation)
        if not drafts:
            continue
        if operation == "bind_material":
            pending, skipped_binds = _split_existing_material_binds(db_path=db_path, drafts=drafts)
            skipped_material_bind_records.extend(skipped_binds)
            skipped = skipped_binds
            skipped_status = "skipped_existing_material_bind"
        elif operation == "lookup_target_material":
            pending, skipped = _split_existing_target_materials(
                db_path=db_path,
                create_execute_artifact=create_execute_artifact,
                drafts=drafts,
            )
            skipped_provider_id_records.extend(skipped)
            skipped_status = "skipped_existing_provider_id"
        else:
            pending, skipped = _split_existing_provider_ids(
                db_path=db_path,
                create_execute_artifact=create_execute_artifact,
                operation=operation,
                drafts=drafts,
            )
            skipped_provider_id_records.extend(skipped)
            skipped_status = "skipped_existing_provider_id"
        if drafts and not pending:
            ordered_steps.append(
                {
                    "operation": operation,
                    "planned_count": len(drafts),
                    "status": skipped_status,
                    "test_transport_call_count": 0,
                }
            )
            continue

        operation_skipped_account_count = 0
        if skipped_account_ids:
            filtered_pending: list[tuple[int, dict[str, Any]]] = []
            for original_index, draft in pending:
                payload = draft.get("payload") if isinstance(draft.get("payload"), dict) else {}
                advertiser_id = _advertiser_id_from_payload(payload)
                if advertiser_id and advertiser_id in skipped_account_ids:
                    operation_skipped_account_count += 1
                    skipped_account_records.append(
                        {
                            "operation": operation,
                            "index": original_index,
                            "advertiser_id": advertiser_id,
                            "status": "skipped_account_after_create_project_failure",
                        }
                    )
                    continue
                filtered_pending.append((original_index, draft))
            pending = filtered_pending
            if drafts and not pending:
                ordered_steps.append(
                    {
                        "operation": operation,
                        "planned_count": len(drafts),
                        "status": "completed_with_skipped_accounts",
                        "test_transport_call_count": 0,
                        "skipped_account_count": operation_skipped_account_count,
                    }
                )
                continue

        pending_drafts = [draft for _index, draft in pending]
        resolution = resolve_provider_payload_drafts(db_path=db_path, provider_payload_drafts=pending_drafts)
        if int(resolution.get("unresolved_count") or 0):
            return {
                "ok": False,
                "status": "create_http_failed",
                "blocking_reasons": ["lookup placeholders unresolved before operation"],
                "ordered_steps": ordered_steps,
                "provider_id_records": provider_id_records,
                "material_bind_records": material_bind_records,
                "transport_call_count": transport_call_count,
                "external_api_calls": transport_call_count,
                "failure": {
                    "operation": operation,
                    "index": 0,
                    "message": "lookup placeholders unresolved before operation",
                    "code": -1,
                },
                "idempotency": _idempotency_summary(
                    skipped_provider_id_records=skipped_provider_id_records,
                    skipped_material_bind_records=skipped_material_bind_records,
                ),
                "project_cap_cleanup": _project_cap_cleanup_summary(project_cap_cleanup_records),
            }

        resolved_drafts = _rows(resolution.get("resolved_provider_payload_drafts"))
        if operation == "lookup_target_material":
            pending, resolved_drafts = _batch_target_material_lookup_drafts(pending, resolved_drafts)
        operation_call_count = 0
        for offset, draft in enumerate(resolved_drafts):
            original_index = pending[offset][0]
            payload = draft.get("payload") if isinstance(draft.get("payload"), dict) else {}
            advertiser_id = _advertiser_id_from_payload(payload)
            if advertiser_id and advertiser_id in skipped_account_ids:
                operation_skipped_account_count += 1
                skipped_account_records.append(
                    {
                        "operation": operation,
                        "index": original_index,
                        "advertiser_id": advertiser_id,
                        "status": "skipped_account_after_create_project_failure",
                    }
                )
                continue
            create_retry_count = 0
            max_create_retry_count = int(_runner_policy(policy).get("recover_create_after_lookup_max_retries") or 1)
            while True:
                call = {
                    "sequence": sequence,
                    "operation": operation,
                    "endpoint": endpoints.get(operation, ""),
                    "payload": payload,
                    "transport_mode": "create_http",
                }
                try:
                    response = transport(call)
                except RuntimeError as exc:
                    sequence += 1
                    transport_call_count += 1
                    operation_call_count += 1
                    failure_response = {"code": -1, "message": str(exc)}
                    recovered_response: dict[str, Any] = {}
                    if _is_recoverable_create_failure(operation, failure_response):
                        lookup_operation = _recovery_lookup_operation(operation)
                        lookup_payload = _recovery_lookup_payload(operation, payload)
                        if lookup_operation:
                            lookup_call = {
                                "sequence": sequence,
                                "operation": lookup_operation,
                                "endpoint": endpoints.get(lookup_operation, ""),
                                "payload": lookup_payload,
                                "transport_mode": "create_http",
                            }
                            try:
                                lookup_response = transport(lookup_call)
                            except RuntimeError as lookup_exc:
                                sequence += 1
                                transport_call_count += 1
                                operation_call_count += 1
                                return _runner_failure_result(
                                    operation=lookup_operation,
                                    index=original_index,
                                    message=str(lookup_exc),
                                    code=-1,
                                    ordered_steps=ordered_steps,
                                    provider_id_records=provider_id_records,
                                    material_bind_records=material_bind_records,
                                    transport_call_count=transport_call_count,
                                    skipped_provider_id_records=skipped_provider_id_records,
                                    skipped_material_bind_records=skipped_material_bind_records,
                                )
                            sequence += 1
                            transport_call_count += 1
                            operation_call_count += 1
                            if _response_code(lookup_response) == 0:
                                recovered_response = _existing_create_response(
                                    operation,
                                    lookup_response,
                                    str(lookup_payload.get("name") or ""),
                                )
                    if recovered_response:
                        response = recovered_response
                    elif create_retry_count < max_create_retry_count and _is_recoverable_create_failure(
                        operation, failure_response
                    ):
                        create_retry_count += 1
                        continue
                    else:
                        return {
                            "ok": False,
                            "status": "create_http_failed",
                            "blocking_reasons": [],
                            "ordered_steps": ordered_steps,
                            "provider_id_records": provider_id_records,
                            "material_bind_records": material_bind_records,
                            "transport_call_count": transport_call_count,
                            "external_api_calls": transport_call_count,
                            "failure": {
                                "operation": operation,
                                "index": original_index,
                                "message": str(exc),
                                "code": -1,
                            },
                            "idempotency": _idempotency_summary(
                                skipped_provider_id_records=skipped_provider_id_records,
                                skipped_material_bind_records=skipped_material_bind_records,
                            ),
                        }
                else:
                    sequence += 1
                    transport_call_count += 1
                    operation_call_count += 1
                    if _response_code(response) != 0 and _is_recoverable_create_failure(operation, response):
                        recovered_response = {}
                        lookup_operation = _recovery_lookup_operation(operation)
                        lookup_payload = _recovery_lookup_payload(operation, payload)
                        if lookup_operation:
                            lookup_call = {
                                "sequence": sequence,
                                "operation": lookup_operation,
                                "endpoint": endpoints.get(lookup_operation, ""),
                                "payload": lookup_payload,
                                "transport_mode": "create_http",
                            }
                            try:
                                lookup_response = transport(lookup_call)
                            except RuntimeError as lookup_exc:
                                sequence += 1
                                transport_call_count += 1
                                operation_call_count += 1
                                return _runner_failure_result(
                                    operation=lookup_operation,
                                    index=original_index,
                                    message=str(lookup_exc),
                                    code=-1,
                                    ordered_steps=ordered_steps,
                                    provider_id_records=provider_id_records,
                                    material_bind_records=material_bind_records,
                                    transport_call_count=transport_call_count,
                                    skipped_provider_id_records=skipped_provider_id_records,
                                    skipped_material_bind_records=skipped_material_bind_records,
                                )
                            sequence += 1
                            transport_call_count += 1
                            operation_call_count += 1
                            if _response_code(lookup_response) == 0:
                                recovered_response = _existing_create_response(
                                    operation,
                                    lookup_response,
                                    str(lookup_payload.get("name") or ""),
                                )
                        if recovered_response:
                            response = recovered_response
                        elif create_retry_count < max_create_retry_count:
                            create_retry_count += 1
                            continue
                break
            if _response_code(response) != 0 and _is_project_cap_failure(operation, response):
                cleanup_result, sequence, cleanup_call_count = _cleanup_closed_projects_for_project_cap(
                    advertiser_id=advertiser_id,
                    endpoints=endpoints,
                    policy=policy,
                    transport=transport,
                    sequence=sequence,
                )
                transport_call_count += cleanup_call_count
                operation_call_count += cleanup_call_count
                project_cap_cleanup_records.append(cleanup_result)
                if int(cleanup_result.get("deleted_count") or 0) > 0:
                    retry_call = {
                        "sequence": sequence,
                        "operation": operation,
                        "endpoint": endpoints.get(operation, ""),
                        "payload": payload,
                        "transport_mode": "create_http",
                    }
                    try:
                        response = transport(retry_call)
                    except RuntimeError as exc:
                        sequence += 1
                        transport_call_count += 1
                        operation_call_count += 1
                        cleanup_result["status"] = "deleted_retry_failed"
                        cleanup_result["retry_message"] = str(exc)
                        return {
                            "ok": False,
                            "status": "create_http_failed",
                            "blocking_reasons": [],
                            "ordered_steps": ordered_steps,
                            "provider_id_records": provider_id_records,
                            "material_bind_records": material_bind_records,
                            "transport_call_count": transport_call_count,
                            "external_api_calls": transport_call_count,
                            "failure": {
                                "operation": operation,
                                "index": original_index,
                                "message": str(exc),
                                "code": -1,
                            },
                            "idempotency": _idempotency_summary(
                                skipped_provider_id_records=skipped_provider_id_records,
                                skipped_material_bind_records=skipped_material_bind_records,
                            ),
                            "project_cap_cleanup": _project_cap_cleanup_summary(project_cap_cleanup_records),
                        }
                    sequence += 1
                    transport_call_count += 1
                    operation_call_count += 1
                    call = retry_call
                    cleanup_result["retry_response_code"] = _response_code(response)
                    cleanup_result["retry_message"] = _response_message(response)
                    cleanup_result["status"] = (
                        "deleted_and_retried" if _response_code(response) == 0 else "deleted_retry_failed"
                    )
            if _response_code(response) != 0:
                if _is_skip_account_create_project_failure(operation, response):
                    if advertiser_id:
                        skipped_account_ids.add(advertiser_id)
                    skipped_account_records.append(
                        {
                            "operation": operation,
                            "index": original_index,
                            "advertiser_id": advertiser_id,
                            "status": "skipped_account_after_create_project_failure",
                            "code": _response_code(response),
                            "message": _response_message(response),
                        }
                    )
                    operation_skipped_account_count += 1
                    continue
                return {
                    "ok": False,
                    "status": "create_http_failed",
                    "blocking_reasons": [],
                    "ordered_steps": ordered_steps,
                    "provider_id_records": provider_id_records,
                    "material_bind_records": material_bind_records,
                    "transport_call_count": transport_call_count,
                    "external_api_calls": transport_call_count,
                    "failure": _failure(operation, original_index, response),
                    "idempotency": _idempotency_summary(
                            skipped_provider_id_records=skipped_provider_id_records,
                            skipped_material_bind_records=skipped_material_bind_records,
                        ),
                    "project_cap_cleanup": _project_cap_cleanup_summary(project_cap_cleanup_records),
                    "skipped_accounts": skipped_account_records,
                }
            record_result = _record_provider_id(
                db_path=db_path,
                create_execute_artifact=create_execute_artifact,
                operation=operation,
                index=original_index,
                response=response,
                request_payload=call["payload"],
            )
            records = record_result if isinstance(record_result, list) else [record_result] if record_result is not None else []
            for record in records:
                provider_id_records.append(record)
                if str(record.get("status") or "") != "recorded":
                    return {
                        "ok": False,
                        "status": "create_http_failed",
                        "blocking_reasons": [],
                        "ordered_steps": ordered_steps,
                        "provider_id_records": provider_id_records,
                        "material_bind_records": material_bind_records,
                        "transport_call_count": transport_call_count,
                        "external_api_calls": transport_call_count,
                        "failure": {
                            "operation": operation,
                            "index": original_index,
                            "message": str(record.get("status") or "provider id record failed"),
                            "code": -1,
                        },
                        "idempotency": _idempotency_summary(
                            skipped_provider_id_records=skipped_provider_id_records,
                            skipped_material_bind_records=skipped_material_bind_records,
                        ),
                        "project_cap_cleanup": _project_cap_cleanup_summary(project_cap_cleanup_records),
                    }
            if operation == "bind_material":
                bind_payload = draft.get("payload") if isinstance(draft.get("payload"), dict) else {}
                material_bind_records.append(
                    _record_material_bind(
                        db_path=db_path,
                        create_execute_artifact=create_execute_artifact,
                        payload=bind_payload,
                        response=response,
                    )
                )
        step = {
            "operation": operation,
            "planned_count": len(drafts),
            "status": "completed_with_skipped_accounts" if operation_skipped_account_count else "completed",
            "test_transport_call_count": operation_call_count,
        }
        if operation_skipped_account_count:
            step["skipped_account_count"] = operation_skipped_account_count
        ordered_steps.append(step)

    return {
        "ok": True,
        "status": "create_http_completed",
        "blocking_reasons": [],
        "ordered_steps": ordered_steps,
        "provider_id_records": provider_id_records,
        "material_bind_records": material_bind_records,
        "transport_call_count": transport_call_count,
        "external_api_calls": transport_call_count,
        "failure": None,
        "skipped_accounts": skipped_account_records,
        "project_cap_cleanup": _project_cap_cleanup_summary(project_cap_cleanup_records),
        "idempotency": _idempotency_summary(
            skipped_provider_id_records=skipped_provider_id_records,
            skipped_material_bind_records=skipped_material_bind_records,
        ),
    }


def _direct_blocking_reasons(
    *,
    create_execute_artifact: dict[str, Any],
    policy: dict[str, Any],
    runtime: dict[str, Any],
    transport: Transport | None,
) -> list[str]:
    reasons = _pre_transport_blocking_reasons(runtime, transport)
    if not bool(_live_api_policy(policy).get("enabled", False)):
        reasons.append("policy.create_execute.live_api.enabled is false")
    if not bool(_payload_schema_policy(policy).get("live_payload_generation_enabled", False)):
        reasons.append("policy.create_execute.payload_schema.live_payload_generation_enabled is false")
    if not bool(_runner_policy(policy).get("allow_create_http_transport", False)):
        reasons.append("policy.create_live_execute_once.allow_create_http_transport is false")
    if bool(_runner_policy(policy).get("require_provider_field_mapping", False)):
        mapping_contract = _provider_payload_mapping_contract(create_execute_artifact)
        if str(mapping_contract.get("status") or "") != "passed":
            reasons.append(
                "create_execute provider payloads must have verified field mapping before live execute"
            )
    if bool(create_execute_artifact.get("execution_enabled", False)):
        reasons.append("create_execute artifact execution_enabled must be false")
    if int(create_execute_artifact.get("external_api_calls") or 0) != 0:
        reasons.append("create_execute artifact external_api_calls must be 0")
    payload_safety = _create_execute_payload_safety(create_execute_artifact)
    if not bool(payload_safety["payloads_non_executable"]):
        reasons.append("create_execute payload drafts must not be executable")
    if not bool(payload_safety["live_payload_count_zero"]):
        reasons.append("create_execute payload drafts must not contain live payload flags")
    if not bool(payload_safety["lookup_placeholders_chain_resolvable"]):
        reasons.append("create_execute payloads contain lookup placeholders that cannot be produced by this fixed chain")
    reasons.extend(_active_launch_violations(create_execute_artifact))
    return reasons


def build_create_live_execute_once_direct(
    *,
    create_execute_artifact: dict[str, Any],
    policy: dict[str, Any],
    runtime: dict[str, Any],
    db_path: str | Path,
    transport: Transport | None = None,
) -> dict[str, Any]:
    blocking_reasons = _direct_blocking_reasons(
        create_execute_artifact=create_execute_artifact,
        policy=policy,
        runtime=runtime,
        transport=transport,
    )
    if blocking_reasons:
        return _blocked_result(
            reason="direct_execute_not_ready",
            blocking_reasons=blocking_reasons,
        )

    runner_result = _resumable_create_http_run(
        create_execute_artifact=create_execute_artifact,
        policy=policy,
        db_path=db_path,
        transport=transport,
    )
    external_api_calls = int(runner_result.get("external_api_calls") or 0)
    execution_attempted = external_api_calls > 0
    ok = bool(runner_result.get("ok", False)) and str(runner_result.get("status") or "") == "create_http_completed"
    return {
        "ok": ok,
        "workflow": "create_live_execute_once",
        "phase": "phase2_preparation",
        "execution_enabled": execution_attempted,
        "live_execute_enabled": execution_attempted,
        "external_api_calls": external_api_calls,
        "status": str(runner_result.get("status") or "blocked"),
        "reason": "",
        "create_execute_summary": _summary(create_execute_artifact),
        "blocking_reasons": list(runner_result.get("blocking_reasons") or []),
        "ordered_steps": list(runner_result.get("ordered_steps") or []),
        "provider_id_records": list(runner_result.get("provider_id_records") or []),
        "material_bind_records": list(runner_result.get("material_bind_records") or []),
        "skipped_accounts": list(runner_result.get("skipped_accounts") or []),
        "project_cap_cleanup": runner_result.get("project_cap_cleanup")
        if isinstance(runner_result.get("project_cap_cleanup"), dict)
        else _project_cap_cleanup_summary([]),
        "transport_call_count": int(runner_result.get("transport_call_count") or 0),
        "idempotency": runner_result.get("idempotency")
        if isinstance(runner_result.get("idempotency"), dict)
        else {
            "status": "not_checked",
            "skipped_existing_provider_id_count": 0,
            "skipped_provider_id_records": [],
            "skipped_existing_material_bind_count": 0,
            "skipped_material_bind_records": [],
        },
        "runner_result": runner_result,
        "failure": runner_result.get("failure"),
        "actions": [],
    }


def run_create_live_execute_once_request(
    request: dict[str, Any],
    *,
    runs_dir: str | Path,
    db_path: str | Path,
    transport: Transport | None = None,
) -> dict[str, Any]:
    cfg = _once_config(request)
    allowed_keys = {"create_execute_artifact", "policy", "runtime"}
    unexpected_keys = sorted(str(key) for key in cfg if key not in allowed_keys)
    if unexpected_keys:
        raise ValueError(f"create live execute once received unexpected options: {', '.join(unexpected_keys)}")
    create_execute = cfg.get("create_execute_artifact")
    if not isinstance(create_execute, dict):
        raise ValueError("create live execute once requires create_execute_artifact")
    policy = cfg.get("policy") if isinstance(cfg.get("policy"), dict) else {}
    runtime = cfg.get("runtime") if isinstance(cfg.get("runtime"), dict) else {}
    payload = build_create_live_execute_once_direct(
        create_execute_artifact=create_execute,
        policy=policy,
        runtime=runtime,
        db_path=db_path,
        transport=transport,
    )
    artifact_path = write_run_artifact(runs_dir, "create_live_execute_once", payload)
    return {**payload, "artifact_path": str(artifact_path)}
