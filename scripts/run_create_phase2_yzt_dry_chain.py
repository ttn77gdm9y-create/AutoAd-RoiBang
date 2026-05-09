#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from roibang_v2.config import load_json, load_runtime_config
from roibang_v2.db.bootstrap import bootstrap_database
from roibang_v2.workflows.create_phase2_yzt_dry_chain import run_create_phase2_yzt_dry_chain_request


def run_from_args(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Phase 2 勇者突进 full dry create chain.")
    parser.add_argument("--config", default="configs/runtime.example.json")
    parser.add_argument("--preview-config", default="configs/create/yzt-wx-mini-game.preview.example.json")
    parser.add_argument("--policy", default="policies/strategy.example.json")
    args = parser.parse_args(argv)

    config = load_runtime_config(args.config)
    if config.external_api_enabled or config.execution_enabled:
        raise RuntimeError("勇者突进完整预演要求 external_api_enabled=false 且 execution_enabled=false")

    bootstrap_database(config.database_path)
    preview_config = load_json(args.preview_config).get("yzt_create_preview") or {}
    policy = load_json(args.policy)
    result = run_create_phase2_yzt_dry_chain_request(
        {
            "create_phase2_yzt_dry_chain": {
                "preview_config": preview_config,
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
                "chain_steps": result["chain_steps"],
                "blocking_summary": result["blocking_summary"],
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
