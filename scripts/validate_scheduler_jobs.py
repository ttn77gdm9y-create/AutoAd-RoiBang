#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from roibang_v2.scheduler.jobs import load_job_registry, validate_job_registry


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate RoiBang-v2 scheduler job registry.")
    parser.add_argument("--registry", default="configs/scheduler/roibang-v2.jobs.example.json")
    args = parser.parse_args()

    result = validate_job_registry(load_job_registry(args.registry))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
