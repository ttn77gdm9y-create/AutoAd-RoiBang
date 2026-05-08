#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from roibang_v2.config import load_json, load_runtime_config
from roibang_v2.workflows.create_readiness_matrix import run_create_readiness_matrix_request


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
    parser = argparse.ArgumentParser(description="Run Phase 1 create readiness matrix.")
    parser.add_argument("--config", default="configs/runtime.example.json")
    parser.add_argument("--create-provider-field-map-check-artifact", default="")
    parser.add_argument("--create-field-mapping-review-pack-artifact", default="")
    parser.add_argument("--create-template-slot-review-pack-artifact", default="")
    parser.add_argument("--create-preflight-artifact", default="")
    parser.add_argument("--create-dry-run-artifact", default="")
    parser.add_argument("--create-chain-replay-artifact", default="")
    parser.add_argument("--create-chain-manifest-artifact", default="")
    args = parser.parse_args(argv)

    config = load_runtime_config(args.config)
    if config.external_api_enabled or config.execution_enabled:
        raise RuntimeError("Phase 1 create readiness matrix requires external_api_enabled=false and execution_enabled=false")

    field_map_check_path = _artifact_path(
        args.create_provider_field_map_check_artifact,
        config.runs_dir,
        "create_provider_field_map_check",
    )
    field_review_path = _artifact_path(
        args.create_field_mapping_review_pack_artifact,
        config.runs_dir,
        "create_field_mapping_review_pack",
    )
    template_review_path = _artifact_path(
        args.create_template_slot_review_pack_artifact,
        config.runs_dir,
        "create_template_slot_review_pack",
    )
    preflight_path = _artifact_path(args.create_preflight_artifact, config.runs_dir, "create_preflight")
    dry_run_path = _artifact_path(args.create_dry_run_artifact, config.runs_dir, "create_dry_run")
    replay_path = _artifact_path(args.create_chain_replay_artifact, config.runs_dir, "create_chain_replay")
    manifest_path = _artifact_path(args.create_chain_manifest_artifact, config.runs_dir, "create_chain_manifest")

    result = run_create_readiness_matrix_request(
        {
            "create_readiness_matrix": {
                "create_provider_field_map_check_artifact": _load_artifact(field_map_check_path),
                "create_field_mapping_review_pack_artifact": _load_artifact(field_review_path),
                "create_template_slot_review_pack_artifact": _load_artifact(template_review_path),
                "create_preflight_artifact": _load_artifact(preflight_path),
                "create_dry_run_artifact": _load_artifact(dry_run_path),
                "create_chain_replay_artifact": _load_artifact(replay_path),
                "create_chain_manifest_artifact": _load_artifact(manifest_path),
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
                "ready_for_live_execute": result["ready_for_live_execute"],
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
