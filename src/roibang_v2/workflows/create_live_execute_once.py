from __future__ import annotations

import json
import sqlite3
import sys
import time
from datetime import datetime, timezone
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
TRANSIENT_POST_RUN_RETRY_CODES = {50000}
RECOVERY_ENDPOINTS = {
    "lookup_existing_project": "/open_api/v3.0/project/list/",
    "lookup_existing_unit": "/open_api/v3.0/promotion/list/",
}
PROJECT_CAP_CLEANUP_ENDPOINTS = {
    "lookup_disabled_projects": "/open_api/v3.0/project/list/",
    "delete_project": "/open_api/v3.0/project/delete/",
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
        "post_run_retry": _default_post_run_retry(),
        "ledger_archive": [],
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


def _lookup_target_material_visibility_wait_policy(policy: dict[str, Any]) -> dict[str, Any]:
    value = _runner_policy(policy).get("lookup_target_material_visibility_wait")
    data = dict(value) if isinstance(value, dict) else {}
    max_retries = data.get("max_retries")
    sleep_seconds = data.get("sleep_seconds")
    return {
        "enabled": bool(data.get("enabled", True)),
        "max_retries": max(0, int(max_retries if max_retries is not None else 6)),
        "sleep_seconds": max(0.0, float(sleep_seconds if sleep_seconds is not None else 5)),
    }


def _progress_policy(policy: dict[str, Any]) -> dict[str, Any]:
    value = _runner_policy(policy).get("progress")
    return dict(value) if isinstance(value, dict) else {}


def _write_progress(
    policy: dict[str, Any],
    *,
    status: str,
    operation: str,
    done: int,
    total: int,
    transport_call_count: int,
    advertiser_id: str = "",
    index: int | None = None,
    message: str = "",
) -> None:
    config = _progress_policy(policy)
    if not bool(config.get("enabled", False)):
        return
    payload: dict[str, Any] = {
        "ok": status != "failed",
        "workflow": "create_live_execute_once",
        "status": status,
        "operation": operation,
        "done": done,
        "total": total,
        "transport_call_count": transport_call_count,
        "external_api_calls": transport_call_count,
        "advertiser_id": advertiser_id,
        "updated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    if index is not None:
        payload["index"] = index
    if message:
        payload["message"] = message

    progress_dir = Path(str(config.get("dir") or "data/runs/create_live_execute_once/progress"))
    progress_dir.mkdir(parents=True, exist_ok=True)
    (progress_dir / "current.json").write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    if bool(config.get("append_jsonl", True)):
        with (progress_dir / "events.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
    if bool(config.get("stderr", True)):
        bits = [
            "[create_live_execute_once]",
            f"operation={operation}",
            f"done={done}/{total}",
            f"status={status}",
            f"calls={transport_call_count}",
        ]
        if advertiser_id:
            bits.append(f"account={advertiser_id}")
        if message:
            bits.append(f"message={message}")
        print(" ".join(bits), file=sys.stderr, flush=True)


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


def _existing_provider_id(
    *,
    db_path: str | Path,
    entity_type: str,
    local_key: str,
    plan_id: str = "",
    request_id: str = "",
) -> str:
    if not str(local_key or "").strip():
        return ""
    where = [
        "entity_type = ?",
        "local_key = ?",
        "status = 'active'",
        "provider_id NOT LIKE 'mock_%'",
        "source_workflow != 'create_mock_execute'",
    ]
    params = [entity_type, local_key]
    if entity_type in {"project", "promotion"}:
        where.append("plan_id = ?")
        where.append("request_id = ?")
        params.extend([str(plan_id), str(request_id)])
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            f"""
            SELECT provider_id
            FROM create_provider_id_ledger
            WHERE {" AND ".join(where)}
            LIMIT 1
            """,
            params,
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


def _is_skip_account_live_step_failure(operation: str, response: dict[str, Any]) -> bool:
    if operation not in {"bind_material", "lookup_target_material", "create_unit"}:
        return False
    return _response_code(response) != 0


def _skip_account_record(
    *,
    operation: str,
    index: int,
    advertiser_id: str,
    response: dict[str, Any],
) -> dict[str, Any]:
    return {
        "operation": operation,
        "index": index,
        "advertiser_id": advertiser_id,
        "status": "skipped_account_after_live_step_failure",
        "code": _response_code(response),
        "message": _response_message(response),
    }


def _default_post_run_retry() -> dict[str, Any]:
    return {
        "status": "not_triggered",
        "attempted_count": 0,
        "recovered_count": 0,
        "failed_count": 0,
        "external_api_calls": 0,
        "records": [],
    }


def _archive_round_project_unit_ids(
    *,
    db_path: str | Path,
    create_execute_artifact: dict[str, Any],
    stage: str,
) -> dict[str, Any]:
    summary = _summary(create_execute_artifact)
    return {
        "stage": stage,
        "status": "plan_scoped_no_archive",
        "archived_count": 0,
        "plan_id": str(summary.get("plan_id") or ""),
        "request_id": str(summary.get("request_id") or ""),
        "entity_types": ["project", "promotion"],
        "execution_enabled": False,
        "external_api_calls": 0,
        "actions": [],
    }


def _post_run_retry_transient_create_units(
    *,
    create_execute_artifact: dict[str, Any],
    policy: dict[str, Any],
    db_path: str | Path,
    endpoints: dict[str, str],
    transport: Transport,
    skipped_account_records: list[dict[str, Any]],
    sequence: int,
    transport_call_count: int,
) -> dict[str, Any]:
    retry_account_ids = {
        str(row.get("advertiser_id") or "")
        for row in skipped_account_records
        if str(row.get("operation") or "") == "create_unit"
        and str(row.get("status") or "") == "skipped_account_after_live_step_failure"
        and int(row.get("code") or 0) in TRANSIENT_POST_RUN_RETRY_CODES
    }
    retry_account_ids.discard("")
    if not retry_account_ids:
        return {**_default_post_run_retry(), "sequence": sequence, "transport_call_count": transport_call_count}

    pending: list[tuple[int, dict[str, Any]]] = []
    summary = _summary(create_execute_artifact)
    for index, draft in enumerate(_drafts_for_operation(create_execute_artifact, "create_unit")):
        payload = draft.get("payload") if isinstance(draft.get("payload"), dict) else {}
        advertiser_id = _advertiser_id_from_payload(payload)
        if advertiser_id not in retry_account_ids:
            continue
        record = _record_for_operation(create_execute_artifact, "create_unit", index)
        local_key = str(record.get("local_key") or "")
        if _existing_provider_id(
            db_path=db_path,
            entity_type="promotion",
            local_key=local_key,
            plan_id=str(summary.get("plan_id") or ""),
            request_id=str(summary.get("request_id") or ""),
        ):
            continue
        pending.append((index, draft))

    if not pending:
        return {
            **_default_post_run_retry(),
            "status": "nothing_missing",
            "sequence": sequence,
            "transport_call_count": transport_call_count,
        }

    resolution = resolve_provider_payload_drafts(
        db_path=db_path,
        provider_payload_drafts=[draft for _index, draft in pending],
        plan_id=str(summary.get("plan_id") or ""),
        request_id=str(summary.get("request_id") or ""),
    )
    if int(resolution.get("unresolved_count") or 0):
        return {
            "status": "blocked_unresolved_lookup",
            "attempted_count": 0,
            "recovered_count": 0,
            "failed_count": len(pending),
            "external_api_calls": 0,
            "records": _rows(resolution.get("unresolved_lookups")),
            "sequence": sequence,
            "transport_call_count": transport_call_count,
        }

    records: list[dict[str, Any]] = []
    provider_id_records: list[dict[str, Any]] = []
    recovered_count = 0
    failed_count = 0
    retry_call_count = 0
    resolved_drafts = _rows(resolution.get("resolved_provider_payload_drafts"))
    for offset, draft in enumerate(resolved_drafts):
        original_index = pending[offset][0]
        payload = draft.get("payload") if isinstance(draft.get("payload"), dict) else {}
        advertiser_id = _advertiser_id_from_payload(payload)
        call = {
            "sequence": sequence,
            "operation": "create_unit",
            "endpoint": endpoints.get("create_unit", ""),
            "payload": payload,
            "transport_mode": "create_http",
            "retry_stage": "post_run_transient_retry",
        }
        _write_progress(
            policy,
            status="retrying",
            operation="create_unit",
            done=retry_call_count,
            total=len(resolved_drafts),
            transport_call_count=transport_call_count,
            advertiser_id=advertiser_id,
            index=original_index,
            message="post_run_transient_retry",
        )
        try:
            response = transport(call)
        except RuntimeError as exc:
            response = {"code": -1, "message": str(exc)}
        sequence += 1
        retry_call_count += 1
        transport_call_count += 1
        if _response_code(response) == 0:
            record_result = _record_provider_id(
                db_path=db_path,
                create_execute_artifact=create_execute_artifact,
                operation="create_unit",
                index=original_index,
                response=response,
                request_payload=payload,
            )
            created_records = (
                record_result
                if isinstance(record_result, list)
                else [record_result]
                if record_result is not None
                else []
            )
            if created_records and all(str(row.get("status") or "") == "recorded" for row in created_records):
                recovered_count += 1
                provider_id_records.extend(created_records)
                records.append(
                    {
                        "operation": "create_unit",
                        "index": original_index,
                        "advertiser_id": advertiser_id,
                        "status": "recovered",
                        "code": 0,
                        "provider_id_records": created_records,
                    }
                )
            else:
                failed_count += 1
                records.append(
                    {
                        "operation": "create_unit",
                        "index": original_index,
                        "advertiser_id": advertiser_id,
                        "status": "record_failed",
                        "code": 0,
                        "provider_id_records": created_records,
                    }
                )
        else:
            failed_count += 1
            records.append(
                {
                    "operation": "create_unit",
                    "index": original_index,
                    "advertiser_id": advertiser_id,
                    "status": "retry_failed",
                    "code": _response_code(response),
                    "message": _response_message(response),
                }
            )
        _write_progress(
            policy,
            status="retrying" if retry_call_count < len(resolved_drafts) else "completed",
            operation="create_unit",
            done=retry_call_count,
            total=len(resolved_drafts),
            transport_call_count=transport_call_count,
            advertiser_id=advertiser_id,
            index=original_index,
        )

    return {
        "status": "completed" if failed_count == 0 else "completed_with_failures",
        "attempted_count": len(resolved_drafts),
        "recovered_count": recovered_count,
        "failed_count": failed_count,
        "external_api_calls": retry_call_count,
        "records": records,
        "provider_id_records": provider_id_records,
        "sequence": sequence,
        "transport_call_count": transport_call_count,
    }


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
    advertiser_value: int | str = int(advertiser_id) if str(advertiser_id).isdigit() else advertiser_id
    project_value: int | str = int(project_id) if str(project_id).isdigit() else project_id
    return {"advertiser_id": advertiser_value, "project_ids": [project_value]}


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
    if not material_id and not source_video_id and len(rows) == 1:
        return rows[0]
    return {}


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
        summary = _summary(create_execute_artifact)
        provider_id = _existing_provider_id(
            db_path=db_path,
            entity_type=entity_type,
            local_key=local_key,
            plan_id=str(summary.get("plan_id") or ""),
            request_id=str(summary.get("request_id") or ""),
        )
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


def _payload_list(payload: dict[str, Any], *names: str) -> list[str]:
    for name in names:
        value = payload.get(name)
        if isinstance(value, list):
            return [str(item) for item in value if str(item or "").strip()]
    return []


def _lookup_items_by_target_and_video(create_execute_artifact: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    items: dict[tuple[str, str], dict[str, Any]] = {}
    for draft in _drafts_for_operation(create_execute_artifact, "lookup_target_material"):
        payload = draft.get("payload") if isinstance(draft.get("payload"), dict) else {}
        target_advertiser_id = str(payload.get("target_advertiser_id") or payload.get("advertiser_id") or "")
        source_video_id = str(payload.get("source_video_id") or "")
        if not target_advertiser_id or not source_video_id:
            continue
        items[(target_advertiser_id, source_video_id)] = {
            "target_advertiser_id": target_advertiser_id,
            "source_video_id": source_video_id,
            "material_id": str(payload.get("material_id") or ""),
        }
    return items


def _target_material_local_keys(target_advertiser_id: str, source_video_id: str) -> dict[str, str]:
    return {
        "target_video": f"target_video:{target_advertiser_id}:{source_video_id}",
        "target_video_cover": f"target_video_cover:{target_advertiser_id}:{source_video_id}",
    }


def _target_material_pair_exists(
    *,
    db_path: str | Path,
    target_advertiser_id: str,
    source_video_id: str,
) -> bool:
    keys = _target_material_local_keys(target_advertiser_id, source_video_id)
    return bool(
        _existing_provider_id(db_path=db_path, entity_type="target_video", local_key=keys["target_video"])
        and _existing_provider_id(db_path=db_path, entity_type="target_video_cover", local_key=keys["target_video_cover"])
    )


def _target_material_records_exist(
    *,
    db_path: str | Path,
    create_execute_artifact: dict[str, Any],
    target_advertiser_id: str,
    source_video_id: str,
) -> bool:
    keys = _target_material_local_keys(target_advertiser_id, source_video_id)
    record_pair = [
        row
        for row in _target_material_records(create_execute_artifact)
        if str(row.get("local_key") or "") == keys.get(str(row.get("entity_type") or ""), "")
    ]
    if not record_pair:
        return _target_material_pair_exists(
            db_path=db_path,
            target_advertiser_id=target_advertiser_id,
            source_video_id=source_video_id,
        )
    return all(
        bool(
            _existing_provider_id(
                db_path=db_path,
                entity_type=str(row.get("entity_type") or ""),
                local_key=str(row.get("local_key") or ""),
            )
        )
        for row in record_pair
    )


def _missing_provider_id_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [row for row in records if str(row.get("status") or "") == "missing_provider_id"]


def _record_existing_target_material_lookup(
    *,
    db_path: str | Path,
    create_execute_artifact: dict[str, Any],
    response: dict[str, Any],
    lookup_items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    record_result = _record_provider_id(
        db_path=db_path,
        create_execute_artifact=create_execute_artifact,
        operation="lookup_target_material",
        index=0,
        response=response,
        request_payload={"lookup_items": lookup_items},
    )
    records = record_result if isinstance(record_result, list) else [record_result] if record_result else []
    return [record for record in records if str(record.get("status") or "") == "recorded"]


def _precheck_existing_target_materials_for_bind(
    *,
    db_path: str | Path,
    create_execute_artifact: dict[str, Any],
    pending: list[tuple[int, dict[str, Any]]],
    endpoints: dict[str, str],
    transport: Transport,
    sequence: int,
) -> dict[str, Any]:
    lookup_items_by_key = _lookup_items_by_target_and_video(create_execute_artifact)
    pending_after_precheck: list[tuple[int, dict[str, Any]]] = []
    skipped: list[dict[str, Any]] = []
    material_bind_records: list[dict[str, Any]] = []
    provider_id_records: list[dict[str, Any]] = []
    call_count = 0

    for original_index, draft in pending:
        payload = draft.get("payload") if isinstance(draft.get("payload"), dict) else {}
        target_advertiser_ids = _payload_list(payload, "target_advertiser_ids")
        source_video_ids = _payload_list(payload, "source_video_ids", "video_ids")
        if not target_advertiser_ids or not source_video_ids:
            pending_after_precheck.append((original_index, draft))
            continue

        lookup_items: list[dict[str, Any]] = []
        for target_advertiser_id in target_advertiser_ids:
            for source_video_id in source_video_ids:
                item = lookup_items_by_key.get((target_advertiser_id, source_video_id)) or {
                    "target_advertiser_id": target_advertiser_id,
                    "source_video_id": source_video_id,
                    "material_id": "",
                }
                lookup_items.append(dict(item))

        if not lookup_items:
            pending_after_precheck.append((original_index, draft))
            continue

        existing_source_video_ids = [
            source_video_id
            for source_video_id in source_video_ids
            if all(
                _target_material_records_exist(
                    db_path=db_path,
                    create_execute_artifact=create_execute_artifact,
                    target_advertiser_id=target_advertiser_id,
                    source_video_id=source_video_id,
                )
                for target_advertiser_id in target_advertiser_ids
            )
        ]
        missing_source_video_ids = [item for item in source_video_ids if item not in set(existing_source_video_ids)]
        if existing_source_video_ids:
            existing_payload = {
                **payload,
                "source_video_ids": existing_source_video_ids,
                "video_ids": existing_source_video_ids,
            }
            material_bind_records.append(
                _record_material_bind(
                    db_path=db_path,
                    create_execute_artifact=create_execute_artifact,
                    payload=existing_payload,
                    response={"code": 0, "message": "existing_target_material", "data": {"task_id": "existing_target_material"}},
                )
            )
            skipped.append(
                {
                    "operation": "bind_material",
                    "index": original_index,
                    "target_advertiser_ids": target_advertiser_ids,
                    "source_video_ids": existing_source_video_ids,
                    "status": "skipped_existing_target_material",
                }
            )
        if not missing_source_video_ids:
            continue
        lookup_items = [
            item
            for item in lookup_items
            if str(item.get("source_video_id") or "") in set(missing_source_video_ids)
        ]

        material_ids = [str(item.get("material_id") or "") for item in lookup_items if str(item.get("material_id") or "")]
        source_video_id_filters = [
            str(item.get("source_video_id") or "") for item in lookup_items if str(item.get("source_video_id") or "")
        ]
        lookup_payload: dict[str, Any] = {
            "target_advertiser_id": target_advertiser_ids[0],
            "advertiser_id": target_advertiser_ids[0],
            "lookup_items": lookup_items,
        }
        if material_ids:
            lookup_payload["material_ids"] = material_ids
        if source_video_id_filters:
            lookup_payload["source_video_ids"] = source_video_id_filters
        lookup_call = {
            "sequence": sequence,
            "operation": "lookup_target_material",
            "endpoint": endpoints.get("lookup_target_material", ""),
            "payload": lookup_payload,
            "transport_mode": "create_http",
        }
        try:
            lookup_response = transport(lookup_call)
        except RuntimeError:
            sequence += 1
            call_count += 1
            pending_after_precheck.append((original_index, draft))
            continue
        sequence += 1
        call_count += 1
        if _response_code(lookup_response) != 0:
            pending_after_precheck.append((original_index, draft))
            continue

        provider_id_records.extend(
            _record_existing_target_material_lookup(
                db_path=db_path,
                create_execute_artifact=create_execute_artifact,
                response=lookup_response,
                lookup_items=lookup_items,
            )
        )
        existing_after_lookup_source_video_ids = [
            source_video_id
            for source_video_id in missing_source_video_ids
            if all(
                _target_material_records_exist(
                    db_path=db_path,
                    create_execute_artifact=create_execute_artifact,
                    target_advertiser_id=target_advertiser_id,
                    source_video_id=source_video_id,
                )
                for target_advertiser_id in target_advertiser_ids
            )
        ]
        still_missing_source_video_ids = [
            item for item in missing_source_video_ids if item not in set(existing_after_lookup_source_video_ids)
        ]
        if existing_after_lookup_source_video_ids:
            existing_payload = {
                **payload,
                "source_video_ids": existing_after_lookup_source_video_ids,
                "video_ids": existing_after_lookup_source_video_ids,
            }
            material_bind_records.append(
                _record_material_bind(
                    db_path=db_path,
                    create_execute_artifact=create_execute_artifact,
                    payload=existing_payload,
                    response={"code": 0, "message": "existing_target_material", "data": {"task_id": "existing_target_material"}},
                )
            )
            skipped.append(
                {
                    "operation": "bind_material",
                    "index": original_index,
                    "target_advertiser_ids": target_advertiser_ids,
                    "source_video_ids": existing_after_lookup_source_video_ids,
                    "status": "skipped_existing_target_material",
                }
            )
        if still_missing_source_video_ids:
            next_payload = {**payload, "source_video_ids": still_missing_source_video_ids, "video_ids": still_missing_source_video_ids}
            pending_after_precheck.append((original_index, {**draft, "payload": next_payload}))

    return {
        "pending": pending_after_precheck,
        "skipped": skipped,
        "material_bind_records": material_bind_records,
        "provider_id_records": provider_id_records,
        "transport_call_count": call_count,
        "sequence": sequence,
    }


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
    ledger_archive_records: list[dict[str, Any]] = []
    ordered_steps: list[dict[str, Any]] = []
    transport_call_count = 0
    sequence = 0

    for operation in OPERATION_ORDER:
        drafts = _drafts_for_operation(create_execute_artifact, operation)
        if not drafts:
            continue
        operation_call_count = 0
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
            _write_progress(
                policy,
                status=skipped_status,
                operation=operation,
                done=len(drafts),
                total=len(drafts),
                transport_call_count=transport_call_count,
                message=f"skipped={len(skipped)}",
            )
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
                _write_progress(
                    policy,
                    status="completed_with_skipped_accounts",
                    operation=operation,
                    done=len(drafts),
                    total=len(drafts),
                    transport_call_count=transport_call_count,
                    message=f"skipped_accounts={operation_skipped_account_count}",
                )
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

        if operation == "bind_material" and pending:
            precheck = _precheck_existing_target_materials_for_bind(
                db_path=db_path,
                create_execute_artifact=create_execute_artifact,
                pending=pending,
                endpoints=endpoints,
                transport=transport,
                sequence=sequence,
            )
            pending = precheck["pending"]
            sequence = int(precheck["sequence"])
            precheck_call_count = int(precheck["transport_call_count"])
            transport_call_count += precheck_call_count
            operation_call_count += precheck_call_count
            precheck_skipped = _rows(precheck.get("skipped"))
            skipped.extend(precheck_skipped)
            skipped_material_bind_records.extend(precheck_skipped)
            material_bind_records.extend(_rows(precheck.get("material_bind_records")))
            provider_id_records.extend(_rows(precheck.get("provider_id_records")))
            if drafts and not pending:
                _write_progress(
                    policy,
                    status="skipped_existing_target_material",
                    operation=operation,
                    done=len(drafts),
                    total=len(drafts),
                    transport_call_count=transport_call_count,
                    message=f"skipped={len(skipped)}",
                )
                ordered_steps.append(
                    {
                        "operation": operation,
                        "planned_count": len(drafts),
                        "status": "skipped_existing_target_material",
                        "test_transport_call_count": operation_call_count,
                    }
                )
                continue

        pending_drafts = [draft for _index, draft in pending]
        summary = _summary(create_execute_artifact)
        resolution = resolve_provider_payload_drafts(
            db_path=db_path,
            provider_payload_drafts=pending_drafts,
            plan_id=str(summary.get("plan_id") or ""),
            request_id=str(summary.get("request_id") or ""),
        )
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
        operation_done_count = len(skipped)
        _write_progress(
            policy,
            status="running",
            operation=operation,
            done=operation_done_count,
            total=len(drafts),
            transport_call_count=transport_call_count,
            message=f"pending={len(resolved_drafts)} skipped={len(skipped)}",
        )
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
                operation_done_count += 1
                _write_progress(
                    policy,
                    status="skipped_account",
                    operation=operation,
                    done=operation_done_count,
                    total=len(drafts),
                    transport_call_count=transport_call_count,
                    advertiser_id=advertiser_id,
                    index=original_index,
                )
                continue
            create_retry_count = 0
            lookup_visibility_retry_count = 0
            max_create_retry_count = int(_runner_policy(policy).get("recover_create_after_lookup_max_retries") or 1)
            lookup_visibility_wait = _lookup_target_material_visibility_wait_policy(policy)
            skipped_current_account = False
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
                        if _is_skip_account_live_step_failure(operation, failure_response):
                            if advertiser_id:
                                skipped_account_ids.add(advertiser_id)
                            skipped_account_records.append(
                                _skip_account_record(
                                    operation=operation,
                                    index=original_index,
                                    advertiser_id=advertiser_id,
                                    response=failure_response,
                                )
                            )
                            operation_skipped_account_count += 1
                            operation_done_count += 1
                            _write_progress(
                                policy,
                                status="skipped_account",
                                operation=operation,
                                done=operation_done_count,
                                total=len(drafts),
                                transport_call_count=transport_call_count,
                                advertiser_id=advertiser_id,
                                index=original_index,
                                message=str(exc),
                            )
                            skipped_current_account = True
                            break
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
            if skipped_current_account:
                continue
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
                if _is_skip_account_live_step_failure(operation, response):
                    if advertiser_id:
                        skipped_account_ids.add(advertiser_id)
                    skipped_account_records.append(
                        _skip_account_record(
                            operation=operation,
                            index=original_index,
                            advertiser_id=advertiser_id,
                            response=response,
                        )
                    )
                    operation_skipped_account_count += 1
                    operation_done_count += 1
                    _write_progress(
                        policy,
                        status="skipped_account",
                        operation=operation,
                        done=operation_done_count,
                        total=len(drafts),
                        transport_call_count=transport_call_count,
                        advertiser_id=advertiser_id,
                        index=original_index,
                        message=_response_message(response),
                    )
                    continue
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
                    operation_done_count += 1
                    _write_progress(
                        policy,
                        status="skipped_account",
                        operation=operation,
                        done=operation_done_count,
                        total=len(drafts),
                        transport_call_count=transport_call_count,
                        advertiser_id=advertiser_id,
                        index=original_index,
                        message=_response_message(response),
                    )
                    continue
                _write_progress(
                    policy,
                    status="failed",
                    operation=operation,
                    done=operation_done_count,
                    total=len(drafts),
                    transport_call_count=transport_call_count,
                    advertiser_id=advertiser_id,
                    index=original_index,
                    message=_response_message(response),
                )
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
            missing_provider_records = _missing_provider_id_records(records)
            while (
                operation == "lookup_target_material"
                and missing_provider_records
                and bool(lookup_visibility_wait["enabled"])
                and lookup_visibility_retry_count < int(lookup_visibility_wait["max_retries"])
            ):
                lookup_visibility_retry_count += 1
                _write_progress(
                    policy,
                    status="waiting",
                    operation=operation,
                    done=operation_done_count,
                    total=len(drafts),
                    transport_call_count=transport_call_count,
                    advertiser_id=advertiser_id,
                    index=original_index,
                    message=(
                        "target_material_not_visible "
                        f"retry={lookup_visibility_retry_count}/{int(lookup_visibility_wait['max_retries'])}"
                    ),
                )
                sleep_seconds = float(lookup_visibility_wait["sleep_seconds"])
                if sleep_seconds > 0:
                    time.sleep(sleep_seconds)
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
                    return _runner_failure_result(
                        operation=operation,
                        index=original_index,
                        message=str(exc),
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
                call = retry_call
                if _response_code(response) != 0:
                    break
                record_result = _record_provider_id(
                    db_path=db_path,
                    create_execute_artifact=create_execute_artifact,
                    operation=operation,
                    index=original_index,
                    response=response,
                    request_payload=call["payload"],
                )
                records = record_result if isinstance(record_result, list) else [record_result] if record_result is not None else []
                missing_provider_records = _missing_provider_id_records(records)
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
            operation_done_count += 1
            _write_progress(
                policy,
                status="running" if operation_done_count < len(drafts) else "completed",
                operation=operation,
                done=operation_done_count,
                total=len(drafts),
                transport_call_count=transport_call_count,
                advertiser_id=advertiser_id,
                index=original_index,
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

    post_run_retry = _post_run_retry_transient_create_units(
        create_execute_artifact=create_execute_artifact,
        policy=policy,
        db_path=db_path,
        endpoints=endpoints,
        transport=transport,
        skipped_account_records=skipped_account_records,
        sequence=sequence,
        transport_call_count=transport_call_count,
    )
    sequence = int(post_run_retry.get("sequence") or sequence)
    transport_call_count = int(post_run_retry.get("transport_call_count") or transport_call_count)
    provider_id_records.extend(_rows(post_run_retry.get("provider_id_records")))
    ledger_archive_records.append(
        _archive_round_project_unit_ids(
            db_path=db_path,
            create_execute_artifact=create_execute_artifact,
            stage="after_run",
        )
    )

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
        "post_run_retry": post_run_retry,
        "ledger_archive": ledger_archive_records,
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
        "post_run_retry": runner_result.get("post_run_retry")
        if isinstance(runner_result.get("post_run_retry"), dict)
        else _default_post_run_retry(),
        "ledger_archive": list(runner_result.get("ledger_archive") or []),
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
