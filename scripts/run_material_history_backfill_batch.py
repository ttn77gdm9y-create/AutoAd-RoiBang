#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from copy import deepcopy

from roibang_v2.config import load_json
from roibang_v2.config import load_runtime_config
from roibang_v2.db.bootstrap import bootstrap_database
from roibang_v2.fetch.openapi_executor import Transport
from roibang_v2.fetch.workbench_account_discovery import Sleeper as WorkbenchSleeper
from roibang_v2.fetch.workbench_account_discovery import WorkbenchOpener
from roibang_v2.workflows.material_history_backfill_batch import build_material_history_backfill_batch_preflight
from roibang_v2.workflows.material_history_backfill_batch import run_material_history_backfill_batch_request


def _request_external_enabled(request: dict) -> bool:
    wrapper = request.get("material_history_backfill_batch")
    if isinstance(wrapper, dict):
        cfg = wrapper.get("material_history_backfill")
    else:
        cfg = request.get("material_history_backfill")
    if not isinstance(cfg, dict):
        cfg = request
    material_fetch = cfg.get("material_fetch") if isinstance(cfg.get("material_fetch"), dict) else {}
    execution = material_fetch.get("execution") if isinstance(material_fetch.get("execution"), dict) else {}
    openapi_http = material_fetch.get("openapi_http") if isinstance(material_fetch.get("openapi_http"), dict) else {}
    discovery = cfg.get("active_account_discovery") if isinstance(cfg.get("active_account_discovery"), dict) else {}
    workbench = discovery.get("workbench") if isinstance(discovery.get("workbench"), dict) else {}
    return (
        bool(execution.get("external_api_enabled", False))
        or bool(openapi_http.get("enabled", False))
        or bool(workbench.get("enabled", False))
    )


def _material_history_config(request: dict) -> dict:
    wrapper = request.get("material_history_backfill_batch")
    if isinstance(wrapper, dict):
        cfg = wrapper.get("material_history_backfill")
        if isinstance(cfg, dict):
            return cfg
    cfg = request.get("material_history_backfill")
    return cfg if isinstance(cfg, dict) else request


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


def _override_max_dates(request: dict, max_dates: int | None) -> dict:
    if max_dates is None:
        return request
    if max_dates < 1:
        raise RuntimeError("--max-dates must be greater than 0")
    updated = deepcopy(request)
    wrapper = updated.setdefault("material_history_backfill_batch", {})
    if not isinstance(wrapper, dict):
        raise RuntimeError("material_history_backfill_batch must be a JSON object")
    batch = wrapper.setdefault("batch", {})
    if not isinstance(batch, dict):
        raise RuntimeError("material_history_backfill_batch.batch must be a JSON object")
    configured_size = int(batch.get("size") or batch.get("batch_size") or max_dates)
    batch["size"] = min(configured_size, max_dates)
    return updated


def _override_retry_failed(request: dict, retry_failed: bool) -> dict:
    if not retry_failed:
        return request
    updated = deepcopy(request)
    wrapper = updated.setdefault("material_history_backfill_batch", {})
    if not isinstance(wrapper, dict):
        raise RuntimeError("material_history_backfill_batch must be a JSON object")
    batch = wrapper.setdefault("batch", {})
    if not isinstance(batch, dict):
        raise RuntimeError("material_history_backfill_batch.batch must be a JSON object")
    batch["retry_failed"] = True
    return updated


def run_from_args(
    argv: list[str] | None = None,
    *,
    workbench_opener: WorkbenchOpener | None = None,
    workbench_sleeper: WorkbenchSleeper | None = None,
    openapi_transport: Transport | None = None,
) -> int:
    parser = argparse.ArgumentParser(description="Plan RoiBang-v2 material history backfill batches.")
    parser.add_argument("--config", default="configs/runtime.example.json")
    parser.add_argument("--request", default="configs/material-history-backfill-batch.disabled.example.json")
    parser.add_argument("--db", default=None)
    parser.add_argument("--runs-dir", default=None)
    parser.add_argument("--preflight", action="store_true", help="Write the next batch plan without calling APIs.")
    parser.add_argument(
        "--enable-readonly",
        action="store_true",
        help="Temporarily enable readonly workbench and OpenAPI report requests for the selected batch.",
    )
    parser.add_argument(
        "--max-dates",
        type=int,
        default=None,
        help="Temporarily cap selected batch dates for this run without editing request JSON.",
    )
    parser.add_argument(
        "--retry-failed",
        action="store_true",
        help="Temporarily include failed dates in the selected batch without editing request JSON.",
    )
    args = parser.parse_args(argv)

    if args.preflight and args.enable_readonly:
        raise RuntimeError("--preflight cannot be combined with --enable-readonly")
    if not args.preflight and not args.enable_readonly:
        raise RuntimeError("material history backfill batch execution requires --enable-readonly")
    config = load_runtime_config(args.config)
    request = load_json(args.request)
    request = _override_retry_failed(request, args.retry_failed)
    request = _override_max_dates(request, args.max_dates)
    if args.enable_readonly:
        request = _enable_readonly_request(request)
    request_external_enabled = _request_external_enabled(request)
    if args.preflight:
        if config.execution_enabled or config.external_api_enabled:
            raise RuntimeError("material history backfill batch preflight requires runtime gates disabled")
        if request_external_enabled:
            raise RuntimeError("material history backfill batch preflight requires request external gates disabled")
    else:
        if not config.external_api_enabled:
            raise RuntimeError("material history backfill batch readonly execution requires runtime external_api_enabled=true")
        if config.execution_enabled:
            raise RuntimeError("material history backfill batch readonly execution must keep runtime execution_enabled=false")

    db_path = args.db or config.database_path
    runs_dir = args.runs_dir or config.runs_dir
    bootstrap_database(db_path)
    if args.preflight:
        result = build_material_history_backfill_batch_preflight(request, db_path=db_path, runs_dir=runs_dir)
    else:
        result = run_material_history_backfill_batch_request(
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
        "selected_dates": result["selected_dates"],
        "remaining_dates": result["remaining_dates"],
        "artifact_path": result["artifact_path"],
    }
    if "skipped_dates" in result:
        output["skipped_dates"] = result["skipped_dates"]
    if "completed_dates" in result:
        output["completed_dates"] = result["completed_dates"]
        output["failed_dates"] = result["failed_dates"]
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


def main() -> int:
    return run_from_args()


if __name__ == "__main__":
    raise SystemExit(main())
