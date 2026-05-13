#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from roibang_v2.workflows.project_update_preflight import run_project_update_preflight_request


def run_from_args(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Preflight a project_update.json without changing live projects.")
    parser.add_argument("--project-update", required=True)
    parser.add_argument("--db", default="data/roibang_v2.sqlite3")
    parser.add_argument("--runs-dir", default="data/runs")
    args = parser.parse_args(argv)

    result = run_project_update_preflight_request(
        {
            "project_update_path": args.project_update,
            "db_path": args.db,
        },
        runs_dir=args.runs_dir,
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
                "violations": result["violations"],
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
