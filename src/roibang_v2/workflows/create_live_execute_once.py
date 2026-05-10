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


def _once_config(request: dict[str, Any]) -> dict[str, Any]:
    value = request.get("create_live_execute_once")
    return dict(value) if isinstance(value, dict) else dict(request)


def _execution_pack_ready(execution_pack: dict[str, Any]) -> bool:
    final_preflight = execution_pack.get("final_preflight")
    return (
        bool(execution_pack.get("ok", False))
        and str(execution_pack.get("status") or "") == "ready_for_live_execute"
        and not bool(execution_pack.get("execution_enabled", False))
        and int(execution_pack.get("external_api_calls") or 0) == 0
        and isinstance(final_preflight, dict)
        and bool(final_preflight.get("ready_for_live_execute", False))
    )


def _pack_blocking_reasons(execution_pack: dict[str, Any]) -> list[str]:
    final_preflight = execution_pack.get("final_preflight")
    reasons = []
    if isinstance(final_preflight, dict):
        reasons.extend(str(item) for item in final_preflight.get("blocking_reasons") or [])
    return reasons


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
    create_live_execution_pack_artifact: dict[str, Any],
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
        "source_execution_pack_status": str(create_live_execution_pack_artifact.get("status") or ""),
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
    value = policy.get("create_live_execute_runner")
    return dict(value) if isinstance(value, dict) else {}


def _adapter_gate(scaffold: dict[str, Any]) -> dict[str, Any]:
    value = scaffold.get("live_adapter_gate")
    return dict(value) if isinstance(value, dict) else {}


def _endpoints(policy: dict[str, Any], scaffold: dict[str, Any]) -> dict[str, str]:
    scaffold_endpoints = _adapter_gate(scaffold).get("endpoints")
    policy_endpoints = _live_api_policy(policy).get("endpoints")
    source = scaffold_endpoints if isinstance(scaffold_endpoints, dict) else policy_endpoints
    data = source if isinstance(source, dict) else {}
    return {operation: str(data.get(operation) or "") for operation in OPERATION_ORDER}


def _provider_payload_drafts(create_execute: dict[str, Any]) -> list[dict[str, Any]]:
    drafts = _rows(create_execute.get("resolved_provider_payload_drafts"))
    if drafts:
        return drafts
    return _rows(create_execute.get("provider_payload_drafts"))


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
    return {
        "payloads_non_executable": executable_count == 0,
        "live_payload_count_zero": live_payload_count == 0,
        "no_unresolved_lookup_placeholders": unresolved_lookup_count == 0,
        "executable_count": executable_count,
        "live_payload_count": live_payload_count,
        "unresolved_lookup_count": unresolved_lookup_count,
    }


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


def _record_provider_id(
    *,
    db_path: str | Path,
    create_execute_artifact: dict[str, Any],
    operation: str,
    index: int,
    response: dict[str, Any],
) -> dict[str, Any] | list[dict[str, Any]] | None:
    summary = _summary(create_execute_artifact)
    if operation == "lookup_target_material":
        records = _target_material_records(create_execute_artifact)
        provider_ids = {
            "target_video": _target_video_id(response),
            "target_video_cover": _target_video_cover_id(response),
        }
        results: list[dict[str, Any]] = []
        for row in records[index * 2 : index * 2 + 2]:
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
        record_pair = records[index * 2 : index * 2 + 2]
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


def _resumable_create_http_run(
    *,
    create_execute_artifact: dict[str, Any],
    create_live_payload_adapter_scaffold_artifact: dict[str, Any],
    policy: dict[str, Any],
    db_path: str | Path,
    transport: Transport,
) -> dict[str, Any]:
    endpoints = _endpoints(policy, create_live_payload_adapter_scaffold_artifact)
    provider_id_records: list[dict[str, Any]] = []
    material_bind_records: list[dict[str, Any]] = []
    skipped_provider_id_records: list[dict[str, Any]] = []
    skipped_material_bind_records: list[dict[str, Any]] = []
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
            }

        resolved_drafts = _rows(resolution.get("resolved_provider_payload_drafts"))
        operation_call_count = 0
        for offset, draft in enumerate(resolved_drafts):
            original_index = pending[offset][0]
            call = {
                "sequence": sequence,
                "operation": operation,
                "endpoint": endpoints.get(operation, ""),
                "payload": draft.get("payload") if isinstance(draft.get("payload"), dict) else {},
                "transport_mode": "create_http",
            }
            response = transport(call)
            sequence += 1
            transport_call_count += 1
            operation_call_count += 1
            if _response_code(response) != 0:
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
                }
            record_result = _record_provider_id(
                db_path=db_path,
                create_execute_artifact=create_execute_artifact,
                operation=operation,
                index=original_index,
                response=response,
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
        ordered_steps.append(
            {
                "operation": operation,
                "planned_count": len(drafts),
                "status": "completed",
                "test_transport_call_count": operation_call_count,
            }
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
        "idempotency": _idempotency_summary(
            skipped_provider_id_records=skipped_provider_id_records,
            skipped_material_bind_records=skipped_material_bind_records,
        ),
    }


def build_create_live_execute_once(
    *,
    create_live_execution_pack_artifact: dict[str, Any],
    create_execute_artifact: dict[str, Any],
    create_first_live_runbook_artifact: dict[str, Any],
    create_live_payload_adapter_scaffold_artifact: dict[str, Any],
    create_live_approval_artifact: dict[str, Any],
    policy: dict[str, Any],
    runtime: dict[str, Any],
    db_path: str | Path,
    transport: Transport | None = None,
) -> dict[str, Any]:
    if not _execution_pack_ready(create_live_execution_pack_artifact):
        return _blocked_result(
            reason="execution_pack_not_ready",
            blocking_reasons=[
                "execution pack is not ready_for_live_execute",
                *_pack_blocking_reasons(create_live_execution_pack_artifact),
            ],
            create_live_execution_pack_artifact=create_live_execution_pack_artifact,
        )
    pre_transport_reasons = _pre_transport_blocking_reasons(runtime, transport)
    if pre_transport_reasons:
        return _blocked_result(
            reason="transport_not_ready",
            blocking_reasons=pre_transport_reasons,
            create_live_execution_pack_artifact=create_live_execution_pack_artifact,
        )

    runner_result = _resumable_create_http_run(
        create_execute_artifact=create_execute_artifact,
        create_live_payload_adapter_scaffold_artifact=create_live_payload_adapter_scaffold_artifact,
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
        "source_execution_pack_status": str(create_live_execution_pack_artifact.get("status") or ""),
        "blocking_reasons": list(runner_result.get("blocking_reasons") or []),
        "ordered_steps": list(runner_result.get("ordered_steps") or []),
        "provider_id_records": list(runner_result.get("provider_id_records") or []),
        "material_bind_records": list(runner_result.get("material_bind_records") or []),
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
        reasons.append("policy.create_live_execute_runner.allow_create_http_transport is false")
    if bool(create_execute_artifact.get("execution_enabled", False)):
        reasons.append("create_execute artifact execution_enabled must be false")
    if int(create_execute_artifact.get("external_api_calls") or 0) != 0:
        reasons.append("create_execute artifact external_api_calls must be 0")
    payload_safety = _create_execute_payload_safety(create_execute_artifact)
    if not bool(payload_safety["payloads_non_executable"]):
        reasons.append("create_execute payload drafts must not be executable")
    if not bool(payload_safety["live_payload_count_zero"]):
        reasons.append("create_execute payload drafts must not contain live payload flags")
    if not bool(payload_safety["no_unresolved_lookup_placeholders"]):
        reasons.append("create_execute payloads still contain unresolved lookup placeholders")
    return reasons


def build_create_live_execute_once_direct(
    *,
    create_execute_artifact: dict[str, Any],
    create_live_payload_adapter_scaffold_artifact: dict[str, Any],
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
            create_live_execution_pack_artifact={"status": "not_required_direct_create_execute"},
        )

    runner_result = _resumable_create_http_run(
        create_execute_artifact=create_execute_artifact,
        create_live_payload_adapter_scaffold_artifact=create_live_payload_adapter_scaffold_artifact,
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
        "source_execution_pack_status": "not_required_direct_create_execute",
        "blocking_reasons": list(runner_result.get("blocking_reasons") or []),
        "ordered_steps": list(runner_result.get("ordered_steps") or []),
        "provider_id_records": list(runner_result.get("provider_id_records") or []),
        "material_bind_records": list(runner_result.get("material_bind_records") or []),
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
    execution_pack = cfg.get("create_live_execution_pack_artifact")
    create_execute = cfg.get("create_execute_artifact")
    runbook = cfg.get("create_first_live_runbook_artifact")
    scaffold = cfg.get("create_live_payload_adapter_scaffold_artifact")
    approval = cfg.get("create_live_approval_artifact")
    if not isinstance(execution_pack, dict):
        if not isinstance(create_execute, dict):
            raise ValueError("create live execute once requires create_execute_artifact")
        policy = cfg.get("policy") if isinstance(cfg.get("policy"), dict) else {}
        runtime = cfg.get("runtime") if isinstance(cfg.get("runtime"), dict) else {}
        payload = build_create_live_execute_once_direct(
            create_execute_artifact=create_execute,
            create_live_payload_adapter_scaffold_artifact=scaffold if isinstance(scaffold, dict) else {},
            policy=policy,
            runtime=runtime,
            db_path=db_path,
            transport=transport,
        )
        artifact_path = write_run_artifact(runs_dir, "create_live_execute_once", payload)
        return {**payload, "artifact_path": str(artifact_path)}
    if not isinstance(create_execute, dict):
        raise ValueError("create live execute once requires create_execute_artifact")
    if not isinstance(runbook, dict):
        raise ValueError("create live execute once requires create_first_live_runbook_artifact")
    if not isinstance(scaffold, dict):
        raise ValueError("create live execute once requires create_live_payload_adapter_scaffold_artifact")
    if not isinstance(approval, dict):
        raise ValueError("create live execute once requires create_live_approval_artifact")
    policy = cfg.get("policy") if isinstance(cfg.get("policy"), dict) else {}
    runtime = cfg.get("runtime") if isinstance(cfg.get("runtime"), dict) else {}
    payload = build_create_live_execute_once(
        create_live_execution_pack_artifact=execution_pack,
        create_execute_artifact=create_execute,
        create_first_live_runbook_artifact=runbook,
        create_live_payload_adapter_scaffold_artifact=scaffold,
        create_live_approval_artifact=approval,
        policy=policy,
        runtime=runtime,
        db_path=db_path,
        transport=transport,
    )
    artifact_path = write_run_artifact(runs_dir, "create_live_execute_once", payload)
    return {**payload, "artifact_path": str(artifact_path)}
