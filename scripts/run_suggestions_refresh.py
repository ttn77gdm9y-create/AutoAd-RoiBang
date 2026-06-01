#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from datetime import datetime
from datetime import timedelta
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from _repo_bootstrap import bootstrap_project_root

bootstrap_project_root()

from backend.app.services.suggestions import build_suggestions_list
from roibang_v2.runs import write_run_artifact
from roibang_v2.workflows.product_automation_job import run_product_automation_job


REFRESH_JOBS: list[tuple[str, str, bool]] = [
    ("daily_report_sync", "每日报表同步", True),
    ("material_daily_sync", "每日素材明细同步", True),
    ("operation_log_sync", "操作日志同步", True),
    ("source_material_rollup", "源素材表现汇总", False),
    ("delivery_patrol", "小时投放巡检", True),
]


def _summary_value(result: dict[str, Any], label: str) -> str:
    summary = result.get("summary") if isinstance(result.get("summary"), dict) else {}
    for item in summary.get("items", []) if isinstance(summary.get("items"), list) else []:
        if isinstance(item, dict) and str(item.get("label") or "") == label:
            return str(item.get("value") or "").strip()
    return ""


def _concrete_target_date(value: str) -> str:
    text = str(value or "").strip() or "today"
    if text == "today":
        return date.today().isoformat()
    if text == "yesterday":
        return (date.today() - timedelta(days=1)).isoformat()
    return text


def _short_problem(text: Any) -> str:
    lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    if not lines:
        return ""
    return lines[-1][:500]


def _result_problems(result: dict[str, Any]) -> list[str]:
    problems = [_short_problem(item) for item in result.get("blocking_reasons", [])]
    for child in result.get("results", []) if isinstance(result.get("results"), list) else []:
        if not isinstance(child, dict) or bool(child.get("ok", True)):
            continue
        label = str(child.get("product_key") or child.get("product") or child.get("job") or "").strip()
        parsed = child.get("parsed_stdout") if isinstance(child.get("parsed_stdout"), dict) else {}
        child_reasons = [_short_problem(item) for item in parsed.get("blocking_reasons", []) if str(item or "").strip()]
        if not child_reasons:
            child_reasons = [_short_problem(child.get("stderr")) or _short_problem(child.get("stdout"))]
        for reason in child_reasons:
            if reason:
                problems.append(f"{label}：{reason}" if label else reason)
    return [item for item in problems if item]


def _job_row(result: dict[str, Any], *, label: str) -> dict[str, Any]:
    summary = result.get("summary") if isinstance(result.get("summary"), dict) else {}
    return {
        "任务": label,
        "workflow": str(result.get("workflow") or ""),
        "状态": str(result.get("status") or ""),
        "产品数": summary.get("product_count", 0),
        "外部只读调用": int(result.get("external_api_calls") or 0),
        "结果文件": str(result.get("artifact_path") or ""),
        "问题": "；".join(_result_problems(result)),
    }


def _failed_job(job: str, label: str, exc: Exception) -> dict[str, Any]:
    return {
        "ok": False,
        "workflow": f"product_automation_job_{job}",
        "status": "failed",
        "execution_enabled": False,
        "external_api_calls": 0,
        "summary": {"job": job, "product_count": 0},
        "blocking_reasons": [str(exc)],
        "artifact_path": "",
        "label": label,
    }


def run_from_args(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run readonly data sync jobs and rebuild rule suggestions.")
    parser.add_argument("--product-key", default="", help="只刷新某个产品；为空则刷新所有启用产品。")
    parser.add_argument("--target-date", default="today", help="today / yesterday / YYYY-MM-DD")
    parser.add_argument("--products-dir", default="configs/products")
    parser.add_argument("--request-dir", default="data/requests/product-automation")
    parser.add_argument("--runs-dir", default="data/runs")
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--enable-readonly", action="store_true", help="允许固定只读同步脚本读取外部报表。")
    args = parser.parse_args(argv)

    if not args.enable_readonly:
        raise RuntimeError("同步数据并重算建议需要 --enable-readonly；该入口只允许只读同步，不允许真实业务动作。")

    root = Path(args.project_root).resolve()
    runs_dir = root / args.runs_dir
    product_key = str(args.product_key or "").strip()
    target_date = str(args.target_date or "today").strip() or "today"
    concrete_target_date = _concrete_target_date(target_date)
    job_results: list[dict[str, Any]] = []
    total_steps = len(REFRESH_JOBS) + 1

    for index, (job, label, needs_readonly) in enumerate(REFRESH_JOBS, start=1):
        print(f"operation=suggestions_refresh done={index - 1}/{total_steps} status=running", flush=True)
        try:
            result = run_product_automation_job(
                job=job,
                products_dir=root / args.products_dir,
                request_dir=root / args.request_dir,
                runs_dir=runs_dir,
                product_key=product_key,
                target_date=concrete_target_date,
                enable_readonly=bool(needs_readonly),
                execute=False,
                yes=False,
                dry_run=False,
            )
        except Exception as exc:  # noqa: BLE001 - output must preserve the failed fixed step.
            result = _failed_job(job, label, exc)
        result["label"] = label
        job_results.append(result)

    print(f"operation=suggestions_refresh done={len(REFRESH_JOBS)}/{total_steps} status=running", flush=True)
    suggestions_result = build_suggestions_list(
        project_root=root,
        configs_dir=root / "configs",
        runs_dir=runs_dir,
        product_key=product_key,
    )
    job_rows = [_job_row(result, label=str(result.get("label") or result.get("workflow") or "")) for result in job_results]
    failed_count = sum(1 for result in job_results if not bool(result.get("ok", True)))
    external_api_calls = sum(int(result.get("external_api_calls") or 0) for result in job_results)
    suggestion_count = int(_summary_value(suggestions_result, "建议事项") or 0)
    historical_evidence_date = _summary_value(suggestions_result, "历史证据日期") or _summary_value(suggestions_result, "业务数据日期")
    today_patrol_date = _summary_value(suggestions_result, "今日巡检日期")
    suggestions_artifact = str(suggestions_result.get("artifact_path") or "")
    ok = failed_count == 0
    payload = {
        "ok": ok,
        "workflow": "suggestions_refresh",
        "phase": "readonly_sync_and_rule_suggestions",
        "status": "completed" if ok else "failed",
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "execution_enabled": False,
        "external_api_calls": external_api_calls,
        "中文摘要": (
            f"同步数据并重算建议已运行 {len(job_results)} 个固定只读步骤；"
            f"今日巡检日期 {today_patrol_date or '未知'}，历史证据日期 {historical_evidence_date or '未知'}，"
            f"建议 {suggestion_count} 条；不执行真实业务动作。"
        ),
        "summary": {
            "product_key": product_key,
            "target_date": target_date,
            "resolved_target_date": concrete_target_date,
            "job_count": len(job_results),
            "failed_job_count": failed_count,
            "suggestion_count": suggestion_count,
            "business_data_date": historical_evidence_date,
            "historical_evidence_date": historical_evidence_date,
            "today_patrol_date": today_patrol_date,
            "suggestions_artifact_path": suggestions_artifact,
        },
        "blocking_reasons": [
            f"{row['任务']}：{row['问题']}" for row in job_rows if str(row.get("问题") or "").strip()
        ],
        "jobs": job_rows,
        "suggestions_summary": suggestions_result.get("summary", {}),
        "guardrails": [
            "只运行固定只读同步脚本和本地规则建议重算。",
            "不执行创建、删除、暂停、预算、出价或素材绑定等真实业务动作。",
        ],
    }
    payload["artifact_path"] = str(write_run_artifact(runs_dir, "suggestions_refresh", payload))
    print(f"operation=suggestions_refresh done={total_steps}/{total_steps} status=completed", flush=True)
    print(
        json.dumps(
            {
                "ok": payload["ok"],
                "workflow": payload["workflow"],
                "phase": payload["phase"],
                "status": payload["status"],
                "execution_enabled": payload["execution_enabled"],
                "external_api_calls": payload["external_api_calls"],
                "summary": payload["summary"],
                "blocking_reasons": payload["blocking_reasons"],
                "artifact_path": payload["artifact_path"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if ok else 1


def main() -> int:
    return run_from_args()


if __name__ == "__main__":
    raise SystemExit(main())
