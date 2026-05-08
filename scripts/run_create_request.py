#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from roibang_v2.config import load_json, load_runtime_config
from roibang_v2.db.bootstrap import bootstrap_database
from roibang_v2.workflows.create_request import run_create_request


def run_from_args(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Record a Phase 1 create request.")
    parser.add_argument("--config", default="configs/runtime.example.json")
    parser.add_argument("--request", default="configs/requests/example.create-request.json")
    args = parser.parse_args(argv)

    config = load_runtime_config(args.config)
    if config.external_api_enabled or config.execution_enabled:
        raise RuntimeError("Phase 1 create request requires external_api_enabled=false and execution_enabled=false")

    bootstrap_database(config.database_path)
    result = run_create_request(
        load_json(args.request),
        db_path=config.database_path,
        runs_dir=config.runs_dir,
    )
    print(json.dumps({"ok": result["ok"], "artifact_path": result["artifact_path"]}, ensure_ascii=False))
    return 0 if result["ok"] else 1


def main() -> int:
    return run_from_args()


if __name__ == "__main__":
    raise SystemExit(main())
