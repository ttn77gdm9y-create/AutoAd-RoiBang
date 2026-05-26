from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from roibang_v2.runs import write_run_artifact


def _rows(value: Any) -> list[dict[str, Any]]:
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def _plan_body(create_plan: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(create_plan, dict) or not create_plan:
        return {}
    nested = create_plan.get("create_strategy_plan")
    if isinstance(nested, dict):
        return nested
    return create_plan


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
    efficiency = source.get("efficiency_report") if isinstance(source.get("efficiency_report"), dict) else {}
    failure_recovery = efficiency.get("failure_recovery") if isinstance(efficiency.get("failure_recovery"), dict) else {}
    provider_records = [
        *_rows(source.get("provider_id_records")),
        *_rows(_idempotency(source).get("skipped_provider_id_records")),
    ]
    material_bind_records = [
        *_rows(source.get("material_bind_records")),
        *_rows(_idempotency(source).get("skipped_material_bind_records")),
    ]
    ordered_steps = _rows(source.get("ordered_steps"))
    skipped_accounts = _rows(source.get("skipped_accounts"))
    bind_failures = [row for row in skipped_accounts if str(row.get("operation") or "") == "bind_material"]
    skipped_units = [row for row in skipped_accounts if str(row.get("operation") or "") == "create_unit"]
    affected_accounts = sorted({str(row.get("advertiser_id") or "") for row in skipped_accounts if row.get("advertiser_id")})
    first_bind_failure = bind_failures[0] if bind_failures else {}
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
        "skipped_account_count": len(skipped_accounts),
        "affected_account_count": len(affected_accounts),
        "affected_accounts": affected_accounts,
        "skipped_unit_count": len(skipped_units),
        "material_bind_failure_count": len(bind_failures),
        "first_material_bind_failure_code": int(first_bind_failure.get("code") or 0),
        "first_material_bind_failure_message": str(first_bind_failure.get("message") or ""),
        "post_run_retry_status": str(failure_recovery.get("post_run_retry_status") or ""),
        "post_run_retry_attempted_count": int(failure_recovery.get("post_run_retry_attempted_count") or 0),
        "post_run_retry_recovered_count": int(failure_recovery.get("post_run_retry_recovered_count") or 0),
        "post_run_retry_failed_count": int(failure_recovery.get("post_run_retry_failed_count") or 0),
    }


def _execution_issues(source: dict[str, Any]) -> dict[str, Any]:
    skipped_accounts = _rows(source.get("skipped_accounts"))
    by_account: dict[str, dict[str, Any]] = {}
    for row in skipped_accounts:
        advertiser_id = str(row.get("advertiser_id") or "")
        if not advertiser_id:
            continue
        issue = by_account.setdefault(
            advertiser_id,
            {
                "advertiser_id": advertiser_id,
                "material_bind_failure_count": 0,
                "skipped_lookup_count": 0,
                "skipped_unit_count": 0,
                "codes": set(),
                "messages": set(),
                "bind_messages": set(),
                "skip_messages": set(),
                "operations": set(),
            },
        )
        operation = str(row.get("operation") or "")
        issue["operations"].add(operation)
        if operation == "bind_material":
            issue["material_bind_failure_count"] += 1
        elif operation == "lookup_target_material":
            issue["skipped_lookup_count"] += 1
        elif operation == "create_unit":
            issue["skipped_unit_count"] += 1
        if row.get("code") not in (None, ""):
            issue["codes"].add(str(row.get("code")))
        message = str(row.get("message") or "").strip()
        if message:
            issue["messages"].add(message)
            if operation == "bind_material":
                issue["bind_messages"].add(message)
            else:
                issue["skip_messages"].add(message)
    accounts = [
        {
            "advertiser_id": issue["advertiser_id"],
            "material_bind_failure_count": issue["material_bind_failure_count"],
            "skipped_lookup_count": issue["skipped_lookup_count"],
            "skipped_unit_count": issue["skipped_unit_count"],
            "codes": sorted(issue["codes"]),
            "messages": [*sorted(issue["bind_messages"]), *sorted(issue["skip_messages"])],
            "operations": sorted(operation for operation in issue["operations"] if operation),
        }
        for issue in by_account.values()
    ]
    accounts.sort(key=lambda row: str(row.get("advertiser_id") or ""))
    return {
        "manual_review_required": bool(accounts),
        "affected_account_count": len(accounts),
        "skipped_unit_count": sum(int(row.get("skipped_unit_count") or 0) for row in accounts),
        "material_bind_failure_count": sum(int(row.get("material_bind_failure_count") or 0) for row in accounts),
        "accounts": accounts,
        "rebuild_reference": [
            {
                "advertiser_id": str(row.get("advertiser_id") or ""),
                "skipped_unit_count": int(row.get("skipped_unit_count") or 0),
                "reason": "；".join(row.get("messages") or []) or "素材绑定失败后跳过后续单元",
            }
            for row in accounts
            if int(row.get("skipped_unit_count") or 0) > 0
        ],
    }


def _efficiency(source: dict[str, Any]) -> dict[str, Any]:
    return dict(source.get("efficiency_report")) if isinstance(source.get("efficiency_report"), dict) else {}


def _next_steps(*, summary: dict[str, Any], efficiency: dict[str, Any]) -> list[str]:
    steps: list[str] = []
    failure = summary.get("failure") if isinstance(summary.get("failure"), dict) else None
    recovery = efficiency.get("failure_recovery") if isinstance(efficiency.get("failure_recovery"), dict) else {}
    material_push = efficiency.get("material_push") if isinstance(efficiency.get("material_push"), dict) else {}
    if int(recovery.get("post_run_retry_failed_count") or 0) > 0:
        steps.append("有跑后补跑仍失败的单元，需要按失败记录单独排查或补跑。")
    if int(recovery.get("post_run_retry_recovered_count") or 0) > 0:
        steps.append("已有临时失败单元在跑后补跑中恢复，优先看最终单元数是否满足计划。")
    if int(summary.get("skipped_account_count") or 0) > 0 and int(recovery.get("post_run_retry_recovered_count") or 0) == 0:
        steps.append("存在跳过账户，先看跳过原因是素材、接口还是项目上限。")
    if int(summary.get("material_bind_failure_count") or 0) > 0:
        steps.append("素材绑定返回错误的账户需要换素材或先补齐目标账户素材权限，再按跳过账户补建单元。")
    if failure:
        operation = str(failure.get("operation") or "")
        if operation in {"bind_material", "lookup_target_material"}:
            steps.append("失败发生在素材推送或目标素材回查，优先检查素材权限和目标账户素材库。")
        elif operation == "create_unit":
            steps.append("失败发生在创建单元，优先确认项目 ID、素材 ID、封面 ID 是否已落账。")
        else:
            steps.append("存在创建失败，需要查看 source_artifact_path 对应执行产物。")
    if int(material_push.get("skipped_existing_target_material_count") or 0) > 0:
        steps.append("目标账户已存在部分素材，后续可继续提高预推送覆盖率减少实时推送。")
    if not steps:
        steps.append("无需人工处理。")
    return steps


def _plan_summary(create_plan: dict[str, Any] | None) -> dict[str, Any]:
    plan = _plan_body(create_plan)
    if not plan:
        return {}
    request = plan.get("request") if isinstance(plan.get("request"), dict) else {}
    strategy = plan.get("strategy") if isinstance(plan.get("strategy"), dict) else {}
    summary = plan.get("summary") if isinstance(plan.get("summary"), dict) else {}
    accounts = _rows(request.get("target_accounts") or plan.get("target_accounts"))
    projects = _rows(strategy.get("projects"))
    materials = [
        material
        for project in projects
        for unit in _rows(project.get("units"))
        for material in _rows(unit.get("materials"))
    ]
    if not materials:
        materials = _rows(plan.get("materials"))
    unique_material_ids = {
        str(row.get("material_id") or row.get("source_material_id") or "")
        for row in materials
        if str(row.get("material_id") or row.get("source_material_id") or "")
    }

    def int_value(value: Any) -> int:
        try:
            return max(int(value), 0)
        except (TypeError, ValueError):
            return 0

    project_count = int_value(summary.get("planned_project_count")) or sum(int_value(row.get("project_count")) for row in accounts)
    unit_count = int_value(summary.get("planned_unit_count")) or sum(
        int_value(row.get("project_count")) * int_value(row.get("unit_count_per_project", row.get("units_per_project")))
        for row in accounts
    )
    return {
        "plan_id": str(summary.get("plan_id") or plan.get("plan_id") or request.get("plan_id") or ""),
        "request_id": str(summary.get("request_id") or plan.get("request_id") or request.get("request_id") or ""),
        "target_date": str(summary.get("target_date") or plan.get("target_date") or request.get("target_date") or ""),
        "mode_key": str(summary.get("mode_key") or ""),
        "display_name": str(summary.get("display_name") or ""),
        "product": str(request.get("product") or plan.get("product") or ""),
        "platform": str(request.get("platform") or plan.get("platform") or ""),
        "launch_mode": str(plan.get("launch_mode") or ""),
        "source_advertiser_id": str(request.get("source_advertiser_id") or plan.get("source_advertiser_id") or ""),
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
        "material_assignment_count": len(materials),
        "material_count": len(unique_material_ids),
        "source_material_count": int_value(summary.get("source_material_count")),
        "materials": [
            {
                "source_material_id": str(row.get("source_material_id") or row.get("material_id") or ""),
                "source_video_id": str(row.get("source_video_id") or row.get("video_id") or ""),
                "name": str(row.get("name") or ""),
                "stat_cost": float(row.get("stat_cost") or 0),
                "convert_cnt": float(row.get("convert_cnt") or 0),
                "effective_create_date": str(row.get("effective_create_date") or ""),
            }
            for row in materials
        ],
        "reason": str(plan.get("reason") or ""),
    }


def _selected_material_reference(create_plan: dict[str, Any] | None) -> dict[str, Any]:
    plan = _plan_body(create_plan)
    strategy = plan.get("strategy") if isinstance(plan.get("strategy"), dict) else {}
    projects = _rows(strategy.get("projects"))
    assignments: list[dict[str, Any]] = []
    for project in projects:
        advertiser_id = str(project.get("advertiser_id") or "")
        project_name = str(project.get("project_name") or "")
        for unit in _rows(project.get("units")):
            promotion_name = str(unit.get("promotion_name") or "")
            for material in _rows(unit.get("materials")):
                material_id = str(material.get("material_id") or "")
                assignments.append(
                    {
                        "advertiser_id": advertiser_id,
                        "project_name": project_name,
                        "promotion_name": promotion_name,
                        "material_id": material_id,
                        "name": str(material.get("name") or ""),
                        "stat_cost": float(material.get("stat_cost") or 0),
                        "convert_cnt": float(material.get("convert_cnt") or 0),
                        "effective_create_date": str(material.get("effective_create_date") or ""),
                    }
                )
    material_groups: dict[str, dict[str, Any]] = {}
    for row in assignments:
        material_id = str(row.get("material_id") or "")
        if not material_id:
            continue
        group = material_groups.setdefault(
            material_id,
            {
                "material_id": material_id,
                "name": row.get("name") or "",
                "stat_cost": float(row.get("stat_cost") or 0),
                "convert_cnt": float(row.get("convert_cnt") or 0),
                "effective_create_date": row.get("effective_create_date") or "",
                "assigned_count": 0,
                "accounts": set(),
            },
        )
        group["assigned_count"] = int(group.get("assigned_count") or 0) + 1
        group["accounts"].add(str(row.get("advertiser_id") or ""))
    unique_materials = [
        {**row, "accounts": sorted(account for account in row["accounts"] if account)}
        for row in material_groups.values()
    ]
    unique_materials.sort(key=lambda row: (-float(row.get("stat_cost") or 0), str(row.get("material_id") or "")))

    by_account: list[dict[str, Any]] = []
    for advertiser_id in sorted({str(row.get("advertiser_id") or "") for row in assignments if row.get("advertiser_id")}):
        account_rows = [row for row in assignments if str(row.get("advertiser_id") or "") == advertiser_id]
        account_projects: list[dict[str, Any]] = []
        for project_name in sorted({str(row.get("project_name") or "") for row in account_rows if row.get("project_name")}):
            project_rows = [row for row in account_rows if str(row.get("project_name") or "") == project_name]
            account_projects.append(
                {
                    "project_name": project_name,
                    "materials": [
                        {
                            "material_id": str(row.get("material_id") or ""),
                            "name": str(row.get("name") or ""),
                            "stat_cost": float(row.get("stat_cost") or 0),
                            "convert_cnt": float(row.get("convert_cnt") or 0),
                            "effective_create_date": str(row.get("effective_create_date") or ""),
                        }
                        for row in project_rows
                    ],
                }
            )
        by_account.append(
            {
                "advertiser_id": advertiser_id,
                "assignment_count": len(account_rows),
                "unique_material_count": len({str(row.get("material_id") or "") for row in account_rows if row.get("material_id")}),
                "projects": account_projects,
            }
        )
    return {
        "assignment_count": len(assignments),
        "unique_material_count": len(unique_materials),
        "top_materials_by_cost": unique_materials[:30],
        "by_account": by_account,
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
        retry_text = ""
        if int(summary.get("post_run_retry_attempted_count") or 0) > 0:
            retry_text = (
                f"跑后补跑{int(summary.get('post_run_retry_attempted_count') or 0)}个，"
                f"恢复{int(summary.get('post_run_retry_recovered_count') or 0)}个，"
                f"失败{int(summary.get('post_run_retry_failed_count') or 0)}个；"
            )
        partial_text = ""
        if int(summary.get("affected_account_count") or 0) > 0:
            partial_text = (
                f"{int(summary.get('affected_account_count') or 0)}个账户素材绑定异常，"
                f"跳过单元{int(summary.get('skipped_unit_count') or 0)}个；"
            )
        return (
            "真实创建结果：完成项目"
            f"{int(summary.get('created_project_count') or 0)}个、单元"
            f"{int(summary.get('created_unit_count') or 0)}个、素材推送"
            f"{int(summary.get('material_bind_count') or 0)}组；{partial_text}{retry_text}执行脚本外部调用"
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


def _failure_reason(*, summary: dict[str, Any], source_artifact_path: str) -> dict[str, Any] | None:
    failure = summary.get("failure") if isinstance(summary.get("failure"), dict) else None
    if failure:
        return {
            "source_artifact_path": source_artifact_path,
            "operation": str(failure.get("operation") or "unknown"),
            "index": int(failure.get("index") or 0),
            "message": str(failure.get("message") or "无错误信息"),
            "code": int(failure.get("code") or -1),
        }
    reasons = [str(item) for item in summary.get("blocking_reasons") or [] if str(item)]
    if reasons:
        return {
            "source_artifact_path": source_artifact_path,
            "operation": "blocked",
            "index": 0,
            "message": reasons[0],
            "code": -1,
        }
    status = str(summary.get("source_status") or "")
    if status and status != "create_http_completed":
        return {
            "source_artifact_path": source_artifact_path,
            "operation": "status",
            "index": 0,
            "message": status,
            "code": -1,
        }
    return None


def _batch_summary(sources: list[dict[str, Any]], source_paths: list[str]) -> dict[str, Any]:
    source_summaries = [_source_summary(source) for source in sources]
    completed_count = sum(1 for summary in source_summaries if str(summary.get("source_status") or "") == "create_http_completed")
    failure_reasons: list[dict[str, Any]] = []
    for index, summary in enumerate(source_summaries):
        path = source_paths[index] if index < len(source_paths) else ""
        reason = _failure_reason(summary=summary, source_artifact_path=path)
        if reason is not None:
            failure_reasons.append(reason)
    return {
        "artifact_count": len(source_summaries),
        "completed_artifact_count": completed_count,
        "failed_artifact_count": len(source_summaries) - completed_count,
        "manual_review_required": bool(failure_reasons),
        "created_project_count": sum(int(summary.get("created_project_count") or 0) for summary in source_summaries),
        "created_unit_count": sum(int(summary.get("created_unit_count") or 0) for summary in source_summaries),
        "target_video_count": sum(int(summary.get("target_video_count") or 0) for summary in source_summaries),
        "target_video_cover_count": sum(int(summary.get("target_video_cover_count") or 0) for summary in source_summaries),
        "material_bind_count": sum(int(summary.get("material_bind_count") or 0) for summary in source_summaries),
        "source_external_api_calls": sum(int(summary.get("source_external_api_calls") or 0) for summary in source_summaries),
        "source_transport_call_count": sum(int(summary.get("source_transport_call_count") or 0) for summary in source_summaries),
        "failure_reasons": failure_reasons,
        "sources": source_summaries,
    }


def _batch_message(summary: dict[str, Any]) -> str:
    need_manual = "是" if bool(summary.get("manual_review_required")) else "否"
    message = (
        f"真实创建汇总：成功项目{int(summary.get('created_project_count') or 0)}个、"
        f"成功单元{int(summary.get('created_unit_count') or 0)}个、"
        f"素材推送{int(summary.get('material_bind_count') or 0)}组；"
        f"需要人工处理：{need_manual}。"
    )
    reasons = summary.get("failure_reasons") if isinstance(summary.get("failure_reasons"), list) else []
    if reasons:
        first = reasons[0] if isinstance(reasons[0], dict) else {}
        message += f" 首个失败：{first.get('operation') or 'unknown'}，{first.get('message') or '无错误信息'}。"
    return message


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
    efficiency = _efficiency(source)
    source_summary = source.get("create_execute_summary") if isinstance(source.get("create_execute_summary"), dict) else {}
    if not source_summary:
        source_summary = source.get("summary") if isinstance(source.get("summary"), dict) else {}
    plan_id = str(source_summary.get("plan_id") or "")
    create_plan_summary = _plan_summary(create_plan_artifact)
    selected_materials = _selected_material_reference(create_plan_artifact)
    execution_issues = _execution_issues(source)
    payload = {
        "ok": True,
        "workflow": "create_live_execute_report",
        "phase": "phase2_preparation",
        "execution_enabled": False,
        "external_api_calls": 0,
        "status": "reported_partial_completed"
        if bool(execution_issues.get("manual_review_required"))
        else (
            "reported_completed"
            if str(summary.get("source_status") or "") == "create_http_completed"
            else "reported_not_completed"
        ),
        "message": _message(summary),
        "summary": summary,
        "efficiency_report": efficiency,
        "next_steps": _next_steps(summary=summary, efficiency=efficiency),
        "readable_reference": {
            "execution_issues": execution_issues,
            "selected_materials": selected_materials,
        },
        "create_plan_summary": create_plan_summary,
        "create_plan_contract": _plan_contract(plan_summary=create_plan_summary, source_plan_id=plan_id),
        "db_ledger_summary": _db_ledger_summary(db_path=db_path, plan_id=plan_id) if db_path is not None else {},
        "source_artifact_path": source_path,
        "plan_artifact_path": str(plan_artifact_path or ""),
        "actions": [],
    }
    return payload


def build_create_live_execute_batch_report(
    *,
    create_live_execute_once_artifacts: list[dict[str, Any]],
    source_artifact_paths: list[str] | None = None,
) -> dict[str, Any]:
    source_paths = [str(path) for path in (source_artifact_paths or [])]
    summary = _batch_summary(create_live_execute_once_artifacts, source_paths)
    status = "reported_manual_review_required" if bool(summary.get("manual_review_required")) else "reported_completed"
    return {
        "ok": True,
        "workflow": "create_live_execute_report",
        "phase": "phase2_preparation",
        "execution_enabled": False,
        "external_api_calls": 0,
        "status": status,
        "message": _batch_message(summary),
        "summary": {},
        "batch_summary": summary,
        "create_plan_summary": {},
        "create_plan_contract": {"available": False, "plan_id_matches_source": False},
        "db_ledger_summary": {},
        "source_artifact_path": source_paths[0] if source_paths else "",
        "source_artifact_paths": source_paths,
        "plan_artifact_path": "",
        "actions": [],
    }


def run_create_live_execute_report_request(
    request: dict[str, Any],
    *,
    runs_dir: str | Path,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    cfg = request.get("create_live_execute_report")
    cfg = dict(cfg) if isinstance(cfg, dict) else dict(request)
    sources = cfg.get("create_live_execute_once_artifacts")
    if isinstance(sources, list) and sources:
        valid_sources = [dict(source) for source in sources if isinstance(source, dict)]
        if not valid_sources:
            raise ValueError("create live execute report requires create_live_execute_once_artifacts")
        payload = build_create_live_execute_batch_report(
            create_live_execute_once_artifacts=valid_sources,
            source_artifact_paths=[
                str(path) for path in cfg.get("source_artifact_paths", []) if isinstance(path, (str, Path))
            ]
            if isinstance(cfg.get("source_artifact_paths"), list)
            else [],
        )
        artifact_path = write_run_artifact(runs_dir, "create_live_execute_report", payload)
        return {**payload, "artifact_path": str(artifact_path)}
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
