#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from roibang_v2.config import load_json, load_runtime_config
from roibang_v2.workflows.create_first_live_prepare_pack import run_create_first_live_prepare_pack_request


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
    parser = argparse.ArgumentParser(description="Build local-only first live create prepare pack.")
    parser.add_argument("--config", default="configs/runtime.example.json")
    parser.add_argument("--create-live-execution-pack-artifact", default="")
    args = parser.parse_args(argv)

    config = load_runtime_config(args.config)
    execution_pack_path = _artifact_path(
        args.create_live_execution_pack_artifact,
        config.runs_dir,
        "create_live_execution_pack",
    )
    result = run_create_first_live_prepare_pack_request(
        {
            "create_first_live_prepare_pack": {
                "create_live_execution_pack_artifact": _load_artifact(execution_pack_path)
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
                "live_execute_enabled": result["live_execute_enabled"],
                "external_api_calls": result["external_api_calls"],
                "status": result["status"],
                "readiness": result["readiness"],
                "payload_review": result["payload_review"],
                "required_enablement": result["required_enablement"],
                "artifact_path": result["artifact_path"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def main() -> int:
    return run_from_args()


if __name__ == "__main__":
    raise SystemExit(main())
