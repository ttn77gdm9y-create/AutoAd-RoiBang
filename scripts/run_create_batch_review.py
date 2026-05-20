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
from roibang_v2.workflows.create_batch_review import run_create_batch_review_request


def run_from_args(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build readonly create batch review from local material metrics.")
    parser.add_argument("--request", default="")
    parser.add_argument("--db", default="")
    parser.add_argument("--start-date", default="")
    parser.add_argument("--end-date", default="")
    parser.add_argument("--recent-days", type=int, default=0)
    parser.add_argument("--project-name-contains", default="")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--runs-dir", default="data/runs")
    args = parser.parse_args(argv)

    request = load_json(args.request) if args.request else {}
    cfg = request.get("create_batch_review") if isinstance(request.get("create_batch_review"), dict) else request
    payload = dict(cfg if isinstance(cfg, dict) else {})
    if args.db:
        payload["db_path"] = args.db
    if args.start_date:
        payload["start_date"] = args.start_date
    if args.end_date:
        payload["end_date"] = args.end_date
    if args.recent_days:
        payload["recent_days"] = args.recent_days
    if args.project_name_contains:
        payload["project_name_contains"] = args.project_name_contains
    if args.limit:
        payload["limit"] = args.limit

    result = run_create_batch_review_request(payload, runs_dir=args.runs_dir)
    print(
        json.dumps(
            {
                "ok": result["ok"],
                "workflow": result["workflow"],
                "phase": result["phase"],
                "execution_enabled": result["execution_enabled"],
                "external_api_calls": result["external_api_calls"],
                "summary": result["summary"],
                "source": result["source"],
                "artifact_path": result["artifact_path"],
                "latest_artifact_path": result["latest_artifact_path"],
                "message": result["message"],
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
