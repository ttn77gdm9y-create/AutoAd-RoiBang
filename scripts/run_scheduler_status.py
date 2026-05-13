#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from roibang_v2.config import load_json
from roibang_v2.config import load_runtime_config
from roibang_v2.db.bootstrap import bootstrap_database
from roibang_v2.scheduler.jobs import load_job_registry
from roibang_v2.workflows.scheduler_status import run_scheduler_status_request


def run_from_args(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build RoiBang-v2 scheduler status report and optionally push Feishu.")
    parser.add_argument("--config", default="configs/runtime.example.json")
    parser.add_argument("--request", default="configs/scheduler-status.example.json")
    parser.add_argument("--registry", default="configs/scheduler/roibang-v2.jobs.example.json")
    parser.add_argument("--repo-root", default=str(Path.cwd()))
    parser.add_argument("--db", default=None)
    parser.add_argument("--runs-dir", default=None)
    args = parser.parse_args(argv)

    config = load_runtime_config(args.config)
    if config.external_api_enabled or config.execution_enabled:
        raise RuntimeError("scheduler status requires external_api_enabled=false and execution_enabled=false")
    db_path = args.db or config.database_path
    runs_dir = args.runs_dir or config.runs_dir
    bootstrap_database(db_path)
    result = run_scheduler_status_request(
        load_json(args.request),
        registry=load_job_registry(args.registry),
        db_path=db_path,
        runs_dir=runs_dir,
        repo_root=args.repo_root,
    )
    output = {
        "ok": result["ok"],
        "workflow": result["workflow"],
        "phase": result["phase"],
        "execution_enabled": result["execution_enabled"],
        "external_api_calls": result["external_api_calls"],
        "summary": result["summary"],
        "delivery": result["delivery"],
        "artifact_path": result["artifact_path"],
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    feishu = result.get("delivery", {}).get("feishu", {})
    return 0 if feishu.get("ok", True) else 1


def main() -> int:
    return run_from_args()


if __name__ == "__main__":
    raise SystemExit(main())
