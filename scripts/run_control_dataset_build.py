#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from roibang_v2.config import load_json, load_runtime_config
from roibang_v2.db.bootstrap import bootstrap_database
from roibang_v2.workflows.control_dataset_build import run_control_dataset_build_request


def _load_request(path: str) -> dict:
    if not str(path or "").strip():
        return {}
    source = Path(path)
    if not source.exists():
        return {}
    return load_json(source)


def run_from_args(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build local control-analysis dataset from operation_logs and material_daily_metrics."
    )
    parser.add_argument("--config", default="configs/runtime.example.json")
    parser.add_argument("--request", default="")
    parser.add_argument("--db", default=None)
    parser.add_argument("--runs-dir", default=None)
    parser.add_argument("--window-days", type=int, default=None)
    parser.add_argument("--operation-log-page-size", type=int, default=None)
    parser.add_argument("--product-keyword", default="")
    args = parser.parse_args(argv)

    config = load_runtime_config(args.config)
    if config.external_api_enabled or config.execution_enabled:
        raise RuntimeError("control dataset build requires external_api_enabled=false and execution_enabled=false")

    request = _load_request(args.request)
    if args.window_days is not None:
        request["window_days"] = args.window_days
    if args.operation_log_page_size is not None:
        request["operation_log_page_size"] = args.operation_log_page_size
    if str(args.product_keyword or "").strip():
        request["product_keyword"] = str(args.product_keyword).strip()

    db_path = args.db or config.database_path
    runs_dir = args.runs_dir or config.runs_dir
    bootstrap_database(db_path)
    result = run_control_dataset_build_request(request, db_path=db_path, runs_dir=runs_dir)
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
