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

from roibang_v2.workflows.product_automation_job import SUPPORTED_JOBS
from roibang_v2.workflows.product_automation_job import run_product_automation_job


def run_from_args(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one RoiBang-v2 product automation job for enabled products.")
    parser.add_argument("--job", required=True, choices=sorted(SUPPORTED_JOBS))
    parser.add_argument("--product-key", default="", help="只跑某个产品键，例如 diandian-hero；为空则跑所有启用产品。")
    parser.add_argument("--products-dir", default="configs/products")
    parser.add_argument("--request-dir", default="data/requests/product-automation")
    parser.add_argument("--runs-dir", default="data/runs")
    parser.add_argument("--target-date", default="yesterday", help="today / yesterday / YYYY-MM-DD")
    parser.add_argument("--enable-readonly", action="store_true", help="允许只读接口调用。")
    parser.add_argument("--execute", action="store_true", help="允许真实业务动作，仅源素材补材/预推送使用。")
    parser.add_argument("--yes", action="store_true", help="真实业务动作二次确认。")
    parser.add_argument("--dry-run", action="store_true", help="只生成每个产品的请求配置和命令，不执行脚本。")
    args = parser.parse_args(argv)

    if args.execute and not args.yes:
        raise RuntimeError("product automation real mutation requires --yes")
    result = run_product_automation_job(
        job=args.job,
        products_dir=args.products_dir,
        request_dir=args.request_dir,
        runs_dir=args.runs_dir,
        product_key=args.product_key,
        target_date=args.target_date,
        enable_readonly=args.enable_readonly,
        execute=args.execute,
        yes=args.yes,
        dry_run=args.dry_run,
    )
    print(
        json.dumps(
            {
                "ok": result["ok"],
                "workflow": result["workflow"],
                "phase": result["phase"],
                "status": result["status"],
                "execution_enabled": result["execution_enabled"],
                "external_api_calls": result["external_api_calls"],
                "summary": result["summary"],
                "blocking_reasons": result["blocking_reasons"],
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
