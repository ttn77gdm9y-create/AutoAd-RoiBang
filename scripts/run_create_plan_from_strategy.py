#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from roibang_v2.config import load_json, load_runtime_config
from roibang_v2.workflows.create_plan_from_strategy import run_create_plan_from_strategy_request


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
                "strategy_id": result["strategy_id"],
                "summary": result["summary"],
                "plan_file_paths": result["plan_file_paths"],
                "violations": result["violations"],
                "artifact_path": result["artifact_path"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def run_from_args(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build create_plan JSON files from an AI-authored strategy JSON.")
    parser.add_argument("--config", default="configs/runtime.example.json")
    parser.add_argument("--strategy", required=True)
    parser.add_argument("--policy", default="policies/create-policy.example.json")
    parser.add_argument("--template-catalog", default="configs/create-templates/wx-mini-game.json")
    parser.add_argument("--output-dir", default="")
    args = parser.parse_args(argv)

    config = load_runtime_config(args.config)
    if config.external_api_enabled or config.execution_enabled:
        raise RuntimeError("create_plan_from_strategy must run with external_api_enabled=false and execution_enabled=false")

    policy = load_json(args.policy)
    result = run_create_plan_from_strategy_request(
        load_json(args.strategy),
        runs_dir=config.runs_dir,
        template_catalog=load_json(args.template_catalog),
        policy=policy,
        db_path=config.database_path,
        output_dir=args.output_dir or None,
    )
    _print_result(result)
    return 0 if result["ok"] else 1


def main() -> int:
    return run_from_args()


if __name__ == "__main__":
    raise SystemExit(main())
