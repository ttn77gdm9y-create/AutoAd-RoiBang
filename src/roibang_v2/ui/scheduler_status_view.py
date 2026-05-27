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


def build_scheduler_status_view(payload: dict[str, Any]) -> dict[str, Any]:
    summary = _dict(payload.get("summary"))
    jobs = [row for row in _list(payload.get("jobs")) if isinstance(row, dict)]
    product_summary = [row for row in _list(payload.get("product_summary")) if isinstance(row, dict)]
    job_rows = []
    product_rows = []
    issue_rows = []
    artifact_rows = []
    for job in jobs:
        artifact = _dict(job.get("artifact_contract"))
        scheduler_result = _dict(job.get("scheduler_result"))
        data_check = _dict(job.get("data_check"))
        issues = [str(item) for item in _list(job.get("issues"))]
        job_rows.append(
            {
                "job_id": _text(job.get("job_id")),
                "display_name": _text(job.get("display_name")),
                "status": _text(job.get("status")),
                "issue_count": len(issues),
                "data_type": _text(data_check.get("type")),
                "data_status": _text(data_check.get("status")),
                "artifact_path": _text(artifact.get("artifact_path")),
                "scheduler_artifact_path": _text(scheduler_result.get("path")),
                "last_exit_code": _text(_dict(job.get("launchd")).get("last_exit_code")),
            }
        )
        for issue in issues:
            issue_rows.append(
                {
                    "job_id": _text(job.get("job_id")),
                    "display_name": _text(job.get("display_name")),
                    "issue": issue,
                }
            )
        if artifact.get("artifact_path"):
            artifact_rows.append(
                {
                    "job_id": _text(job.get("job_id")),
                    "type": "workflow_artifact",
                    "path": _text(artifact.get("artifact_path")),
                    "ok": bool(artifact.get("ok")),
                }
            )
        if scheduler_result.get("path"):
            artifact_rows.append(
                {
                    "job_id": _text(job.get("job_id")),
                    "type": "scheduler_artifact",
                    "path": _text(scheduler_result.get("path")),
                    "ok": bool(scheduler_result.get("ok")),
                }
            )
        for result in _list(job.get("product_results")):
            if not isinstance(result, dict):
                continue
            result_summary = _dict(result.get("summary"))
            product_rows.append(
                {
                    "product": _text(result.get("product")),
                    "product_key": _text(result.get("product_key")),
                    "job_id": _text(job.get("job_id")),
                    "display_name": _text(job.get("display_name")),
                    "job": _text(result.get("job")),
                    "status": "ok" if bool(result.get("ok", True)) and _text(job.get("status")) == "ok" else "attention",
                    "result_status": _text(result.get("status")),
                    "artifact_path": _text(result.get("artifact_path") or artifact.get("artifact_path")),
                    "summary": result_summary,
                }
            )
    if not product_rows and product_summary:
        for product in product_summary:
            for job in _list(product.get("jobs")):
                if not isinstance(job, dict):
                    continue
                product_rows.append(
                    {
                        "product": _text(product.get("product")),
                        "product_key": _text(product.get("product_key")),
                        "job_id": _text(job.get("job_id")),
                        "display_name": _text(job.get("display_name")),
                        "job": _text(job.get("job")),
                        "status": _text(job.get("status")),
                        "result_status": "",
                        "artifact_path": _text(job.get("artifact_path")),
                        "summary": _dict(job.get("summary")),
                    }
                )
    return {
        "ok": bool(payload.get("ok")),
        "summary": {
            "report_date": _text(summary.get("report_date")),
            "expected_data_date": _text(summary.get("expected_data_date")),
            "job_count": _int(summary.get("job_count")),
            "ok_count": _int(summary.get("ok_count")),
            "attention_count": _int(summary.get("attention_count")),
            "product_count": _int(summary.get("product_count") or len(product_summary)),
        },
        "job_rows": job_rows,
        "product_rows": product_rows,
        "issue_rows": issue_rows,
        "artifact_rows": artifact_rows,
        "message": _text(payload.get("message")),
    }
