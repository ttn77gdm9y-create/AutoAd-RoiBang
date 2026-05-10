from __future__ import annotations

from pathlib import Path
from typing import Any

from roibang_v2.runs import write_run_artifact

OPERATION_ORDER = ["create_project", "create_unit", "bind_material"]


def _pack_config(request: dict[str, Any]) -> dict[str, Any]:
    value = request.get("create_live_execution_pack")
    return dict(value) if isinstance(value, dict) else dict(request)


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


def _adapter_required_gates(scaffold: dict[str, Any]) -> dict[str, Any]:
    value = _adapter_gate(scaffold).get("required_gates")
    return dict(value) if isinstance(value, dict) else {}


def _endpoints(policy: dict[str, Any], scaffold: dict[str, Any]) -> dict[str, str]:
    scaffold_endpoints = _adapter_gate(scaffold).get("endpoints")
    policy_endpoints = _live_api_policy(policy).get("endpoints")
    source = scaffold_endpoints if isinstance(scaffold_endpoints, dict) else policy_endpoints
    data = source if isinstance(source, dict) else {}
    return {operation: str(data.get(operation) or "") for operation in OPERATION_ORDER}


def _approval(approval_artifact: dict[str, Any]) -> dict[str, Any]:
    value = approval_artifact.get("approval")
    return dict(value) if isinstance(value, dict) else {}


def _scope(runbook: dict[str, Any]) -> dict[str, Any]:
    value = runbook.get("scope")
    return dict(value) if isinstance(value, dict) else {}


def _summary(create_execute: dict[str, Any]) -> dict[str, Any]:
    value = create_execute.get("summary")
    return dict(value) if isinstance(value, dict) else {}


def _provider_payload_drafts(create_execute: dict[str, Any]) -> list[dict[str, Any]]:
    drafts = _rows(create_execute.get("resolved_provider_payload_drafts"))
    if drafts:
        return drafts
    return _rows(create_execute.get("provider_payload_drafts"))


def _drafts_for_operation(create_execute: dict[str, Any], operation: str) -> list[dict[str, Any]]:
    return [draft for draft in _provider_payload_drafts(create_execute) if str(draft.get("operation") or "") == operation]


def _payloads_by_operation(create_execute: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    return {operation: _drafts_for_operation(create_execute, operation) for operation in OPERATION_ORDER}


def _payload_counts(payloads_by_operation: dict[str, list[dict[str, Any]]]) -> dict[str, int]:
    counts = {operation: len(payloads_by_operation[operation]) for operation in OPERATION_ORDER}
    counts["total"] = sum(counts.values())
    return counts


def _contains_lookup_placeholder(value: Any) -> bool:
    if isinstance(value, str):
        return value.startswith("<lookup:") and value.endswith(">")
    if isinstance(value, dict):
        return any(_contains_lookup_placeholder(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_lookup_placeholder(item) for item in value)
    return False


def _lookup_placeholder_count(value: Any) -> int:
    if isinstance(value, str):
        return 1 if _contains_lookup_placeholder(value) else 0
    if isinstance(value, dict):
        return sum(_lookup_placeholder_count(item) for item in value.values())
    if isinstance(value, list):
        return sum(_lookup_placeholder_count(item) for item in value)
    return 0


def _unresolved_lookup_count(create_execute: dict[str, Any]) -> int:
    contract = create_execute.get("resolved_payload_contract")
    if isinstance(contract, dict):
        return int(contract.get("unresolved_lookup_count") or 0)
    return sum(
        _lookup_placeholder_count(draft.get("payload") if isinstance(draft.get("payload"), dict) else {})
        for draft in _provider_payload_drafts(create_execute)
    )


def _payload_safety(create_execute: dict[str, Any]) -> dict[str, Any]:
    drafts = _provider_payload_drafts(create_execute)
    executable_count = sum(1 for draft in drafts if bool(draft.get("executable", False)))
    live_payload_count = sum(
        1
        for draft in drafts
        if bool(draft.get("live_api_payload", False)) or bool(draft.get("live_payload", False))
    )
    unresolved_lookup_count = _unresolved_lookup_count(create_execute)
    return {
        "payloads_non_executable": executable_count == 0,
        "live_payload_count_zero": live_payload_count == 0,
        "no_unresolved_lookup_placeholders": unresolved_lookup_count == 0,
        "executable_count": executable_count,
        "live_payload_count": live_payload_count,
        "unresolved_lookup_count": unresolved_lookup_count,
    }


def _safe_upstream_artifacts(
    *,
    create_execute_artifact: dict[str, Any],
    create_first_live_runbook_artifact: dict[str, Any],
    create_live_payload_adapter_scaffold_artifact: dict[str, Any],
    create_live_approval_artifact: dict[str, Any],
) -> bool:
    for artifact in (
        create_execute_artifact,
        create_first_live_runbook_artifact,
        create_live_payload_adapter_scaffold_artifact,
        create_live_approval_artifact,
    ):
        if bool(artifact.get("execution_enabled", False)):
            return False
        if int(artifact.get("external_api_calls") or 0) != 0:
            return False
    return True


def _scope_matches_payload_counts(scope: dict[str, Any], counts: dict[str, int]) -> bool:
    return (
        int(scope.get("project_count") or 0) == int(counts.get("create_project") or 0)
        and int(scope.get("unit_count") or 0) == int(counts.get("create_unit") or 0)
        and int(scope.get("material_count") or 0) >= int(counts.get("bind_material") or 0)
        and int(scope.get("project_count") or 0) <= int(scope.get("max_project_count") or 0)
        and int(scope.get("unit_count") or 0) <= int(scope.get("max_unit_count") or 0)
        and int(scope.get("material_count") or 0) <= int(scope.get("max_material_count") or 0)
    )


def _runbook_ready(runbook: dict[str, Any]) -> bool:
    return (
        bool(runbook.get("ok", True))
        and str(runbook.get("status") or "") == "ready_for_human_approval"
        and not bool(runbook.get("execution_enabled", False))
        and int(runbook.get("external_api_calls") or 0) == 0
    )


def _live_approval_present(approval_artifact: dict[str, Any]) -> bool:
    return (
        bool(approval_artifact.get("ok", False))
        and str(approval_artifact.get("status") or "") == "approved"
        and not bool(approval_artifact.get("execution_enabled", False))
        and int(approval_artifact.get("external_api_calls") or 0) == 0
    )


def _human_approval_present(approval_artifact: dict[str, Any]) -> bool:
    approval = _approval(approval_artifact)
    return _live_approval_present(approval_artifact) and bool(approval.get("approved", False)) and bool(
        str(approval.get("approval_id") or "").strip()
    )


def _create_http_transport_allowed(policy: dict[str, Any], approval_artifact: dict[str, Any]) -> bool:
    approval = _approval(approval_artifact)
    return bool(_runner_policy(policy).get("allow_create_http_transport", False)) and bool(
        approval.get("allow_create_http_transport", False)
    )


def _final_preflight(
    *,
    create_execute_artifact: dict[str, Any],
    create_first_live_runbook_artifact: dict[str, Any],
    create_live_payload_adapter_scaffold_artifact: dict[str, Any],
    create_live_approval_artifact: dict[str, Any],
    policy: dict[str, Any],
    runtime: dict[str, Any],
    payload_counts: dict[str, int],
) -> dict[str, Any]:
    scope = _scope(create_first_live_runbook_artifact)
    payload_safety = _payload_safety(create_execute_artifact)
    adapter_gate = _adapter_gate(create_live_payload_adapter_scaffold_artifact)
    adapter_required_gates = _adapter_required_gates(create_live_payload_adapter_scaffold_artifact)
    approval_artifact_scope = create_live_approval_artifact.get("scope")
    checks = {
        "safe_artifact_boundary": _safe_upstream_artifacts(
            create_execute_artifact=create_execute_artifact,
            create_first_live_runbook_artifact=create_first_live_runbook_artifact,
            create_live_payload_adapter_scaffold_artifact=create_live_payload_adapter_scaffold_artifact,
            create_live_approval_artifact=create_live_approval_artifact,
        ),
        "runtime_execution_enabled": bool(runtime.get("execution_enabled", False)),
        "runtime_external_api_enabled": bool(runtime.get("external_api_enabled", False)),
        "policy_live_api_enabled": bool(_live_api_policy(policy).get("enabled", False)),
        "policy_live_payload_generation_enabled": bool(
            _payload_schema_policy(policy).get("live_payload_generation_enabled", False)
        ),
        "phase_gate_allows_live_execute": bool(adapter_required_gates.get("phase_gate_allows_live_execute", False))
        or bool(adapter_gate.get("ready_for_live_execute", False)),
        "runbook_ready_for_human_approval": _runbook_ready(create_first_live_runbook_artifact),
        "live_approval_artifact_present": _live_approval_present(create_live_approval_artifact),
        "human_approval_record_present": _human_approval_present(create_live_approval_artifact),
        "create_http_transport_allowed": _create_http_transport_allowed(policy, create_live_approval_artifact),
        "approval_scope_matches_runbook": isinstance(approval_artifact_scope, dict)
        and dict(approval_artifact_scope) == scope,
        "scope_matches_payload_counts": _scope_matches_payload_counts(scope, payload_counts),
        "payloads_non_executable": bool(payload_safety["payloads_non_executable"]),
        "live_payload_count_zero": bool(payload_safety["live_payload_count_zero"]),
        "no_unresolved_lookup_placeholders": bool(payload_safety["no_unresolved_lookup_placeholders"]),
    }
    live_enablement_gate_names = {
        "runtime_execution_enabled",
        "runtime_external_api_enabled",
        "policy_live_api_enabled",
        "policy_live_payload_generation_enabled",
        "create_http_transport_allowed",
    }
    blocking_labels = {
        "safe_artifact_boundary": "upstream artifacts must keep execution_enabled=false and external_api_calls=0",
        "runtime_execution_enabled": "runtime.execution_enabled is false",
        "runtime_external_api_enabled": "runtime.external_api_enabled is false",
        "policy_live_api_enabled": "policy.create_execute.live_api.enabled is false",
        "policy_live_payload_generation_enabled": (
            "policy.create_execute.payload_schema.live_payload_generation_enabled is false"
        ),
        "phase_gate_allows_live_execute": "phase gate has not allowed live execute",
        "runbook_ready_for_human_approval": "first live runbook is not ready for human approval",
        "live_approval_artifact_present": "create_live_approval artifact is missing or not approved",
        "human_approval_record_present": "human approval record is missing",
        "create_http_transport_allowed": "create_http transport is not allowed by policy and approval",
        "approval_scope_matches_runbook": "approval scope must match first live runbook scope",
        "scope_matches_payload_counts": "first live run scope does not match payload counts",
        "payloads_non_executable": "execution pack payload drafts must not be executable",
        "live_payload_count_zero": "execution pack must not contain live payload flags",
        "no_unresolved_lookup_placeholders": "execution pack payloads still contain unresolved lookup placeholders",
    }
    blocking_reasons = [message for key, message in blocking_labels.items() if not bool(checks.get(key, False))]
    ready_for_live_execute = all(bool(value) for value in checks.values())
    ready_for_live_enablement = all(
        bool(value) for key, value in checks.items() if key not in live_enablement_gate_names
    )
    return {
        "status": "ready_for_live_execute" if ready_for_live_execute else "blocked",
        "ready_for_live_execute": ready_for_live_execute,
        "ready_for_live_enablement": ready_for_live_enablement,
        "checks": checks,
        "payload_safety": payload_safety,
        "blocking_reasons": blocking_reasons,
        "execution_enabled": False,
        "external_api_calls": 0,
        "actions": [],
    }


def _approve_contract() -> dict[str, Any]:
    return {
        "approve_is_record_only": True,
        "approve_opens_execution": False,
        "execution_pack_opens_execution": False,
        "requires_separate_human_approval_for_live": True,
    }


def _execution_pack(
    *,
    create_execute_artifact: dict[str, Any],
    create_first_live_runbook_artifact: dict[str, Any],
    create_live_payload_adapter_scaffold_artifact: dict[str, Any],
    create_live_approval_artifact: dict[str, Any],
    policy: dict[str, Any],
    payloads_by_operation: dict[str, list[dict[str, Any]]],
    payload_counts: dict[str, int],
) -> dict[str, Any]:
    approval = _approval(create_live_approval_artifact)
    return {
        "summary": _summary(create_execute_artifact),
        "scope": _scope(create_first_live_runbook_artifact),
        "approval": approval,
        "approve_contract": _approve_contract(),
        "ordered_operations": OPERATION_ORDER,
        "endpoints": _endpoints(policy, create_live_payload_adapter_scaffold_artifact),
        "payload_counts": payload_counts,
        "payloads_by_operation": payloads_by_operation,
        "transport": {
            "mode": "create_http",
            "create_http_transport_allowed": _create_http_transport_allowed(policy, create_live_approval_artifact),
            "external_api_calls_in_pack": 0,
        },
        "execution_enabled": False,
        "external_api_calls": 0,
        "actions": [],
    }


def build_create_live_execution_pack(
    *,
    create_execute_artifact: dict[str, Any],
    create_first_live_runbook_artifact: dict[str, Any],
    create_live_payload_adapter_scaffold_artifact: dict[str, Any],
    create_live_approval_artifact: dict[str, Any],
    policy: dict[str, Any],
    runtime: dict[str, Any],
) -> dict[str, Any]:
    payloads_by_operation = _payloads_by_operation(create_execute_artifact)
    payload_counts = _payload_counts(payloads_by_operation)
    final_preflight = _final_preflight(
        create_execute_artifact=create_execute_artifact,
        create_first_live_runbook_artifact=create_first_live_runbook_artifact,
        create_live_payload_adapter_scaffold_artifact=create_live_payload_adapter_scaffold_artifact,
        create_live_approval_artifact=create_live_approval_artifact,
        policy=policy,
        runtime=runtime,
        payload_counts=payload_counts,
    )
    execution_pack = _execution_pack(
        create_execute_artifact=create_execute_artifact,
        create_first_live_runbook_artifact=create_first_live_runbook_artifact,
        create_live_payload_adapter_scaffold_artifact=create_live_payload_adapter_scaffold_artifact,
        create_live_approval_artifact=create_live_approval_artifact,
        policy=policy,
        payloads_by_operation=payloads_by_operation,
        payload_counts=payload_counts,
    )
    ready = bool(final_preflight["ready_for_live_execute"])
    return {
        "ok": ready,
        "workflow": "create_live_execution_pack",
        "phase": "phase2_preparation",
        "execution_enabled": False,
        "live_execute_enabled": False,
        "external_api_calls": 0,
        "status": "ready_for_live_execute" if ready else "blocked",
        "final_preflight": final_preflight,
        "execution_pack": execution_pack,
        "actions": [],
    }


def run_create_live_execution_pack_request(
    request: dict[str, Any],
    *,
    runs_dir: str | Path,
) -> dict[str, Any]:
    cfg = _pack_config(request)
    create_execute = cfg.get("create_execute_artifact")
    runbook = cfg.get("create_first_live_runbook_artifact")
    scaffold = cfg.get("create_live_payload_adapter_scaffold_artifact")
    approval = cfg.get("create_live_approval_artifact")
    if not isinstance(create_execute, dict):
        raise ValueError("create live execution pack requires create_execute_artifact")
    if not isinstance(runbook, dict):
        raise ValueError("create live execution pack requires create_first_live_runbook_artifact")
    if not isinstance(scaffold, dict):
        raise ValueError("create live execution pack requires create_live_payload_adapter_scaffold_artifact")
    if not isinstance(approval, dict):
        raise ValueError("create live execution pack requires create_live_approval_artifact")
    policy = cfg.get("policy") if isinstance(cfg.get("policy"), dict) else {}
    runtime = cfg.get("runtime") if isinstance(cfg.get("runtime"), dict) else {}
    payload = build_create_live_execution_pack(
        create_execute_artifact=create_execute,
        create_first_live_runbook_artifact=runbook,
        create_live_payload_adapter_scaffold_artifact=scaffold,
        create_live_approval_artifact=approval,
        policy=policy,
        runtime=runtime,
    )
    artifact_path = write_run_artifact(runs_dir, "create_live_execution_pack", payload)
    return {**payload, "artifact_path": str(artifact_path)}
