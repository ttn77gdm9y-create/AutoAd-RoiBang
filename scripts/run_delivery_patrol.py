#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from _repo_bootstrap import bootstrap_project_root

bootstrap_project_root()

from roibang_v2.config import load_json
from roibang_v2.config import load_runtime_config
from roibang_v2.db.bootstrap import bootstrap_database
from roibang_v2.workflows.delivery_patrol import build_delivery_patrol_plan
from roibang_v2.workflows.delivery_patrol import run_delivery_patrol_request


def run_from_args(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run readonly delivery account/project/promotion patrol.")
    parser.add_argument("--config", default="configs/runtime.example.json")
    parser.add_argument("--request", default="configs/delivery-patrol.example.json")
    parser.add_argument("--db", default=None)
    parser.add_argument("--runs-dir", default=None)
    parser.add_argument("--enable-readonly", action="store_true")
    args = parser.parse_args(argv)

    config = load_runtime_config(args.config)
    request = load_json(args.request)
    db_path = args.db or config.database_path
    runs_dir = args.runs_dir or config.runs_dir
    bootstrap_database(db_path)
    if args.enable_readonly:
        if not config.external_api_enabled or config.execution_enabled:
            raise RuntimeError("delivery patrol readonly requires external_api_enabled=true and execution_enabled=false")
        result = run_delivery_patrol_request(request, db_path=db_path, runs_dir=runs_dir)
    else:
        if config.external_api_enabled or config.execution_enabled:
            raise RuntimeError("delivery patrol plan requires external_api_enabled=false and execution_enabled=false")
        cfg = request.get("delivery_patrol") if isinstance(request.get("delivery_patrol"), dict) else request
        execution = cfg.get("execution") if isinstance(cfg.get("execution"), dict) else {}
        if str(execution.get("status") or "") == "execute" or bool(execution.get("external_api_enabled", False)):
            raise RuntimeError("delivery patrol real readonly execution requires --enable-readonly")
        result = build_delivery_patrol_plan(db_path, cfg)
    output = {
        "ok": result["ok"],
        "workflow": result["workflow"],
        "phase": result["phase"],
        "execution_enabled": result["execution_enabled"],
        "external_api_calls": result["external_api_calls"],
        "summary": result["summary"],
        "artifact_path": result.get("artifact_path", ""),
    }
    if result["workflow"] == "delivery_patrol_plan":
        output["plan_summary"] = result["summary"]
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


def main() -> int:
    return run_from_args()


if __name__ == "__main__":
    raise SystemExit(main())
