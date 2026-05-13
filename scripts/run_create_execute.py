#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from roibang_v2.config import load_json, load_runtime_config
from roibang_v2.workflows.create_execute import run_create_execute_request


def run_from_args(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run local create execute review from an explicit dry-run artifact.")
    parser.add_argument("--config", default="configs/runtime.example.json")
    parser.add_argument("--request", default="")
    parser.add_argument("--policy", default="policies/create-policy.example.json")
    parser.add_argument("--create-dry-run-artifact", required=True)
    args = parser.parse_args(argv)

    config = load_runtime_config(args.config)
    if config.external_api_enabled or config.execution_enabled:
        raise RuntimeError("本地 create execute 要求 external_api_enabled=false 且 execution_enabled=false")

    dry_run_path = Path(args.create_dry_run_artifact)
    policy = load_json(args.policy).get("create_execute") or {}
    request_cfg = load_json(args.request).get("create_execute") if str(args.request or "").strip() else {}
    if isinstance(request_cfg, dict):
        policy = {**policy, **request_cfg}
    result = run_create_execute_request(
        {
            "create_execute": {
                "create_dry_run_artifact": load_json(dry_run_path),
                "create_dry_run_artifact_path": str(dry_run_path),
                "policy": policy,
            }
        },
        runs_dir=config.runs_dir,
        db_path=config.database_path,
    )
    print(
        json.dumps(
            {
                "ok": result["ok"],
                "workflow": result["workflow"],
                "phase": result["phase"],
                "execution_enabled": result["execution_enabled"],
                "external_api_calls": result["external_api_calls"],
                "status": result["status"],
                "reason": result["reason"],
                "summary": result["summary"],
                "artifact_path": result["artifact_path"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if result["ok"] else 1


def main() -> int:
    return run_from_args()


if __name__ == "__main__":
    raise SystemExit(main())
