#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from _repo_bootstrap import bootstrap_project_root

bootstrap_project_root()

from roibang_v2.workflows.gravity_api_probe import run_gravity_api_probe


def run_from_args(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Probe Gravity material library auth safely.")
    parser.add_argument("--auth-file", default="data/gravity_token.json")
    parser.add_argument("--runs-dir", default="data/runs")
    args = parser.parse_args(argv)

    result = run_gravity_api_probe(auth_file=args.auth_file, runs_dir=args.runs_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if bool(result.get("ok")) else 1


def main() -> int:
    return run_from_args()


if __name__ == "__main__":
    raise SystemExit(main())
