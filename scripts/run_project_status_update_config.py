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
        "workflow": "project_status_update_config",
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


def run_from_args(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate project_update.json for project status update from live project list.")
    parser.add_argument("--project-update-id", required=True)
    parser.add_argument("--operator", default="")
    parser.add_argument("--allowed-target-accounts-path", default="configs/control-allowed-accounts.local.json")
    parser.add_argument("--advertiser-id", action="append", required=True)
    parser.add_argument("--opt-status", choices=["ENABLE", "DISABLE"], required=True)
    parser.add_argument("--name-contains", action="append", default=[])
    parser.add_argument("--reason", default="")
    parser.add_argument("--output", required=True)
    parser.add_argument("--config", default="")
    parser.add_argument("--runs-dir", default="data/runs")
    args = parser.parse_args(argv)

    if not args.config:
        payload = _blocked_payload("project status update config requires --config for live project lookup")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 1

    runtime = _load_json(args.config)
    transport_config = _transport_config(runtime)
    transport = build_create_http_transport(
        transport_config,
        response_dir=Path(args.runs_dir) / "project_status_update_config_http",
    )
    result = run_project_status_update_config_request(
        {
            "project_update_id": args.project_update_id,
            "operator": args.operator,
            "allowed_target_accounts_path": args.allowed_target_accounts_path,
            "advertiser_ids": args.advertiser_id,
            "opt_status": args.opt_status,
            "name_contains": args.name_contains,
            "reason": args.reason,
            "output_path": args.output,
        },
        runs_dir=args.runs_dir,
        transport=transport,
    )
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
