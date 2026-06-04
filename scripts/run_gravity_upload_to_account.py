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
from roibang_v2.db.bootstrap import bootstrap_database
from roibang_v2.fetch.gravity_material_library import load_gravity_auth_file
from roibang_v2.workflows.gravity_upload_to_account import run_gravity_upload_execute_request


def run_from_args(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Execute confirmed Gravity material upload preview.")
    parser.add_argument("--config", default="configs/runtime.example.json")
    parser.add_argument("--preview-path", required=True)
    parser.add_argument("--auth-file", default="data/gravity_token.json")
    parser.add_argument("--db", default=None)
    parser.add_argument("--runs-dir", default=None)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)

    if not args.execute:
        raise RuntimeError("gravity upload requires --execute and a confirmed preview artifact")

    runtime = load_runtime_config(args.config)
    db_path = Path(args.db) if args.db else runtime.database_path
    runs_dir = Path(args.runs_dir) if args.runs_dir else runtime.runs_dir
    bootstrap_database(db_path)
    request = {
        "preview_path": args.preview_path,
        "auth_file": args.auth_file,
    }
    try:
        request["auth"] = load_gravity_auth_file(args.auth_file)
    except Exception:
        pass
    result = run_gravity_upload_execute_request(request, db_path=db_path, runs_dir=runs_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if bool(result.get("ok")) else 1


def main() -> int:
    return run_from_args()


if __name__ == "__main__":
    raise SystemExit(main())
