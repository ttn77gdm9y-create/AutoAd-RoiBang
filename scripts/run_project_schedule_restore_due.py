#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from roibang_v2.workflows.create_http_transport import build_create_http_transport
from roibang_v2.workflows.project_schedule_restore_due import run_project_schedule_restore_due_request


def _load_json(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def run_from_args(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Restore due project schedules from restore queue.")
    parser.add_argument("--restore-queue", default="data/runs/project_schedule_restore_queue.json")
    parser.add_argument("--config", default="")
    parser.add_argument("--runs-dir", default="data/runs")
    parser.add_argument("--schedule-scene", default="REALTIME")
    parser.add_argument("--now", default="")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--yes", action="store_true")
    args = parser.parse_args(argv)

    transport = None
    if args.execute and args.yes:
        if not args.config:
            raise RuntimeError("project schedule restore due requires --config when --execute --yes is used")
        state = {}

        def transport(request: dict):
            if "transport" not in state:
                runtime = _load_json(args.config)
                transport_config = runtime.get("create_http_transport") if isinstance(runtime.get("create_http_transport"), dict) else {}
                response_dir = Path(args.runs_dir) / "project_schedule_restore_due_http"
                state["transport"] = build_create_http_transport(transport_config, response_dir=response_dir)
            return state["transport"](request)

    result = run_project_schedule_restore_due_request(
        {
            "restore_queue_path": args.restore_queue,
            "execute_enabled": args.execute,
            "approved": args.yes,
            "schedule_scene": args.schedule_scene,
            "now": args.now,
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
                "restore_report": result.get("restore_report", {}),
                "restore_queue_path": result["restore_queue_path"],
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
