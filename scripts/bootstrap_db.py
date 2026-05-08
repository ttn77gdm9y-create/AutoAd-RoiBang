#!/usr/bin/env python3
from __future__ import annotations

import argparse

from roibang_v2.config import load_runtime_config
from roibang_v2.db.bootstrap import bootstrap_database


def main() -> int:
    parser = argparse.ArgumentParser(description="Bootstrap RoiBang-v2 SQLite schema.")
    parser.add_argument("--config", default="configs/runtime.example.json")
    args = parser.parse_args()

    config = load_runtime_config(args.config)
    bootstrap_database(config.database_path)
    print(f"bootstrapped {config.database_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
