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

from roibang_v2.config import load_json
from roibang_v2.workflows.product_foundation_extract import run_product_foundation_extract_request


def run_from_args(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Extract product foundation fields from an existing Ocean Engine project.")
    parser.add_argument("--config", default="configs/project-update-execute.local.json")
    parser.add_argument("--request", default=None, help="Optional JSON request file.")
    parser.add_argument("--advertiser-id", default=None)
    parser.add_argument("--project-id", default=None)
    parser.add_argument("--product", default="点点英雄")
    parser.add_argument("--product-key", default="diandian-hero")
    parser.add_argument("--source-advertiser-id", default=None)
    parser.add_argument("--allowed-target-accounts-path", default="")
    parser.add_argument("--account-remark-pattern", default="")
    parser.add_argument("--runs-dir", default="data/runs")
    args = parser.parse_args(argv)

    config = load_json(args.config)
    if args.request:
        request = load_json(args.request)
    else:
        request = {
            "product_foundation_extract": {
                "product": args.product,
                "product_key": args.product_key,
                "advertiser_id": args.advertiser_id,
                "source_advertiser_id": args.source_advertiser_id or args.advertiser_id,
                "project_id": args.project_id,
                "platform": "WECHAT_GAME",
                "allowed_target_accounts_path": args.allowed_target_accounts_path,
                "account_remark_pattern": args.account_remark_pattern,
            }
        }
    result = run_product_foundation_extract_request(
        request,
        config=config,
        runs_dir=args.runs_dir,
    )
    output = {
        "ok": result["ok"],
        "workflow": result["workflow"],
        "status": result["status"],
        "execution_enabled": result["execution_enabled"],
        "external_api_calls": result["external_api_calls"],
        "summary": result["summary"],
        "draft": result.get("draft", {}),
        "artifact_path": result.get("artifact_path", ""),
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if bool(result.get("ok", False)) else 1


def main() -> int:
    return run_from_args()


if __name__ == "__main__":
    raise SystemExit(main())
