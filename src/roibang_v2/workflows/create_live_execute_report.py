from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from roibang_v2.runs import write_run_artifact


def _rows(value: Any) -> list[dict[str, Any]]:
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def _status(value: dict[str, Any]) -> str:
    return str(value.get("status") or "")


def _count_provider(records: list[dict[str, Any]], *, entity_type: str) -> int:
    return sum(
        1
        for row in records
        if str(row.get("entity_type") or "") == entity_type and _status(row) in {"recorded", "skipped_existing_provider_id"}
    )


def _count_material_binds(records: list[dict[str, Any]]) -> int:
    return sum(1 for row in records if _status(row) in {"recorded", "skipped_existing_material_bind"})


def _idempotency(source: dict[str, Any]) -> dict[str, Any]:
    value = source.get("idempotency")
    return dict(value) if isinstance(value, dict) else {}


def _source_summary(source: dict[str, Any]) -> dict[str, Any]:
    runner = source.get("runner_result") if isinstance(source.get("runner_result"), dict) else {}
    provider_records = [
        *_rows(source.get("provider_id_records")),
        *_rows(_idempotency(source).get("skipped_provider_id_records")),
    ]
    material_bind_records = [
        *_rows(source.get("material_bind_records")),
        *_rows(_idempotency(source).get("skipped_material_bind_records")),
    ]
    ordered_steps = _rows(source.get("ordered_steps"))
    failure = source.get("failure") if isinstance(source.get("failure"), dict) else None
    return {
        "source_ok": bool(source.get("ok", False)),
        "source_status": _status(source),
        "source_external_api_calls": int(source.get("external_api_calls") or 0),
        "source_transport_call_count": int(source.get("transport_call_count") or 0),
        "completed_step_count": sum(1 for row in ordered_steps if _status(row) == "completed"),
        "skipped_step_count": sum(1 for row in ordered_steps if _status(row).startswith("skipped_")),
        "created_project_count": _count_provider(provider_records, entity_type="project"),
        "created_unit_count": _count_provider(provider_records, entity_type="promotion"),
        "target_video_count": _count_provider(provider_records, entity_type="target_video"),
        "target_video_cover_count": _count_provider(provider_records, entity_type="target_video_cover"),
        "material_bind_count": _count_material_binds(material_bind_records),
        "blocking_reasons": [str(item) for item in source.get("blocking_reasons") or []],
        "failure": failure,
        "runner_status": _status(runner),
    }


def _plan_summary(create_plan: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(create_plan, dict) or not create_plan:
        return {}
    accounts = _rows(create_plan.get("target_accounts"))
    materials = _rows(create_plan.get("materials"))

    def int_value(value: Any) -> int:
        try:
            return max(int(value), 0)
        except (TypeError, ValueError):
            return 0

    project_count = sum(int_value(row.get("project_count")) for row in accounts)
    unit_count = sum(
        int_value(row.get("project_count")) * int_value(row.get("unit_count_per_project", row.get("units_per_project")))
        for row in accounts
    )
    return {
        "plan_id": str(create_plan.get("plan_id") or ""),
        "product": str(create_plan.get("product") or ""),
        "platform": str(create_plan.get("platform") or ""),
        "source_advertiser_id": str(create_plan.get("source_advertiser_id") or ""),
        "target_account_count": len(accounts),
        "target_accounts": [
            {
                "advertiser_id": str(row.get("advertiser_id") or ""),
                "project_count": int_value(row.get("project_count")),
                "unit_count_per_project": int_value(row.get("unit_count_per_project", row.get("units_per_project"))),
                "daily_budget": float(row.get("daily_budget") or 0),
            }
            for row in accounts
        ],
        "project_count": project_count,
        "unit_count": unit_count,
        "material_count": len(materials),
        "materials": [
            {
                "source_material_id": str(row.get("source_material_id") or row.get("material_id") or ""),
                "source_video_id": str(row.get("source_video_id") or row.get("video_id") or ""),
            }
            for row in materials
        ],
        "reason": str(create_plan.get("reason") or ""),
    }


def _plan_contract(*, plan_summary: dict[str, Any], source_plan_id: str) -> dict[str, Any]:
    plan_id = str(plan_summary.get("plan_id") or "")
    if not plan_id:
        return {"available": False, "plan_id_matches_source": False}
    return {
        "available": True,
        "plan_id": plan_id,
        "source_plan_id": source_plan_id,
        "plan_id_matches_source": not source_plan_id or plan_id == source_plan_id,
    }


def _message(summary: dict[str, Any]) -> str:
    status = str(summary.get("source_status") or "")
    failure = summary.get("failure") if isinstance(summary.get("failure"), dict) else None
    if status == "create_http_completed":
        return (
            "真实创建结果：完成项目"
            f"{int(summary.get('created_project_count') or 0)}个、单元"
            f"{int(summary.get('created_unit_count') or 0)}个、素材推送"
            f"{int(summary.get('material_bind_count') or 0)}组；执行脚本外部调用"
            f"{int(summary.get('source_external_api_calls') or 0)}次。"
        )
    if failure:
        return (
            "真实创建失败："
            f"{failure.get('operation') or 'unknown'} 第{failure.get('index', '')}条，"
            f"{failure.get('message') or '无错误信息'}。"
        )
    reasons = [str(item) for item in summary.get("blocking_reasons") or []]
    if reasons:
        return f"未执行真实创建：{reasons[0]}"
    return f"未执行真实创建：source status={status or 'unknown'}。"


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ? LIMIT 1",
        (table,),
    ).fetchone()
    return row is not None


def _db_ledger_summary(*, db_path: str | Path, plan_id: str) -> dict[str, Any]:
    path = Path(db_path)
    if not str(plan_id or "").strip() or not path.exists():
        return {"available": False, "reason": "missing_plan_id_or_database"}
    try:
        with sqlite3.connect(path) as conn:
            if not _table_exists(conn, "create_provider_id_ledger") or not _table_exists(
                conn,
                "create_material_bind_ledger",
            ):
                return {"available": False, "reason": "ledger_tables_not_found"}
            provider_rows = conn.execute(
                """
                SELECT entity_type, COUNT(*)
                FROM create_provider_id_ledger
                WHERE plan_id = ? AND status = 'active'
                GROUP BY entity_type
                """,
                (plan_id,),
            ).fetchall()
            material_bind_count = conn.execute(
                """
                SELECT COUNT(*)
                FROM create_material_bind_ledger
                WHERE plan_id = ? AND status = 'active'
                """,
                (plan_id,),
            ).fetchone()
    except sqlite3.Error as exc:
        return {"available": False, "reason": str(exc)}
    return {
        "available": True,
        "plan_id": plan_id,
        "provider_id_counts": {str(entity): int(count) for entity, count in provider_rows},
        "material_bind_count": int(material_bind_count[0] if material_bind_count else 0),
    }


def build_create_live_execute_report(
    *,
    create_live_execute_once_artifact: dict[str, Any],
    create_plan_artifact: dict[str, Any] | None = None,
    source_artifact_path: str = "",
    plan_artifact_path: str = "",
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    source = dict(create_live_execute_once_artifact)
    source_path = str(source_artifact_path or source.get("artifact_path") or "")
    summary = _source_summary(source)
    source_summary = source.get("create_execute_summary") if isinstance(source.get("create_execute_summary"), dict) else {}
    if not source_summary:
        source_summary = source.get("summary") if isinstance(source.get("summary"), dict) else {}
    plan_id = str(source_summary.get("plan_id") or "")
    create_plan_summary = _plan_summary(create_plan_artifact)
    payload = {
        "ok": True,
        "workflow": "create_live_execute_report",
        "phase": "phase2_preparation",
        "execution_enabled": False,
        "external_api_calls": 0,
        "status": "reported_completed"
        if str(summary.get("source_status") or "") == "create_http_completed"
        else "reported_not_completed",
        "message": _message(summary),
        "summary": summary,
        "create_plan_summary": create_plan_summary,
        "create_plan_contract": _plan_contract(plan_summary=create_plan_summary, source_plan_id=plan_id),
        "db_ledger_summary": _db_ledger_summary(db_path=db_path, plan_id=plan_id) if db_path is not None else {},
        "source_artifact_path": source_path,
        "plan_artifact_path": str(plan_artifact_path or ""),
        "actions": [],
    }
    return payload


def run_create_live_execute_report_request(
    request: dict[str, Any],
    *,
    runs_dir: str | Path,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    cfg = request.get("create_live_execute_report")
    cfg = dict(cfg) if isinstance(cfg, dict) else dict(request)
    source = cfg.get("create_live_execute_once_artifact")
    if not isinstance(source, dict):
        raise ValueError("create live execute report requires create_live_execute_once_artifact")
    payload = build_create_live_execute_report(
        create_live_execute_once_artifact=source,
        create_plan_artifact=cfg.get("create_plan_artifact") if isinstance(cfg.get("create_plan_artifact"), dict) else None,
        source_artifact_path=str(cfg.get("source_artifact_path") or source.get("artifact_path") or ""),
        plan_artifact_path=str(cfg.get("plan_artifact_path") or ""),
        db_path=db_path,
    )
    artifact_path = write_run_artifact(runs_dir, "create_live_execute_report", payload)
    return {**payload, "artifact_path": str(artifact_path)}
