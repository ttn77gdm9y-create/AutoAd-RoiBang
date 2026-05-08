#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from roibang_v2.config import load_json, load_runtime_config
from roibang_v2.db.bootstrap import bootstrap_database
from roibang_v2.fetch.report_snapshot import run_report_fetch_request


def fetch_from_args(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build local/mock RoiBang-v2 report snapshot files.")
    parser.add_argument("--config", default="configs/runtime.example.json")
    parser.add_argument("--request", default="configs/report-fetch.backfill.example.json")
    parser.add_argument("--db", default=None)
    parser.add_argument("--runs-dir", default=None)
    args = parser.parse_args(argv)

    config = load_runtime_config(args.config)
    request = load_json(args.request)
    report_fetch = request.get("report_fetch") if isinstance(request.get("report_fetch"), dict) else request
    source = str(report_fetch.get("source") or "mock_openapi")
    if source == "openapi_http_execute":
        if not config.external_api_enabled:
            raise RuntimeError("openapi_http_execute requires runtime external_api_enabled=true")
        if config.execution_enabled:
            raise RuntimeError("report fetch must keep runtime execution_enabled=false")
    elif config.external_api_enabled or config.execution_enabled:
        raise RuntimeError("Phase 1 report fetch requires external_api_enabled=false and execution_enabled=false")
    db_path = args.db or config.database_path
    runs_dir = args.runs_dir or config.runs_dir
    bootstrap_database(db_path)
    result = run_report_fetch_request(request, db_path=db_path, runs_dir=runs_dir)
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
    return fetch_from_args()


if __name__ == "__main__":
    raise SystemExit(main())
