#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from copy import deepcopy

from roibang_v2.config import load_json, load_runtime_config
from roibang_v2.db.bootstrap import bootstrap_database
from roibang_v2.workflows.control_dataset_build import (
    build_operation_log_sync_plan_from_metrics,
    run_control_operation_log_history_sync_request,
)


def _request_config(request: dict) -> dict:
    value = request.get("operation_log_history_sync")
    return dict(value) if isinstance(value, dict) else dict(request)


def _enable_readonly_request(request: dict) -> dict:
    updated = deepcopy(request)
    cfg = updated.setdefault("operation_log_history_sync", {}) if "operation_log_history_sync" in updated else updated
    if not isinstance(cfg, dict):
        raise RuntimeError("operation_log_history_sync must be a JSON object")
    openapi_http = cfg.setdefault("openapi_http", {})
    if not isinstance(openapi_http, dict):
        raise RuntimeError("operation_log_history_sync.openapi_http must be a JSON object")
    openapi_http["enabled"] = True
    execution = cfg.setdefault("execution", {})
    if not isinstance(execution, dict):
        raise RuntimeError("operation_log_history_sync.execution must be a JSON object")
    execution["status"] = "execute"
    execution["external_api_enabled"] = True
    return updated


def run_from_args(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sync historical operation logs and build local control dataset.")
    parser.add_argument("--config", default="configs/runtime.example.json")
    parser.add_argument("--request", default="configs/operation-log-history-sync.example.json")
    parser.add_argument("--db", default=None)
    parser.add_argument("--runs-dir", default=None)
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--enable-readonly", action="store_true")
    args = parser.parse_args(argv)

    if args.preflight and args.enable_readonly:
        raise RuntimeError("--preflight cannot be combined with --enable-readonly")

    runtime = load_runtime_config(args.config)
    request = load_json(args.request)
    if args.enable_readonly:
        request = _enable_readonly_request(request)
    cfg = _request_config(request)
    openapi_http = cfg.get("openapi_http") if isinstance(cfg.get("openapi_http"), dict) else {}
    execution = cfg.get("execution") if isinstance(cfg.get("execution"), dict) else {}
    request_external_enabled = bool(openapi_http.get("enabled", False)) or bool(execution.get("external_api_enabled", False))
    if args.preflight:
        if runtime.external_api_enabled or runtime.execution_enabled:
            raise RuntimeError("operation log history preflight requires runtime gates disabled")
        if request_external_enabled:
            raise RuntimeError("operation log history preflight requires request gates disabled")
    elif request_external_enabled:
        if not runtime.external_api_enabled:
            raise RuntimeError("operation log history readonly execution requires runtime external_api_enabled=true")
        if runtime.execution_enabled:
            raise RuntimeError("operation log history sync must keep runtime execution_enabled=false")
    else:
        raise RuntimeError("operation log history sync needs --preflight or --enable-readonly")

    db_path = args.db or runtime.database_path
    runs_dir = args.runs_dir or runtime.runs_dir
    bootstrap_database(db_path)
    if args.preflight:
        result = build_operation_log_sync_plan_from_metrics(
            db_path,
            product_keyword=str(cfg.get("product_keyword") or ""),
            page_size=int(cfg.get("operation_log_page_size") or 20),
            date_range=cfg.get("date_range") if isinstance(cfg.get("date_range"), dict) else None,
            window_days=int(cfg.get("window_days") or 3),
        )
        output = {
            "ok": result["ok"],
            "workflow": "control_operation_log_history_sync_preflight",
            "phase": result["phase"],
            "execution_enabled": result["execution_enabled"],
            "external_api_calls": result["external_api_calls"],
            "summary": result["summary"],
        }
    else:
        result = run_control_operation_log_history_sync_request(cfg, db_path=db_path, runs_dir=runs_dir)
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
    return 0 if output["ok"] else 1


def main() -> int:
    return run_from_args()


if __name__ == "__main__":
    raise SystemExit(main())
