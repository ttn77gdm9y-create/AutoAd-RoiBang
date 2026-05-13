#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from roibang_v2.workflows.project_update_from_suggestions import run_project_update_from_suggestions_request


def run_from_args(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build project_update.json from readonly control suggestions.")
    parser.add_argument("--suggestions-artifact", required=True)
    parser.add_argument("--project-update-id", required=True)
    parser.add_argument("--operator", default="")
    parser.add_argument("--allowed-target-accounts-path", default="")
    parser.add_argument("--output", required=True)
    parser.add_argument("--runs-dir", default="data/runs")
    args = parser.parse_args(argv)

    result = run_project_update_from_suggestions_request(
        {
            "suggestions_artifact_path": args.suggestions_artifact,
            "project_update_id": args.project_update_id,
            "operator": args.operator,
            "allowed_target_accounts_path": args.allowed_target_accounts_path,
            "output_path": args.output,
        },
        runs_dir=args.runs_dir,
    )
    print(
        json.dumps(
            {
                "ok": result["ok"],
                "workflow": result["workflow"],
                "phase": result["phase"],
                "execution_enabled": result["execution_enabled"],
                "external_api_calls": result["external_api_calls"],
                "summary": result["summary"],
                "project_update_path": result["project_update_path"],
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
