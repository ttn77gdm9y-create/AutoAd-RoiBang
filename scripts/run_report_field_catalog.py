#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from roibang_v2.config import load_json, load_runtime_config
from roibang_v2.db.bootstrap import bootstrap_database
from roibang_v2.workflows.report_field_catalog import (
    build_report_field_catalog_preflight,
    run_report_field_catalog_request,
)


def run_from_args(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check current OceanEngine report fields and local report presets.")
    parser.add_argument("--config", default="configs/runtime.example.json")
    parser.add_argument("--request", default="configs/report-field-catalog.disabled.example.json")
    parser.add_argument("--db", default=None)
    parser.add_argument("--runs-dir", default=None)
    parser.add_argument("--preflight", action="store_true", help="Write a plan without external calls.")
    args = parser.parse_args(argv)

    config = load_runtime_config(args.config)
    request = load_json(args.request)
    cfg = request.get("report_field_catalog") if isinstance(request.get("report_field_catalog"), dict) else request
    openapi_http = cfg.get("openapi_http") if isinstance(cfg.get("openapi_http"), dict) else {}

    if args.preflight:
        if config.execution_enabled or config.external_api_enabled:
            raise RuntimeError("report field catalog preflight requires runtime gates disabled")
        if bool(openapi_http.get("enabled", False)):
            raise RuntimeError("report field catalog preflight requires openapi_http.enabled=false")
    else:
        if not config.external_api_enabled:
            raise RuntimeError("report field catalog requires runtime external_api_enabled=true")
        if config.execution_enabled:
            raise RuntimeError("report field catalog must keep runtime execution_enabled=false")
        if not bool(openapi_http.get("enabled", False)):
            raise RuntimeError("report field catalog requires openapi_http.enabled=true")

    db_path = args.db or config.database_path
    runs_dir = args.runs_dir or config.runs_dir
    bootstrap_database(db_path)
    if args.preflight:
        result = build_report_field_catalog_preflight(request, db_path=db_path, runs_dir=runs_dir)
    else:
        result = run_report_field_catalog_request(request, db_path=db_path, runs_dir=runs_dir)
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
