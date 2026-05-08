#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from roibang_v2.config import load_json, load_runtime_config
from roibang_v2.db.bootstrap import bootstrap_database
from roibang_v2.workflows.strategy_plan import run_strategy_plan_request


def _latest_artifact(runs_dir: Path, workflow: str) -> Path:
    workflow_dir = runs_dir / workflow
    candidates = sorted(workflow_dir.glob("*.json"))
    if not candidates:
        raise FileNotFoundError(f"no {workflow} artifacts found under {workflow_dir}")
    return candidates[-1]


def _optional_latest_artifact(runs_dir: Path, workflow: str) -> Path | None:
    workflow_dir = runs_dir / workflow
    candidates = sorted(workflow_dir.glob("*.json"))
    return candidates[-1] if candidates else None


def run_from_args(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Phase 1 strategy plan generation.")
    parser.add_argument("--config", default="configs/runtime.example.json")
    parser.add_argument("--request", default="configs/requests/example.strategy-request.json")
    parser.add_argument("--policy", default="policies/strategy.example.json")
    parser.add_argument("--learning-artifact", default="")
    parser.add_argument("--material-source-artifact", default="")
    args = parser.parse_args(argv)

    config = load_runtime_config(args.config)
    if config.external_api_enabled or config.execution_enabled:
        raise RuntimeError("Phase 1 strategy plan requires external_api_enabled=false and execution_enabled=false")

    bootstrap_database(config.database_path)
    learning_path = Path(args.learning_artifact) if args.learning_artifact else _latest_artifact(config.runs_dir, "daily_learning")
    material_source_path = (
        Path(args.material_source_artifact)
        if str(args.material_source_artifact or "").strip()
        else _optional_latest_artifact(config.runs_dir, "material_source")
    )
    material_source_artifact = load_json(material_source_path) if material_source_path else None
    policy = load_json(args.policy).get("strategy_plan") or {}
    result = run_strategy_plan_request(
        load_json(args.request),
        db_path=config.database_path,
        runs_dir=config.runs_dir,
        learning_artifact=load_json(learning_path),
        material_source_artifact=material_source_artifact,
        policy=policy,
    )
    print(json.dumps({"ok": result["ok"], "artifact_path": result["artifact_path"]}, ensure_ascii=False))
    return 0 if result["ok"] else 1


def main() -> int:
    return run_from_args()


if __name__ == "__main__":
    raise SystemExit(main())
