#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from roibang_v2.config import load_json, load_runtime_config
from roibang_v2.workflows.create_provider_evidence_review import (
    run_create_provider_evidence_review_request,
)


def run_from_args(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Phase 2 provider evidence review.")
    parser.add_argument("--config", default="configs/runtime.example.json")
    parser.add_argument("--policy", default="policies/strategy.example.json")
    args = parser.parse_args(argv)

    config = load_runtime_config(args.config)
    if config.external_api_enabled or config.execution_enabled:
        raise RuntimeError(
            "Phase 2 provider evidence review requires external_api_enabled=false and execution_enabled=false"
        )
    policy_root = load_json(args.policy)
    policy = policy_root.get("create_provider_evidence_review") or policy_root.get("create_phase2_provider_mapping_prep") or {}
    result = run_create_provider_evidence_review_request(
        {"create_provider_evidence_review": {"policy": policy}},
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
                "operator_guide": result["operator_guide"],
                "evidence_worksheet_summary": result["evidence_worksheet"]["summary"],
                "provider_field_gap_summary": result["provider_field_gap_report"]["summary"],
                "provider_field_gap_resolution_summary": result["provider_field_gap_resolution_plan"]["summary"],
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
