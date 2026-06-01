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

from roibang_v2.config import load_runtime_config
from roibang_v2.db.bootstrap import bootstrap_database
from roibang_v2.workflows.create_suggestion_strategy_review import run_create_suggestion_strategy_review_request


def run_from_args(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Review readonly create-suggestion strategies and current hit estimates.")
    parser.add_argument("--config", default="configs/runtime.example.json")
    parser.add_argument("--strategy", action="append", default=[], help="策略 JSON，可重复；为空时读取策略目录。")
    parser.add_argument("--strategy-dir", default="configs/create-suggestion-strategies")
    parser.add_argument("--products-dir", default="configs/products")
    parser.add_argument("--mode-dir", default="configs/create-modes")
    parser.add_argument("--template-dir", default="configs/create-templates")
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--product-key", default="")
    parser.add_argument("--target-date", default="")
    parser.add_argument("--include-examples", action="store_true", default=True)
    parser.add_argument("--exclude-examples", action="store_false", dest="include_examples")
    args = parser.parse_args(argv)

    config = load_runtime_config(args.config)
    if config.external_api_enabled or config.execution_enabled:
        raise RuntimeError(
            "create_suggestion_strategy_review only reads local data and requires "
            "external_api_enabled=false and execution_enabled=false"
        )
    bootstrap_database(config.database_path)
    result = run_create_suggestion_strategy_review_request(
        {
            "db_path": str(config.database_path),
            "project_root": args.project_root,
            "products_dir": args.products_dir,
            "mode_dir": args.mode_dir,
            "template_dir": args.template_dir,
            "strategy_paths": args.strategy,
            "strategy_dir": args.strategy_dir,
            "product_key": args.product_key,
            "target_date": args.target_date,
            "include_examples": args.include_examples,
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
                "blocking_reasons": result.get("blocking_reasons", []),
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
