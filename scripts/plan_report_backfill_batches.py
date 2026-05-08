#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from roibang_v2.accounts.pool import build_backfill_batch_plan
from roibang_v2.config import load_runtime_config


def plan_from_args(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build dry-run batch plans for RoiBang-v2 report backfill.")
    parser.add_argument("--config", default="configs/runtime.example.json")
    parser.add_argument("--db", default=None)
    parser.add_argument("--runs-dir", default=None)
    parser.add_argument("--product", required=True)
    parser.add_argument("--platform", action="append", dest="platforms", required=True)
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--endpoint", action="append", dest="endpoints", default=[])
    parser.add_argument("--report-preset", action="append", dest="report_presets", default=[])
    parser.add_argument("--max-accounts-per-batch", type=int, default=20)
    parser.add_argument("--max-dates-per-batch", type=int, default=3)
    parser.add_argument("--max-requests-per-batch", type=int, default=None)
    parser.add_argument("--page-size", type=int, default=100)
    args = parser.parse_args(argv)

    config = load_runtime_config(args.config)
    if config.external_api_enabled or config.execution_enabled:
        raise RuntimeError("batch backfill planning requires external_api_enabled=false and execution_enabled=false")
    result = build_backfill_batch_plan(
        db_path=args.db or config.database_path,
        product=args.product,
        platforms=args.platforms,
        start_date=args.start_date,
        end_date=args.end_date,
        endpoints=args.endpoints or ["report_custom", "operation_log_search"],
        report_presets=args.report_presets or ["promotion_daily"],
        max_accounts_per_batch=args.max_accounts_per_batch,
        max_dates_per_batch=args.max_dates_per_batch,
        max_requests_per_batch=args.max_requests_per_batch,
        page_size=args.page_size,
        runs_dir=args.runs_dir or config.runs_dir,
    )
    output = {
        "ok": result["ok"],
        "workflow": result["workflow"],
        "phase": result["phase"],
        "execution_enabled": result["execution_enabled"],
        "external_api_calls": result["external_api_calls"],
        "summary": result["summary"],
        "limits": result["limits"],
        "artifact_path": result["artifact_path"],
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    return plan_from_args()


if __name__ == "__main__":
    raise SystemExit(main())
