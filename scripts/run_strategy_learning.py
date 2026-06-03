#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from _repo_bootstrap import bootstrap_project_root

bootstrap_project_root()

from roibang_v2.config import load_json, load_runtime_config
from roibang_v2.db.bootstrap import bootstrap_database
from roibang_v2.workflows.strategy_learning import run_strategy_learning_request


def run_from_args(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run readonly strategy learning from operation logs and historical metrics.")
    parser.add_argument("--config", default="configs/runtime.example.json")
    parser.add_argument("--request", default="configs/strategy-learning.example.json")
    parser.add_argument("--target-date", default="")
    parser.add_argument("--start-date", default="")
    parser.add_argument("--end-date", default="")
    parser.add_argument("--products-dir", default="")
    parser.add_argument("--runs-dir", default="")
    args = parser.parse_args(argv)

    runtime = load_runtime_config(args.config)
    if runtime.external_api_enabled or runtime.execution_enabled:
        raise RuntimeError("strategy learning requires external_api_enabled=false and execution_enabled=false")

    bootstrap_database(runtime.database_path)
    request = load_json(args.request)
    payload = dict(request.get("strategy_learning") if isinstance(request.get("strategy_learning"), dict) else request)
    if args.target_date:
        payload["target_date"] = args.target_date
    if args.start_date:
        payload["start_date"] = args.start_date
    if args.end_date:
        payload["end_date"] = args.end_date
    if args.products_dir:
        payload["products_dir"] = args.products_dir
    result = run_strategy_learning_request(
        {"strategy_learning": payload},
        db_path=runtime.database_path,
        runs_dir=args.runs_dir or runtime.runs_dir,
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
                "generated_strategy_config_paths": result["generated_strategy_config_paths"],
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
