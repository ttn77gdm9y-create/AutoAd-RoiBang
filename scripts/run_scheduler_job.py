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

PROJECT_ROOT = bootstrap_project_root()

from roibang_v2.scheduler.jobs import load_job_registry
from roibang_v2.scheduler.runner import run_scheduler_job


def run_from_args(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one RoiBang-v2 scheduler job from the fixed registry.")
    parser.add_argument("--registry", default="configs/scheduler/roibang-v2.jobs.example.json")
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--repo-root", default=str(PROJECT_ROOT))
    parser.add_argument("--execution-runs-dir", default="data/runs")
    args = parser.parse_args(argv)

    result = run_scheduler_job(
        load_job_registry(args.registry),
        job_id=args.job_id,
        repo_root=args.repo_root,
        execution_runs_dir=args.execution_runs_dir,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


def main() -> int:
    return run_from_args()


if __name__ == "__main__":
    raise SystemExit(main())
