from __future__ import annotations

from typing import Any

from roibang_v2.ui.create_execution_summary import build_create_execution_summary


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any) -> str:
    return str(value or "").strip()


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _progress_percent(progress: dict[str, Any]) -> int:
    value = progress.get("percent")
    try:
        return max(0, min(100, int(value)))
    except (TypeError, ValueError):
        return 0


def _status_level(status: str, execution: dict[str, Any], current: dict[str, Any]) -> str:
    raw = status.lower()
    if raw.startswith("running") or raw == "queued":
        return "running"
    if raw in {"failed", "create_http_failed"} or bool(execution.get("failure")):
        return "error"
    if raw in {"reported_partial_completed", "completed_with_failures"} or bool(execution.get("manual_review_required")):
        return "warning"
    if raw in {"completed", "reported_completed", "create_http_completed", "sent", "config_ready"}:
        return "success"
    return "neutral"


def build_task_status_summary(
    *,
    task: dict[str, Any] | None = None,
    progress: dict[str, Any] | None = None,
    execute_payload: dict[str, Any] | None = None,
    report_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    task_payload = _dict(task)
    progress_payload = _dict(progress)
    current = _dict(progress_payload.get("current"))
    execution = build_create_execution_summary(
        task=task_payload,
        execute_payload=execute_payload or {},
        report_payload=report_payload or {},
    )
    status = _text(execution.get("status") or current.get("status") or task_payload.get("status"))
    events = [row for row in _list(progress_payload.get("events")) if isinstance(row, dict)]
    level = _status_level(status, execution, current)
    return {
        "task_id": _text(task_payload.get("task_id")),
        "operation_type": _text(task_payload.get("operation_type")),
        "status": status,
        "status_level": level,
        "task_status": _text(task_payload.get("status")),
        "return_code": task_payload.get("return_code"),
        "progress_percent": _progress_percent(progress_payload),
        "progress_operation": _text(current.get("operation")),
        "progress_done": _int(current.get("done")),
        "progress_total": _int(current.get("total")),
        "progress_account": _text(current.get("advertiser_id")),
        "progress_message": _text(current.get("message")),
        "external_api_calls": _int(current.get("external_api_calls") or execution.get("external_api_calls")),
        "created_project_count": _int(execution.get("created_project_count")),
        "created_unit_count": _int(execution.get("created_unit_count")),
        "material_bind_count": _int(execution.get("material_bind_count")),
        "manual_review_required": bool(execution.get("manual_review_required")),
        "affected_account_count": _int(execution.get("affected_account_count")),
        "skipped_unit_count": _int(execution.get("skipped_unit_count")),
        "material_bind_failure_count": _int(execution.get("material_bind_failure_count")),
        "issue_accounts": [row for row in _list(execution.get("issue_accounts")) if isinstance(row, dict)],
        "rebuild_reference": [row for row in _list(execution.get("rebuild_reference")) if isinstance(row, dict)],
        "failure": _dict(execution.get("failure")),
        "feishu_status": _text(execution.get("feishu_status")),
        "feishu_reason": _text(execution.get("feishu_reason")),
        "message": _text(execution.get("message") or current.get("message")),
        "execute_artifact_path": _text(task_payload.get("execute_artifact_path")),
        "report_artifact_path": _text(task_payload.get("report_artifact_path")),
        "task_artifact_path": _text(task_payload.get("artifact_path")),
        "stdout_path": _text(task_payload.get("stdout_path")),
        "stderr_path": _text(task_payload.get("stderr_path")),
        "recent_events": events,
        "should_auto_refresh": level == "running",
    }
