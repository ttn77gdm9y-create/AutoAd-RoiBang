#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from roibang_v2.config import load_json, load_runtime_config
from roibang_v2.workflows.strategy_execute import run_strategy_execute_request


def _latest_artifact(runs_dir: Path, workflow: str) -> Path:
    workflow_dir = runs_dir / workflow
    candidates = sorted(workflow_dir.glob("*.json"))
    if not candidates:
        raise FileNotFoundError(f"no {workflow} artifacts found under {workflow_dir}")
    return candidates[-1]


def run_from_args(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Phase 1 strategy execute hard-block.")
    parser.add_argument("--config", default="configs/runtime.example.json")
    parser.add_argument("--policy", default="policies/strategy.example.json")
    parser.add_argument("--strategy-approval-artifact", default="")
    args = parser.parse_args(argv)

    config = load_runtime_config(args.config)
    if config.external_api_enabled or config.execution_enabled:
        raise RuntimeError("Phase 1 strategy execute requires external_api_enabled=false and execution_enabled=false")

    approval_path = (
        Path(args.strategy_approval_artifact)
        if str(args.strategy_approval_artifact or "").strip()
        else _latest_artifact(config.runs_dir, "strategy_approval")
    )
    policy = load_json(args.policy).get("strategy_execute") or {}
    result = run_strategy_execute_request(
        {
            "strategy_execute": {
                "strategy_approval_artifact": load_json(approval_path),
                "strategy_approval_artifact_path": str(approval_path),
                "policy": policy,
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
