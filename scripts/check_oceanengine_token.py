#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from roibang_v2.integrations.oceanengine.tokens import token_health


def run_from_args(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check RoiBang-v2 OceanEngine token health without printing secrets.")
    parser.add_argument("--store-file", default="data/secrets/oceanengine-tokens.local.json")
    parser.add_argument("--user-id", default="default")
    parser.add_argument("--refresh-lead-seconds", type=int, default=900)
    args = parser.parse_args(argv)

    result = token_health(
        args.store_file,
        user_id=args.user_id,
        refresh_lead_seconds=args.refresh_lead_seconds,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("status") in {"valid", "refresh_due"} else 1


def main() -> int:
    return run_from_args()


if __name__ == "__main__":
    raise SystemExit(main())
