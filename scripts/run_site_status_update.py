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
from roibang_v2.workflows.site_status_update import run_site_status_update_request


def run_from_args(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Update Orange Site landing page status in batches.")
    parser.add_argument("--config", default="configs/project-update-execute.local.json")
    parser.add_argument("--request", default=None, help="Optional JSON request file.")
    parser.add_argument("--handsel-artifact", default="", help="Use success_list from a site_handsel artifact.")
    parser.add_argument("--advertiser-id", default="", help="Single advertiser account ID.")
    parser.add_argument("--site-ids", default="", help="Comma or newline separated site IDs for --advertiser-id.")
    parser.add_argument("--status", default="delete", choices=["published", "unpublished", "delete", "undeleted"])
    parser.add_argument("--runs-dir", default="data/runs")
    parser.add_argument("--execute", action="store_true", help="Really call the status update API. Default is dry-run.")
    args = parser.parse_args(argv)

    config = load_json(args.config)
    if args.request:
        request = load_json(args.request)
    else:
        request = {
            "site_status_update": {
                "handsel_artifact": args.handsel_artifact,
                "advertiser_id": args.advertiser_id,
                "site_ids": args.site_ids,
                "status": args.status,
                "execute": args.execute,
            }
        }
    result = run_site_status_update_request(request, config=config, runs_dir=args.runs_dir)
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
