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
from roibang_v2.workflows.delivery_business_report import run_delivery_business_report_request


def run_from_args(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build readonly delivery business report from patrol artifacts.")
    parser.add_argument("--request", default="")
    parser.add_argument("--patrol-artifact", default="")
    parser.add_argument("--suggestions-artifact", default="")
    parser.add_argument("--backtest-artifact", default="")
    parser.add_argument("--runs-dir", default="data/runs")
    args = parser.parse_args(argv)

    request = load_json(args.request) if args.request else {}
    cfg = request.get("delivery_business_report") if isinstance(request.get("delivery_business_report"), dict) else request
    payload = dict(cfg if isinstance(cfg, dict) else {})
    if args.patrol_artifact:
        payload["patrol_artifact_path"] = args.patrol_artifact
    if args.suggestions_artifact:
        payload["suggestions_artifact_path"] = args.suggestions_artifact
    if args.backtest_artifact:
        payload["backtest_artifact_path"] = args.backtest_artifact
    result = run_delivery_business_report_request(payload, runs_dir=args.runs_dir)
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
