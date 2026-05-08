#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from roibang_v2.config import load_json, load_runtime_config
from roibang_v2.workflows.create_live_execute_phase_gate import (
    run_create_live_execute_phase_gate_request,
)


def _latest_artifact(runs_dir: Path, workflow: str) -> Path:
    workflow_dir = runs_dir / workflow
    candidates = sorted(workflow_dir.glob("*.json"))
    if not candidates:
        raise FileNotFoundError(f"no {workflow} artifacts found under {workflow_dir}")
    return candidates[-1]


def _artifact_path(value: str, runs_dir: Path, workflow: str) -> Path:
    return Path(value) if str(value or "").strip() else _latest_artifact(runs_dir, workflow)


def _load_artifact(path: Path) -> dict:
    artifact = load_json(path)
    artifact["artifact_path"] = str(path)
    return artifact


def run_from_args(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Phase 1 create live execute phase gate.")
    parser.add_argument("--config", default="configs/runtime.example.json")
    parser.add_argument("--policy", default="policies/strategy.example.json")
    parser.add_argument("--create-readiness-matrix-artifact", default="")
    args = parser.parse_args(argv)

    config = load_runtime_config(args.config)
    if config.external_api_enabled or config.execution_enabled:
        raise RuntimeError("Phase 1 live execute phase gate requires external_api_enabled=false and execution_enabled=false")

    readiness_path = _artifact_path(
        args.create_readiness_matrix_artifact,
        config.runs_dir,
        "create_readiness_matrix",
    )
    result = run_create_live_execute_phase_gate_request(
        {
            "create_live_execute_phase_gate": {
                "create_readiness_matrix_artifact": _load_artifact(readiness_path),
                "policy": load_json(args.policy),
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
                "status": result["status"],
                "live_execute_development_allowed": result["live_execute_development_allowed"],
                "live_execute_allowed": result["live_execute_allowed"],
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
