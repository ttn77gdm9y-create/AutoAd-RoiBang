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
from roibang_v2.workflows.site_game_path_update import run_site_game_path_update_request


def run_from_args(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Deprecated unsafe full-update path for Orange Site WeChat game path. Prefer run_site_template_foundation.py."
    )
    parser.add_argument("--config", default="configs/project-update-execute.local.json")
    parser.add_argument("--request", default=None, help="Optional JSON request file.")
    parser.add_argument("--handsel-artifact", default="", help="site_handsel result JSON with success_list.")
    parser.add_argument("--advertiser-id", default="")
    parser.add_argument("--site-id", default="")
    parser.add_argument("--game-name", default="点点英雄")
    parser.add_argument("--game-path", required=False, default="")
    parser.add_argument("--instance-id", default="", help="Known WeChat game instance_id. If set, skip game lookup.")
    parser.add_argument("--runs-dir", default="data/runs")
    parser.add_argument("--execute", action="store_true", help="Really update and publish sites. Default is dry-run.")
    parser.add_argument("--no-publish", action="store_true", help="Update only, do not publish.")
    parser.add_argument(
        "--allow-unsafe-full-site-update",
        action="store_true",
        help="Allow the deprecated full site update API. This may drop components/images.",
    )
    args = parser.parse_args(argv)

    config = load_json(args.config)
    if args.request:
        request = load_json(args.request)
    else:
        request = {
            "site_game_path_update": {
                "handsel_artifact": args.handsel_artifact,
                "advertiser_id": args.advertiser_id,
                "site_id": args.site_id,
                "game_name": args.game_name,
                "game_path": args.game_path,
                "instance_id": args.instance_id,
                "execute": args.execute,
                "publish": not args.no_publish,
                "allow_unsafe_full_site_update": args.allow_unsafe_full_site_update,
            }
        }
    result = run_site_game_path_update_request(request, config=config, runs_dir=args.runs_dir)
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
