#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from roibang_v2.accounts.pool import import_accounts_csv
from roibang_v2.config import load_runtime_config
from roibang_v2.db.bootstrap import bootstrap_database


def import_from_args(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import RoiBang-v2 account pool CSV.")
    parser.add_argument("--csv", default="data/sources/accounts/roibangv2yztj.csv")
    parser.add_argument("--config", default="configs/runtime.example.json")
    parser.add_argument("--db", default=None)
    args = parser.parse_args(argv)

    config = load_runtime_config(args.config)
    if config.external_api_enabled or config.execution_enabled:
        raise RuntimeError("account import requires external_api_enabled=false and execution_enabled=false")
    db_path = args.db or config.database_path
    bootstrap_database(db_path)
    result = import_accounts_csv(args.csv, db_path=db_path)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    return import_from_args()


if __name__ == "__main__":
    raise SystemExit(main())
