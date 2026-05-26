#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from roibang_v2.accounts.pool import import_allowed_accounts_json
from roibang_v2.config import load_json, load_runtime_config
from roibang_v2.db.bootstrap import bootstrap_database


def _allowed_path_from_args(args: argparse.Namespace) -> str:
    if args.allowed_target_accounts_path:
        return args.allowed_target_accounts_path
    if args.product_config:
        product_config = load_json(args.product_config)
        path = str(product_config.get("allowed_target_accounts_path") or "").strip()
        if path:
            return path
    raise ValueError("requires --allowed-target-accounts-path or --product-config with allowed_target_accounts_path")


def import_from_args(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import allowed create accounts into local account_pool.")
    parser.add_argument("--config", default="configs/runtime.example.json")
    parser.add_argument("--db", default=None)
    parser.add_argument("--allowed-target-accounts-path", default="")
    parser.add_argument("--product-config", default="")
    args = parser.parse_args(argv)

    config = load_runtime_config(args.config)
    if config.external_api_enabled or config.execution_enabled:
        raise RuntimeError("allowed create account import requires external_api_enabled=false and execution_enabled=false")
    db_path = args.db or config.database_path
    bootstrap_database(db_path)
    result = import_allowed_accounts_json(_allowed_path_from_args(args), db_path=db_path)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    return import_from_args()


if __name__ == "__main__":
    raise SystemExit(main())
