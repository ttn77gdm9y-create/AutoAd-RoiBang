#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from roibang_v2.config import load_json, load_runtime_config
from roibang_v2.runs import write_run_artifact
from roibang_v2.workflows.create_live_execute_report import run_create_live_execute_report_request


def _latest_artifact(runs_dir: Path, workflow: str) -> Path:
    workflow_dir = runs_dir / workflow
    candidates = sorted(workflow_dir.glob("*.json"))
    if not candidates:
        raise FileNotFoundError(f"no {workflow} artifacts found under {workflow_dir}")
    return candidates[-1]


def _load_artifact(path: Path) -> dict:
    artifact = load_json(path)
    artifact["artifact_path"] = str(path)
    return artifact


def _missing_result(*, runs_dir: Path, message: str) -> dict:
    payload = {
        "ok": False,
        "workflow": "create_live_execute_report",
        "phase": "phase2_preparation",
        "execution_enabled": False,
        "external_api_calls": 0,
        "status": "not_found",
        "message": f"还没有找到真实执行结果：{message}",
        "summary": {
            "source_ok": False,
            "source_status": "not_found",
            "source_external_api_calls": 0,
            "source_transport_call_count": 0,
            "completed_step_count": 0,
            "skipped_step_count": 0,
            "created_project_count": 0,
            "created_unit_count": 0,
            "target_video_count": 0,
            "target_video_cover_count": 0,
            "material_bind_count": 0,
            "blocking_reasons": [message],
            "failure": None,
            "runner_status": "",
        },
        "db_ledger_summary": {},
        "create_plan_summary": {},
        "create_plan_contract": {"available": False, "plan_id_matches_source": False},
        "source_artifact_path": "",
        "plan_artifact_path": "",
        "actions": [],
    }
    payload["artifact_path"] = str(write_run_artifact(runs_dir, "create_live_execute_report", payload))
    return payload


def _print_result(result: dict) -> None:
    print(
        json.dumps(
            {
                "ok": result["ok"],
                "workflow": result["workflow"],
                "phase": result["phase"],
                "execution_enabled": result["execution_enabled"],
                "external_api_calls": result["external_api_calls"],
                "status": result["status"],
                "message": result["message"],
                "summary": result["summary"],
                "create_plan_summary": result["create_plan_summary"],
                "create_plan_contract": result["create_plan_contract"],
                "db_ledger_summary": result["db_ledger_summary"],
                "source_artifact_path": result["source_artifact_path"],
                "plan_artifact_path": result["plan_artifact_path"],
                "artifact_path": result["artifact_path"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def run_from_args(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Report latest one-shot live create execution result.")
    parser.add_argument("--config", default="configs/runtime.example.json")
    parser.add_argument("--plan", default="")
    parser.add_argument("--create-live-execute-once-artifact", default="")
    args = parser.parse_args(argv)

    config = load_runtime_config(args.config)
    create_plan = None
    plan_path = Path(args.plan) if str(args.plan or "").strip() else None
    if plan_path is not None:
        try:
            create_plan = load_json(plan_path)
        except FileNotFoundError as exc:
            result = _missing_result(runs_dir=config.runs_dir, message=str(exc))
            _print_result(result)
            return 0
    try:
        source_path = (
            Path(args.create_live_execute_once_artifact)
            if str(args.create_live_execute_once_artifact or "").strip()
            else _latest_artifact(config.runs_dir, "create_live_execute_once")
        )
        source = _load_artifact(source_path)
    except FileNotFoundError as exc:
        result = _missing_result(runs_dir=config.runs_dir, message=str(exc))
        _print_result(result)
        return 0

    result = run_create_live_execute_report_request(
        {
            "create_live_execute_report": {
                "create_live_execute_once_artifact": source,
                "source_artifact_path": str(source_path),
                "create_plan_artifact": create_plan if isinstance(create_plan, dict) else None,
                "plan_artifact_path": str(plan_path) if plan_path is not None else "",
            }
        },
        runs_dir=config.runs_dir,
        db_path=config.database_path,
    )
    _print_result(result)
    return 0


def main() -> int:
    return run_from_args()


if __name__ == "__main__":
    raise SystemExit(main())
