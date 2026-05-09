#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from roibang_v2.config import load_json, load_runtime_config
from roibang_v2.workflows.create_phase2_template_confirmation_pack import (
    run_create_phase2_template_confirmation_pack_request,
)


def _latest_artifact(runs_dir: str | Path, workflow: str) -> Path:
    workflow_dir = Path(runs_dir) / workflow
    candidates = sorted(workflow_dir.glob("*.json"))
    if not candidates:
        raise FileNotFoundError(f"no artifact found for {workflow}")
    return candidates[-1]


def run_from_args(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Phase 2 template confirmation pack.")
    parser.add_argument("--config", default="configs/runtime.example.json")
    parser.add_argument("--template-slot-artifact", default="")
    args = parser.parse_args(argv)

    config = load_runtime_config(args.config)
    if config.external_api_enabled or config.execution_enabled:
        raise RuntimeError(
            "Phase 2 template confirmation pack requires external_api_enabled=false and execution_enabled=false"
        )

    artifact_path = Path(args.template_slot_artifact) if args.template_slot_artifact else _latest_artifact(
        config.runs_dir,
        "create_phase2_template_slot_prep",
    )
    result = run_create_phase2_template_confirmation_pack_request(
        {
            "create_phase2_template_confirmation_pack": {
                "create_phase2_template_slot_prep_artifact": load_json(artifact_path),
            }
        },
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
                "required_user_input_now": result["required_user_input_now"],
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
