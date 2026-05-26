#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from roibang_v2.config import load_json, load_runtime_config
from roibang_v2.runs import write_run_artifact
from roibang_v2.workflows.create_live_execute_report import run_create_live_execute_report_request
from roibang_v2.workflows.scheduler_status import send_feishu_app_chat_text


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
                "batch_summary": result.get("batch_summary", {}),
                "readable_reference": result.get("readable_reference", {}),
                "create_plan_summary": result["create_plan_summary"],
                "create_plan_contract": result["create_plan_contract"],
                "db_ledger_summary": result["db_ledger_summary"],
                "delivery": result.get("delivery", {}),
                "source_artifact_path": result["source_artifact_path"],
                "source_artifact_paths": result.get("source_artifact_paths", []),
                "plan_artifact_path": result["plan_artifact_path"],
                "artifact_path": result["artifact_path"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def _format_number(value: object, *, digits: int = 2) -> str:
    try:
        number = float(value or 0)
    except (TypeError, ValueError):
        return "0"
    if number.is_integer():
        return str(int(number))
    return f"{number:.{digits}f}".rstrip("0").rstrip(".")


def _format_feishu_message(result: dict) -> str:
    lines = [
        "RoiBang-V2 创建执行报告",
        "",
        str(result.get("message") or ""),
    ]
    issues = result.get("readable_reference", {}).get("execution_issues", {})
    if isinstance(issues, dict) and bool(issues.get("manual_review_required")):
        lines.extend(
            [
                "",
                "需要处理",
                f"- 影响账户：{int(issues.get('affected_account_count') or 0)} 个",
                f"- 跳过单元：{int(issues.get('skipped_unit_count') or 0)} 个",
                f"- 素材绑定异常：{int(issues.get('material_bind_failure_count') or 0)} 次",
            ]
        )
        for row in (issues.get("accounts") if isinstance(issues.get("accounts"), list) else [])[:8]:
            if not isinstance(row, dict):
                continue
            codes = "/".join(str(item) for item in row.get("codes") or [])
            messages = "；".join(str(item) for item in row.get("messages") or [])
            lines.append(
                "- "
                f"{row.get('advertiser_id')}："
                f"跳过单元 {int(row.get('skipped_unit_count') or 0)}，"
                f"错误 {codes or '-'} {messages or ''}".rstrip()
            )
    selected = result.get("readable_reference", {}).get("selected_materials", {})
    if isinstance(selected, dict) and selected:
        lines.extend(
            [
                "",
                "选材摘要",
                f"- 素材分配：{int(selected.get('assignment_count') or 0)} 次",
                f"- 唯一素材：{int(selected.get('unique_material_count') or 0)} 个",
            ]
        )
        accounts = selected.get("by_account") if isinstance(selected.get("by_account"), list) else []
        if accounts:
            lines.append("- 账户分布：" + " / ".join(
                f"{row.get('advertiser_id')}：{int(row.get('unique_material_count') or 0)} 个唯一素材"
                for row in accounts[:8]
                if isinstance(row, dict)
            ))
        top_materials = selected.get("top_materials_by_cost") if isinstance(selected.get("top_materials_by_cost"), list) else []
        if top_materials:
            lines.extend(["", "高消耗素材 Top 5"])
            for row in top_materials[:5]:
                if not isinstance(row, dict):
                    continue
                name = str(row.get("name") or "未命名素材")
                material_id = str(row.get("material_id") or "")
                lines.append(
                    "- "
                    f"{name}（{material_id}）："
                    f"消耗 {_format_number(row.get('stat_cost'))}，"
                    f"转化 {_format_number(row.get('convert_cnt'))}，"
                    f"使用 {int(row.get('assigned_count') or 0)} 次"
                )
    artifact_path = str(result.get("artifact_path") or "")
    if artifact_path:
        lines.extend(["", f"完整 JSON：{artifact_path}"])
    return "\n".join(line for line in lines if line is not None)


def _deliver_feishu(result: dict, *, runtime_file: str) -> dict:
    if not str(runtime_file or "").strip():
        return {"enabled": False, "attempted": False, "ok": True, "reason": "missing_runtime_file"}
    try:
        delivery = send_feishu_app_chat_text({"enabled": True, "runtime_file": runtime_file}, _format_feishu_message(result))
    except Exception as exc:
        return {"enabled": True, "attempted": True, "ok": False, "reason": str(exc)}
    return {"enabled": True, "attempted": True, **delivery}


def run_from_args(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Report latest one-shot live create execution result.")
    parser.add_argument("--config", default="configs/runtime.example.json")
    parser.add_argument("--plan", default="")
    parser.add_argument("--create-live-execute-once-artifact", action="append", default=[])
    parser.add_argument("--push-feishu", action="store_true")
    parser.add_argument("--feishu-runtime-file", default="data/secrets/feishu.runtime.local.json")
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
        source_paths = [
            Path(value)
            for value in args.create_live_execute_once_artifact
            if str(value or "").strip()
        ]
        if not source_paths:
            source_paths = [_latest_artifact(config.runs_dir, "create_live_execute_once")]
        sources = [_load_artifact(source_path) for source_path in source_paths]
    except FileNotFoundError as exc:
        result = _missing_result(runs_dir=config.runs_dir, message=str(exc))
        _print_result(result)
        return 0

    if len(sources) > 1:
        result = run_create_live_execute_report_request(
            {
                "create_live_execute_report": {
                    "create_live_execute_once_artifacts": sources,
                    "source_artifact_paths": [str(source_path) for source_path in source_paths],
                }
            },
            runs_dir=config.runs_dir,
            db_path=config.database_path,
        )
        if args.push_feishu:
            result["delivery"] = {"feishu": _deliver_feishu(result, runtime_file=args.feishu_runtime_file)}
        _print_result(result)
        return 0

    source_path = source_paths[0]
    source = sources[0]
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
    if args.push_feishu:
        result["delivery"] = {"feishu": _deliver_feishu(result, runtime_file=args.feishu_runtime_file)}
    _print_result(result)
    return 0


def main() -> int:
    return run_from_args()


if __name__ == "__main__":
    raise SystemExit(main())
