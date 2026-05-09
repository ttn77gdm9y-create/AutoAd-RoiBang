#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from roibang_v2.config import load_json, load_runtime_config
from roibang_v2.workflows.create_phase2_provider_mapping_prep import (
    run_create_phase2_provider_mapping_prep_request,
)


def run_from_args(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Phase 2 preparation provider mapping review pack.")
    parser.add_argument("--config", default="configs/runtime.example.json")
    parser.add_argument("--policy", default="policies/strategy.example.json")
    args = parser.parse_args(argv)

    config = load_runtime_config(args.config)
    if config.external_api_enabled or config.execution_enabled:
        raise RuntimeError(
            "Phase 2 provider mapping preparation requires external_api_enabled=false and execution_enabled=false"
        )
    policy_root = load_json(args.policy)
    policy = policy_root.get("create_phase2_provider_mapping_prep") or policy_root.get("create_dry_run") or {}
    result = run_create_phase2_provider_mapping_prep_request(
        {"create_phase2_provider_mapping_prep": {"policy": policy}},
        runs_dir=config.runs_dir,
    )
    print(
        json.dumps(
            {
                "ok": result["ok"],
                "workflow": result["workflow"],
                "phase": result["phase"],
                "execution_enabled": result["execution_enabled"],
                "external_api_calls": result["external_api_calls"],
                "status": result["status"],
                "summary": result["summary"],
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
