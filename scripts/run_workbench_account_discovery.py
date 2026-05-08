#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from copy import deepcopy
from datetime import date

from roibang_v2.config import load_json, load_runtime_config
from roibang_v2.fetch.workbench_account_discovery import WorkbenchOpener
from roibang_v2.db.bootstrap import bootstrap_database
from roibang_v2.workflows.workbench_account_discovery import (
    build_workbench_account_discovery_preflight,
    run_workbench_account_discovery_request,
)


def _enable_readonly_request(request: dict) -> dict:
    enabled_request = deepcopy(request)
    cfg = enabled_request.get("workbench_account_discovery")
    if not isinstance(cfg, dict):
        cfg = enabled_request
    workbench = cfg.setdefault("workbench", {})
    if not isinstance(workbench, dict):
        raise RuntimeError("workbench_account_discovery.workbench must be a JSON object")
    workbench["enabled"] = True
    return enabled_request


def run_from_args(
    argv: list[str] | None = None,
    *,
    opener: WorkbenchOpener | None = None,
    today: date | None = None,
) -> int:
    parser = argparse.ArgumentParser(description="Run RoiBang-v2 workbench spend account discovery only.")
    parser.add_argument("--config", default="configs/runtime.example.json")
    parser.add_argument("--request", default="configs/workbench-account-discovery.disabled.example.json")
    parser.add_argument("--db", default=None)
    parser.add_argument("--runs-dir", default=None)
    parser.add_argument("--preflight", action="store_true", help="Write a request-count plan without external calls.")
    parser.add_argument(
        "--enable-readonly",
        action="store_true",
        help="Temporarily enable readonly workbench requests for this run without editing the request JSON.",
    )
    args = parser.parse_args(argv)

    config = load_runtime_config(args.config)
    request = load_json(args.request)
    if args.enable_readonly:
        request = _enable_readonly_request(request)
    cfg = request.get("workbench_account_discovery") if isinstance(request.get("workbench_account_discovery"), dict) else request
    workbench = cfg.get("workbench") if isinstance(cfg.get("workbench"), dict) else {}
    if args.preflight and args.enable_readonly:
        raise RuntimeError("--preflight cannot be combined with --enable-readonly")
    if args.preflight:
        if config.execution_enabled or config.external_api_enabled:
            raise RuntimeError("workbench account discovery preflight requires runtime gates disabled")
        if bool(workbench.get("enabled", False)):
            raise RuntimeError("workbench account discovery preflight requires request workbench.enabled=false")
    else:
        if not config.external_api_enabled:
            raise RuntimeError("workbench account discovery requires runtime external_api_enabled=true")
        if config.execution_enabled:
            raise RuntimeError("workbench account discovery must keep runtime execution_enabled=false")
        if not bool(workbench.get("enabled", False)):
            raise RuntimeError("workbench account discovery requires workbench.enabled=true")

    db_path = args.db or config.database_path
    runs_dir = args.runs_dir or config.runs_dir
    bootstrap_database(db_path)
    if args.preflight:
        result = build_workbench_account_discovery_preflight(request, db_path=db_path, runs_dir=runs_dir, today=today)
    else:
        result = run_workbench_account_discovery_request(
            request,
            db_path=db_path,
            runs_dir=runs_dir,
            today=today,
            opener=opener,
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
    if "active_account_ids" in result:
        output["active_account_count"] = len(result["active_account_ids"])
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


def main() -> int:
    return run_from_args()


if __name__ == "__main__":
    raise SystemExit(main())
