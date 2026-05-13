#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from roibang_v2.workflows.create_http_transport import build_create_http_transport
from roibang_v2.workflows.project_status_update_config import run_project_status_update_config_request


def _blocked_payload(reason: str) -> dict:
    return {
        "ok": False,
        "workflow": "project_management_update_config",
        "phase": "control_config",
        "status": "blocked",
        "execution_enabled": False,
        "external_api_calls": 0,
        "summary": {},
        "blocking_reasons": [reason],
    }


def _load_json(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _transport_config(runtime: dict) -> dict:
    root_config = runtime.get("create_http_transport")
    if isinstance(root_config, dict):
        return root_config
    runner = runtime.get("create_live_execute_once")
    if isinstance(runner, dict) and isinstance(runner.get("create_http_transport"), dict):
        return dict(runner["create_http_transport"])
    return {}


def run_from_args(argv: list[str] | None = None, *, default_action_type: str = "status_update") -> int:
    parser = argparse.ArgumentParser(description="Generate project_update.json from live project list by account/name.")
    parser.add_argument("--project-update-id", required=True)
    parser.add_argument("--operator", default="")
    parser.add_argument("--allowed-target-accounts-path", default="configs/control-allowed-accounts.local.json")
    parser.add_argument("--advertiser-id", action="append", required=True)
    parser.add_argument(
        "--action-type",
        choices=["status_update", "budget_update", "bid_update", "roi_coeff_update", "delete_project"],
        default=default_action_type,
    )
    parser.add_argument("--opt-status", choices=["ENABLE", "DISABLE"], default="")
    parser.add_argument("--budget-mode", default="")
    parser.add_argument("--budget", default="")
    parser.add_argument("--cpa-bid", default="")
    parser.add_argument("--roi-goal", default="")
    parser.add_argument("--name-contains", action="append", default=[])
    parser.add_argument("--filter-status-first", default="")
    parser.add_argument("--filter-status-second", default="")
    parser.add_argument("--server-name-query", default="")
    parser.add_argument("--reason", default="")
    parser.add_argument("--output", required=True)
    parser.add_argument("--config", default="")
    parser.add_argument("--runs-dir", default="data/runs")
    args = parser.parse_args(argv)

    if not args.config:
        payload = _blocked_payload("project management update config requires --config for live project lookup")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 1

    filtering = {}
    if args.filter_status_first:
        filtering["status_first"] = args.filter_status_first
    if args.filter_status_second:
        filtering["status_second"] = args.filter_status_second
    if args.server_name_query:
        filtering["name"] = args.server_name_query

    request = {
        "project_update_id": args.project_update_id,
        "operator": args.operator,
        "allowed_target_accounts_path": args.allowed_target_accounts_path,
        "advertiser_ids": args.advertiser_id,
        "action_type": args.action_type,
        "opt_status": args.opt_status,
        "budget_mode": args.budget_mode,
        "budget": args.budget,
        "cpa_bid": args.cpa_bid,
        "roi_goal": args.roi_goal,
        "name_contains": args.name_contains,
        "reason": args.reason,
        "output_path": args.output,
        "workflow": "project_management_update_config" if args.action_type != "status_update" else "project_status_update_config",
    }
    if filtering:
        request["filtering"] = filtering

    runtime = _load_json(args.config)
    transport = build_create_http_transport(
        _transport_config(runtime),
        response_dir=Path(args.runs_dir) / "project_management_update_config_http",
    )
    result = run_project_status_update_config_request(request, runs_dir=args.runs_dir, transport=transport)
    print(
        json.dumps(
            {
                "ok": result["ok"],
                "workflow": result["workflow"],
                "phase": result["phase"],
                "status": result["status"],
                "execution_enabled": result["execution_enabled"],
                "external_api_calls": result["external_api_calls"],
                "summary": result["summary"],
                "project_update_path": result["project_update_path"],
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
