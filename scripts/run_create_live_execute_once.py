#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from roibang_v2.config import load_json, load_runtime_config
from roibang_v2.integrations.oceanengine.tokens import token_health
from roibang_v2.runs import write_run_artifact
from roibang_v2.workflows.create_http_transport import CREATE_ENDPOINT_ALLOWLIST, build_create_http_transport
from roibang_v2.workflows.create_live_execute_once import run_create_live_execute_once_request
from roibang_v2.workflows.create_plan_contract import validate_create_plan


def _load_artifact(path: Path) -> dict:
    artifact = load_json(path)
    artifact["artifact_path"] = str(path)
    return artifact


def _runner_policy(policy: dict) -> dict:
    value = policy.get("create_live_execute_once")
    return dict(value) if isinstance(value, dict) else {}


def _transport_config(policy: dict) -> dict:
    runner_policy = _runner_policy(policy)
    cfg = runner_policy.get("create_http_transport")
    return dict(cfg) if isinstance(cfg, dict) else {}


def _create_execute_policy(policy: dict) -> dict:
    cfg = policy.get("create_execute")
    return dict(cfg) if isinstance(cfg, dict) else {}


def _live_api_policy(policy: dict) -> dict:
    cfg = _create_execute_policy(policy).get("live_api")
    return dict(cfg) if isinstance(cfg, dict) else {}


def _payload_schema_policy(policy: dict) -> dict:
    cfg = _create_execute_policy(policy).get("payload_schema")
    return dict(cfg) if isinstance(cfg, dict) else {}


_TOKEN_HEALTH_FIELDS = (
    "ok",
    "workflow",
    "status",
    "store_file",
    "user_id",
    "access_token_present",
    "refresh_token_present",
    "expires_at",
    "refresh_token_expires_at",
    "updated_at",
    "expires_in_seconds",
    "refresh_token_expires_in_seconds",
)


def _redacted_token_health(value: dict[str, Any]) -> dict[str, Any]:
    return {name: value.get(name) for name in _TOKEN_HEALTH_FIELDS if name in value}


def _token_pointer_status(transport_cfg: dict) -> dict[str, Any]:
    token_store = transport_cfg.get("token_store") if isinstance(transport_cfg.get("token_store"), dict) else {}
    token_store_enabled = bool(token_store.get("enabled", False))
    token_store_file = str(token_store.get("store_file") or "").strip()
    if token_store_enabled:
        health: dict[str, Any] = {"ok": False, "status": "missing_store_file"}
        if token_store_file:
            try:
                health = _redacted_token_health(
                    token_health(token_store_file, user_id=str(token_store.get("user_id") or "default"))
                )
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                health = {
                    "ok": False,
                    "workflow": "oceanengine_token_health",
                    "status": "unreadable_store",
                    "store_file": token_store_file,
                    "user_id": str(token_store.get("user_id") or "default"),
                    "error_type": type(exc).__name__,
                }
        auto_refresh_ready = (
            bool(token_store.get("auto_refresh", False))
            and bool(health.get("refresh_token_present"))
            and int(health.get("refresh_token_expires_in_seconds") or 0) > 0
        )
        return {
            "source": "token_store",
            "pointer_ready": bool(token_store_file),
            "value_ready": bool(health.get("ok")) or auto_refresh_ready,
            "token_health": health,
        }
    token_env = str(transport_cfg.get("token_env") or "").strip()
    if token_env:
        return {
            "source": "token_env",
            "pointer_ready": True,
            "value_ready": bool(os.environ.get(token_env, "").strip()),
        }
    token_file = str(transport_cfg.get("token_file") or "").strip()
    if token_file:
        path = Path(token_file)
        return {
            "source": "token_file",
            "pointer_ready": True,
            "value_ready": bool(path.exists() and path.read_text(encoding="utf-8").strip()),
        }
    return {"source": "", "pointer_ready": False, "value_ready": False}


def _endpoint_checks(policy: dict) -> dict[str, bool]:
    endpoints = _live_api_policy(policy).get("endpoints")
    rows = endpoints if isinstance(endpoints, dict) else {}
    required_operations = {"create_project", "create_unit", "bind_material", "lookup_target_material"}
    return {
        f"create_execute.live_api.endpoints.{operation}": str(rows.get(operation) or "").strip() == endpoint
        for operation, endpoint in CREATE_ENDPOINT_ALLOWLIST.items()
        if operation in required_operations
    }


def _transport_config_readiness(*, policy: dict, runtime_execution: bool, runtime_external_api: bool) -> dict:
    runner_policy = _runner_policy(policy)
    transport_cfg = _transport_config(policy)
    token_status = _token_pointer_status(transport_cfg)
    checks = {
        "runtime.execution_enabled": bool(runtime_execution),
        "runtime.external_api_enabled": bool(runtime_external_api),
        "create_execute.live_api.enabled": bool(_live_api_policy(policy).get("enabled", False)),
        "create_execute.payload_schema.live_payload_generation_enabled": bool(
            _payload_schema_policy(policy).get("live_payload_generation_enabled", False)
        ),
        "create_live_execute_once.allow_create_http_transport": bool(
            runner_policy.get("allow_create_http_transport", False)
        ),
        "create_http_transport.enabled": bool(transport_cfg.get("enabled", False)),
        "create_http_transport.allow_mutation": bool(transport_cfg.get("allow_mutation", False)),
        "create_http_transport.run_id": bool(str(transport_cfg.get("run_id") or "").strip()),
        "create_http_transport.operator": bool(str(transport_cfg.get("operator") or "").strip()),
        "create_http_transport.token_pointer": bool(token_status.get("pointer_ready")),
        "create_http_transport.token_value": bool(token_status.get("value_ready")),
        **_endpoint_checks(policy),
    }
    missing = [name for name, ok in checks.items() if not ok]
    readiness = {
        "ready": not missing,
        "token_pointer": str(token_status.get("source") or ""),
        "checks": checks,
        "missing": missing,
        "plain_language": "本地真实执行配置已就绪。" if not missing else "本地真实执行配置还缺：" + "、".join(missing),
    }
    if isinstance(token_status.get("token_health"), dict):
        readiness["token_health"] = token_status["token_health"]
    return readiness


def _should_construct_direct_transport(*, policy: dict, runtime_execution: bool, runtime_external_api: bool) -> bool:
    runner_policy = _runner_policy(policy)
    return (
        runtime_execution
        and runtime_external_api
        and bool(runner_policy.get("allow_create_http_transport", False))
    )


def _blocked_missing_artifact(*, runs_dir: Path, message: str, local_config_readiness: dict | None = None) -> dict:
    payload = {
        "ok": False,
        "workflow": "create_live_execute_once",
        "phase": "phase2_preparation",
        "execution_enabled": False,
        "live_execute_enabled": False,
        "external_api_calls": 0,
        "status": "blocked",
        "blocking_reasons": [message],
        "transport_call_count": 0,
        "idempotency": {
            "status": "not_checked",
            "skipped_existing_provider_id_count": 0,
            "skipped_provider_id_records": [],
            "skipped_existing_material_bind_count": 0,
            "skipped_material_bind_records": [],
        },
        "material_bind_records": [],
        "actions": [],
    }
    if local_config_readiness is not None:
        payload["local_config_readiness"] = local_config_readiness
    payload["artifact_path"] = str(write_run_artifact(runs_dir, "create_live_execute_once", payload))
    return payload


def _blocked_plan_result(
    *,
    runs_dir: Path,
    blocking_reasons: list[str],
    create_plan_validation: dict | None = None,
    local_config_readiness: dict | None = None,
) -> dict:
    payload = {
        "ok": False,
        "workflow": "create_live_execute_once",
        "phase": "phase2_preparation",
        "execution_enabled": False,
        "live_execute_enabled": False,
        "external_api_calls": 0,
        "status": "blocked",
        "blocking_reasons": blocking_reasons,
        "transport_call_count": 0,
        "idempotency": {
            "status": "not_checked",
            "skipped_existing_provider_id_count": 0,
            "skipped_provider_id_records": [],
            "skipped_existing_material_bind_count": 0,
            "skipped_material_bind_records": [],
        },
        "material_bind_records": [],
        "create_plan_validation": create_plan_validation or {},
        "actions": [],
    }
    if local_config_readiness is not None:
        payload["local_config_readiness"] = local_config_readiness
    payload["artifact_path"] = str(write_run_artifact(runs_dir, "create_live_execute_once", payload))
    return payload


def _config_only_result(
    *,
    runs_dir: Path,
    local_config_readiness: dict,
    create_plan_validation: dict | None = None,
) -> dict:
    ready = bool(local_config_readiness.get("ready", False))
    blocking_reasons = [] if ready else [str(local_config_readiness.get("plain_language") or "本地真实执行配置未就绪。")]
    payload = {
        "ok": ready,
        "workflow": "create_live_execute_once",
        "phase": "phase2_preparation",
        "execution_enabled": False,
        "live_execute_enabled": False,
        "external_api_calls": 0,
        "status": "config_ready" if ready else "blocked",
        "blocking_reasons": blocking_reasons,
        "transport_call_count": 0,
        "idempotency": {
            "status": "not_checked",
            "skipped_existing_provider_id_count": 0,
            "skipped_provider_id_records": [],
            "skipped_existing_material_bind_count": 0,
            "skipped_material_bind_records": [],
        },
        "material_bind_records": [],
        "create_plan_validation": create_plan_validation or {},
        "local_config_readiness": local_config_readiness,
        "actions": [],
    }
    payload["artifact_path"] = str(write_run_artifact(runs_dir, "create_live_execute_once", payload))
    return payload


def _create_execute_summary(create_execute: dict) -> dict:
    value = create_execute.get("summary")
    return dict(value) if isinstance(value, dict) else {}


def _plan_blocking_reasons(*, create_plan: dict, create_execute: dict, policy: dict, db_path: Path) -> tuple[list[str], dict]:
    validation = validate_create_plan(create_plan, policy=policy, db_path=db_path)
    reasons = [str(item) for item in validation.get("violations") or []]
    plan_id = str(create_plan.get("plan_id") or "")
    execute_plan_id = str(_create_execute_summary(create_execute).get("plan_id") or "")
    if plan_id and execute_plan_id and plan_id != execute_plan_id:
        reasons.append("create_plan.plan_id must match create_execute.summary.plan_id")
    return reasons, validation


def _print_result(result: dict) -> None:
    output = {
        "ok": result["ok"],
        "workflow": result["workflow"],
        "phase": result["phase"],
        "execution_enabled": result["execution_enabled"],
        "live_execute_enabled": result["live_execute_enabled"],
        "external_api_calls": result["external_api_calls"],
        "status": result["status"],
        "blocking_reasons": result["blocking_reasons"],
        "transport_call_count": result["transport_call_count"],
        "idempotency": result["idempotency"],
        "material_bind_records": result["material_bind_records"],
        "artifact_path": result["artifact_path"],
    }
    if "local_config_readiness" in result:
        output["local_config_readiness"] = result["local_config_readiness"]
    if "create_plan_validation" in result:
        validation = result["create_plan_validation"] if isinstance(result["create_plan_validation"], dict) else {}
        output["allowed_account_contract"] = validation.get("allowed_account_contract", {})
    print(json.dumps(output, ensure_ascii=False, indent=2))


def _persist_result_update(result: dict) -> None:
    artifact_path = str(result.get("artifact_path") or "").strip()
    if artifact_path:
        Path(artifact_path).write_text(json.dumps(result, ensure_ascii=False, sort_keys=True), encoding="utf-8")


def run_from_args(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one-shot live create from create_plan JSON and create_execute artifact.")
    parser.add_argument("--config", default="configs/runtime.example.json")
    parser.add_argument("--policy", default="policies/create-policy.example.json")
    parser.add_argument("--plan", required=True)
    parser.add_argument("--create-execute-artifact", required=True)
    parser.add_argument("--check-config-only", action="store_true")
    args = parser.parse_args(argv)

    config = load_runtime_config(args.config)
    policy = load_json(args.policy)
    local_config_readiness = _transport_config_readiness(
        policy=policy,
        runtime_execution=config.execution_enabled,
        runtime_external_api=config.external_api_enabled,
    )
    try:
        create_plan = load_json(args.plan)
    except FileNotFoundError as exc:
        result = _blocked_plan_result(
            runs_dir=config.runs_dir,
            blocking_reasons=[str(exc)],
            local_config_readiness=local_config_readiness,
        )
        _print_result(result)
        return 0
    try:
        create_execute = _load_artifact(Path(args.create_execute_artifact))
    except FileNotFoundError as exc:
        result = _blocked_missing_artifact(
            runs_dir=config.runs_dir,
            message=str(exc),
            local_config_readiness=local_config_readiness,
        )
        _print_result(result)
        return 0
    reasons, validation = _plan_blocking_reasons(
        create_plan=create_plan,
        create_execute=create_execute,
        policy=policy,
        db_path=config.database_path,
    )
    if reasons:
        result = _blocked_plan_result(
            runs_dir=config.runs_dir,
            blocking_reasons=reasons,
            create_plan_validation=validation,
            local_config_readiness=local_config_readiness,
        )
        _print_result(result)
        return 0
    if args.check_config_only:
        result = _config_only_result(
            runs_dir=config.runs_dir,
            local_config_readiness=local_config_readiness,
            create_plan_validation=validation,
        )
        _print_result(result)
        return 0
    if not bool(local_config_readiness.get("ready", False)):
        result = _blocked_plan_result(
            runs_dir=config.runs_dir,
            blocking_reasons=[str(local_config_readiness.get("plain_language") or "本地真实执行配置未就绪。")],
            create_plan_validation=validation,
            local_config_readiness=local_config_readiness,
        )
        _print_result(result)
        return 0
    transport = None
    if _should_construct_direct_transport(
        policy=policy,
        runtime_execution=config.execution_enabled,
        runtime_external_api=config.external_api_enabled,
    ):
        transport_cfg = _transport_config(policy)
        response_dir = transport_cfg.get("response_audit_dir") or Path(config.runs_dir) / "create_live_execute_once" / "audit"
        try:
            transport = build_create_http_transport(transport_cfg, response_dir=response_dir)
        except RuntimeError as exc:
            result = _blocked_plan_result(
                runs_dir=config.runs_dir,
                blocking_reasons=[str(exc)],
                create_plan_validation=validation,
                local_config_readiness=local_config_readiness,
            )
            _print_result(result)
            return 0

    request_payload = {
        "create_execute_artifact": create_execute,
        "policy": policy,
        "runtime": {
            "execution_enabled": config.execution_enabled,
            "external_api_enabled": config.external_api_enabled,
        },
    }
    result = run_create_live_execute_once_request(
        {"create_live_execute_once": request_payload},
        runs_dir=config.runs_dir,
        db_path=config.database_path,
        transport=transport,
    )
    result["local_config_readiness"] = local_config_readiness
    _persist_result_update(result)
    _print_result(result)
    return 0 if result["ok"] else 1


def main() -> int:
    return run_from_args()


if __name__ == "__main__":
    raise SystemExit(main())
