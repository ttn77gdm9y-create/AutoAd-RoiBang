#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from roibang_v2.config import load_json, load_runtime_config
from roibang_v2.workflows.create_phase1_baseline_freeze import run_create_phase1_baseline_freeze_request


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
    parser = argparse.ArgumentParser(description="Run Phase 1 create baseline freeze.")
    parser.add_argument("--config", default="configs/runtime.example.json")
    args = parser.parse_args(argv)

    config = load_runtime_config(args.config)
    if config.external_api_enabled or config.execution_enabled:
        raise RuntimeError(
            "Phase 1 create baseline freeze requires external_api_enabled=false and execution_enabled=false"
        )

    artifacts = {
        workflow: _load_artifact(_latest_artifact(config.runs_dir, workflow))
        for workflow in [
            "create_phase1_acceptance_checklist",
            "create_chain_final_report",
            "create_chain_index",
        ]
    }
    result = run_create_phase1_baseline_freeze_request(
        {
            "create_phase1_baseline_freeze": {
                "create_phase1_acceptance_checklist_artifact": artifacts[
                    "create_phase1_acceptance_checklist"
                ],
                "create_chain_final_report_artifact": artifacts["create_chain_final_report"],
                "create_chain_index_artifact": artifacts["create_chain_index"],
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
                "phase1_baseline_status": result["phase1_baseline_status"],
                "baseline_id": result["baseline_id"],
                "baseline_digest": result["baseline_digest"],
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
