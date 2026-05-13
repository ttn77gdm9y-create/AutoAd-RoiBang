#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from copy import deepcopy

from roibang_v2.config import load_json, load_runtime_config
from roibang_v2.db.bootstrap import bootstrap_database
from roibang_v2.runs import write_run_artifact
from roibang_v2.workflows.project_hourly_realtime_sync import build_project_hourly_realtime_plan
from roibang_v2.workflows.project_hourly_realtime_sync import run_project_hourly_realtime_sync_request


def _request_payload(path: str) -> dict:
    payload = load_json(path)
    value = payload.get("project_hourly_realtime_sync")
    return dict(value) if isinstance(value, dict) else dict(payload)


def _enable_readonly(request: dict) -> dict:
    enabled = deepcopy(request)
    openapi_http = enabled.setdefault("openapi_http", {})
    if not isinstance(openapi_http, dict):
        raise RuntimeError("project_hourly_realtime_sync.openapi_http must be a JSON object")
    openapi_http["enabled"] = True
    execution = enabled.setdefault("execution", {})
    if not isinstance(execution, dict):
        raise RuntimeError("project_hourly_realtime_sync.execution must be a JSON object")
    execution["status"] = "execute"
    execution["external_api_enabled"] = True
    return enabled


def run_from_args(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sync readonly project hourly realtime metrics for control suggestions.")
    parser.add_argument("--config", default="configs/runtime.example.json")
    parser.add_argument("--request", default="configs/project-hourly-realtime-sync.example.json")
    parser.add_argument("--db", default=None)
    parser.add_argument("--runs-dir", default=None)
    parser.add_argument("--target-date", default="")
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--enable-readonly", action="store_true")
    args = parser.parse_args(argv)

    config = load_runtime_config(args.config)
    request = _request_payload(args.request)
    if str(args.target_date or "").strip():
        request["target_date"] = str(args.target_date).strip()
    db_path = args.db or config.database_path
    runs_dir = args.runs_dir or config.runs_dir
    bootstrap_database(db_path)
    if args.preflight:
        if args.enable_readonly:
            raise RuntimeError("--preflight cannot be combined with --enable-readonly")
        if config.external_api_enabled or config.execution_enabled:
            raise RuntimeError("project hourly realtime preflight requires runtime gates disabled")
        result = build_project_hourly_realtime_plan(db_path, request)
        result["artifact_path"] = str(write_run_artifact(runs_dir, "project_hourly_realtime_sync_plan", result))
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
        return 0
    if args.enable_readonly:
        request = _enable_readonly(request)
    if not args.enable_readonly:
        raise RuntimeError("project hourly realtime sync requires --enable-readonly")
    if not config.external_api_enabled:
        raise RuntimeError("project hourly realtime sync requires runtime external_api_enabled=true")
    if config.execution_enabled:
        raise RuntimeError("project hourly realtime sync must keep runtime execution_enabled=false")

    result = run_project_hourly_realtime_sync_request(request, db_path=db_path, runs_dir=runs_dir)
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
