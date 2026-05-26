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

from roibang_v2.workflows.product_config_publish import publish_product_config_draft


def run_from_args(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Publish a product draft JSON into configs/products as a local product config.")
    parser.add_argument("--draft", required=True, help="Product draft JSON path.")
    parser.add_argument("--products-dir", default="configs/products")
    parser.add_argument("--runs-dir", default="data/runs")
    parser.add_argument("--replace", action="store_true", help="Allow replacing an existing local product config.")
    args = parser.parse_args(argv)

    result = publish_product_config_draft(
        draft_path=args.draft,
        products_dir=args.products_dir,
        runs_dir=args.runs_dir,
        replace=args.replace,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if bool(result.get("ok", False)) else 1


def main() -> int:
    return run_from_args()


if __name__ == "__main__":
    raise SystemExit(main())
