#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from roibang_v2.artifacts.contract import validate_artifact_contract
from roibang_v2.scheduler.jobs import load_job_registry


def validate_from_args(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate a RoiBang-v2 run artifact against scheduler result contract.")
    parser.add_argument("--registry", default="configs/scheduler/roibang-v2.jobs.example.json")
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--artifact", default=None)
    parser.add_argument("--repo-root", default=str(Path.cwd()))
    args = parser.parse_args(argv)

    result = validate_artifact_contract(
        load_job_registry(args.registry),
        job_id=args.job_id,
        artifact_path=args.artifact,
        repo_root=args.repo_root,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


def main() -> int:
    return validate_from_args()


if __name__ == "__main__":
    raise SystemExit(main())
