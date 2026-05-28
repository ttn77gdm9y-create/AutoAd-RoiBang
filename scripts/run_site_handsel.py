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
from roibang_v2.workflows.site_handsel import run_site_handsel_request


def run_from_args(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Handsel one Orange Site landing page to target advertiser accounts.")
    parser.add_argument("--config", default="configs/project-update-execute.local.json")
    parser.add_argument("--request", default=None, help="Optional JSON request file.")
    parser.add_argument("--source-advertiser-id", default=None, help="Source advertiser account ID.")
    parser.add_argument("--site-id", default=None, help="Orange Site ID to handsel.")
    parser.add_argument("--target-advertiser-ids", default="", help="Comma or newline separated target advertiser IDs.")
    parser.add_argument("--target-accounts-file", default="", help="Text file with one target advertiser ID per line.")
    parser.add_argument("--runs-dir", default="data/runs")
    parser.add_argument("--execute", action="store_true", help="Really call the handsel API. Default is dry-run.")
    args = parser.parse_args(argv)

    config = load_json(args.config)
    if args.request:
        request = load_json(args.request)
    else:
        request = {
            "site_handsel": {
                "source_advertiser_id": args.source_advertiser_id,
                "site_id": args.site_id,
                "target_advertiser_ids": args.target_advertiser_ids,
                "target_accounts_path": args.target_accounts_file,
                "execute": args.execute,
            }
        }
    result = run_site_handsel_request(request, config=config, runs_dir=args.runs_dir)
    output = {
        "ok": result["ok"],
        "workflow": result["workflow"],
        "status": result["status"],
        "execution_enabled": result["execution_enabled"],
        "external_api_calls": result["external_api_calls"],
        "blocking_reasons": result.get("blocking_reasons", []),
        "summary": result["summary"],
        "success_list": result.get("success_list", []),
        "error_list": result.get("error_list", []),
        "artifact_path": result.get("artifact_path", ""),
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if bool(result.get("ok", False)) else 1


def main() -> int:
    return run_from_args()


if __name__ == "__main__":
    raise SystemExit(main())
