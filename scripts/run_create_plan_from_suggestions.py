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

from roibang_v2.config import load_runtime_config
from roibang_v2.workflows.create_plan_from_suggestions import run_create_plan_from_suggestions_request


def run_from_args(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a create-plan preview request from readonly create-project suggestions.")
    parser.add_argument("--config", default="configs/runtime.example.json")
    parser.add_argument("--suggestions-artifact", required=True)
    parser.add_argument("--suggestion-id", action="append", default=[])
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--template-dir", default="configs/create-templates")
    parser.add_argument("--product-key", default="")
    parser.add_argument("--product-name", default="")
    parser.add_argument("--owner", default="")
    parser.add_argument("--target-date", default="")
    parser.add_argument("--template-catalog", default="")
    parser.add_argument("--cpa-bid", default="")
    parser.add_argument("--roi-coefficient", default="")
    args = parser.parse_args(argv)

    config = load_runtime_config(args.config)
    if config.external_api_enabled or config.execution_enabled:
        raise RuntimeError(
            "create_plan_from_suggestions only builds preview requests and requires "
            "external_api_enabled=false and execution_enabled=false"
        )

    result = run_create_plan_from_suggestions_request(
        {
            "suggestions_artifact_path": str(Path(args.suggestions_artifact).resolve()),
            "selected_suggestion_ids": args.suggestion_id,
            "project_root": args.project_root,
            "template_dir": args.template_dir,
            "product_key": args.product_key,
            "product_name": args.product_name,
            "owner": args.owner,
            "target_date": args.target_date,
            "template_catalog": args.template_catalog,
            "cpa_bid": args.cpa_bid,
            "roi_coefficient": args.roi_coefficient,
        },
        runs_dir=config.runs_dir,
    )
    print(
        json.dumps(
            {
                "ok": result["ok"],
                "workflow": result["workflow"],
                "phase": result["phase"],
                "status": result["status"],
                "execution_enabled": result["execution_enabled"],
                "external_api_calls": result["external_api_calls"],
                "summary": result["summary"],
                "blocking_reasons": result["blocking_reasons"],
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
