#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from roibang_v2.workflows.project_update_config import run_project_update_config_request


def _project(value: str) -> dict:
    parts = [part.strip() for part in value.split(":")]
    if len(parts) < 2 or not parts[0] or not parts[1]:
        raise argparse.ArgumentTypeError("project must be advertiser_id:project_id[:project_name]")
    return {
        "advertiser_id": parts[0],
        "project_id": parts[1],
        "project_name": parts[2] if len(parts) > 2 else "",
    }


def run_from_args(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate project_update.json for project schedule control.")
    parser.add_argument("--project-update-id", required=True)
    parser.add_argument("--operator", default="")
    parser.add_argument("--allowed-target-accounts-path", default="configs/control-allowed-accounts.local.json")
    parser.add_argument("--target-date", required=True)
    parser.add_argument("--block-start", required=True)
    parser.add_argument("--block-end", required=True)
    parser.add_argument("--restore-date", default="")
    parser.add_argument("--restore-time", required=True)
    parser.add_argument("--project", action="append", type=_project, required=True)
    parser.add_argument("--reason", default="")
    parser.add_argument("--restore-reason", default="")
    parser.add_argument("--output", required=True)
    parser.add_argument("--runs-dir", default="data/runs")
    args = parser.parse_args(argv)

    result = run_project_update_config_request(
        {
            "project_update_id": args.project_update_id,
            "operator": args.operator,
            "allowed_target_accounts_path": args.allowed_target_accounts_path,
            "target_date": args.target_date,
            "block_start": args.block_start,
            "block_end": args.block_end,
            "restore_date": args.restore_date,
            "restore_time": args.restore_time,
            "projects": args.project,
            "reason": args.reason,
            "restore_reason": args.restore_reason,
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
    return 0


def main() -> int:
    return run_from_args()


if __name__ == "__main__":
    raise SystemExit(main())
