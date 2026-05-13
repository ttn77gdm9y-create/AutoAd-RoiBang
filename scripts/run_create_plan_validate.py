#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from roibang_v2.config import load_json, load_runtime_config
from roibang_v2.runs import write_run_artifact
from roibang_v2.workflows.create_plan_contract import validate_create_plan


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
                "summary": result["summary"],
                "source_contract": result["source_contract"],
                "allowed_account_contract": result["allowed_account_contract"],
                "violations": result["violations"],
                "artifact_path": result["artifact_path"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def run_from_args(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate create_plan JSON before preview or live create.")
    parser.add_argument("--config", default="configs/runtime.example.json")
    parser.add_argument("--plan", required=True)
    parser.add_argument("--policy", default="policies/create-policy.example.json")
    args = parser.parse_args(argv)

    config = load_runtime_config(args.config)
    plan = load_json(args.plan)
    policy = load_json(args.policy)
    result = validate_create_plan(plan, policy=policy, db_path=config.database_path)
    artifact_path = write_run_artifact(config.runs_dir, "create_plan_validate", result)
    result = {**result, "artifact_path": str(artifact_path)}
    _print_result(result)
    return 0 if result["ok"] else 1


def main() -> int:
    return run_from_args()


if __name__ == "__main__":
    raise SystemExit(main())
