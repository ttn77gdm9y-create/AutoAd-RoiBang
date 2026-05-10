#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from roibang_v2.config import load_json, load_runtime_config
from roibang_v2.db.bootstrap import bootstrap_database
from roibang_v2.workflows.create_first_live_local_chain import run_create_first_live_local_chain_request


def run_from_args(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run first-live local-only create chain.")
    parser.add_argument("--config", default="configs/runtime.example.json")
    parser.add_argument("--preview-config", default="configs/create/yzt-wx-mini-game.preview.example.json")
    parser.add_argument("--policy", default="policies/strategy.example.json")
    args = parser.parse_args(argv)

    config = load_runtime_config(args.config)
    if config.external_api_enabled or config.execution_enabled:
        raise RuntimeError("首单本地链路要求 external_api_enabled=false 且 execution_enabled=false")

    bootstrap_database(config.database_path)
    preview_config = load_json(args.preview_config).get("yzt_create_preview") or {}
    policy = load_json(args.policy)
    result = run_create_first_live_local_chain_request(
        {
            "create_first_live_local_chain": {
                "preview_config": preview_config,
                "preview_config_path": args.preview_config,
                "policy": policy,
            }
        },
        db_path=config.database_path,
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
                "scope_guard": result["scope_guard"],
                "chain_steps": result["chain_steps"],
                "approved_for_execute": result["approved_for_execute"],
                "human_next_steps": result["human_next_steps"],
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
