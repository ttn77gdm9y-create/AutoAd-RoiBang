#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from roibang_v2.config import load_json, load_runtime_config
from roibang_v2.workflows.create_first_live_runbook import run_create_first_live_runbook_request


def _latest_artifact(runs_dir: Path, workflow: str) -> Path:
    workflow_dir = runs_dir / workflow
    candidates = sorted(workflow_dir.glob("*.json"))
    if not candidates:
        raise FileNotFoundError(f"no {workflow} artifacts found under {workflow_dir}")
    return candidates[-1]


def _load_artifact(path: Path) -> dict:
    artifact = load_json(path)
    artifact["artifact_path"] = str(path)
    return artifact


def run_from_args(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build first live create runbook without enabling execution.")
    parser.add_argument("--config", default="configs/runtime.example.json")
    parser.add_argument("--policy", default="policies/strategy.example.json")
    args = parser.parse_args(argv)

    config = load_runtime_config(args.config)
    if config.external_api_enabled or config.execution_enabled:
        raise RuntimeError("first live runbook requires external_api_enabled=false and execution_enabled=false")

    mock_execute_path = _latest_artifact(config.runs_dir, "create_mock_execute")
    adapter_path = _latest_artifact(config.runs_dir, "create_live_payload_adapter_scaffold")
    policy = load_json(args.policy)
    result = run_create_first_live_runbook_request(
        {
            "create_first_live_runbook": {
                "create_mock_execute_artifact": _load_artifact(mock_execute_path),
                "create_live_payload_adapter_scaffold_artifact": _load_artifact(adapter_path),
                "policy": policy,
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
                "scope": result["scope"],
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
