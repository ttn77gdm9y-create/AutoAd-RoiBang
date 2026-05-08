#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from roibang_v2.config import load_json, load_runtime_config
from roibang_v2.db.bootstrap import bootstrap_database
from roibang_v2.workflows.daily_report_pipeline import (
    build_daily_report_pipeline_preflight,
    run_daily_report_pipeline_request,
)


def run_from_args(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run RoiBang-v2 daily report fetch, data sync, and learning pipeline.")
    parser.add_argument("--config", default="configs/runtime.example.json")
    parser.add_argument("--request", default="configs/daily-report-pipeline.example.json")
    parser.add_argument("--db", default=None)
    parser.add_argument("--runs-dir", default=None)
    parser.add_argument("--preflight", action="store_true", help="Write a request-count plan without calling OpenAPI.")
    args = parser.parse_args(argv)

    config = load_runtime_config(args.config)
    request = load_json(args.request)
    pipeline = request.get("daily_report_pipeline") if isinstance(request.get("daily_report_pipeline"), dict) else request
    report_fetch = pipeline.get("report_fetch") if isinstance(pipeline.get("report_fetch"), dict) else {}
    source = str(report_fetch.get("source") or "")
    if args.preflight:
        execution = report_fetch.get("execution") if isinstance(report_fetch.get("execution"), dict) else {}
        openapi_http = report_fetch.get("openapi_http") if isinstance(report_fetch.get("openapi_http"), dict) else {}
        if config.execution_enabled or config.external_api_enabled:
            raise RuntimeError("daily report pipeline preflight requires runtime gates disabled")
        if bool(execution.get("external_api_enabled", False)) or bool(openapi_http.get("enabled", False)):
            raise RuntimeError("daily report pipeline preflight requires request external gates disabled")
    elif source == "openapi_http_execute":
        if not config.external_api_enabled:
            raise RuntimeError("daily report pipeline HTTP source requires runtime external_api_enabled=true")
        if config.execution_enabled:
            raise RuntimeError("daily report pipeline must keep runtime execution_enabled=false")
    elif config.external_api_enabled or config.execution_enabled:
        raise RuntimeError("daily report pipeline dry-run requires external_api_enabled=false and execution_enabled=false")

    db_path = args.db or config.database_path
    runs_dir = args.runs_dir or config.runs_dir
    bootstrap_database(db_path)
    if args.preflight:
        result = build_daily_report_pipeline_preflight(request, db_path=db_path, runs_dir=runs_dir)
    else:
        result = run_daily_report_pipeline_request(request, db_path=db_path, runs_dir=runs_dir)
    output = {
        "ok": result["ok"],
        "workflow": result["workflow"],
        "phase": result["phase"],
        "execution_enabled": result["execution_enabled"],
        "external_api_calls": result["external_api_calls"],
        "summary": result["summary"],
        "artifact_path": result["artifact_path"],
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


def main() -> int:
    return run_from_args()


if __name__ == "__main__":
    raise SystemExit(main())
