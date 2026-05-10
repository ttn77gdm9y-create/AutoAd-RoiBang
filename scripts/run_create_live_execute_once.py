#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from roibang_v2.config import load_json, load_runtime_config
from roibang_v2.workflows.create_http_transport import build_create_http_transport
from roibang_v2.workflows.create_live_execute_once import run_create_live_execute_once_request


def _latest_artifact(runs_dir: Path, workflow: str) -> Path:
    workflow_dir = runs_dir / workflow
    candidates = sorted(workflow_dir.glob("*.json"))
    if not candidates:
        raise FileNotFoundError(f"no {workflow} artifacts found under {workflow_dir}")
    return candidates[-1]


def _artifact_path(value: str, runs_dir: Path, workflow: str) -> Path:
    return Path(value) if str(value or "").strip() else _latest_artifact(runs_dir, workflow)


def _load_artifact(path: Path) -> dict:
    artifact = load_json(path)
    artifact["artifact_path"] = str(path)
    return artifact


def _runner_policy(policy: dict) -> dict:
    value = policy.get("create_live_execute_runner")
    return dict(value) if isinstance(value, dict) else {}


def _transport_config(policy: dict, approval_artifact: dict) -> dict:
    runner_policy = _runner_policy(policy)
    cfg = runner_policy.get("create_http_transport")
    result = dict(cfg) if isinstance(cfg, dict) else {}
    approval = approval_artifact.get("approval") if isinstance(approval_artifact.get("approval"), dict) else {}
    if str(approval.get("approval_id") or "").strip():
        result["approval_id"] = str(approval.get("approval_id") or "")
    if str(approval.get("approved_by") or "").strip():
        result["approved_by"] = str(approval.get("approved_by") or "")
    return result


def _execution_pack_ready(execution_pack: dict) -> bool:
    final_preflight = execution_pack.get("final_preflight")
    return (
        bool(execution_pack.get("ok", False))
        and str(execution_pack.get("status") or "") == "ready_for_live_execute"
        and isinstance(final_preflight, dict)
        and bool(final_preflight.get("ready_for_live_execute", False))
    )


def _should_construct_transport(*, execution_pack: dict, runtime_execution: bool, runtime_external_api: bool) -> bool:
    return _execution_pack_ready(execution_pack) and runtime_execution and runtime_external_api


def run_from_args(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one-shot first live create only after execution pack is ready.")
    parser.add_argument("--config", default="configs/runtime.example.json")
    parser.add_argument("--policy", default="policies/strategy.example.json")
    parser.add_argument("--create-live-execution-pack-artifact", default="")
    parser.add_argument("--create-execute-artifact", default="")
    parser.add_argument("--create-first-live-runbook-artifact", default="")
    parser.add_argument("--create-live-payload-adapter-scaffold-artifact", default="")
    parser.add_argument("--create-live-approval-artifact", default="")
    args = parser.parse_args(argv)

    config = load_runtime_config(args.config)
    policy = load_json(args.policy)
    execution_pack = _load_artifact(
        _artifact_path(args.create_live_execution_pack_artifact, config.runs_dir, "create_live_execution_pack")
    )
    create_execute = _load_artifact(_artifact_path(args.create_execute_artifact, config.runs_dir, "create_execute"))
    runbook = _load_artifact(
        _artifact_path(args.create_first_live_runbook_artifact, config.runs_dir, "create_first_live_runbook")
    )
    scaffold = _load_artifact(
        _artifact_path(
            args.create_live_payload_adapter_scaffold_artifact,
            config.runs_dir,
            "create_live_payload_adapter_scaffold",
        )
    )
    approval = _load_artifact(_artifact_path(args.create_live_approval_artifact, config.runs_dir, "create_live_approval"))
    transport = None
    if _should_construct_transport(
        execution_pack=execution_pack,
        runtime_execution=config.execution_enabled,
        runtime_external_api=config.external_api_enabled,
    ):
        transport_cfg = _transport_config(policy, approval)
        response_dir = transport_cfg.get("response_audit_dir") or Path(config.runs_dir) / "create_live_execute_once" / "audit"
        transport = build_create_http_transport(transport_cfg, response_dir=response_dir)

    result = run_create_live_execute_once_request(
        {
            "create_live_execute_once": {
                "create_live_execution_pack_artifact": execution_pack,
                "create_execute_artifact": create_execute,
                "create_first_live_runbook_artifact": runbook,
                "create_live_payload_adapter_scaffold_artifact": scaffold,
                "create_live_approval_artifact": approval,
                "policy": policy,
                "runtime": {
                    "execution_enabled": config.execution_enabled,
                    "external_api_enabled": config.external_api_enabled,
                },
            }
        },
        runs_dir=config.runs_dir,
        db_path=config.database_path,
        transport=transport,
    )
    print(
        json.dumps(
            {
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
                "artifact_path": result["artifact_path"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def main() -> int:
    return run_from_args()


if __name__ == "__main__":
    raise SystemExit(main())
