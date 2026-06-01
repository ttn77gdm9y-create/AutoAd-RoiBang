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

from roibang_v2.workflows.ai_template_draft_promote import promote_ai_template_draft_preview


def run_from_args(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Promote an AI template draft preview JSON into configs/create-modes.")
    parser.add_argument("--preview", required=True, help="AI template draft preview JSON path.")
    parser.add_argument("--mode-dir", default="configs/create-modes")
    parser.add_argument("--runs-dir", default="data/runs")
    parser.add_argument("--product-key", default="", help="Expected product_key for the selected page context.")
    parser.add_argument("--replace", action="store_true", help="Allow replacing an existing local create mode.")
    args = parser.parse_args(argv)

    result = promote_ai_template_draft_preview(
        preview_path=args.preview,
        mode_dir=args.mode_dir,
        runs_dir=args.runs_dir,
        replace=args.replace,
        expected_product_key=args.product_key,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if bool(result.get("ok", False)) else 1


def main() -> int:
    return run_from_args()


if __name__ == "__main__":
    raise SystemExit(main())
