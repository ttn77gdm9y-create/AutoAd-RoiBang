#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from roibang_v2.backfill.runner import run_backfill_batches_request
from roibang_v2.config import load_json, load_runtime_config
from roibang_v2.db.bootstrap import bootstrap_database


def run_from_args(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run or dry-run RoiBang-v2 report backfill batches.")
    parser.add_argument("--config", default="configs/runtime.example.json")
    parser.add_argument("--request", default="configs/backfill-runner.disabled.example.json")
    parser.add_argument("--db", default=None)
    parser.add_argument("--runs-dir", default=None)
    args = parser.parse_args(argv)

    config = load_runtime_config(args.config)
    request = load_json(args.request)
    runner = request.get("backfill_runner") if isinstance(request.get("backfill_runner"), dict) else request
    execution = runner.get("execution") if isinstance(runner.get("execution"), dict) else {}
    wants_execute = str(execution.get("status") or "") == "execute" and bool(execution.get("external_api_enabled", False))
    if wants_execute:
        if not config.external_api_enabled:
            raise RuntimeError("backfill runner execute requires runtime external_api_enabled=true")
        if config.execution_enabled:
            raise RuntimeError("backfill runner must keep runtime execution_enabled=false")
    elif config.external_api_enabled or config.execution_enabled:
        raise RuntimeError("backfill runner dry-run requires external_api_enabled=false and execution_enabled=false")

    db_path = args.db or config.database_path
    runs_dir = args.runs_dir or config.runs_dir
    bootstrap_database(db_path)
    result = run_backfill_batches_request(request, db_path=db_path, runs_dir=runs_dir)
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
