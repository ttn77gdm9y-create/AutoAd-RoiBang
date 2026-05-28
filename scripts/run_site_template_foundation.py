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
from roibang_v2.workflows.site_template_foundation import run_site_template_foundation_request


def run_from_args(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Create or repair local Orange Site landing pages from a site template with WeChat game path."
    )
    parser.add_argument("--config", default="configs/project-update-execute.local.json")
    parser.add_argument("--request", default=None, help="Optional JSON request file.")
    parser.add_argument("--source-advertiser-id", default="")
    parser.add_argument("--source-site-id", default="")
    parser.add_argument("--template-id", default="")
    parser.add_argument("--template-name", default="")
    parser.add_argument("--wechat-game-index", default="")
    parser.add_argument("--game-instance-id", default="")
    parser.add_argument("--game-path", default="")
    parser.add_argument("--target-advertiser-ids", default="", help="Comma or newline separated target advertiser IDs.")
    parser.add_argument("--target-accounts-file", default="", help="Text file with one target advertiser ID per line.")
    parser.add_argument("--site-mapping-artifact", default="", help="Existing site mapping artifact for edit mode.")
    parser.add_argument("--site-name-prefix", default="")
    parser.add_argument("--runs-dir", default="data/runs")
    parser.add_argument("--edit-existing", action="store_true", help="Edit provided site IDs instead of creating new sites.")
    parser.add_argument("--execute", action="store_true", help="Really create/edit and publish sites. Default is dry-run.")
    parser.add_argument("--no-publish", action="store_true", help="Do not publish after create/edit.")
    args = parser.parse_args(argv)

    config = load_json(args.config)
    if args.request:
        request = load_json(args.request)
    else:
        request = {
            "site_template_foundation": {
                "source_advertiser_id": args.source_advertiser_id,
                "source_site_id": args.source_site_id,
                "template_id": args.template_id,
                "template_name": args.template_name,
                "wechat_game_index": args.wechat_game_index,
                "game_instance_id": args.game_instance_id,
                "game_path": args.game_path,
                "target_advertiser_ids": args.target_advertiser_ids,
                "target_accounts_path": args.target_accounts_file,
                "site_mapping_artifact": args.site_mapping_artifact,
                "site_name_prefix": args.site_name_prefix,
                "edit_existing": args.edit_existing,
                "execute": args.execute,
                "publish": not args.no_publish,
            }
        }
    result = run_site_template_foundation_request(request, config=config, runs_dir=args.runs_dir)
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
