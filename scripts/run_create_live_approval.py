#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from roibang_v2.config import load_json, load_runtime_config
from roibang_v2.workflows.create_live_approval import run_create_live_approval_request


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
    parser = argparse.ArgumentParser(description="Validate one-shot first live create approval without execution.")
    parser.add_argument("--config", default="configs/runtime.example.json")
    parser.add_argument("--approval-file", required=True)
    parser.add_argument("--create-execute-artifact", default="")
    parser.add_argument("--create-first-live-runbook-artifact", default="")
    parser.add_argument("--create-live-payload-adapter-scaffold-artifact", default="")
    args = parser.parse_args(argv)

    config = load_runtime_config(args.config)
    if config.external_api_enabled or config.execution_enabled:
        raise RuntimeError("create live approval requires external_api_enabled=false and execution_enabled=false")

    execute_path = _artifact_path(args.create_execute_artifact, config.runs_dir, "create_execute")
    runbook_path = _artifact_path(
        args.create_first_live_runbook_artifact,
        config.runs_dir,
        "create_first_live_runbook",
    )
    scaffold_path = _artifact_path(
        args.create_live_payload_adapter_scaffold_artifact,
        config.runs_dir,
        "create_live_payload_adapter_scaffold",
    )
    result = run_create_live_approval_request(
        {
            "create_live_approval": {
                "approval_request": load_json(args.approval_file),
                "create_execute_artifact": _load_artifact(execute_path),
                "create_first_live_runbook_artifact": _load_artifact(runbook_path),
                "create_live_payload_adapter_scaffold_artifact": _load_artifact(scaffold_path),
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
                "approval": result["approval"],
                "scope": result["scope"],
                "violations": result["violations"],
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
