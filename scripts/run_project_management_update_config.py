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

from roibang_v2.workflows.create_http_transport import build_create_http_transport
from roibang_v2.workflows.project_status_update_config import run_project_status_update_config_request

PROJECT_UPDATE_RUNTIME_CONFIG = "configs/project-update-execute.local.json"


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


def _parse_metric_filter(value: str) -> dict:
    parts = str(value or "").split(":", 2)
    if len(parts) != 3:
        raise argparse.ArgumentTypeError("--metric-filter must use field:op:value format")
    field, op, raw_value = [part.strip() for part in parts]
    if not field or not op or not raw_value:
        raise argparse.ArgumentTypeError("--metric-filter must use field:op:value format")
    try:
        numeric_value = float(raw_value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("--metric-filter value must be numeric") from exc
    return {"field": field, "op": op, "value": numeric_value}


def _validate_entry_config_path(config_path: str) -> dict | None:
    if str(config_path or "").strip() == PROJECT_UPDATE_RUNTIME_CONFIG:
        return None
    return _blocked_payload(
        f"项目管理生成配置必须使用 {PROJECT_UPDATE_RUNTIME_CONFIG}，不能使用 {str(config_path or '').strip() or '空配置'}"
    )


def _build_parser(*, default_action_type: str = "status_update") -> argparse.ArgumentParser:
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
    parser.add_argument(
        "--spend-window",
        choices=["today", "yesterday", "last_3_days"],
        default="",
    )
    parser.add_argument("--spend-end-date", default="")
    parser.add_argument("--max-stat-cost", default="")
    parser.add_argument("--metric-filter", action="append", type=_parse_metric_filter, default=[])
    parser.add_argument("--filter-status-first", default="")
    parser.add_argument("--filter-status-second", default="")
    parser.add_argument("--server-name-query", default="")
    parser.add_argument("--reason", default="")
    parser.add_argument("--output", required=True)
    parser.add_argument("--config", default=PROJECT_UPDATE_RUNTIME_CONFIG)
    parser.add_argument("--runs-dir", default="data/runs")
    return parser


def run_from_args(argv: list[str] | None = None, *, default_action_type: str = "status_update") -> int:
    parser = _build_parser(default_action_type=default_action_type)
    args = parser.parse_args(argv)

    payload = _validate_entry_config_path(args.config)
    if payload is not None:
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
    if args.spend_window or args.max_stat_cost or args.metric_filter:
        realtime_filter = {
            "window": args.spend_window or "today",
            "end_date": args.spend_end_date,
        }
        if args.metric_filter:
            realtime_filter["metric_filters"] = args.metric_filter
        if args.max_stat_cost:
            realtime_filter["max_stat_cost_exclusive"] = args.max_stat_cost
        request["realtime_filter"] = realtime_filter
        request["workflow"] = "project_realtime_filter_config"
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
