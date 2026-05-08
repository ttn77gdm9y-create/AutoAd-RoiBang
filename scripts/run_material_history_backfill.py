#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from copy import deepcopy
from datetime import date

from roibang_v2.config import load_json
from roibang_v2.config import load_runtime_config
from roibang_v2.db.bootstrap import bootstrap_database
from roibang_v2.fetch.openapi_executor import Transport
from roibang_v2.fetch.workbench_account_discovery import WorkbenchOpener
from roibang_v2.fetch.workbench_account_discovery import Sleeper as WorkbenchSleeper
from roibang_v2.workflows.material_history_backfill import build_material_history_backfill_preflight
from roibang_v2.workflows.material_history_backfill import run_material_history_backfill_request


def _material_history_config(request: dict) -> dict:
    value = request.get("material_history_backfill")
    return value if isinstance(value, dict) else request


def _enable_readonly_request(request: dict) -> dict:
    enabled_request = deepcopy(request)
    cfg = _material_history_config(enabled_request)
    discovery = cfg.setdefault("active_account_discovery", {})
    if not isinstance(discovery, dict):
        raise RuntimeError("material_history_backfill.active_account_discovery must be a JSON object")
    discovery["enabled"] = True
    workbench = discovery.setdefault("workbench", {})
    if not isinstance(workbench, dict):
        raise RuntimeError("material_history_backfill.active_account_discovery.workbench must be a JSON object")
    workbench["enabled"] = True
    material_fetch = cfg.setdefault("material_fetch", {})
    if not isinstance(material_fetch, dict):
        raise RuntimeError("material_history_backfill.material_fetch must be a JSON object")
    material_fetch["source"] = "openapi_http_execute"
    openapi_http = material_fetch.setdefault("openapi_http", {})
    if not isinstance(openapi_http, dict):
        raise RuntimeError("material_history_backfill.material_fetch.openapi_http must be a JSON object")
    openapi_http["enabled"] = True
    execution = material_fetch.setdefault("execution", {})
    if not isinstance(execution, dict):
        raise RuntimeError("material_history_backfill.material_fetch.execution must be a JSON object")
    execution["status"] = "execute"
    execution["external_api_enabled"] = True
    return enabled_request


def _override_target_date(request: dict, target_date: str | None) -> dict:
    if not target_date:
        return request
    updated = deepcopy(request)
    cfg = _material_history_config(updated)
    cfg["date_range"] = {"start": target_date, "end": target_date}
    return updated


def run_from_args(
    argv: list[str] | None = None,
    *,
    workbench_opener: WorkbenchOpener | None = None,
    workbench_sleeper: WorkbenchSleeper | None = None,
    openapi_transport: Transport | None = None,
    today: date | None = None,
) -> int:
    parser = argparse.ArgumentParser(description="Run RoiBang-v2 material daily history backfill.")
    parser.add_argument("--config", default="configs/runtime.example.json")
    parser.add_argument("--request", default="configs/material-history-backfill.disabled.example.json")
    parser.add_argument("--db", default=None)
    parser.add_argument("--runs-dir", default=None)
    parser.add_argument("--preflight", action="store_true", help="Write a request-count plan without calling APIs.")
    parser.add_argument("--target-date", default=None, help="Temporarily run exactly one date without editing request JSON.")
    parser.add_argument(
        "--enable-readonly",
        action="store_true",
        help="Temporarily enable readonly workbench and OpenAPI report requests for this run.",
    )
    args = parser.parse_args(argv)

    config = load_runtime_config(args.config)

    request = load_json(args.request)
    if args.preflight and args.enable_readonly:
        raise RuntimeError("--preflight cannot be combined with --enable-readonly")
    request = _override_target_date(request, args.target_date)
    if args.enable_readonly:
        request = _enable_readonly_request(request)
    cfg = _material_history_config(request)
    material_fetch = cfg.get("material_fetch") if isinstance(cfg.get("material_fetch"), dict) else {}
    execution = material_fetch.get("execution") if isinstance(material_fetch.get("execution"), dict) else {}
    openapi_http = material_fetch.get("openapi_http") if isinstance(material_fetch.get("openapi_http"), dict) else {}
    request_external_enabled = bool(execution.get("external_api_enabled", False)) or bool(openapi_http.get("enabled", False))
    if args.preflight:
        if config.execution_enabled or config.external_api_enabled:
            raise RuntimeError("material history backfill preflight requires runtime gates disabled")
        if request_external_enabled:
            raise RuntimeError("material history backfill preflight requires request external gates disabled")
    elif request_external_enabled:
        if not config.external_api_enabled:
            raise RuntimeError("material history backfill readonly execution requires runtime external_api_enabled=true")
        if config.execution_enabled:
            raise RuntimeError("material history backfill readonly execution must keep runtime execution_enabled=false")

    db_path = args.db or config.database_path
    runs_dir = args.runs_dir or config.runs_dir
    bootstrap_database(db_path)
    if args.preflight:
        result = build_material_history_backfill_preflight(request, db_path=db_path, runs_dir=runs_dir)
    else:
        result = run_material_history_backfill_request(
            request,
            db_path=db_path,
            runs_dir=runs_dir,
            workbench_opener=workbench_opener,
            workbench_sleeper=workbench_sleeper,
            openapi_transport=openapi_transport,
        )
    output = {
        "ok": result["ok"],
        "workflow": result["workflow"],
        "phase": result["phase"],
        "execution_enabled": result["execution_enabled"],
        "external_api_calls": result["external_api_calls"],
        "summary": result["summary"],
        "artifact_path": result["artifact_path"],
    }
    if "skipped" in result:
        output["skipped"] = result["skipped"]
        output["skip_reason"] = result.get("skip_reason", "")
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


def main() -> int:
    return run_from_args()


if __name__ == "__main__":
    raise SystemExit(main())
