#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from roibang_v2.config import load_json, load_runtime_config
from roibang_v2.workflows.create_chain_manifest import run_create_chain_manifest_request


def _latest_artifact(runs_dir: Path, workflow: str) -> Path:
    workflow_dir = runs_dir / workflow
    candidates = sorted(workflow_dir.glob("*.json"))
    if not candidates:
        raise FileNotFoundError(f"no {workflow} artifacts found under {workflow_dir}")
    return candidates[-1]


def _artifact_path(value: str, runs_dir: Path, workflow: str) -> Path:
    return Path(value) if str(value or "").strip() else _latest_artifact(runs_dir, workflow)


def _load_artifact_with_path(path: Path) -> dict:
    artifact = load_json(path)
    artifact["artifact_path"] = str(path)
    return artifact


def run_from_args(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Phase 1 create chain manifest build.")
    parser.add_argument("--config", default="configs/runtime.example.json")
    parser.add_argument("--create-request-artifact", default="")
    parser.add_argument("--create-strategy-plan-artifact", default="")
    parser.add_argument("--create-preflight-artifact", default="")
    parser.add_argument("--create-dry-run-artifact", default="")
    parser.add_argument("--create-approval-artifact", default="")
    parser.add_argument("--create-plan-snapshot-artifact", default="")
    parser.add_argument("--create-execute-artifact", default="")
    parser.add_argument("--create-chain-replay-artifact", default="")
    args = parser.parse_args(argv)

    config = load_runtime_config(args.config)
    if config.external_api_enabled or config.execution_enabled:
        raise RuntimeError("Phase 1 create chain manifest requires external_api_enabled=false and execution_enabled=false")

    request_path = _artifact_path(args.create_request_artifact, config.runs_dir, "create_request")
    plan_path = _artifact_path(args.create_strategy_plan_artifact, config.runs_dir, "create_strategy_plan")
    preflight_path = _artifact_path(args.create_preflight_artifact, config.runs_dir, "create_preflight")
    dry_run_path = _artifact_path(args.create_dry_run_artifact, config.runs_dir, "create_dry_run")
    approval_path = _artifact_path(args.create_approval_artifact, config.runs_dir, "create_approval")
    snapshot_path = _artifact_path(args.create_plan_snapshot_artifact, config.runs_dir, "create_plan_snapshot")
    execute_path = _artifact_path(args.create_execute_artifact, config.runs_dir, "create_execute")
    replay_path = _artifact_path(args.create_chain_replay_artifact, config.runs_dir, "create_chain_replay")

    result = run_create_chain_manifest_request(
        {
            "create_chain_manifest": {
                "create_request_artifact": _load_artifact_with_path(request_path),
                "create_strategy_plan_artifact": _load_artifact_with_path(plan_path),
                "create_preflight_artifact": _load_artifact_with_path(preflight_path),
                "create_dry_run_artifact": _load_artifact_with_path(dry_run_path),
                "create_approval_artifact": _load_artifact_with_path(approval_path),
                "create_plan_snapshot_artifact": _load_artifact_with_path(snapshot_path),
                "create_execute_artifact": _load_artifact_with_path(execute_path),
                "create_chain_replay_artifact": _load_artifact_with_path(replay_path),
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
                "status": result["status"],
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
