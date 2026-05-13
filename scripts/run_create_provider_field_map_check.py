#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from roibang_v2.config import load_json, load_runtime_config
from roibang_v2.workflows.create_provider_field_map_check import run_create_provider_field_map_check_request


def run_from_args(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check Phase 1 create provider field map config.")
    parser.add_argument("--config", default="configs/runtime.example.json")
    parser.add_argument("--policy", default="policies/create-policy.example.json")
    args = parser.parse_args(argv)

    config = load_runtime_config(args.config)
    if config.external_api_enabled or config.execution_enabled:
        raise RuntimeError("Phase 1 provider field map check requires external_api_enabled=false and execution_enabled=false")

    policy = load_json(args.policy).get("create_dry_run") or {}
    result = run_create_provider_field_map_check_request(
        {"create_provider_field_map_check": {"policy": policy}},
        runs_dir=config.runs_dir,
    )
    print(
        json.dumps(
            {
                "ok": result["ok"],
                "status": result["status"],
                "artifact_path": result["artifact_path"],
            },
            ensure_ascii=False,
        )
    )
    return 0 if result["ok"] else 1


def main() -> int:
    return run_from_args()


if __name__ == "__main__":
    raise SystemExit(main())
