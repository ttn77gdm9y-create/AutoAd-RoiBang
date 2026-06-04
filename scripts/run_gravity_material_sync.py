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
from roibang_v2.workflows.gravity_material_sync import run_gravity_material_sync_request


def run_from_args(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sync Gravity material library into local source material pool safely.")
    parser.add_argument("--config", default="configs/runtime.example.json")
    parser.add_argument("--auth-file", default="data/gravity_token.json")
    parser.add_argument("--product", default="")
    parser.add_argument("--page-size", default=100, type=int)
    parser.add_argument("--max-pages", default=20, type=int)
    parser.add_argument("--db", default=None)
    parser.add_argument("--runs-dir", default=None)
    args = parser.parse_args(argv)

    runtime = load_runtime_config(args.config)
    if runtime.execution_enabled:
        raise RuntimeError("gravity material sync must not run with execution_enabled=true")

    db_path = Path(args.db) if args.db else runtime.database_path
    runs_dir = Path(args.runs_dir) if args.runs_dir else runtime.runs_dir
    bootstrap_database(db_path)
    request = {
        "auth_file": args.auth_file,
        "product": args.product,
        "page_size": args.page_size,
        "max_pages": args.max_pages,
    }
    result = run_gravity_material_sync_request(request, db_path=db_path, runs_dir=runs_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if bool(result.get("ok")) else 1


def main() -> int:
    return run_from_args()


if __name__ == "__main__":
    raise SystemExit(main())
