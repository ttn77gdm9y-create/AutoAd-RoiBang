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
from roibang_v2.workflows.delivery_readonly_report_chain import run_delivery_readonly_report_chain_request


def run_from_args(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run readonly delivery report chain.")
    parser.add_argument("--request", default="")
    parser.add_argument("--db", default="")
    parser.add_argument("--patrol-artifact", default="")
    parser.add_argument("--suggestions-artifact", default="")
    parser.add_argument("--lookahead-days", type=int, default=0)
    parser.add_argument("--recent-days", type=int, default=0)
    parser.add_argument("--project-name-contains", default="")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--runs-dir", default="data/runs")
    args = parser.parse_args(argv)

    request = load_json(args.request) if args.request else {}
    cfg = request.get("delivery_readonly_report_chain") if isinstance(request.get("delivery_readonly_report_chain"), dict) else request
    payload = dict(cfg if isinstance(cfg, dict) else {})
    if args.db:
        payload["db_path"] = args.db
    if args.patrol_artifact:
        payload["patrol_artifact_path"] = args.patrol_artifact
    if args.suggestions_artifact:
        payload["suggestions_artifact_path"] = args.suggestions_artifact
    if args.lookahead_days:
        payload["lookahead_days"] = args.lookahead_days
    if args.recent_days:
        payload["recent_days"] = args.recent_days
    if args.project_name_contains:
        payload["project_name_contains"] = args.project_name_contains
    if args.limit:
        payload["limit"] = args.limit

    result = run_delivery_readonly_report_chain_request(payload, runs_dir=args.runs_dir)
    print(
        json.dumps(
            {
                "ok": result["ok"],
                "workflow": result["workflow"],
                "phase": result["phase"],
                "execution_enabled": result["execution_enabled"],
                "external_api_calls": result["external_api_calls"],
                "summary": result["summary"],
                "artifacts": result["artifacts"],
                "delivery": result["delivery"],
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
