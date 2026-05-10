from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from roibang_v2.runs import write_run_artifact
from roibang_v2.workflows.create_provider_id_ledger import (
    record_create_provider_id,
    resolve_provider_payload_drafts,
)

Transport = Callable[[dict[str, Any]], dict[str, Any]]

OPERATION_ORDER = ["create_project", "bind_material", "lookup_target_material", "create_unit"]


def _runner_config(request: dict[str, Any]) -> dict[str, Any]:
    value = request.get("create_live_execute_runner")
    return dict(value) if isinstance(value, dict) else dict(request)


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


def _human_approval_from_policy(policy: dict[str, Any]) -> dict[str, Any]:
    value = _runner_policy(policy).get("human_approval")
    return dict(value) if isinstance(value, dict) else {}


def _approval_from_artifact(approval_artifact: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(approval_artifact, dict):
        return {}
    value = approval_artifact.get("approval")
    return dict(value) if isinstance(value, dict) else {}


def _adapter_gate(scaffold: dict[str, Any]) -> dict[str, Any]:
    value = scaffold.get("live_adapter_gate")
    return dict(value) if isinstance(value, dict) else {}


def _adapter_required_gates(scaffold: dict[str, Any]) -> dict[str, Any]:
    value = _adapter_gate(scaffold).get("required_gates")
    return dict(value) if isinstance(value, dict) else {}


def _endpoints(policy: dict[str, Any], scaffold: dict[str, Any]) -> dict[str, str]:
    scaffold_endpoints = _adapter_gate(scaffold).get("endpoints")
    policy_endpoints = _live_api_policy(policy).get("endpoints")
    source = scaffold_endpoints if isinstance(scaffold_endpoints, dict) else policy_endpoints
    data = source if isinstance(source, dict) else {}
    return {operation: str(data.get(operation) or "") for operation in OPERATION_ORDER}


def _runtime_enabled(runtime: dict[str, Any], key: str) -> bool:
    return bool(runtime.get(key, False))


def _runbook_ready(runbook: dict[str, Any]) -> bool:
    return (
        bool(runbook.get("ok", True))
        and str(runbook.get("status") or "") == "ready_for_human_approval"
        and not bool(runbook.get("execution_enabled", False))
        and int(runbook.get("external_api_calls") or 0) == 0
    )


def _policy_live_api_enabled(policy: dict[str, Any]) -> bool:
    return bool(_live_api_policy(policy).get("enabled", False))


def _policy_live_payload_generation_enabled(policy: dict[str, Any]) -> bool:
    return bool(_payload_schema_policy(policy).get("live_payload_generation_enabled", False))


def _live_approval_artifact_present(approval_artifact: dict[str, Any] | None) -> bool:
    if not isinstance(approval_artifact, dict):
        return False
    return (
        bool(approval_artifact.get("ok", False))
        and str(approval_artifact.get("status") or "") == "approved"
        and not bool(approval_artifact.get("execution_enabled", False))
        and int(approval_artifact.get("external_api_calls") or 0) == 0
    )


def _human_approval_present(approval_artifact: dict[str, Any] | None) -> bool:
    approval = _approval_from_artifact(approval_artifact)
    return _live_approval_artifact_present(approval_artifact) and bool(approval.get("approved", False)) and bool(
        str(approval.get("approval_id") or "").strip()
    )


def _allow_create_http_transport(policy: dict[str, Any], approval_artifact: dict[str, Any] | None) -> bool:
    approval = _approval_from_artifact(approval_artifact)
    return bool(_runner_policy(policy).get("allow_create_http_transport", False)) and bool(
        approval.get("allow_create_http_transport", False)
    )


def _rows(value: Any) -> list[dict[str, Any]]:
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def _provider_payload_drafts(create_execute: dict[str, Any]) -> list[dict[str, Any]]:
    drafts = _rows(create_execute.get("provider_payload_drafts"))
    if drafts:
        return drafts
    return _rows(create_execute.get("resolved_provider_payload_drafts"))


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


def _unresolved_lookup_count(create_execute: dict[str, Any]) -> int:
    contract = create_execute.get("resolved_payload_contract")
    if isinstance(contract, dict):
        return int(contract.get("unresolved_lookup_count") or 0)
    resolution = create_execute.get("provider_payload_resolution")
    if isinstance(resolution, dict):
        return int(resolution.get("unresolved_count") or 0)
    return 0


def _chain_resolvable(create_execute: dict[str, Any]) -> bool:
    project_count = len(_drafts_for_operation(create_execute, "create_project"))
    unit_count = len(_drafts_for_operation(create_execute, "create_unit"))
    return len(_project_records(create_execute)) >= project_count and len(_unit_records(create_execute)) >= unit_count


def _runner_gate(
    *,
    create_execute_artifact: dict[str, Any],
    create_first_live_runbook_artifact: dict[str, Any],
    create_live_payload_adapter_scaffold_artifact: dict[str, Any],
    create_live_approval_artifact: dict[str, Any] | None,
    policy: dict[str, Any],
    runtime: dict[str, Any],
    transport: Transport | None,
    transport_mode: str = "injected_test_transport",
) -> dict[str, Any]:
    adapter_gates = _adapter_required_gates(create_live_payload_adapter_scaffold_artifact)
    normalized_transport_mode = str(transport_mode or "injected_test_transport")
    create_http_allowed = _allow_create_http_transport(policy, create_live_approval_artifact)
    transport_allowed = normalized_transport_mode == "injected_test_transport" or create_http_allowed
    external_api_call_accounting = (
        "test_transport_not_counted_as_external_api"
        if normalized_transport_mode == "injected_test_transport"
        else "external_api_calls_count_real_transport"
        if create_http_allowed
        else "blocked_zero"
    )
    required_gates = {
        "runtime_execution_enabled": _runtime_enabled(runtime, "execution_enabled"),
        "runtime_external_api_enabled": _runtime_enabled(runtime, "external_api_enabled"),
        "policy_live_api_enabled": _policy_live_api_enabled(policy),
        "policy_live_payload_generation_enabled": _policy_live_payload_generation_enabled(policy),
        "phase_gate_allows_live_execute": bool(adapter_gates.get("phase_gate_allows_live_execute", False))
        or bool(_adapter_gate(create_live_payload_adapter_scaffold_artifact).get("ready_for_live_execute", False)),
        "runbook_ready_for_human_approval": _runbook_ready(create_first_live_runbook_artifact),
        "live_approval_artifact_present": _live_approval_artifact_present(create_live_approval_artifact),
        "human_approval_record_present": _human_approval_present(create_live_approval_artifact),
        "transport_injected_for_test": transport is not None,
        "no_unresolved_lookup_placeholders": _unresolved_lookup_count(create_execute_artifact) == 0,
    }
    ready = (
        required_gates["runtime_execution_enabled"]
        and required_gates["runtime_external_api_enabled"]
        and required_gates["policy_live_api_enabled"]
        and required_gates["policy_live_payload_generation_enabled"]
        and required_gates["phase_gate_allows_live_execute"]
        and required_gates["runbook_ready_for_human_approval"]
        and required_gates["human_approval_record_present"]
        and required_gates["transport_injected_for_test"]
        and transport_allowed
        and _chain_resolvable(create_execute_artifact)
    )
    return {
        "status": "ready_for_test_transport" if ready else "blocked",
        "ready_for_live_execute": ready,
        "required_gates": required_gates,
        "transport_contract": {
            "mode": normalized_transport_mode,
            "transport_present": transport is not None,
            "create_http_transport_allowed": create_http_allowed,
            "external_api_call_accounting": external_api_call_accounting,
        },
        "lookup_placeholders_chain_resolvable": _chain_resolvable(create_execute_artifact),
        "execution_enabled": False,
        "external_api_calls": 0,
        "actions": [],
    }


def _blocking_reasons(gate: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    labels = {
        "runtime_execution_enabled": "runtime.execution_enabled is false",
        "runtime_external_api_enabled": "runtime.external_api_enabled is false",
        "policy_live_api_enabled": "policy.create_execute.live_api.enabled is false",
        "policy_live_payload_generation_enabled": "policy.create_execute.payload_schema.live_payload_generation_enabled is false",
        "phase_gate_allows_live_execute": "phase gate has not allowed live execute",
        "runbook_ready_for_human_approval": "first live runbook is not ready for human approval",
        "live_approval_artifact_present": "create_live_approval artifact is missing or not approved",
        "human_approval_record_present": "human approval record is missing",
        "transport_injected_for_test": "test transport is not injected",
    }
    required_gates = gate.get("required_gates") if isinstance(gate.get("required_gates"), dict) else {}
    for key, message in labels.items():
        if not bool(required_gates.get(key, False)):
            reasons.append(message)
    transport_contract = gate.get("transport_contract") if isinstance(gate.get("transport_contract"), dict) else {}
    if str(transport_contract.get("mode") or "") != "injected_test_transport" and not bool(
        transport_contract.get("create_http_transport_allowed", False)
    ):
        reasons.append("create_http transport is not allowed by policy")
    if not bool(gate.get("lookup_placeholders_chain_resolvable", False)):
        reasons.append("provider id lookup placeholders are not chain-resolvable")
    return reasons


def _approve_contract() -> dict[str, Any]:
    return {
        "approve_is_record_only": True,
        "approve_opens_execution": False,
        "requires_separate_human_approval_for_live": True,
    }


def _failure_policy() -> dict[str, Any]:
    return {
        "on_create_project_error": "stop_without_create_unit",
        "on_create_unit_error": "stop_without_bind_material",
        "on_bind_material_error": "stop_and_keep_created_ids_for_manual_review",
        "auto_retry_enabled": False,
    }


def _empty_result(
    *,
    create_execute_artifact: dict[str, Any],
    create_first_live_runbook_artifact: dict[str, Any],
    create_live_payload_adapter_scaffold_artifact: dict[str, Any],
    create_live_approval_artifact: dict[str, Any] | None,
    policy: dict[str, Any],
    runtime: dict[str, Any],
    transport: Transport | None,
    transport_mode: str = "injected_test_transport",
) -> dict[str, Any]:
    gate = _runner_gate(
        create_execute_artifact=create_execute_artifact,
        create_first_live_runbook_artifact=create_first_live_runbook_artifact,
        create_live_payload_adapter_scaffold_artifact=create_live_payload_adapter_scaffold_artifact,
        create_live_approval_artifact=create_live_approval_artifact,
        policy=policy,
        runtime=runtime,
        transport=transport,
        transport_mode=transport_mode,
    )
    return {
        "ok": False,
        "workflow": "create_live_execute_runner",
        "phase": "phase2_preparation",
        "execution_enabled": False,
        "live_execute_enabled": False,
        "external_api_calls": 0,
        "status": "blocked",
        "runner_gate": gate,
        "approve_contract": _approve_contract(),
        "failure_policy": _failure_policy(),
        "blocking_reasons": _blocking_reasons(gate),
        "ordered_steps": [],
        "provider_id_records": [],
        "test_transport_call_count": 0,
        "live_api_calls": [],
        "failure": None,
        "actions": [],
    }


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


def _project_id(response: dict[str, Any]) -> str:
    data = _response_data(response)
    return str(data.get("project_id") or response.get("project_id") or "")


def _promotion_id(response: dict[str, Any]) -> str:
    data = _response_data(response)
    return str(data.get("promotion_id") or response.get("promotion_id") or "")


def _target_video_id(response: dict[str, Any]) -> str:
    data = _response_data(response)
    return str(data.get("target_video_id") or data.get("video_id") or response.get("target_video_id") or response.get("video_id") or "")


def _target_video_cover_id(response: dict[str, Any]) -> str:
    data = _response_data(response)
    return str(
        data.get("target_video_cover_id")
        or data.get("video_cover_id")
        or data.get("cover_id")
        or response.get("target_video_cover_id")
        or response.get("video_cover_id")
        or response.get("cover_id")
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
    summary = create_execute_artifact.get("summary") if isinstance(create_execute_artifact.get("summary"), dict) else {}
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
                    source_workflow="create_live_execute_runner",
                    response_payload=_safe_response(response),
                )
            )
        return results
    if operation == "create_project":
        records = _project_records(create_execute_artifact)
        provider_id = _project_id(response)
        entity_type = "project"
    elif operation == "create_unit":
        records = _unit_records(create_execute_artifact)
        provider_id = _promotion_id(response)
        entity_type = "promotion"
    else:
        return None
    row = records[index] if index < len(records) else {}
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
        source_workflow="create_live_execute_runner",
        response_payload=_safe_response(response),
    )


def _resolve_operation_drafts(
    *,
    db_path: str | Path,
    drafts: list[dict[str, Any]],
) -> dict[str, Any]:
    if not drafts:
        return {
            "status": "resolved",
            "resolved_provider_payload_drafts": [],
            "unresolved_count": 0,
            "unresolved_placeholders": [],
        }
    return resolve_provider_payload_drafts(db_path=db_path, provider_payload_drafts=drafts)


def build_create_live_execute_runner(
    *,
    create_execute_artifact: dict[str, Any],
    create_first_live_runbook_artifact: dict[str, Any],
    create_live_payload_adapter_scaffold_artifact: dict[str, Any],
    create_live_approval_artifact: dict[str, Any] | None = None,
    policy: dict[str, Any],
    runtime: dict[str, Any],
    db_path: str | Path,
    transport: Transport | None = None,
    transport_mode: str = "injected_test_transport",
) -> dict[str, Any]:
    normalized_transport_mode = str(transport_mode or "injected_test_transport")
    result = _empty_result(
        create_execute_artifact=create_execute_artifact,
        create_first_live_runbook_artifact=create_first_live_runbook_artifact,
        create_live_payload_adapter_scaffold_artifact=create_live_payload_adapter_scaffold_artifact,
        create_live_approval_artifact=create_live_approval_artifact,
        policy=policy,
        runtime=runtime,
        transport=transport,
        transport_mode=normalized_transport_mode,
    )
    if not bool(result["runner_gate"]["ready_for_live_execute"]):
        return result

    endpoints = _endpoints(policy, create_live_payload_adapter_scaffold_artifact)
    provider_id_records: list[dict[str, Any]] = []
    ordered_steps: list[dict[str, Any]] = []
    test_transport_call_count = 0
    sequence = 0
    assert transport is not None

    for operation in OPERATION_ORDER:
        drafts = _drafts_for_operation(create_execute_artifact, operation)
        if not drafts:
            continue
        resolution = _resolve_operation_drafts(db_path=db_path, drafts=drafts)
        if int(resolution.get("unresolved_count") or 0):
            result.update(
                {
                    "status": "test_transport_failed",
                    "failure": {
                        "operation": operation,
                        "index": 0,
                        "message": "lookup placeholders unresolved before operation",
                        "code": -1,
                    },
                    "blocking_reasons": ["lookup placeholders unresolved before operation"],
                    "ordered_steps": ordered_steps,
                    "provider_id_records": provider_id_records,
                    "test_transport_call_count": test_transport_call_count,
                }
            )
            return result

        resolved_drafts = _rows(resolution.get("resolved_provider_payload_drafts"))
        operation_call_count = 0
        for index, draft in enumerate(resolved_drafts):
            call = {
                "sequence": sequence,
                "operation": operation,
                "endpoint": endpoints.get(operation, ""),
                "payload": draft.get("payload") if isinstance(draft.get("payload"), dict) else {},
                "transport_mode": normalized_transport_mode,
            }
            response = transport(call)
            sequence += 1
            test_transport_call_count += 1
            operation_call_count += 1
            if _response_code(response) != 0:
                result.update(
                    {
                        "status": "test_transport_failed"
                        if normalized_transport_mode == "injected_test_transport"
                        else "create_http_failed",
                        "failure": _failure(operation, index, response),
                        "ordered_steps": ordered_steps,
                        "provider_id_records": provider_id_records,
                        "test_transport_call_count": test_transport_call_count,
                        "external_api_calls": 0
                        if normalized_transport_mode == "injected_test_transport"
                        else test_transport_call_count,
                    }
                )
                return result
            record_result = _record_provider_id(
                db_path=db_path,
                create_execute_artifact=create_execute_artifact,
                operation=operation,
                index=index,
                response=response,
            )
            records = record_result if isinstance(record_result, list) else [record_result] if record_result is not None else []
            for record in records:
                provider_id_records.append(record)
                if str(record.get("status") or "") != "recorded":
                    result.update(
                        {
                            "status": "test_transport_failed",
                            "failure": {
                                "operation": operation,
                                "index": index,
                                "message": str(record.get("status") or "provider id record failed"),
                                "code": -1,
                            },
                            "ordered_steps": ordered_steps,
                            "provider_id_records": provider_id_records,
                            "test_transport_call_count": test_transport_call_count,
                        }
                    )
                    return result
        ordered_steps.append(
            {
                "operation": operation,
                "planned_count": len(drafts),
                "status": "completed",
                "test_transport_call_count": operation_call_count,
            }
        )

    result.update(
        {
            "ok": True,
            "status": "test_transport_completed"
            if normalized_transport_mode == "injected_test_transport"
            else "create_http_completed",
            "blocking_reasons": [],
            "ordered_steps": ordered_steps,
            "provider_id_records": provider_id_records,
            "test_transport_call_count": test_transport_call_count,
            "external_api_calls": 0
            if normalized_transport_mode == "injected_test_transport"
            else test_transport_call_count,
            "failure": None,
        }
    )
    return result


def run_create_live_execute_runner_request(
    request: dict[str, Any],
    *,
    runs_dir: str | Path,
    db_path: str | Path,
) -> dict[str, Any]:
    cfg = _runner_config(request)
    create_execute = cfg.get("create_execute_artifact")
    runbook = cfg.get("create_first_live_runbook_artifact")
    scaffold = cfg.get("create_live_payload_adapter_scaffold_artifact")
    live_approval = cfg.get("create_live_approval_artifact")
    if not isinstance(create_execute, dict):
        raise ValueError("create live execute runner requires create_execute_artifact")
    if not isinstance(runbook, dict):
        raise ValueError("create live execute runner requires create_first_live_runbook_artifact")
    if not isinstance(scaffold, dict):
        raise ValueError("create live execute runner requires create_live_payload_adapter_scaffold_artifact")
    policy = cfg.get("policy") if isinstance(cfg.get("policy"), dict) else {}
    runtime = cfg.get("runtime") if isinstance(cfg.get("runtime"), dict) else {}
    payload = build_create_live_execute_runner(
        create_execute_artifact=create_execute,
        create_first_live_runbook_artifact=runbook,
        create_live_payload_adapter_scaffold_artifact=scaffold,
        create_live_approval_artifact=live_approval if isinstance(live_approval, dict) else None,
        policy=policy,
        runtime=runtime,
        db_path=db_path,
    )
    artifact_path = write_run_artifact(runs_dir, "create_live_execute_runner", payload)
    return {**payload, "artifact_path": str(artifact_path)}
