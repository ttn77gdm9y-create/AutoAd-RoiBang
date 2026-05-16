#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from _repo_bootstrap import bootstrap_project_root

bootstrap_project_root()

from roibang_v2.config import load_json, load_runtime_config
from roibang_v2.integrations.oceanengine.tokens import token_health
from roibang_v2.runs import write_run_artifact
from roibang_v2.workflows.create_dry_run import build_create_dry_run
from roibang_v2.workflows.create_execute import build_create_execute_from_dry_run
from roibang_v2.workflows.create_http_transport import CREATE_ENDPOINT_ALLOWLIST, build_create_http_transport
from roibang_v2.workflows.create_lineage import create_ref
from roibang_v2.workflows.create_live_execute_once import run_create_live_execute_once_request
from roibang_v2.workflows.create_plan_contract import validate_create_plan


DEFAULT_DIRECT_CREATE_DRY_RUN_POLICY = {
    "max_projects_per_dry_run": 500,
    "max_units_per_dry_run": 5000,
    "provider_adapter": {
        "provider": "oceanengine",
        "field_mapping_version": "phase2.oceanengine.create_payload.prep.v1",
        "mapping_verified": True,
    },
    "provider_field_map_path": "configs/provider-field-maps/oceanengine.create.phase2-prep.example.json",
}


def _load_artifact(path: Path) -> dict:
    artifact = load_json(path)
    artifact["artifact_path"] = str(path)
    return artifact


def _create_plan_artifact(artifact: dict) -> dict:
    nested = artifact.get("create_strategy_plan") if isinstance(artifact.get("create_strategy_plan"), dict) else None
    return nested if nested is not None else artifact


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


def _create_execute_payload_drafts(create_execute: dict) -> list[dict]:
    drafts = create_execute.get("provider_payload_drafts")
    if isinstance(drafts, list) and drafts:
        return [row for row in drafts if isinstance(row, dict)]
    drafts = create_execute.get("resolved_provider_payload_drafts")
    return [row for row in drafts if isinstance(row, dict)] if isinstance(drafts, list) else []


def _existing_plan_ledger(*, db_path: Path, create_execute: dict) -> dict[str, Any]:
    summary = _create_execute_summary(create_execute)
    plan_id = str(summary.get("plan_id") or "").strip()
    request_id = str(summary.get("request_id") or "").strip()
    if not plan_id or not request_id:
        return {"count": 0, "plan_id": plan_id, "request_id": request_id, "by_entity_type": {}, "samples": []}
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT entity_type, COUNT(*)
            FROM create_provider_id_ledger
            WHERE plan_id = ?
              AND request_id = ?
              AND status = 'active'
              AND entity_type IN ('project', 'promotion')
              AND provider_id NOT LIKE 'mock_%'
              AND source_workflow != 'create_mock_execute'
            GROUP BY entity_type
            """,
            (plan_id, request_id),
        ).fetchall()
        samples = conn.execute(
            """
            SELECT entity_type, local_key, provider_id, advertiser_id
            FROM create_provider_id_ledger
            WHERE plan_id = ?
              AND request_id = ?
              AND status = 'active'
              AND entity_type IN ('project', 'promotion')
              AND provider_id NOT LIKE 'mock_%'
              AND source_workflow != 'create_mock_execute'
            ORDER BY entity_type, first_seen_at
            LIMIT 10
            """,
            (plan_id, request_id),
        ).fetchall()
    by_entity_type = {str(entity_type): int(count) for entity_type, count in rows}
    return {
        "count": sum(by_entity_type.values()),
        "plan_id": plan_id,
        "request_id": request_id,
        "by_entity_type": by_entity_type,
        "samples": [
            {
                "entity_type": str(row[0]),
                "local_key": str(row[1]),
                "provider_id": str(row[2]),
                "advertiser_id": str(row[3]),
            }
            for row in samples
        ],
    }


def _plan_blocking_reasons(*, create_plan: dict, create_execute: dict | None, policy: dict, db_path: Path) -> tuple[list[str], dict]:
    validation = validate_create_plan(create_plan, policy=policy, db_path=db_path)
    reasons = [str(item) for item in validation.get("violations") or []]
    plan_id = str(create_plan.get("plan_id") or "")
    execute_plan_id = str(_create_execute_summary(create_execute or {}).get("plan_id") or "")
    if plan_id and execute_plan_id and plan_id != execute_plan_id:
        reasons.append("create_plan.plan_id must match create_execute.summary.plan_id")
    return reasons, validation


def _synthetic_preflight_artifact(create_plan: dict) -> dict:
    plan_ref = create_ref(workflow="create_strategy_plan", artifact=create_plan)
    return {
        "ok": True,
        "workflow": "create_preflight",
        "phase": "phase1",
        "execution_enabled": False,
        "external_api_calls": 0,
        "status": "passed",
        "summary": {
            "plan_id": plan_ref["plan_id"],
            "request_id": plan_ref["request_id"],
            "target_date": plan_ref["target_date"],
        },
        "lineage": {"create_strategy_plan": plan_ref},
        "violations": [],
        "actions": [],
    }


def _direct_dry_run_policy(policy: dict) -> dict:
    cfg = policy.get("create_dry_run") if isinstance(policy.get("create_dry_run"), dict) else {}
    return {**DEFAULT_DIRECT_CREATE_DRY_RUN_POLICY, **cfg}


def _project_unit_ledger_scope(*, create_plan: dict, stage: str) -> dict:
    plan_ref = create_ref(workflow="create_strategy_plan", artifact=create_plan)
    return {
        "stage": stage,
        "status": "plan_scoped_no_archive",
        "plan_id": str(plan_ref.get("plan_id") or ""),
        "request_id": str(plan_ref.get("request_id") or ""),
        "archived_count": 0,
        "entity_types": ["project", "promotion"],
        "execution_enabled": False,
        "external_api_calls": 0,
        "actions": [],
    }


def _build_internal_create_execute(*, create_plan: dict, policy: dict, db_path: Path) -> dict:
    ledger_scope = _project_unit_ledger_scope(
        create_plan=create_plan,
        stage="before_internal_create_execute",
    )
    dry_run = build_create_dry_run(
        create_strategy_plan_artifact=create_plan,
        create_preflight_artifact=_synthetic_preflight_artifact(create_plan),
        policy=_direct_dry_run_policy(policy),
    )
    create_execute = build_create_execute_from_dry_run(
        create_dry_run_artifact=dry_run,
        policy={},
        db_path=db_path,
    )
    if not create_execute.get("resolved_provider_payload_drafts") and dry_run.get("provider_payload_drafts"):
        create_execute["provider_payload_drafts"] = list(dry_run["provider_payload_drafts"])
    create_execute["generated_from_create_plan"] = True
    create_execute["pre_create_execute_ledger_archive"] = ledger_scope
    return create_execute


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
    if "pre_create_execute_ledger_archive" in result:
        output["pre_create_execute_ledger_archive"] = result["pre_create_execute_ledger_archive"]
    if "existing_plan_ledger" in result:
        output["existing_plan_ledger"] = result["existing_plan_ledger"]
    if "create_plan_validation" in result:
        validation = result["create_plan_validation"] if isinstance(result["create_plan_validation"], dict) else {}
        output["allowed_account_contract"] = validation.get("allowed_account_contract", {})
    print(json.dumps(output, ensure_ascii=False, indent=2))


def _persist_result_update(result: dict) -> None:
    artifact_path = str(result.get("artifact_path") or "").strip()
    if artifact_path:
        Path(artifact_path).write_text(json.dumps(result, ensure_ascii=False, sort_keys=True), encoding="utf-8")


def run_from_args(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one-shot live create from create_plan JSON.")
    parser.add_argument("--config", default="configs/runtime.example.json")
    parser.add_argument("--policy", default="policies/create-policy.example.json")
    parser.add_argument("--plan", required=True)
    parser.add_argument("--create-execute-artifact", default="")
    parser.add_argument("--check-config-only", action="store_true")
    parser.add_argument(
        "--resume-existing-plan",
        action="store_true",
        help="Allow continuing a plan that already has project/unit provider IDs in the local ledger.",
    )
    args = parser.parse_args(argv)

    config = load_runtime_config(args.config)
    policy = load_json(args.policy)
    local_config_readiness = _transport_config_readiness(
        policy=policy,
        runtime_execution=config.execution_enabled,
        runtime_external_api=config.external_api_enabled,
    )
    try:
        create_plan = _create_plan_artifact(load_json(args.plan))
    except FileNotFoundError as exc:
        result = _blocked_plan_result(
            runs_dir=config.runs_dir,
            blocking_reasons=[str(exc)],
            local_config_readiness=local_config_readiness,
        )
        _print_result(result)
        return 0
    create_execute = None
    if str(args.create_execute_artifact or "").strip():
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
    if create_execute is None:
        create_execute = _build_internal_create_execute(
            create_plan=create_plan,
            policy=policy,
            db_path=config.database_path,
        )
    if not _create_execute_payload_drafts(create_execute):
        result = _blocked_plan_result(
            runs_dir=config.runs_dir,
            blocking_reasons=["create_plan did not produce provider payload drafts; use a create_mode artifact or create_strategy_plan artifact"],
            create_plan_validation=validation,
            local_config_readiness=local_config_readiness,
        )
        _print_result(result)
        return 0
    existing_plan_ledger = _existing_plan_ledger(db_path=config.database_path, create_execute=create_execute)
    if int(existing_plan_ledger.get("count") or 0) > 0 and not args.resume_existing_plan:
        result = _blocked_plan_result(
            runs_dir=config.runs_dir,
            blocking_reasons=[
                "existing active project/unit provider IDs found for this plan_id/request_id; generate a new create_mode plan or pass --resume-existing-plan to continue the old plan"
            ],
            create_plan_validation=validation,
            local_config_readiness=local_config_readiness,
        )
        result["existing_plan_ledger"] = existing_plan_ledger
        if isinstance(create_execute.get("pre_create_execute_ledger_archive"), dict):
            result["pre_create_execute_ledger_archive"] = create_execute["pre_create_execute_ledger_archive"]
        _persist_result_update(result)
        _print_result(result)
        return 1
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
    if isinstance(create_execute.get("pre_create_execute_ledger_archive"), dict):
        result["pre_create_execute_ledger_archive"] = create_execute["pre_create_execute_ledger_archive"]
    _persist_result_update(result)
    _print_result(result)
    return 0 if result["ok"] else 1


def main() -> int:
    return run_from_args()


if __name__ == "__main__":
    raise SystemExit(main())
