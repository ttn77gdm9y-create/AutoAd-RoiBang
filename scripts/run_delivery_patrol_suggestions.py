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
from roibang_v2.workflows.delivery_patrol_suggestions import run_delivery_patrol_suggestions_request


def run_from_args(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build readonly suggestions from a delivery patrol artifact.")
    parser.add_argument("--patrol-artifact", required=True)
    parser.add_argument("--request", default="")
    parser.add_argument("--target-date", default="")
    parser.add_argument("--db", default="")
    parser.add_argument("--runs-dir", default="data/runs")
    args = parser.parse_args(argv)

    request = load_json(args.request) if args.request else {}
    cfg = request.get("delivery_patrol_suggestions") if isinstance(request.get("delivery_patrol_suggestions"), dict) else request
    payload = {
        **(cfg if isinstance(cfg, dict) else {}),
        "patrol_artifact_path": args.patrol_artifact,
    }
    if args.target_date:
        payload["target_date"] = args.target_date
    if args.db:
        payload["db_path"] = args.db
    result = run_delivery_patrol_suggestions_request(payload, runs_dir=args.runs_dir)
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
