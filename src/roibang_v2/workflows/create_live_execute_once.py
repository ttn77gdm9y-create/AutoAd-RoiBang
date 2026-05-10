from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from roibang_v2.runs import write_run_artifact
from roibang_v2.workflows.create_live_execute_runner import build_create_live_execute_runner

Transport = Callable[[dict[str, Any]], dict[str, Any]]


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
        "runner_result": None,
        "failure": None,
        "actions": [],
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

    runner_result = build_create_live_execute_runner(
        create_execute_artifact=create_execute_artifact,
        create_first_live_runbook_artifact=create_first_live_runbook_artifact,
        create_live_payload_adapter_scaffold_artifact=create_live_payload_adapter_scaffold_artifact,
        create_live_approval_artifact=create_live_approval_artifact,
        policy=policy,
        runtime=runtime,
        db_path=db_path,
        transport=transport,
        transport_mode="create_http",
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
        "transport_call_count": int(runner_result.get("test_transport_call_count") or 0),
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
        raise ValueError("create live execute once requires create_live_execution_pack_artifact")
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
