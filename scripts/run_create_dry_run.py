#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from roibang_v2.config import load_json, load_runtime_config
from roibang_v2.workflows.create_dry_run import run_create_dry_run_request


def _latest_artifact(runs_dir: Path, workflow: str) -> Path:
    workflow_dir = runs_dir / workflow
    candidates = sorted(workflow_dir.glob("*.json"))
    if not candidates:
        raise FileNotFoundError(f"no {workflow} artifacts found under {workflow_dir}")
    return candidates[-1]


def run_from_args(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Phase 1 create dry-run simulation.")
    parser.add_argument("--config", default="configs/runtime.example.json")
    parser.add_argument("--policy", default="policies/strategy.example.json")
    parser.add_argument("--create-strategy-plan-artifact", default="")
    parser.add_argument("--create-preflight-artifact", default="")
    parser.add_argument("--create-provider-field-map-check-artifact", default="")
    args = parser.parse_args(argv)

    config = load_runtime_config(args.config)
    if config.external_api_enabled or config.execution_enabled:
        raise RuntimeError("Phase 1 create dry-run requires external_api_enabled=false and execution_enabled=false")

    plan_path = Path(args.create_strategy_plan_artifact) if args.create_strategy_plan_artifact else _latest_artifact(
        config.runs_dir,
        "create_strategy_plan",
    )
    preflight_path = Path(args.create_preflight_artifact) if args.create_preflight_artifact else _latest_artifact(
        config.runs_dir,
        "create_preflight",
    )
    field_map_check_path = (
        Path(args.create_provider_field_map_check_artifact)
        if args.create_provider_field_map_check_artifact
        else _latest_artifact(config.runs_dir, "create_provider_field_map_check")
    )
    result = run_create_dry_run_request(
        {
            "create_dry_run": {
                "create_strategy_plan_artifact": load_json(plan_path),
                "create_strategy_plan_artifact_path": str(plan_path),
                "create_preflight_artifact": load_json(preflight_path),
                "create_preflight_artifact_path": str(preflight_path),
                "create_provider_field_map_check_artifact": load_json(field_map_check_path),
                "create_provider_field_map_check_artifact_path": str(field_map_check_path),
                "policy": load_json(args.policy).get("create_dry_run") or {},
            }
        },
        runs_dir=config.runs_dir,
        db_path=config.database_path,
    )
    print(
        json.dumps(
            {"ok": result["ok"], "status": result["status"], "artifact_path": result["artifact_path"]},
            ensure_ascii=False,
        )
    )
    return 0 if result["ok"] else 1


def main() -> int:
    return run_from_args()


if __name__ == "__main__":
    raise SystemExit(main())
