from __future__ import annotations

import json
import sqlite3
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from roibang_v2.runs import write_latest_artifact
from roibang_v2.runs import write_run_artifact
from roibang_v2.workflows.create_suggestion_lifecycle import build_create_suggestion_lifecycle


CREATE_ACTION = "suggest_create_project"

PROJECT_ACTIONS = {
    "suggest_close_project",
    "suggest_delete_project",
    "suggest_lower_budget",
    "suggest_lower_bid",
    "pause_project",
    "adjust_project_budget",
    "adjust_project_bid",
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _number(value: Any) -> float:
    try:
        if value in (None, ""):
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _rows(value: Any) -> list[dict[str, Any]]:
    return [dict(item) for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _load_json(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ? LIMIT 1",
        (table,),
    ).fetchone()
    return row is not None


def _date(value: str) -> date:
    return date.fromisoformat(value[:10])


def _after_window(target_date: str, lookahead_days: int) -> tuple[str, str]:
    start = _date(target_date) + timedelta(days=1)
    end = _date(target_date) + timedelta(days=max(lookahead_days, 1))
    return start.isoformat(), end.isoformat()


def _suggestion_target_date(suggestion: dict[str, Any], artifact: dict[str, Any]) -> str:
    return _text(suggestion.get("target_date")) or _text(artifact.get("summary", {}).get("target_date"))


def _suggestion_action(suggestion: dict[str, Any]) -> str:
    return _text(suggestion.get("suggested_action") or suggestion.get("suggestion_type"))


def _project_metrics(
    conn: sqlite3.Connection,
    *,
    advertiser_id: str,
    project_id: str,
    start_date: str,
    end_date: str,
) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT
          COUNT(DISTINCT metric_date) AS active_days,
          COALESCE(SUM(stat_cost), 0) AS stat_cost,
          COALESCE(SUM(convert_cnt), 0) AS convert_cnt,
          CASE
            WHEN COALESCE(SUM(stat_cost), 0) > 0
            THEN COALESCE(SUM(stat_cost * roi_1day), 0) / COALESCE(SUM(stat_cost), 0)
            ELSE 0
          END AS roi_1day
        FROM material_daily_metrics
        WHERE advertiser_id = ?
          AND project_id = ?
          AND metric_date >= ?
          AND metric_date <= ?
        """,
        (advertiser_id, project_id, start_date, end_date),
    ).fetchone()
    if row is None:
        return {"active_days": 0, "stat_cost": 0.0, "convert_cnt": 0.0, "roi_1day": 0.0}
    return {
        "active_days": int(row["active_days"] or 0),
        "stat_cost": round(float(row["stat_cost"] or 0), 4),
        "convert_cnt": round(float(row["convert_cnt"] or 0), 4),
        "roi_1day": round(float(row["roi_1day"] or 0), 6),
    }


def _project_metrics_for_ids(
    conn: sqlite3.Connection,
    *,
    advertiser_id: str,
    project_ids: list[str],
    start_date: str,
    end_date: str,
) -> dict[str, Any]:
    project_ids = _unique(project_ids)
    if not project_ids or not _table_exists(conn, "material_daily_metrics"):
        return {"active_days": 0, "stat_cost": 0.0, "convert_cnt": 0.0, "roi_1day": 0.0}
    placeholders = ", ".join("?" for _ in project_ids)
    row = conn.execute(
        f"""
        SELECT
          COUNT(DISTINCT metric_date) AS active_days,
          COALESCE(SUM(stat_cost), 0) AS stat_cost,
          COALESCE(SUM(convert_cnt), 0) AS convert_cnt,
          CASE
            WHEN COALESCE(SUM(stat_cost), 0) > 0
            THEN COALESCE(SUM(stat_cost * roi_1day), 0) / COALESCE(SUM(stat_cost), 0)
            ELSE 0
          END AS roi_1day
        FROM material_daily_metrics
        WHERE advertiser_id = ?
          AND project_id IN ({placeholders})
          AND metric_date >= ?
          AND metric_date <= ?
        """,
        (advertiser_id, *project_ids, start_date, end_date),
    ).fetchone()
    if row is None:
        return {"active_days": 0, "stat_cost": 0.0, "convert_cnt": 0.0, "roi_1day": 0.0}
    return {
        "active_days": int(row["active_days"] or 0),
        "stat_cost": round(float(row["stat_cost"] or 0), 4),
        "convert_cnt": round(float(row["convert_cnt"] or 0), 4),
        "roi_1day": round(float(row["roi_1day"] or 0), 6),
    }


def _max_metric_date(conn: sqlite3.Connection) -> str:
    if not _table_exists(conn, "material_daily_metrics"):
        return ""
    row = conn.execute("SELECT MAX(metric_date) AS max_metric_date FROM material_daily_metrics").fetchone()
    return _text(row["max_metric_date"] if row is not None else "")


def _operation_after(
    conn: sqlite3.Connection,
    *,
    advertiser_id: str,
    project_id: str,
    target_date: str,
    action: str,
) -> dict[str, Any]:
    keywords = {
        "suggest_close_project": ["启用 -> 暂停", "暂停"],
        "pause_project": ["启用 -> 暂停", "暂停"],
        "suggest_delete_project": ["删除"],
        "suggest_lower_budget": ["预算"],
        "adjust_project_budget": ["预算"],
        "suggest_lower_bid": ["出价"],
        "adjust_project_bid": ["出价"],
    }.get(action, [])
    if not keywords:
        return {"found": False, "samples": []}
    rows = conn.execute(
        """
        SELECT occurred_at, action, detail
        FROM operation_logs
        WHERE advertiser_id = ?
          AND entity_type = 'project'
          AND entity_id = ?
          AND occurred_at >= ?
        ORDER BY occurred_at ASC
        LIMIT 20
        """,
        (advertiser_id, project_id, f"{target_date} 00:00:00"),
    ).fetchall()
    samples = [
        {"occurred_at": row["occurred_at"], "action": row["action"], "detail": row["detail"]}
        for row in rows
        if any(keyword in f"{row['action']} {row['detail']}" for keyword in keywords)
    ]
    return {"found": bool(samples), "samples": samples[:3]}


def _today_metrics(suggestion: dict[str, Any]) -> dict[str, Any]:
    metrics = suggestion.get("metrics") if isinstance(suggestion.get("metrics"), dict) else {}
    today = metrics.get("today") if isinstance(metrics.get("today"), dict) else {}
    return dict(today)


def _unique(values: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _text(value)
        if text and text not in seen:
            output.append(text)
            seen.add(text)
    return output


def _resolve_path(project_root: str | Path, path_text: str) -> Path:
    path = Path(path_text)
    return path if path.is_absolute() else Path(project_root) / path


def _plan_id_from_payload(payload: dict[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    operation_record = payload.get("operation_record") if isinstance(payload.get("operation_record"), dict) else {}
    result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
    details = payload.get("details") if isinstance(payload.get("details"), dict) else {}
    request = payload.get("create_plan_request") if isinstance(payload.get("create_plan_request"), dict) else {}
    return _text(
        payload.get("plan_id")
        or summary.get("plan_id")
        or operation_record.get("plan_id")
        or result.get("plan_id")
        or details.get("plan_id")
        or request.get("plan_id")
    )


def _load_plan_id_from_path(project_root: str | Path, path_text: str) -> str:
    if not _text(path_text):
        return ""
    try:
        return _plan_id_from_payload(_load_json(_resolve_path(project_root, path_text)))
    except (FileNotFoundError, json.JSONDecodeError, ValueError):
        return ""


def _plan_ids_from_lifecycle_record(project_root: str | Path, lifecycle_record: dict[str, Any]) -> list[str]:
    plan_ids: list[str] = []
    for key in ["execution_review_path", "plan_preview_path"]:
        plan_ids.append(_load_plan_id_from_path(project_root, _text(lifecycle_record.get(key))))
    for event in _rows(lifecycle_record.get("events")):
        plan_ids.append(_load_plan_id_from_path(project_root, _text(event.get("path"))))
    return _unique(plan_ids)


def _created_project_records(
    conn: sqlite3.Connection,
    *,
    plan_ids: list[str],
    advertiser_id: str,
) -> list[dict[str, Any]]:
    plan_ids = _unique(plan_ids)
    if not plan_ids or not _table_exists(conn, "create_provider_id_ledger"):
        return []
    placeholders = ", ".join("?" for _ in plan_ids)
    params: list[Any] = [*plan_ids]
    advertiser_clause = ""
    if advertiser_id:
        advertiser_clause = "AND advertiser_id = ?"
        params.append(advertiser_id)
    rows = conn.execute(
        f"""
        SELECT local_key, provider_id, plan_id, request_id, advertiser_id, status, source_workflow
        FROM create_provider_id_ledger
        WHERE entity_type = 'project'
          AND plan_id IN ({placeholders})
          {advertiser_clause}
          AND provider_id <> ''
          AND provider_id NOT LIKE 'mock_%'
          AND status = 'active'
        ORDER BY advertiser_id, plan_id, local_key, provider_id
        """,
        params,
    ).fetchall()
    return [dict(row) for row in rows]


def _create_lifecycle_label(lifecycle_record: dict[str, Any]) -> str:
    return _text(lifecycle_record.get("lifecycle_label")) or "未处理"


def _evaluate_create_suggestion(
    conn: sqlite3.Connection,
    suggestion: dict[str, Any],
    *,
    artifact: dict[str, Any],
    lookahead_days: int,
    max_metric_date: str,
    lifecycle_record: dict[str, Any],
    project_root: str | Path,
) -> dict[str, Any] | None:
    suggestion_id = _text(suggestion.get("suggestion_id"))
    target_date = _suggestion_target_date(suggestion, artifact)
    advertiser_id = _text(suggestion.get("advertiser_id"))
    if not suggestion_id or not target_date or not advertiser_id:
        return None
    start_date, end_date = _after_window(target_date, lookahead_days)
    lifecycle_status = _text(lifecycle_record.get("lifecycle_status")) or "unprocessed"
    plan_ids = _plan_ids_from_lifecycle_record(project_root, lifecycle_record)
    created_projects = _created_project_records(conn, plan_ids=plan_ids, advertiser_id=advertiser_id)
    project_ids = _unique([_text(row.get("provider_id")) for row in created_projects])
    after_metrics = (
        _project_metrics_for_ids(
            conn,
            advertiser_id=advertiser_id,
            project_ids=project_ids,
            start_date=start_date,
            end_date=end_date,
        )
        if project_ids
        else {"active_days": 0, "stat_cost": 0.0, "convert_cnt": 0.0, "roi_1day": 0.0}
    )

    status = "create_not_adopted"
    reason = "创建建议尚未进入创建计划预览，视为未采纳。"
    if lifecycle_status in {"plan_previewed", "plan_split_required"}:
        status = "create_plan_previewed"
        reason = "创建建议已生成计划预览，但还没有提交真实执行。"
    elif lifecycle_status in {"reviewed_ready", "reviewed_warning"}:
        status = "create_reviewed_not_submitted"
        reason = "创建计划已完成执行前复核，但还没有提交真实执行。"
    elif lifecycle_status == "reviewed_blocked":
        status = "create_review_blocked"
        reason = "执行前复核发现阻断项，创建建议不能直接视为有效。"
    elif lifecycle_status == "execution_failed":
        status = "create_execution_failed"
        reason = "创建建议已进入真实执行链路，但执行结果失败，需要人工复核。"
    elif lifecycle_status in {"execution_submitted", "execution_completed"}:
        if not project_ids:
            status = "create_execution_evidence_missing" if lifecycle_status == "execution_completed" else "create_adopted_pending_result"
            reason = (
                "创建执行产物显示已完成，但本地创建台账里没有找到新项目 ID。"
                if lifecycle_status == "execution_completed"
                else "创建任务已提交，本地创建台账尚未记录新项目 ID。"
            )
        elif max_metric_date and max_metric_date < end_date:
            status = "create_adopted_pending_future_data"
            reason = "创建建议已采纳并记录新项目，但本地数据还没有覆盖完整后续观察窗口。"
        elif after_metrics["active_days"] <= 0:
            status = "create_adopted_no_future_data"
            reason = "创建建议已采纳并记录新项目，但后续观察窗口没有项目投放数据。"
        else:
            status = "create_adopted_with_future_data"
            reason = "创建建议已采纳并记录新项目，后续观察窗口已有投放表现数据。"

    return {
        "suggestion_id": suggestion_id,
        "suggested_action": CREATE_ACTION,
        "advertiser_id": advertiser_id,
        "project_id": "、".join(project_ids),
        "project_ids": project_ids,
        "project_name": "",
        "target_date": target_date,
        "after_window": {"start_date": start_date, "end_date": end_date},
        "evaluation_status": status,
        "evaluation_reason": reason,
        "before_metrics": _today_metrics(suggestion),
        "after_metrics": after_metrics,
        "operation_after": {"found": False, "samples": []},
        "create_lifecycle": lifecycle_record,
        "create_lifecycle_status": lifecycle_status,
        "create_lifecycle_label": _create_lifecycle_label(lifecycle_record),
        "plan_preview_path": _text(lifecycle_record.get("plan_preview_path")),
        "execution_review_path": _text(lifecycle_record.get("execution_review_path")),
        "execution_task_id": _text(lifecycle_record.get("execution_task_id")),
        "plan_ids": plan_ids,
        "created_projects": created_projects,
        "created_project_count": len(project_ids),
    }


def _evaluate_suggestion(
    conn: sqlite3.Connection,
    suggestion: dict[str, Any],
    *,
    artifact: dict[str, Any],
    lookahead_days: int,
    max_after_stat_cost: float,
    max_after_convert_cnt: float,
    max_metric_date: str,
    lifecycle_by_id: dict[str, Any],
    project_root: str | Path,
) -> dict[str, Any] | None:
    action = _suggestion_action(suggestion)
    if action == CREATE_ACTION:
        lifecycle_record = lifecycle_by_id.get(_text(suggestion.get("suggestion_id")))
        lifecycle_record = lifecycle_record if isinstance(lifecycle_record, dict) else {}
        return _evaluate_create_suggestion(
            conn,
            suggestion,
            artifact=artifact,
            lookahead_days=lookahead_days,
            max_metric_date=max_metric_date,
            lifecycle_record=lifecycle_record,
            project_root=project_root,
        )
    if action not in PROJECT_ACTIONS or _text(suggestion.get("entity_type")) != "project":
        return None
    target_date = _suggestion_target_date(suggestion, artifact)
    advertiser_id = _text(suggestion.get("advertiser_id"))
    project_id = _text(suggestion.get("project_id") or suggestion.get("entity_id"))
    if not target_date or not advertiser_id or not project_id:
        return None
    start_date, end_date = _after_window(target_date, lookahead_days)
    if max_metric_date and max_metric_date < end_date:
        return {
            "suggestion_id": _text(suggestion.get("suggestion_id")),
            "suggested_action": action,
            "advertiser_id": advertiser_id,
            "project_id": project_id,
            "project_name": _text(suggestion.get("project_name") or suggestion.get("entity_name")),
            "target_date": target_date,
            "after_window": {"start_date": start_date, "end_date": end_date},
            "evaluation_status": "pending_future_data",
            "evaluation_reason": "本地数据库还没有覆盖完整后续窗口，暂不评估建议准确率。",
            "before_metrics": _today_metrics(suggestion),
            "after_metrics": {"active_days": 0, "stat_cost": 0.0, "convert_cnt": 0.0, "roi_1day": 0.0},
            "operation_after": {"found": False, "samples": []},
        }
    after = _project_metrics(
        conn,
        advertiser_id=advertiser_id,
        project_id=project_id,
        start_date=start_date,
        end_date=end_date,
    )
    operation = _operation_after(
        conn,
        advertiser_id=advertiser_id,
        project_id=project_id,
        target_date=target_date,
        action=action,
    )
    status = "needs_review"
    reason = "后续数据不满足该建议的支持条件。"
    if after["active_days"] == 0:
        status = "no_future_data"
        reason = "后续窗口没有该项目数据，无法仅凭数据判断。"
    if action in {"suggest_close_project", "suggest_delete_project", "pause_project"}:
        if after["stat_cost"] <= max_after_stat_cost and after["convert_cnt"] <= max_after_convert_cnt:
            status = "supported"
            reason = "后续窗口低消耗且无转化，支持关闭/删除类建议。"
        elif after["convert_cnt"] > max_after_convert_cnt:
            status = "needs_review"
            reason = "后续窗口出现转化，需要复核是否误判。"
    elif action in {"suggest_lower_budget", "suggest_lower_bid", "adjust_project_budget", "adjust_project_bid"}:
        if not operation["found"]:
            status = "not_evaluated_no_execution"
            reason = "未发现对应预算/出价操作日志，暂不评估建议效果。"
        elif after["active_days"] == 0:
            status = "no_future_data"
            reason = "已发现操作日志，但后续窗口没有项目数据。"
        else:
            status = "execution_observed"
            reason = "已发现对应操作日志，后续效果留给更长窗口继续观察。"
    return {
        "suggestion_id": _text(suggestion.get("suggestion_id")),
        "suggested_action": action,
        "advertiser_id": advertiser_id,
        "project_id": project_id,
        "project_name": _text(suggestion.get("project_name") or suggestion.get("entity_name")),
        "target_date": target_date,
        "after_window": {"start_date": start_date, "end_date": end_date},
        "evaluation_status": status,
        "evaluation_reason": reason,
        "before_metrics": _today_metrics(suggestion),
        "after_metrics": after,
        "operation_after": operation,
    }


def run_delivery_suggestion_backtest_request(
    request: dict[str, Any] | None,
    *,
    runs_dir: str | Path,
) -> dict[str, Any]:
    cfg = dict(request or {})
    artifact_paths = cfg.get("suggestions_artifact_paths") or cfg.get("suggestions_artifacts") or []
    if isinstance(artifact_paths, str):
        artifact_paths = [artifact_paths]
    artifact_paths = [str(path) for path in artifact_paths if str(path or "").strip()]
    inline_artifact = cfg.get("suggestions_artifact") if isinstance(cfg.get("suggestions_artifact"), dict) else None
    if not artifact_paths and inline_artifact is None:
        raise ValueError("delivery suggestion backtest requires suggestions_artifact_paths")
    db_path = Path(str(cfg.get("db_path") or "data/roibang_v2.sqlite3"))
    if not db_path.exists():
        raise ValueError(f"delivery suggestion backtest db does not exist: {db_path}")
    runs_path = Path(runs_dir)
    project_root = Path(str(cfg.get("project_root") or (runs_path.parent.parent if runs_path.parent.name == "data" else ".")))
    lookahead_days = int(cfg.get("lookahead_days") or 1)
    max_after_stat_cost = float(cfg.get("max_after_stat_cost") or 100)
    max_after_convert_cnt = float(cfg.get("max_after_convert_cnt") or 0)

    evaluations: list[dict[str, Any]] = []
    source_suggestion_count = 0
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        max_metric_date = _max_metric_date(conn)
        artifacts: list[tuple[str, dict[str, Any]]] = []
        if inline_artifact is not None:
            artifacts.append(("<inline>", inline_artifact))
        for path in artifact_paths:
            artifacts.append((path, _load_json(path)))
        for path, artifact in artifacts:
            suggestions = _rows(artifact.get("suggestions"))
            source_suggestion_count += len(suggestions)
            lifecycle = build_create_suggestion_lifecycle(
                runs_dir=runs_path,
                project_root=project_root,
                suggestions_artifact=artifact,
                suggestions_artifact_path="" if path == "<inline>" else path,
            )
            lifecycle_by_id = lifecycle.get("by_suggestion_id") if isinstance(lifecycle.get("by_suggestion_id"), dict) else {}
            for suggestion in suggestions:
                evaluation = _evaluate_suggestion(
                    conn,
                    suggestion,
                    artifact=artifact,
                    lookahead_days=lookahead_days,
                    max_after_stat_cost=max_after_stat_cost,
                    max_after_convert_cnt=max_after_convert_cnt,
                    max_metric_date=max_metric_date,
                    lifecycle_by_id=lifecycle_by_id,
                    project_root=project_root,
                )
                if evaluation is not None:
                    evaluation["source_artifact_path"] = path
                    evaluations.append(evaluation)

    status_counts: dict[str, int] = {}
    action_counts: dict[str, int] = {}
    for evaluation in evaluations:
        status = _text(evaluation.get("evaluation_status"))
        action = _text(evaluation.get("suggested_action"))
        status_counts[status] = status_counts.get(status, 0) + 1
        action_counts[action] = action_counts.get(action, 0) + 1
    create_evaluations = [evaluation for evaluation in evaluations if _text(evaluation.get("suggested_action")) == CREATE_ACTION]
    create_submitted_statuses = {
        "create_adopted_pending_result",
        "create_adopted_pending_future_data",
        "create_adopted_no_future_data",
        "create_adopted_with_future_data",
        "create_execution_evidence_missing",
        "create_execution_failed",
    }

    payload = {
        "ok": True,
        "workflow": "delivery_suggestion_backtest",
        "phase": "readonly_analysis",
        "execution_enabled": False,
        "external_api_calls": 0,
        "summary": {
            "artifact_count": len(artifact_paths) + (1 if inline_artifact is not None else 0),
            "source_suggestion_count": source_suggestion_count,
            "evaluated_suggestion_count": len(evaluations),
            "lookahead_days": lookahead_days,
            "status_counts": status_counts,
            "action_counts": action_counts,
            "max_metric_date": max_metric_date,
            "create_suggestion_count": len(create_evaluations),
            "create_adopted_count": sum(
                1 for evaluation in create_evaluations if _text(evaluation.get("evaluation_status")) in create_submitted_statuses
            ),
            "create_executed_count": sum(
                1
                for evaluation in create_evaluations
                if _text(evaluation.get("create_lifecycle_status")) in {"execution_submitted", "execution_completed", "execution_failed"}
            ),
            "create_with_future_data_count": sum(
                1 for evaluation in create_evaluations if _text(evaluation.get("evaluation_status")) == "create_adopted_with_future_data"
            ),
            "create_execution_failed_count": sum(
                1 for evaluation in create_evaluations if _text(evaluation.get("evaluation_status")) == "create_execution_failed"
            ),
        },
        "evaluations": evaluations,
    }
    payload["artifact_path"] = str(write_run_artifact(runs_dir, "delivery_suggestion_backtest", payload))
    payload["latest_artifact_path"] = str(Path(runs_dir) / "delivery_suggestion_backtest" / "latest.json")
    write_latest_artifact(runs_dir, "delivery_suggestion_backtest", payload)
    return payload
