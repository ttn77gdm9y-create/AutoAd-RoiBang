from __future__ import annotations

from datetime import datetime
from datetime import timedelta
from datetime import timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from backend.app.services.artifacts import read_json


REGISTRY_PATH = Path("scheduler") / "roibang-v2.jobs.example.json"
STATUS_LOCAL_PATH = Path("scheduler-status.local.json")
STATUS_EXAMPLE_PATH = Path("scheduler-status.example.json")

DEFAULT_TIMEZONE = "Asia/Shanghai"
DAILY_TOLERANCE_MINUTES = 30
HOURLY_TOLERANCE_MINUTES = 90
RUN_MATCH_GRACE_MINUTES = 15

STATUS_LABELS = {
    "ok": "正常",
    "attention": "需关注",
    "overdue": "未按时运行",
    "pending": "待今日运行",
    "missing": "无运行记录",
}

RISK_BY_STATUS = {
    "ok": "low",
    "pending": "low",
    "missing": "medium",
    "attention": "high",
    "overdue": "high",
}

SCOPE_LABELS = {
    "diandian-hero-guojing": "点点英雄-郭靖",
    "diandian-hero-all": "点点英雄全量账户",
}


def build_automation_health_overview(
    *,
    project_root: str | Path,
    configs_dir: str | Path,
    runs_dir: str | Path,
    now: datetime | None = None,
) -> dict[str, Any]:
    root = Path(project_root)
    configs_path = Path(configs_dir)
    runs_path = Path(runs_dir)
    registry = read_json(configs_path / REGISTRY_PATH)
    status_request = _status_request(configs_path)
    timezone_name = str(registry.get("timezone") or _nested(status_request, "scheduler_status", "timezone") or DEFAULT_TIMEZONE)
    tz = ZoneInfo(timezone_name)
    current = (now.astimezone(tz) if now else datetime.now(tz)).replace(microsecond=0)
    enabled_jobs = [job for job in registry.get("jobs", []) if isinstance(job, dict) and bool(job.get("enabled", False))]
    covered_job_ids = _covered_scheduler_status_job_ids(status_request)
    latest_status_payload, latest_status_path = _latest_json_payload(runs_path / "scheduler_status")

    job_states = [
        _build_job_state(
            job,
            current=current,
            tz=tz,
            root=root,
            runs_dir=runs_path,
            covered_job_ids=covered_job_ids,
        )
        for job in enabled_jobs
    ]
    job_rows = [_job_table_row(state) for state in job_states]
    issue_rows = _issue_rows(job_states)
    product_rows = _product_rows(job_states)
    artifact_rows = _artifact_rows(job_states)
    warning_rows = [state for state in job_states if not state["scheduler_status_covered"] and not state["is_scheduler_status_job"]]
    coverable_jobs = [state for state in job_states if not state["is_scheduler_status_job"]]
    covered_count = sum(1 for state in coverable_jobs if state["scheduler_status_covered"])
    status_counts = _status_counts(job_states)
    risk_level = _overall_risk(job_states)
    warnings = _warnings(warning_rows, latest_status_payload)

    return {
        "summary": {
            "title": "每日自动化健康看板",
            "status": "loaded",
            "risk_level": risk_level,
            "execution_enabled": False,
            "items": [
                {"label": "检查时间", "value": _format_local(current)},
                {"label": "启用任务", "value": len(job_states)},
                {"label": "今日正常", "value": status_counts["ok"]},
                {"label": "需关注", "value": status_counts["attention"]},
                {"label": "未按时运行", "value": status_counts["overdue"]},
                {"label": "待今日运行", "value": status_counts["pending"]},
                {"label": "日报覆盖", "value": f"{covered_count}/{len(coverable_jobs)}"},
                {"label": "06:00 日报", "value": _status_report_label(latest_status_payload)},
            ],
            "warnings": warnings,
            "blocking_reasons": [],
        },
        "table": {
            "columns": [
                "任务",
                "计划时间",
                "今日状态",
                "调度结果",
                "业务结果",
                "最近运行",
                "今日运行",
                "日报检查",
                "问题摘要",
            ],
            "rows": job_rows,
        },
        "sections": [
            {
                "title": "异常与待处理",
                "table": {
                    "columns": ["任务", "状态", "问题", "调度产物", "业务产物"],
                    "rows": issue_rows,
                },
            },
            {
                "title": "产品与范围结果",
                "table": {
                    "columns": ["任务", "产品", "范围", "结果", "业务摘要", "结果文件"],
                    "rows": product_rows,
                },
            },
            {
                "title": "调度产物",
                "table": {
                    "columns": ["任务", "最近调度产物", "业务产物", "退出码", "耗时秒"],
                    "rows": artifact_rows,
                },
            },
        ],
        "artifact_path": str(latest_status_path or ""),
        "raw": {
            "checked_at": current.isoformat(),
            "registry_path": str(configs_path / REGISTRY_PATH),
            "scheduler_status_request_path": _status_request_path(configs_path),
            "scheduler_status_artifact_path": str(latest_status_path or ""),
            "scheduler_status_summary": latest_status_payload.get("summary", {}),
            "scheduler_status_message": str(latest_status_payload.get("message") or ""),
            "jobs": job_states,
        },
    }


def _build_job_state(
    job: dict[str, Any],
    *,
    current: datetime,
    tz: ZoneInfo,
    root: Path,
    runs_dir: Path,
    covered_job_ids: set[str],
) -> dict[str, Any]:
    job_id = _text(job.get("id"))
    scheduler_results = _scheduler_results(runs_dir / "scheduler" / job_id, tz=tz)
    latest_scheduler = scheduler_results[-1] if scheduler_results else {}
    today_results = [result for result in scheduler_results if _same_local_day(result.get("started_at"), current)]
    latest_today = today_results[-1] if today_results else {}
    expected_times = _schedule_times_today(job, current)
    tolerance_minutes = HOURLY_TOLERANCE_MINUTES if len(expected_times) > 1 else DAILY_TOLERANCE_MINUTES
    due_times = [time for time in expected_times if current >= time + timedelta(minutes=tolerance_minutes)]
    latest_due_time = due_times[-1] if due_times else None
    business = _business_result(root, latest_scheduler)
    issues = _issues(latest_scheduler, business)
    is_scheduler_status_job = job_id == "roibang-scheduler-status" or _text(job.get("category")) == "scheduler_status"
    covered = job_id in covered_job_ids
    status = _today_status(
        latest_today=latest_today,
        latest_scheduler=latest_scheduler,
        business=business,
        issues=issues,
        latest_due_time=latest_due_time,
        current=current,
    )
    schedule = job.get("schedule") if isinstance(job.get("schedule"), dict) else {}
    return {
        "job_id": job_id,
        "job_name": _text(job.get("name")) or job_id,
        "category": _text(job.get("category")),
        "schedule_expr": _text(schedule.get("expr")),
        "schedule_tz": _text(schedule.get("tz")) or DEFAULT_TIMEZONE,
        "schedule_label": _schedule_label(schedule),
        "status": status,
        "status_label": STATUS_LABELS.get(status, status),
        "risk_level": RISK_BY_STATUS.get(status, "medium"),
        "issues": issues,
        "is_scheduler_status_job": is_scheduler_status_job,
        "scheduler_status_covered": covered,
        "scheduler_status_label": "自检任务" if is_scheduler_status_job else ("已覆盖" if covered else "未覆盖"),
        "expected_times_today": [_format_local(time) for time in expected_times],
        "latest_due_time": _format_local(latest_due_time) if latest_due_time else "",
        "today_run_count": len(today_results),
        "latest_scheduler": _public_scheduler_result(latest_scheduler),
        "business_result": business,
        "product_results": _product_results(business),
    }


def _today_status(
    *,
    latest_today: dict[str, Any],
    latest_scheduler: dict[str, Any],
    business: dict[str, Any],
    issues: list[str],
    latest_due_time: datetime | None,
    current: datetime,
) -> str:
    if latest_due_time and not _latest_run_covers_due_time(latest_today, latest_due_time):
        return "overdue"
    if latest_today:
        return "attention" if issues else "ok"
    if latest_scheduler and issues:
        return "attention"
    if latest_due_time:
        return "overdue"
    if not latest_scheduler:
        return "pending" if not _has_any_due_window(current, latest_due_time) else "missing"
    if business.get("exists"):
        return "pending"
    return "pending"


def _has_any_due_window(_current: datetime, latest_due_time: datetime | None) -> bool:
    return latest_due_time is not None


def _latest_run_covers_due_time(latest_today: dict[str, Any], latest_due_time: datetime) -> bool:
    if not latest_today:
        return False
    started_at = latest_today.get("started_at")
    if not isinstance(started_at, datetime):
        return False
    return started_at >= latest_due_time - timedelta(minutes=RUN_MATCH_GRACE_MINUTES)


def _issues(latest_scheduler: dict[str, Any], business: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    if latest_scheduler:
        script = latest_scheduler.get("script") if isinstance(latest_scheduler.get("script"), dict) else {}
        exit_code = script.get("exit_code")
        if exit_code not in (None, "", 0, "0"):
            issues.append(f"调度脚本退出码 {exit_code}")
        for violation in latest_scheduler.get("violations") or []:
            issues.append(str(violation))
        if not bool(latest_scheduler.get("ok", False)) and not issues:
            issues.append("调度产物标记失败")
        contract = latest_scheduler.get("artifact_contract") if isinstance(latest_scheduler.get("artifact_contract"), dict) else {}
        if contract and not bool(contract.get("ok", False)):
            issues.extend(str(item) for item in contract.get("violations", []) if str(item).strip())
    if business.get("exists") and not bool(business.get("ok", False)):
        issues.append("业务产物标记失败")
    if not business.get("exists") and latest_scheduler:
        issues.append("未找到业务产物")
    for failed in business.get("failed_results") or []:
        product = _text(failed.get("product")) or "未知产品"
        scope = _scope_label(_text(failed.get("scope_id")))
        error = _short_error(_text(failed.get("error")) or _text(failed.get("stderr")))
        suffix = f"：{error}" if error else ""
        issues.append(f"{product}{f' {scope}' if scope else ''}失败{suffix}")
    return _unique_texts(issues)


def _business_result(root: Path, scheduler_result: dict[str, Any]) -> dict[str, Any]:
    contract = scheduler_result.get("artifact_contract") if isinstance(scheduler_result.get("artifact_contract"), dict) else {}
    artifact_path_text = _text(contract.get("artifact_path"))
    artifact_path = _resolve_path(root, artifact_path_text)
    payload = read_json(artifact_path) if artifact_path else {}
    failed_results = _failed_product_results(payload)
    ok = bool(payload.get("ok", contract.get("ok", False))) and not failed_results
    return {
        "exists": bool(payload),
        "ok": ok,
        "workflow": _text(payload.get("workflow") or contract.get("workflow")),
        "status": _text(payload.get("status")),
        "artifact_path": str(artifact_path or artifact_path_text),
        "summary": payload.get("summary") if isinstance(payload.get("summary"), dict) else {},
        "failed_results": failed_results,
        "payload": payload,
    }


def _failed_product_results(payload: dict[str, Any]) -> list[dict[str, Any]]:
    failed: list[dict[str, Any]] = []
    for row in payload.get("results") or []:
        if not isinstance(row, dict):
            continue
        parsed = row.get("parsed_stdout") if isinstance(row.get("parsed_stdout"), dict) else {}
        row_ok = bool(row.get("ok", True)) and row.get("return_code", 0) in (None, "", 0, "0")
        if parsed:
            row_ok = row_ok and bool(parsed.get("ok", True))
        if row_ok:
            continue
        failed.append(
            {
                "product": _text(row.get("product")),
                "product_key": _text(row.get("product_key")),
                "scope_id": _text(row.get("scope_id")),
                "return_code": row.get("return_code", ""),
                "stderr": _text(row.get("stderr")),
                "error": _text(parsed.get("error") or parsed.get("message")),
            }
        )
    return failed


def _product_results(business: dict[str, Any]) -> list[dict[str, Any]]:
    payload = business.get("payload") if isinstance(business.get("payload"), dict) else {}
    rows = payload.get("results") if isinstance(payload.get("results"), list) else []
    result_rows: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        parsed = row.get("parsed_stdout") if isinstance(row.get("parsed_stdout"), dict) else {}
        summary = parsed.get("summary") if isinstance(parsed.get("summary"), dict) else {}
        if not summary and isinstance(row.get("summary"), dict):
            summary = row["summary"]
        row_ok = bool(row.get("ok", True)) and row.get("return_code", 0) in (None, "", 0, "0")
        if parsed:
            row_ok = row_ok and bool(parsed.get("ok", True))
        result_rows.append(
            {
                "product": _text(row.get("product")) or "未知产品",
                "product_key": _text(row.get("product_key")),
                "scope_id": _text(row.get("scope_id")),
                "job": _text(row.get("job")),
                "ok": row_ok,
                "return_code": row.get("return_code", ""),
                "summary": summary,
                "artifact_path": _text(parsed.get("artifact_path") or row.get("artifact_path") or business.get("artifact_path")),
                "stderr": _short_error(_text(row.get("stderr"))),
            }
        )
    return result_rows


def _job_table_row(state: dict[str, Any]) -> dict[str, Any]:
    latest_scheduler = state.get("latest_scheduler") if isinstance(state.get("latest_scheduler"), dict) else {}
    business = state.get("business_result") if isinstance(state.get("business_result"), dict) else {}
    return {
        "任务": state["job_name"],
        "计划时间": state["schedule_label"],
        "今日状态": state["status_label"],
        "调度结果": _ok_label(latest_scheduler.get("ok"), missing_label="无记录"),
        "业务结果": _ok_label(business.get("ok"), missing_label="无产物") if business.get("exists") else "无产物",
        "最近运行": latest_scheduler.get("started_at_text") or "无",
        "今日运行": state["today_run_count"],
        "日报检查": state["scheduler_status_label"],
        "问题摘要": "；".join(state["issues"][:2]) if state["issues"] else "无",
    }


def _issue_rows(job_states: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for state in job_states:
        if state["status"] not in {"attention", "overdue", "missing"} and not state["issues"]:
            continue
        issues = state["issues"] or [state["status_label"]]
        for issue in issues:
            business = state.get("business_result") if isinstance(state.get("business_result"), dict) else {}
            scheduler = state.get("latest_scheduler") if isinstance(state.get("latest_scheduler"), dict) else {}
            rows.append(
                {
                    "任务": state["job_name"],
                    "状态": state["status_label"],
                    "问题": issue,
                    "调度产物": scheduler.get("path") or "",
                    "业务产物": business.get("artifact_path") or "",
                }
            )
    return rows


def _product_rows(job_states: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for state in job_states:
        for result in state.get("product_results") or []:
            rows.append(
                {
                    "任务": state["job_name"],
                    "产品": result["product"],
                    "范围": _scope_label(result.get("scope_id")) or result.get("product_key") or "产品默认范围",
                    "结果": "正常" if result.get("ok") else "失败",
                    "业务摘要": _format_product_summary(result),
                    "结果文件": result.get("artifact_path") or "",
                }
            )
    return rows


def _artifact_rows(job_states: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for state in job_states:
        scheduler = state.get("latest_scheduler") if isinstance(state.get("latest_scheduler"), dict) else {}
        business = state.get("business_result") if isinstance(state.get("business_result"), dict) else {}
        script = scheduler.get("script") if isinstance(scheduler.get("script"), dict) else {}
        rows.append(
            {
                "任务": state["job_name"],
                "最近调度产物": scheduler.get("path") or "",
                "业务产物": business.get("artifact_path") or "",
                "退出码": script.get("exit_code", ""),
                "耗时秒": scheduler.get("duration_seconds", ""),
            }
        )
    return rows


def _format_product_summary(result: dict[str, Any]) -> str:
    job = _text(result.get("job"))
    summary = result.get("summary") if isinstance(result.get("summary"), dict) else {}
    if not result.get("ok"):
        error = _text(result.get("stderr"))
        return f"失败，{error}" if error else "失败，请查看调度产物"
    if job == "material_daily_sync":
        return (
            f"活跃账户 {summary.get('active_account_count', 0)} 个，"
            f"导入素材行 {summary.get('material_rows_imported', 0)}，"
            f"接口调用 {summary.get('material_fetch_transport_calls', 0)} 次"
        )
    if job == "operation_log_sync":
        return (
            f"计划账户 {summary.get('planned_request_count', 0)} 个，"
            f"导入日志 {summary.get('operation_logs_imported', 0)} 条，"
            f"接口调用 {summary.get('transport_calls', summary.get('external_api_calls', 0))} 次"
        )
    if job == "daily_report_sync":
        return (
            f"发现账户 {summary.get('active_accounts_discovered', 0)} 个，"
            f"写入快照 {summary.get('snapshots_written', 0)} 条，"
            f"接口调用 {summary.get('transport_calls', summary.get('external_api_calls', 0))} 次"
        )
    if job == "source_material_auto_push":
        return (
            f"新增素材 {summary.get('new_material_count', 0)} 个，"
            f"已推视频 {summary.get('pushed_video_count', 0)} 个，"
            f"失败批次 {summary.get('failed_batch_count', 0)}"
        )
    if job == "source_material_preload":
        return (
            f"目标账户 {summary.get('target_account_count', 0)} 个，"
            f"计划推送 {summary.get('planned_bind_material_count', 0)} 条，"
            f"已推 {summary.get('executed_bind_material_count', 0)} 条，"
            f"失败批次 {summary.get('failed_batch_count', 0)}"
        )
    if job == "source_material_rollup":
        return (
            f"源素材 {summary.get('source_material_count', 0)} 个，"
            f"写入汇总 {summary.get('rollup_rows_written', 0)} 行，"
            f"映射回填 {summary.get('material_source_mappings_backfilled', 0)} 条"
        )
    if job == "delivery_patrol":
        return (
            f"账户 {summary.get('account_count', summary.get('accounts', 0))} 个，"
            f"项目 {summary.get('project_count', summary.get('projects', 0))} 个，"
            f"单元 {summary.get('promotion_count', summary.get('promotions', 0))} 个，"
            f"重点关注 {summary.get('attention_count', 0)}，"
            f"建议 {summary.get('suggestion_count', 0)}"
        )
    return f"任务 {job or '未知'} 已完成"


def _warnings(warning_rows: list[dict[str, Any]], latest_status_payload: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    if warning_rows:
        names = "、".join(row["job_name"] for row in warning_rows[:4])
        suffix = "等" if len(warning_rows) > 4 else ""
        warnings.append(f"{len(warning_rows)} 个启用任务未纳入 06:00 定时任务日报检查：{names}{suffix}。")
    if not latest_status_payload:
        warnings.append("未找到 06:00 定时任务日报产物；页面仍会基于 scheduler 产物展示最近运行状态。")
    else:
        summary = latest_status_payload.get("summary") if isinstance(latest_status_payload.get("summary"), dict) else {}
        expected_date = _text(summary.get("expected_data_date"))
        report_date = _text(summary.get("report_date"))
        if report_date or expected_date:
            warnings.append(f"06:00 定时任务日报口径：报告日期 {report_date or '未知'}，数据应到 {expected_date or '未知'}。")
    return warnings


def _overall_risk(job_states: list[dict[str, Any]]) -> str:
    statuses = {state.get("status") for state in job_states}
    if statuses & {"attention", "overdue"}:
        return "high"
    if statuses & {"missing"}:
        return "medium"
    return "low"


def _status_counts(job_states: list[dict[str, Any]]) -> dict[str, int]:
    counts = {key: 0 for key in STATUS_LABELS}
    for state in job_states:
        status = str(state.get("status") or "")
        counts[status] = counts.get(status, 0) + 1
    return counts


def _status_report_label(payload: dict[str, Any]) -> str:
    if not payload:
        return "暂无"
    return "正常" if bool(payload.get("ok")) else "需关注"


def _ok_label(value: Any, *, missing_label: str) -> str:
    if value is None:
        return missing_label
    return "成功" if bool(value) else "失败"


def _public_scheduler_result(result: dict[str, Any]) -> dict[str, Any]:
    if not result:
        return {}
    return {
        "ok": bool(result.get("ok")),
        "path": _text(result.get("path")),
        "started_at": result.get("started_at").isoformat() if isinstance(result.get("started_at"), datetime) else "",
        "started_at_text": _format_local(result.get("started_at")) if isinstance(result.get("started_at"), datetime) else "",
        "finished_at": result.get("finished_at").isoformat() if isinstance(result.get("finished_at"), datetime) else "",
        "duration_seconds": result.get("duration_seconds", ""),
        "script": result.get("script") if isinstance(result.get("script"), dict) else {},
        "violations": [str(item) for item in result.get("violations", [])],
        "artifact_contract": result.get("artifact_contract") if isinstance(result.get("artifact_contract"), dict) else {},
    }


def _scheduler_results(directory: Path, *, tz: ZoneInfo) -> list[dict[str, Any]]:
    candidates = sorted(path for path in directory.glob("*.json") if path.name != "latest.json") if directory.exists() else []
    results: list[dict[str, Any]] = []
    for path in candidates:
        payload = read_json(path)
        if not payload:
            continue
        started_at = _parse_datetime(payload.get("started_at"), tz) or _datetime_from_artifact_name(path, tz)
        finished_at = _parse_datetime(payload.get("finished_at"), tz)
        results.append(
            {
                **payload,
                "path": str(path),
                "started_at": started_at,
                "finished_at": finished_at,
            }
        )
    return sorted(results, key=lambda result: result.get("started_at") or datetime.min.replace(tzinfo=tz))


def _latest_json_payload(directory: Path) -> tuple[dict[str, Any], Path | None]:
    if not directory.exists():
        return {}, None
    candidates = sorted(path for path in directory.glob("*.json") if path.name != "latest.json")
    if candidates:
        path = candidates[-1]
        return read_json(path), path
    latest = directory / "latest.json"
    if latest.exists():
        return read_json(latest), latest
    return {}, None


def _schedule_times_today(job: dict[str, Any], current: datetime) -> list[datetime]:
    schedule = job.get("schedule") if isinstance(job.get("schedule"), dict) else {}
    expr = _text(schedule.get("expr"))
    parts = expr.split()
    if len(parts) != 5:
        return []
    minute_text, hour_text, day_text, month_text, weekday_text = parts
    if day_text != "*" or month_text != "*" or weekday_text != "*":
        return []
    minutes = _minute_values(minute_text)
    hours = _hour_values(hour_text)
    return sorted(current.replace(hour=hour, minute=minute, second=0, microsecond=0) for hour in hours for minute in minutes)


def _minute_values(text: str) -> list[int]:
    if text.isdigit():
        value = int(text)
        return [value] if 0 <= value <= 59 else []
    if text.startswith("*/") and text[2:].isdigit():
        step = int(text[2:])
        if step <= 0:
            return []
        return list(range(0, 60, step))
    return []


def _hour_values(text: str) -> list[int]:
    if text.isdigit():
        value = int(text)
        return [value] if 0 <= value <= 23 else []
    if text == "*":
        return list(range(24))
    if "-" in text:
        start_text, _, end_text = text.partition("-")
        if start_text.isdigit() and end_text.isdigit():
            start = int(start_text)
            end = int(end_text)
            if 0 <= start <= end <= 23:
                return list(range(start, end + 1))
    return []


def _schedule_label(schedule: dict[str, Any]) -> str:
    expr = _text(schedule.get("expr"))
    parts = expr.split()
    if len(parts) != 5:
        return expr or "未配置"
    minute, hour, day, month, weekday = parts
    if day != "*" or month != "*" or weekday != "*":
        return expr
    if hour.isdigit() and minute.isdigit():
        return f"每天 {int(hour):02d}:{int(minute):02d}"
    if "-" in hour and minute.isdigit():
        start, _, end = hour.partition("-")
        if start.isdigit() and end.isdigit():
            return f"每天 {int(start):02d}:{int(minute):02d}-{int(end):02d}:{int(minute):02d}"
    return expr


def _status_request(configs_path: Path) -> dict[str, Any]:
    local = configs_path / STATUS_LOCAL_PATH
    if local.exists():
        return read_json(local)
    return read_json(configs_path / STATUS_EXAMPLE_PATH)


def _status_request_path(configs_path: Path) -> str:
    local = configs_path / STATUS_LOCAL_PATH
    return str(local if local.exists() else configs_path / STATUS_EXAMPLE_PATH)


def _covered_scheduler_status_job_ids(status_request: dict[str, Any]) -> set[str]:
    cfg = status_request.get("scheduler_status") if isinstance(status_request.get("scheduler_status"), dict) else {}
    jobs = cfg.get("jobs") if isinstance(cfg.get("jobs"), list) else []
    return {_text(job.get("job_id")) for job in jobs if isinstance(job, dict) and _text(job.get("job_id"))}


def _resolve_path(root: Path, path_text: str) -> Path | None:
    if not path_text:
        return None
    path = Path(path_text)
    return path if path.is_absolute() else root / path


def _parse_datetime(value: Any, tz: ZoneInfo) -> datetime | None:
    text = _text(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(tz)


def _datetime_from_artifact_name(path: Path, tz: ZoneInfo) -> datetime | None:
    stem = path.stem.removesuffix("-001")
    try:
        parsed = datetime.strptime(stem[:16], "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return parsed.astimezone(tz)


def _same_local_day(value: Any, current: datetime) -> bool:
    return isinstance(value, datetime) and value.date() == current.date()


def _nested(payload: dict[str, Any], *keys: str) -> Any:
    current: Any = payload
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _scope_label(scope_id: Any) -> str:
    text = _text(scope_id)
    return SCOPE_LABELS.get(text, text)


def _short_error(error: str) -> str:
    text = " ".join(error.strip().split())
    if not text:
        return ""
    marker = "RuntimeError:"
    if marker in text:
        text = text.split(marker, 1)[1].strip()
    return text[:160]


def _format_local(value: datetime | None) -> str:
    if not isinstance(value, datetime):
        return ""
    return value.strftime("%Y-%m-%d %H:%M:%S")


def _text(value: Any) -> str:
    return str(value or "").strip()


def _unique_texts(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = _text(value)
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result
