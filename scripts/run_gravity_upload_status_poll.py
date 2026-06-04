#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from roibang_v2.config import load_runtime_config
from roibang_v2.db.bootstrap import bootstrap_database
from roibang_v2.workflows.gravity_upload_to_account import run_gravity_upload_status_poll_request


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh Gravity upload task status and local video_id ledger.")
    parser.add_argument("--config", default="configs/runtime.example.json")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--auth-file", default="data/gravity_token.json")
    parser.add_argument("--db", default="")
    parser.add_argument("--runs-dir", default="")
    args = parser.parse_args()

    runtime = load_runtime_config(args.config)
    db_path = Path(args.db or runtime.database_path)
    runs_dir = Path(args.runs_dir or runtime.runs_dir)
    bootstrap_database(db_path)
    result = run_gravity_upload_status_poll_request(
        {"task_id": args.task_id, "auth_file": args.auth_file},
        db_path=db_path,
        runs_dir=runs_dir,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
