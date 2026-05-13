#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from roibang_v2.config import load_json, load_runtime_config
from roibang_v2.workflows.create_http_transport import build_create_http_transport
from roibang_v2.workflows.create_live_activate_once import run_create_live_activate_once_request


def _transport_config(policy: dict) -> dict:
    runner = policy.get("create_live_execute_once")
    runner = runner if isinstance(runner, dict) else {}
    cfg = runner.get("create_http_transport")
    return dict(cfg) if isinstance(cfg, dict) else {}


def _print_result(result: dict) -> None:
    print(
        json.dumps(
            {
                "ok": result["ok"],
                "workflow": result["workflow"],
                "phase": result["phase"],
                "execution_enabled": result["execution_enabled"],
                "external_api_calls": result["external_api_calls"],
                "status": result["status"],
                "plan_id": result["plan_id"],
                "blocking_reasons": result["blocking_reasons"],
                "summary": result["summary"],
                "activation_batches": result["activation_batches"],
                "artifact_path": result["artifact_path"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def run_from_args(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Activate created live units from provider ID ledger.")
    parser.add_argument("--config", default="configs/runtime.example.json")
    parser.add_argument("--policy", default="policies/create-policy.example.json")
    parser.add_argument("--plan-id", required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)

    config = load_runtime_config(args.config)
    policy = load_json(args.policy)
    execute = bool(args.execute)
    transport = None
    if execute and config.execution_enabled and config.external_api_enabled:
        transport_cfg = _transport_config(policy)
        response_dir = transport_cfg.get("response_audit_dir") or Path(config.runs_dir) / "create_live_activate_once" / "audit"
        transport = build_create_http_transport(transport_cfg, response_dir=response_dir)

    result = run_create_live_activate_once_request(
        {
            "create_live_activate_once": {
                "plan_id": args.plan_id,
                "execute": execute,
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
    _print_result(result)
    return 0 if result["ok"] else 1


def main() -> int:
    return run_from_args()


if __name__ == "__main__":
    raise SystemExit(main())
