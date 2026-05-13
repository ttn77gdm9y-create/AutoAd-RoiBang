#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from roibang_v2.workflows.create_http_transport import build_create_http_transport
from roibang_v2.workflows.project_update_execute import run_project_update_execute_request


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
    parser = argparse.ArgumentParser(description="Execute project_update.json schedule changes after preflight.")
    parser.add_argument("--project-update", required=True)
    parser.add_argument("--preflight-artifact", required=True)
    parser.add_argument("--config", default="")
    parser.add_argument("--runs-dir", default="data/runs")
    parser.add_argument("--schedule-scene", default="REALTIME")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--yes", action="store_true")
    args = parser.parse_args(argv)

    transport = None
    if args.execute and args.yes:
        if not args.config:
            raise RuntimeError("project update execute requires --config when --execute --yes is used")
        runtime = _load_json(args.config)
        transport_config = _transport_config(runtime)
        response_dir = Path(args.runs_dir) / "project_update_execute_http"
        transport = build_create_http_transport(transport_config, response_dir=response_dir)

    result = run_project_update_execute_request(
        {
            "project_update_path": args.project_update,
            "preflight_artifact_path": args.preflight_artifact,
            "execute_enabled": args.execute,
            "approved": args.yes,
            "schedule_scene": args.schedule_scene,
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
                "blocking_reasons": result["blocking_reasons"],
                "project_update_path": result["project_update_path"],
                "preflight_artifact_path": result["preflight_artifact_path"],
                "schedule_ledger_path": result.get("schedule_ledger_path", ""),
                "restore_queue_path": result.get("restore_queue_path", ""),
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
