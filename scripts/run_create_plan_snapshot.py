#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from roibang_v2.config import load_json, load_runtime_config
from roibang_v2.workflows.create_plan_snapshot import run_create_plan_snapshot_request


def _latest_artifact(runs_dir: Path, workflow: str) -> Path:
    workflow_dir = runs_dir / workflow
    candidates = sorted(workflow_dir.glob("*.json"))
    if not candidates:
        raise FileNotFoundError(f"no {workflow} artifacts found under {workflow_dir}")
    return candidates[-1]


def run_from_args(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Phase 1 create plan snapshot.")
    parser.add_argument("--config", default="configs/runtime.example.json")
    parser.add_argument("--create-strategy-plan-artifact", default="")
    parser.add_argument("--create-preflight-artifact", default="")
    parser.add_argument("--create-dry-run-artifact", default="")
    parser.add_argument("--create-approval-artifact", default="")
    args = parser.parse_args(argv)

    config = load_runtime_config(args.config)
    if config.external_api_enabled or config.execution_enabled:
        raise RuntimeError("Phase 1 create plan snapshot requires external_api_enabled=false and execution_enabled=false")

    plan_path = (
        Path(args.create_strategy_plan_artifact)
        if str(args.create_strategy_plan_artifact or "").strip()
        else _latest_artifact(config.runs_dir, "create_strategy_plan")
    )
    preflight_path = (
        Path(args.create_preflight_artifact)
        if str(args.create_preflight_artifact or "").strip()
        else _latest_artifact(config.runs_dir, "create_preflight")
    )
    dry_run_path = (
        Path(args.create_dry_run_artifact)
        if str(args.create_dry_run_artifact or "").strip()
        else _latest_artifact(config.runs_dir, "create_dry_run")
    )
    approval_path = (
        Path(args.create_approval_artifact)
        if str(args.create_approval_artifact or "").strip()
        else _latest_artifact(config.runs_dir, "create_approval")
    )
    result = run_create_plan_snapshot_request(
        {
            "create_plan_snapshot": {
                "create_strategy_plan_artifact": load_json(plan_path),
                "create_preflight_artifact": load_json(preflight_path),
                "create_dry_run_artifact": load_json(dry_run_path),
                "create_approval_artifact": load_json(approval_path),
            }
        },
        runs_dir=config.runs_dir,
    )
    print(
        json.dumps(
            {
                "ok": result["ok"],
                "workflow": result["workflow"],
                "phase": result["phase"],
                "execution_enabled": result["execution_enabled"],
                "external_api_calls": result["external_api_calls"],
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
