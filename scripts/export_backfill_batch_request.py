#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from roibang_v2.backfill.batches import export_batch_request


def export_from_args(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export one disabled report-fetch request from a backfill batch plan.")
    parser.add_argument("--plan", required=True)
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--output-dir", default="data/requests/backfill")
    args = parser.parse_args(argv)

    result = export_batch_request(
        plan_path=args.plan,
        batch_id=args.batch_id,
        output_dir=args.output_dir,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    return export_from_args()


if __name__ == "__main__":
    raise SystemExit(main())
