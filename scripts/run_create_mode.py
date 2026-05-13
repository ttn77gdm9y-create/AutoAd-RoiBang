#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from roibang_v2.config import load_json, load_runtime_config
from roibang_v2.db.bootstrap import bootstrap_database
from roibang_v2.workflows.create_mode import run_create_mode_request


def run_from_args(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a create plan from a fixed create mode config.")
    parser.add_argument("--config", default="configs/runtime.example.json")
    parser.add_argument("--request", required=True)
    parser.add_argument("--policy", default="policies/create-policy.example.json")
    parser.add_argument("--template-catalog", default="configs/create-templates/wx-mini-game.json")
    args = parser.parse_args(argv)

    config = load_runtime_config(args.config)
    if config.external_api_enabled or config.execution_enabled:
        raise RuntimeError("create_mode only builds plans and requires external_api_enabled=false and execution_enabled=false")

    bootstrap_database(config.database_path)
    result = run_create_mode_request(
        load_json(args.request),
        db_path=config.database_path,
        runs_dir=config.runs_dir,
        policy=load_json(args.policy),
        template_catalog_path=args.template_catalog,
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
                "mode_key": result["mode_key"],
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
