#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from roibang_v2.config import load_json, load_runtime_config
from roibang_v2.db.bootstrap import bootstrap_database
from roibang_v2.workflows.create_strategy_plan import run_create_strategy_plan_request


def _latest_artifact(runs_dir: Path, workflow: str) -> Path:
    workflow_dir = runs_dir / workflow
    candidates = sorted(workflow_dir.glob("*.json"))
    if not candidates:
        raise FileNotFoundError(f"no {workflow} artifacts found under {workflow_dir}")
    return candidates[-1]


def run_from_args(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a Phase 1 create strategy plan.")
    parser.add_argument("--config", default="configs/runtime.example.json")
    parser.add_argument("--policy", default="policies/create-policy.example.json")
    parser.add_argument("--create-request-artifact", default="")
    args = parser.parse_args(argv)

    config = load_runtime_config(args.config)
    if config.external_api_enabled or config.execution_enabled:
        raise RuntimeError("Phase 1 create strategy plan requires external_api_enabled=false and execution_enabled=false")

    bootstrap_database(config.database_path)
    request_path = Path(args.create_request_artifact) if args.create_request_artifact else _latest_artifact(
        config.runs_dir,
        "create_request",
    )
    policy = load_json(args.policy).get("create_strategy_plan") or {}
    result = run_create_strategy_plan_request(
        load_json(request_path),
        db_path=config.database_path,
        runs_dir=config.runs_dir,
        policy=policy,
        create_request_artifact_path=request_path,
    )
    print(json.dumps({"ok": result["ok"], "artifact_path": result["artifact_path"]}, ensure_ascii=False))
    return 0 if result["ok"] else 1


def main() -> int:
    return run_from_args()


if __name__ == "__main__":
    raise SystemExit(main())
