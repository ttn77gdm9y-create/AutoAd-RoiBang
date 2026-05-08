#!/usr/bin/env python3
from __future__ import annotations

import argparse

from roibang_v2.config import load_json, load_runtime_config
from roibang_v2.runs import write_run_artifact
from roibang_v2.workflows.placeholders import phase1_noop_result


ALLOWED_WORKFLOWS = {
    "data_sync",
    "daily_learning",
    "material_sync",
    "strategy_plan",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a safe Phase 1 RoiBang-v2 workflow.")
    parser.add_argument("workflow", choices=sorted(ALLOWED_WORKFLOWS))
    parser.add_argument("--config", default="configs/runtime.example.json")
    parser.add_argument("--policy", default="policies/strategy.example.json")
    args = parser.parse_args()

    config = load_runtime_config(args.config)
    policy = load_json(args.policy)

    if config.execution_enabled or policy.get("execution_enabled") is True:
        raise RuntimeError("Phase 1 workflows refuse execution_enabled=true")

    payload = phase1_noop_result(args.workflow, policy)
    artifact = write_run_artifact(config.runs_dir, args.workflow, payload)
    print(f"wrote {artifact}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
