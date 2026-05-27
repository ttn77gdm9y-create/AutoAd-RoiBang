from __future__ import annotations

from typing import Any


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


def _feishu_status(report_payload: dict[str, Any]) -> tuple[str, str]:
    delivery = _dict(report_payload.get("delivery"))
    feishu = _dict(delivery.get("feishu"))
    if not feishu:
        return "", ""
    if not bool(feishu.get("attempted")):
        return "not_attempted", _text(feishu.get("reason") or feishu.get("error"))
    if bool(feishu.get("ok")):
        return "sent", ""
    return "failed", _text(feishu.get("reason") or feishu.get("error"))


def build_create_execution_summary(
    *,
    task: dict[str, Any] | None = None,
    execute_payload: dict[str, Any] | None = None,
    report_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    task_payload = _dict(task)
    execute = _dict(execute_payload)
    report = _dict(report_payload)
    report_summary = _dict(report.get("summary"))
    readable = _dict(report.get("readable_reference"))
    issues = _dict(readable.get("execution_issues"))
    feishu_status, feishu_reason = _feishu_status(report)
    return {
        "status": _text(report.get("status") or execute.get("status") or task_payload.get("status")),
        "task_status": _text(task_payload.get("status")),
        "return_code": task_payload.get("return_code"),
        "created_project_count": _int(report_summary.get("created_project_count")),
        "created_unit_count": _int(report_summary.get("created_unit_count")),
        "material_bind_count": _int(report_summary.get("material_bind_count")),
        "external_api_calls": _int(report_summary.get("source_external_api_calls") or execute.get("external_api_calls")),
        "manual_review_required": bool(issues.get("manual_review_required")),
        "affected_account_count": _int(report_summary.get("affected_account_count") or issues.get("affected_account_count")),
        "skipped_unit_count": _int(report_summary.get("skipped_unit_count") or issues.get("skipped_unit_count")),
        "material_bind_failure_count": _int(
            report_summary.get("material_bind_failure_count") or issues.get("material_bind_failure_count")
        ),
        "issue_accounts": [row for row in _list(issues.get("accounts")) if isinstance(row, dict)],
        "rebuild_reference": [row for row in _list(issues.get("rebuild_reference")) if isinstance(row, dict)],
        "failure": _dict(execute.get("failure")),
        "feishu_status": feishu_status,
        "feishu_reason": feishu_reason,
        "message": _text(report.get("message") or execute.get("message")),
    }
