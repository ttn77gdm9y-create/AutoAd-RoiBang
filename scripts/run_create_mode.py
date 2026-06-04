#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from _repo_bootstrap import bootstrap_project_root

bootstrap_project_root()

from roibang_v2.config import load_json, load_runtime_config
from roibang_v2.db.bootstrap import bootstrap_database
from roibang_v2.workflows.create_mode import run_create_mode_request


def _split_accounts(values: list[str] | None) -> list[str]:
    accounts: list[str] = []
    for value in values or []:
        for part in str(value).replace("\n", ",").split(","):
            account = part.strip()
            if account:
                accounts.append(account)
    return accounts


def _request_from_args(args: argparse.Namespace) -> dict:
    if args.request:
        return load_json(args.request)
    accounts = _split_accounts(args.account) + _split_accounts(args.accounts)
    if not args.mode:
        raise ValueError("run_create_mode requires --request or --mode")
    if not accounts:
        raise ValueError("run_create_mode --mode requires at least one --account or --accounts")
    request = {
        "create_mode": {
            "mode_key": args.mode,
            "product_key": args.product_key or "",
            "product_config_path": args.product_config_path or "",
            "product_config_dir": args.product_config_dir or "",
            "target_date": args.target_date or date.today().isoformat(),
            "owner": args.owner,
            "target_accounts": accounts,
            "cpa_bid": args.cpa_bid or "",
            "roi_coefficient": args.roi_coefficient or "",
            "material_source": args.material_source or "",
        }
    }
    if args.template_catalog:
        request["create_mode"]["template_catalog_path"] = args.template_catalog
    return request


def run_from_args(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a create plan from a fixed create mode config.")
    parser.add_argument("--config", default="configs/runtime.example.json")
    parser.add_argument("--request")
    parser.add_argument("--mode", help="Create mode name or mode_key, for example 每付通投近期放量.")
    parser.add_argument("--product-key", help="产品键，例如 yzt-wechat-mini-game；为空时使用创建模式里的 product_key。")
    parser.add_argument("--product-config-path", help="显式指定产品配置 JSON。")
    parser.add_argument("--product-config-dir", default="configs/products", help="产品配置目录。")
    parser.add_argument("--account", action="append", help="Target advertiser ID. Can be repeated.")
    parser.add_argument("--accounts", action="append", help="Comma/newline separated target advertiser IDs.")
    parser.add_argument("--target-date")
    parser.add_argument("--owner", default="郭靖")
    parser.add_argument("--cpa-bid", help="本次项目出价；为空时不写入创建计划。")
    parser.add_argument("--roi-coefficient", help="本次 ROI 系数；为空时不写入创建计划。")
    parser.add_argument("--material-source", choices=["source_account", "gravity_engine"], default="")
    parser.add_argument("--policy", default="policies/create-policy.example.json")
    parser.add_argument("--template-catalog", default="")
    args = parser.parse_args(argv)

    config = load_runtime_config(args.config)
    if config.external_api_enabled or config.execution_enabled:
        raise RuntimeError("create_mode only builds plans and requires external_api_enabled=false and execution_enabled=false")

    bootstrap_database(config.database_path)
    result = run_create_mode_request(
        _request_from_args(args),
        db_path=config.database_path,
        runs_dir=config.runs_dir,
        policy=load_json(args.policy),
        template_catalog_path=args.template_catalog or "configs/create-templates/wx-mini-game.json",
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
                "mode_key": result["mode_key"],
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
