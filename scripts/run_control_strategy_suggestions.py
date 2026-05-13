#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from roibang_v2.config import load_json, load_runtime_config
from roibang_v2.db.bootstrap import bootstrap_database
from roibang_v2.workflows.control_strategy_suggestions import run_control_strategy_suggestions_request


def _load_request(path: str) -> dict:
    if not str(path or "").strip():
        return {}
    source = Path(path)
    if not source.exists():
        return {}
    return load_json(source)


def run_from_args(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build readonly RoiBang-v2 control strategy suggestions.")
    parser.add_argument("--config", default="configs/runtime.example.json")
    parser.add_argument("--request", default="configs/control-strategy-suggestions.example.json")
    parser.add_argument("--db", default=None)
    parser.add_argument("--runs-dir", default=None)
    parser.add_argument("--target-date", default="")
    parser.add_argument("--product-keyword", default="")
    args = parser.parse_args(argv)

    config = load_runtime_config(args.config)
    if config.external_api_enabled or config.execution_enabled:
        raise RuntimeError("control strategy suggestions requires external_api_enabled=false and execution_enabled=false")

    request = _load_request(args.request)
    if "control_strategy_suggestions" in request and isinstance(request["control_strategy_suggestions"], dict):
        request = dict(request["control_strategy_suggestions"])
    if str(args.target_date or "").strip():
        request["target_date"] = str(args.target_date).strip()
    if str(args.product_keyword or "").strip():
        request["product_keyword"] = str(args.product_keyword).strip()

    db_path = args.db or config.database_path
    runs_dir = args.runs_dir or config.runs_dir
    bootstrap_database(db_path)
    result = run_control_strategy_suggestions_request(request, db_path=db_path, runs_dir=runs_dir)
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
