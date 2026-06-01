from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from datetime import timezone
from pathlib import Path
from typing import Any

from roibang_v2.runs import write_run_artifact
from roibang_v2.ui.create_plan_preview import build_create_plan_preview
from roibang_v2.workflows.frontend_operation_log import create_operation_details_from_plan


WORKFLOW = "create_plan_execution_review"
DEFAULT_REVIEW_CONFIG_PATH = "configs/create-plan-reviews/example.json"


def build_create_plan_execution_review(
    create_plan_artifact: dict[str, Any],
    cfg: dict[str, Any] | None = None,
    *,
    plan_path: str = "",
    db_path: str | Path | None = None,
    review_config: dict[str, Any] | None = None,
    source_suggestion_preview_artifact: dict[str, Any] | None = None,
    source_suggestion_preview_path: str = "",
) -> dict[str, Any]:
    cfg = dict(cfg or {})
    review_config = dict(review_config or {})
    generated_at = _now_iso()
    preview = build_create_plan_preview(create_plan_artifact)
    plan_summary = preview.get("summary") if isinstance(preview.get("summary"), dict) else {}
    details = create_operation_details_from_plan(create_plan_artifact)
    details["_has_roi_goal"] = _plan_has_roi_goal(create_plan_artifact)
    plan_id = _text(plan_summary.get("plan_id") or details.get("plan_id") or _summary(create_plan_artifact).get("plan_id"))
    batch_name = _batch_name(
        plan_summary=plan_summary,
        details=details,
        cfg=cfg,
        review_config=review_config,
        generated_at=generated_at,
    )
    source_preview = source_suggestion_preview_artifact if isinstance(source_suggestion_preview_artifact, dict) else {}
    checks = [
        _plan_ready_check(preview),
        _required_fields_check(plan_summary=plan_summary, details=details, plan_id=plan_id),
        _batch_scope_check(plan_summary=plan_summary, details=details, review_config=review_config),
        _material_readiness_check(plan_summary=plan_summary, preview=preview, review_config=review_config),
        _source_suggestion_check(
            plan_summary=plan_summary,
            preview=preview,
            source_preview=source_preview,
            source_suggestion_preview_path=source_suggestion_preview_path,
            review_config=review_config,
        ),
        _duplicate_ledger_check(
            db_path=db_path,
            plan_id=plan_id,
            resume_existing_plan=bool(cfg.get("resume_existing_plan")),
            review_config=review_config,
        ),
    ]
    risk_summary = _risk_summary(checks)
    if risk_summary["blockers"]:
        status = "blocked"
    elif risk_summary["warnings"]:
        status = "warning_only"
    else:
        status = "ready_for_confirmation"
    source_evidence_rows = _source_evidence_rows(source_preview)
    operation_record = _operation_record(
        generated_at=generated_at,
        status=status,
        batch_name=batch_name,
        plan_path=plan_path,
        plan_id=plan_id,
        details=details,
        checks=checks,
        cfg=cfg,
        source_preview=source_preview,
        source_suggestion_preview_path=source_suggestion_preview_path,
    )
    execution_manifest = _execution_manifest(
        status=status,
        batch_name=batch_name,
        plan_path=plan_path,
        plan_id=plan_id,
        details=details,
        plan_summary=plan_summary,
        source_preview=source_preview,
        generated_at=generated_at,
        cfg=cfg,
    )
    return {
        "ok": status != "blocked",
        "workflow": WORKFLOW,
        "phase": "execution_review_preview",
        "status": status,
        "execution_enabled": False,
        "external_api_calls": 0,
        "generated_at": generated_at,
        "summary": {
            "status": status,
            "batch_name": batch_name,
            "plan_id": plan_id,
            "plan_path": plan_path,
            "product": _text(details.get("product")),
            "product_key": _text(details.get("product_key")),
            "mode_key": _text(plan_summary.get("mode_key") or details.get("mode_key")),
            "target_date": _text(details.get("target_date")),
            "account_count": _int(plan_summary.get("target_account_count")),
            "planned_project_count": _int(plan_summary.get("planned_project_count")),
            "planned_unit_count": _int(plan_summary.get("planned_unit_count")),
            "source_material_count": _int(plan_summary.get("source_material_count")),
            "unique_material_count": _int(plan_summary.get("unique_material_count")),
            "check_count": len(checks),
            "passed_check_count": risk_summary["passed"],
            "warning_count": risk_summary["warnings"],
            "blocking_reason_count": risk_summary["blockers"],
            "source_suggestion_count": len(_source_suggestions(source_preview)),
            "source_strategy_ids": _source_strategy_ids(source_preview),
        },
        "risk_summary": risk_summary,
        "checks": checks,
        "blocking_reasons": [check["message"] for check in checks if check.get("status") == "blocked"],
        "warnings": [check["message"] for check in checks if check.get("status") == "warning"],
        "operation_record": operation_record,
        "execution_manifest": execution_manifest,
        "source_suggestion_evidence": {
            "source_suggestion_preview_path": source_suggestion_preview_path,
            "strategy_ids": _source_strategy_ids(source_preview),
            "rows": source_evidence_rows,
        },
        "source": {
            "plan_path": plan_path,
            "source_suggestion_preview_path": source_suggestion_preview_path,
            "review_config_id": _text(review_config.get("review_config_id")) or "default",
        },
        "guardrails": [
            "这里只生成执行前复核产物，不会调用外部接口。",
            "真实创建仍必须经过创建计划页人工确认。",
            "执行入口会重新跑复核，不能绕过阻断项直接创建。",
        ],
    }


def run_create_plan_execution_review_request(
    request: dict[str, Any],
    *,
    runs_dir: str | Path,
    project_root: str | Path = ".",
) -> dict[str, Any]:
    root = Path(project_root)
    plan_path = _text(request.get("plan_path") or request.get("create_plan_preview_path") or request.get("path"))
    if not plan_path:
        raise ValueError("create plan execution review requires plan_path")
    plan_artifact = request.get("create_plan_artifact")
    if not isinstance(plan_artifact, dict):
        plan_artifact = _load_json(_resolve_path(root, plan_path))

    review_config_path = _text(request.get("review_config_path")) or DEFAULT_REVIEW_CONFIG_PATH
    review_config = request.get("review_config")
    if not isinstance(review_config, dict):
        review_config = _load_json(_resolve_path(root, review_config_path))

    source_suggestion_preview_path = _text(
        request.get("source_suggestion_preview_path")
        or request.get("create_plan_from_suggestions_path")
        or request.get("suggestion_preview_path")
    )
    source_preview = request.get("source_suggestion_preview_artifact")
    if not isinstance(source_preview, dict) and source_suggestion_preview_path:
        source_preview = _load_json(_resolve_path(root, source_suggestion_preview_path))
    if not isinstance(source_preview, dict):
        source_preview = {}

    db_path = request.get("db_path")
    if not _text(db_path):
        db_path = root / "data" / "roibang_v2.sqlite3"

    result = build_create_plan_execution_review(
        plan_artifact,
        request,
        plan_path=plan_path,
        db_path=db_path,
        review_config=review_config,
        source_suggestion_preview_artifact=source_preview,
        source_suggestion_preview_path=source_suggestion_preview_path,
    )
    result["source"]["review_config_path"] = review_config_path
    artifact_path = write_run_artifact(runs_dir, WORKFLOW, result)
    result["artifact_path"] = str(artifact_path)
    return result


def _plan_ready_check(preview: dict[str, Any]) -> dict[str, Any]:
    if not preview:
        return _check(
            "plan_preview",
            "创建计划摘要",
            "blocked",
            "high",
            "创建计划 JSON 无法生成中文摘要，不能进入真实创建确认。",
        )
    blocking = [str(item) for item in preview.get("blocking_reasons") or [] if str(item)]
    warnings = [str(item) for item in preview.get("warnings") or [] if str(item)]
    if blocking:
        return _check(
            "plan_preview",
            "创建计划摘要",
            "blocked",
            "high",
            "创建计划自身存在阻断项：" + "；".join(blocking),
            {"blocking_reason_count": len(blocking)},
        )
    if warnings:
        return _check(
            "plan_preview",
            "创建计划摘要",
            "warning",
            "medium",
            "创建计划可读，但存在需要人工确认的警告：" + "；".join(warnings[:3]),
            {"warning_count": len(warnings)},
        )
    return _check("plan_preview", "创建计划摘要", "passed", "low", "创建计划摘要可读，未发现基础阻断。")


def _required_fields_check(*, plan_summary: dict[str, Any], details: dict[str, Any], plan_id: str) -> dict[str, Any]:
    missing: list[str] = []
    if not plan_id:
        missing.append("计划 ID")
    if not _text(details.get("product")):
        missing.append("产品")
    if not _text(details.get("product_key")):
        missing.append("产品 Key")
    if not _text(plan_summary.get("mode_key") or details.get("mode_key")):
        missing.append("创建模式")
    if _int(plan_summary.get("target_account_count")) <= 0:
        missing.append("账户")
    if _int(plan_summary.get("planned_project_count")) <= 0:
        missing.append("项目")
    if _int(plan_summary.get("planned_unit_count")) <= 0:
        missing.append("单元")
    if missing:
        return _check(
            "required_fields",
            "关键字段完整性",
            "blocked",
            "high",
            "创建计划缺少关键字段：" + "、".join(missing),
            {"missing": missing},
        )
    return _check("required_fields", "关键字段完整性", "passed", "low", "计划 ID、产品、模式、账户、项目和单元字段完整。")


def _batch_scope_check(
    *,
    plan_summary: dict[str, Any],
    details: dict[str, Any],
    review_config: dict[str, Any],
) -> dict[str, Any]:
    checks = _checks_config(review_config)
    accounts = details.get("accounts") if isinstance(details.get("accounts"), list) else []
    max_accounts = _int(checks.get("max_accounts_per_batch"), 0)
    if max_accounts and len(accounts) > max_accounts:
        return _check(
            "batch_scope",
            "批次范围",
            "blocked",
            "high",
            f"本批账户数 {len(accounts)} 超过单批上限 {max_accounts}。",
            {"account_count": len(accounts), "max_accounts_per_batch": max_accounts},
        )
    mode_key = _text(plan_summary.get("mode_key") or details.get("mode_key"))
    has_roi = _has_roi_goal(details)
    if checks.get("block_7r_roi_missing", True) and _is_7r_mode(mode_key) and not has_roi:
        return _check("batch_scope", "批次范围", "blocked", "high", "7R 创建模式缺少 ROI 系数字段。")
    if checks.get("block_non_7r_roi_present", True) and not _is_7r_mode(mode_key) and has_roi:
        return _check("batch_scope", "批次范围", "blocked", "high", "非 7R 创建模式不允许带 ROI 系数字段。")
    return _check(
        "batch_scope",
        "批次范围",
        "passed",
        "low",
        "本批产品、模式和 ROI 属性可作为一个执行批次复核。",
        {"account_count": len(accounts), "mode_key": mode_key},
    )


def _material_readiness_check(
    *,
    plan_summary: dict[str, Any],
    preview: dict[str, Any],
    review_config: dict[str, Any],
) -> dict[str, Any]:
    checks = _checks_config(review_config)
    min_unique = _int(checks.get("min_unique_material_count"), 1)
    min_source = _int(checks.get("min_source_material_count"), 1)
    unique_material_count = _int(plan_summary.get("unique_material_count"))
    source_material_count = _int(plan_summary.get("source_material_count"))
    missing_video_count = _int(plan_summary.get("missing_video_id_material_count"))
    reasons: list[str] = []
    if source_material_count < min_source:
        reasons.append(f"候选素材数 {source_material_count} 低于最低要求 {min_source}")
    if unique_material_count < min_unique:
        reasons.append(f"唯一素材数 {unique_material_count} 低于最低要求 {min_unique}")
    if missing_video_count:
        reasons.append(f"缺视频 ID 素材数 {missing_video_count}")
    if reasons:
        return _check(
            "material_readiness",
            "素材资格",
            "blocked",
            "high",
            "素材资格未通过：" + "；".join(reasons),
            {
                "source_material_count": source_material_count,
                "unique_material_count": unique_material_count,
                "missing_video_id_material_count": missing_video_count,
            },
        )

    warn_usage = _int(checks.get("warn_material_usage_at_or_above"), 10)
    hot_materials = [
        row
        for row in preview.get("materials") or []
        if isinstance(row, dict) and warn_usage and _int(row.get("usage_count")) >= warn_usage
    ]
    if hot_materials:
        return _check(
            "material_readiness",
            "素材资格",
            "warning",
            "medium",
            f"有 {len(hot_materials)} 个素材使用次数达到预警阈值 {warn_usage}，执行前需要确认复用风险。",
            {"warn_material_usage_at_or_above": warn_usage, "hot_material_count": len(hot_materials)},
        )
    return _check(
        "material_readiness",
        "素材资格",
        "passed",
        "low",
        "素材数量、唯一素材和视频 ID 检查通过。",
        {"source_material_count": source_material_count, "unique_material_count": unique_material_count},
    )


def _source_suggestion_check(
    *,
    plan_summary: dict[str, Any],
    preview: dict[str, Any],
    source_preview: dict[str, Any],
    source_suggestion_preview_path: str,
    review_config: dict[str, Any],
) -> dict[str, Any]:
    checks = _checks_config(review_config)
    suggestions = _source_suggestions(source_preview)
    if not suggestions:
        status = "blocked" if checks.get("require_source_suggestion_evidence", False) else "warning"
        severity = "high" if status == "blocked" else "medium"
        return _check(
            "source_suggestion_evidence",
            "来源建议证据",
            status,
            severity,
            "没有提供创建建议来源证据；手动计划需要人工核对策略、账户容量和素材资格。",
            {"source_suggestion_preview_path": source_suggestion_preview_path},
        )

    plan_accounts = set(_account_ids_from_preview(preview))
    source_accounts = set(_text(row.get("advertiser_id")) for row in suggestions if _text(row.get("advertiser_id")))
    plan_mode = _text(plan_summary.get("mode_key"))
    source_modes = {_text(row.get("mode_key") or row.get("recommended_mode_key")) for row in suggestions if _text(row.get("mode_key") or row.get("recommended_mode_key"))}
    plan_product_key = _text(plan_summary.get("product_key"))
    source_product_keys = {_text(row.get("product_key")) for row in suggestions if _text(row.get("product_key"))}
    blockers: list[str] = []
    if source_accounts and plan_accounts != source_accounts:
        blockers.append("创建计划账户与来源建议账户不一致")
    if source_modes and (len(source_modes) != 1 or plan_mode not in source_modes):
        blockers.append("创建计划模式与来源建议模式不一致")
    if source_product_keys and (len(source_product_keys) != 1 or plan_product_key not in source_product_keys):
        blockers.append("创建计划产品与来源建议产品不一致")

    account_project_count = _account_project_counts(preview)
    low_capacity: list[str] = []
    low_material: list[str] = []
    low_roi: list[str] = []
    low_conversion: list[str] = []
    min_qualified_material = _int(checks.get("min_qualified_material_count"), 1)
    min_roi = _float(checks.get("min_roi_1day"), 0)
    min_conversion = _float(checks.get("min_convert_cnt"), 0)
    for suggestion in suggestions:
        advertiser_id = _text(suggestion.get("advertiser_id"))
        planned_projects = account_project_count.get(advertiser_id, 0)
        has_project_capacity, project_capacity = _metric_value(suggestion, "project_capacity")
        if has_project_capacity and planned_projects > project_capacity:
            low_capacity.append(f"{advertiser_id} 容量 {project_capacity:g} < 计划项目 {planned_projects}")
        has_qualified_material, qualified_material = _metric_value(suggestion, "qualified_material_count")
        if min_qualified_material and has_qualified_material and qualified_material < min_qualified_material:
            low_material.append(f"{advertiser_id} 合格素材 {qualified_material:g} < {min_qualified_material}")
        has_roi, roi = _metric_value(suggestion, "roi_1day", "weighted_roi_1day", "roi")
        if min_roi and has_roi and roi < min_roi:
            low_roi.append(f"{advertiser_id} ROI {roi:g} < {min_roi:g}")
        has_conversion, convert = _metric_value(suggestion, "convert_cnt", "billing_convert_cnt")
        if min_conversion and has_conversion and convert < min_conversion:
            low_conversion.append(f"{advertiser_id} 转化 {convert:g} < {min_conversion:g}")
    blockers.extend(low_capacity)
    if checks.get("block_below_qualified_material", True):
        blockers.extend(low_material)
    if checks.get("block_below_roi", True):
        blockers.extend(low_roi)
    if checks.get("block_below_conversion", True):
        blockers.extend(low_conversion)

    if blockers:
        return _check(
            "source_suggestion_evidence",
            "来源建议证据",
            "blocked",
            "high",
            "来源建议证据未通过：" + "；".join(blockers),
            {
                "source_suggestion_count": len(suggestions),
                "strategy_ids": _source_strategy_ids(source_preview),
                "source_suggestion_preview_path": source_suggestion_preview_path,
            },
        )
    warnings = [] if checks.get("block_below_qualified_material", True) else low_material
    if warnings:
        return _check(
            "source_suggestion_evidence",
            "来源建议证据",
            "warning",
            "medium",
            "来源建议证据有预警：" + "；".join(warnings),
            {"source_suggestion_count": len(suggestions), "strategy_ids": _source_strategy_ids(source_preview)},
        )
    return _check(
        "source_suggestion_evidence",
        "来源建议证据",
        "passed",
        "low",
        "来源建议账户、产品、模式、容量、素材和阈值证据通过。",
        {"source_suggestion_count": len(suggestions), "strategy_ids": _source_strategy_ids(source_preview)},
    )


def _duplicate_ledger_check(
    *,
    db_path: str | Path | None,
    plan_id: str,
    resume_existing_plan: bool,
    review_config: dict[str, Any],
) -> dict[str, Any]:
    checks = _checks_config(review_config)
    if not checks.get("block_duplicate_plan_ledger", True):
        return _check("duplicate_ledger", "重复创建账本", "passed", "low", "配置允许跳过重复创建账本检查。")
    if not plan_id:
        return _check("duplicate_ledger", "重复创建账本", "warning", "medium", "计划 ID 为空，无法做本地创建账本去重。")
    ledger = _ledger_summary(db_path=db_path, plan_id=plan_id)
    if not ledger.get("available"):
        return _check("duplicate_ledger", "重复创建账本", "passed", "low", "本地创建账本不可用，本次未发现可用重复记录。", ledger)
    count = _int(ledger.get("count"))
    if count and not resume_existing_plan:
        return _check(
            "duplicate_ledger",
            "重复创建账本",
            "blocked",
            "high",
            f"本地账本已存在计划 {plan_id} 的创建记录 {count} 条，禁止重复创建。",
            ledger,
        )
    if count and resume_existing_plan:
        return _check(
            "duplicate_ledger",
            "重复创建账本",
            "warning",
            "medium",
            f"本地账本已存在计划 {plan_id} 的创建记录 {count} 条，本次按续跑模式复核。",
            ledger,
        )
    return _check("duplicate_ledger", "重复创建账本", "passed", "low", "本地账本未发现同计划已创建记录。", ledger)


def _ledger_summary(*, db_path: str | Path | None, plan_id: str) -> dict[str, Any]:
    if not db_path or not Path(db_path).exists():
        return {"available": False, "reason": "db_not_found", "count": 0}
    try:
        with sqlite3.connect(db_path) as conn:
            if not _table_exists(conn, "create_provider_id_ledger"):
                return {"available": False, "reason": "table_not_found", "count": 0}
            rows = conn.execute(
                """
                SELECT entity_type, COUNT(*) AS count
                FROM create_provider_id_ledger
                WHERE plan_id = ?
                  AND status = 'active'
                  AND entity_type IN ('project', 'promotion')
                GROUP BY entity_type
                """,
                (plan_id,),
            ).fetchall()
    except sqlite3.Error as exc:
        return {"available": False, "reason": f"sqlite_error:{exc}", "count": 0}
    by_entity_type = {str(row[0]): int(row[1] or 0) for row in rows}
    return {
        "available": True,
        "count": sum(by_entity_type.values()),
        "by_entity_type": by_entity_type,
    }


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ? LIMIT 1",
        (table_name,),
    ).fetchone()
    return row is not None


def _operation_record(
    *,
    generated_at: str,
    status: str,
    batch_name: str,
    plan_path: str,
    plan_id: str,
    details: dict[str, Any],
    checks: list[dict[str, Any]],
    cfg: dict[str, Any],
    source_preview: dict[str, Any],
    source_suggestion_preview_path: str,
) -> dict[str, Any]:
    return {
        "operation_type": WORKFLOW,
        "status": status,
        "created_at": generated_at,
        "operator": _text(cfg.get("operator") or cfg.get("owner")) or "local-ui",
        "batch_name": batch_name,
        "plan_id": plan_id,
        "plan_path": plan_path,
        "product": _text(details.get("product")),
        "product_key": _text(details.get("product_key")),
        "mode_key": _text(details.get("mode_key")),
        "account_count": len(details.get("accounts") or []),
        "material_assignment_count": _int(details.get("material_assignment_count")),
        "unique_material_count": _int(details.get("unique_material_count")),
        "source_suggestion_preview_path": source_suggestion_preview_path,
        "source_suggestion_ids": [_text(row.get("suggestion_id")) for row in _source_suggestions(source_preview)],
        "source_strategy_ids": _source_strategy_ids(source_preview),
        "check_results": [
            {
                "check_id": _text(check.get("check_id")),
                "status": _text(check.get("status")),
                "message": _text(check.get("message")),
            }
            for check in checks
        ],
    }


def _execution_manifest(
    *,
    status: str,
    batch_name: str,
    plan_path: str,
    plan_id: str,
    details: dict[str, Any],
    plan_summary: dict[str, Any],
    source_preview: dict[str, Any],
    generated_at: str,
    cfg: dict[str, Any],
) -> dict[str, Any]:
    return {
        "can_confirm_execution": status in {"ready_for_confirmation", "warning_only"},
        "review_status": status,
        "reviewed_at": generated_at,
        "operator": _text(cfg.get("operator") or cfg.get("owner")),
        "batch_name": batch_name,
        "plan_id": plan_id,
        "plan_path": plan_path,
        "product": _text(details.get("product")),
        "product_key": _text(details.get("product_key")),
        "mode_key": _text(plan_summary.get("mode_key") or details.get("mode_key")),
        "accounts": [
            {
                "advertiser_id": _text(row.get("advertiser_id")),
                "project_count": _int(row.get("project_count")),
                "unit_count": _int(row.get("unit_count")),
                "unique_material_count": _int(row.get("unique_material_count")),
            }
            for row in details.get("accounts") or []
            if isinstance(row, dict)
        ],
        "source_suggestions": [
            {
                "suggestion_id": _text(row.get("suggestion_id")),
                "advertiser_id": _text(row.get("advertiser_id")),
                "strategy_id": _text(row.get("strategy_id") or row.get("rule_id")),
            }
            for row in _source_suggestions(source_preview)
        ],
    }


def _source_evidence_rows(source_preview: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for suggestion in _source_suggestions(source_preview):
        rows.append(
            {
                "suggestion_id": _text(suggestion.get("suggestion_id")),
                "advertiser_id": _text(suggestion.get("advertiser_id")),
                "account_name": _text(suggestion.get("account_name") or suggestion.get("advertiser_name")),
                "strategy_id": _text(suggestion.get("strategy_id") or suggestion.get("rule_id")),
                "project_capacity": _metric_number(suggestion, "project_capacity"),
                "qualified_material_count": _metric_number(suggestion, "qualified_material_count"),
                "roi_1day": _metric_number(suggestion, "roi_1day", "weighted_roi_1day", "roi"),
                "convert_cnt": _metric_number(suggestion, "convert_cnt", "billing_convert_cnt"),
                "reason": _text(suggestion.get("reason") or suggestion.get("message")),
            }
        )
    return rows


def _risk_summary(checks: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "passed": sum(1 for check in checks if check.get("status") == "passed"),
        "warnings": sum(1 for check in checks if check.get("status") == "warning"),
        "blockers": sum(1 for check in checks if check.get("status") == "blocked"),
    }


def _check(
    check_id: str,
    title: str,
    status: str,
    severity: str,
    message: str,
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "check_id": check_id,
        "title": title,
        "status": status,
        "severity": severity,
        "message": message,
        "evidence": evidence or {},
    }


def _batch_name(
    *,
    plan_summary: dict[str, Any],
    details: dict[str, Any],
    cfg: dict[str, Any],
    review_config: dict[str, Any],
    generated_at: str,
) -> str:
    explicit = _text(cfg.get("batch_name"))
    if explicit:
        return explicit
    naming = review_config.get("batch_naming") if isinstance(review_config.get("batch_naming"), dict) else {}
    sequence = _text(cfg.get("batch_sequence") or naming.get("default_sequence")) or "01"
    target_date = _text(details.get("target_date")) or generated_at[:10]
    product = _text(details.get("product") or details.get("product_key")) or "未指定产品"
    mode = _text(plan_summary.get("mode_key") or details.get("mode_key")) or "未指定模式"
    mode_label = _mode_label(mode)
    pattern = _text(naming.get("pattern"))
    values = {
        "target_date": target_date,
        "product": product,
        "mode": mode,
        "mode_label": mode_label,
        "sequence": sequence,
    }
    if pattern:
        try:
            return pattern.format(**values)
        except (KeyError, ValueError):
            pass
    return f"{target_date} {product} {mode_label} 批次 {sequence}"


def _mode_label(mode_key: str) -> str:
    labels = {
        "wx_pay_male_random_materials": "每付男素材不限",
        "wx_pay_general_random_materials": "每付通投素材不限",
        "wx_pay_male_test_new": "每付男测新",
        "wx_pay_general_test_new": "每付通投测新",
        "wx_pay_male_recent_scale": "每付男近期放量",
        "wx_pay_general_recent_scale": "每付通投近期放量",
        "wx_pay_male_scale": "每付男历史放量",
        "wx_pay_general_scale": "每付通投历史放量",
        "wx_7r_male_recent_scale": "7R 男近期放量",
        "wx_7r_general_recent_scale": "7R 通投近期放量",
        "wx_7r_male_scale": "7R 男历史放量",
        "wx_7r_general_scale": "7R 通投历史放量",
    }
    return labels.get(mode_key, mode_key)


def _summary(plan: dict[str, Any]) -> dict[str, Any]:
    value = plan.get("summary")
    return value if isinstance(value, dict) else {}


def _checks_config(review_config: dict[str, Any]) -> dict[str, Any]:
    value = review_config.get("checks")
    return value if isinstance(value, dict) else {}


def _account_ids_from_preview(preview: dict[str, Any]) -> list[str]:
    accounts = preview.get("accounts") if isinstance(preview.get("accounts"), list) else []
    result: list[str] = []
    for row in accounts:
        if isinstance(row, dict) and _text(row.get("advertiser_id")):
            result.append(_text(row.get("advertiser_id")))
    if result:
        return _unique(result)
    units = preview.get("units") if isinstance(preview.get("units"), list) else []
    return _unique(_text(row.get("advertiser_id")) for row in units if isinstance(row, dict))


def _account_project_counts(preview: dict[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    accounts = preview.get("accounts") if isinstance(preview.get("accounts"), list) else []
    for row in accounts:
        if isinstance(row, dict) and _text(row.get("advertiser_id")):
            counts[_text(row.get("advertiser_id"))] = _int(row.get("project_count"))
    if counts:
        return counts
    projects_by_account: dict[str, set[str]] = {}
    for row in preview.get("units") or []:
        if not isinstance(row, dict):
            continue
        advertiser_id = _text(row.get("advertiser_id"))
        project_key = _text(row.get("project_key") or row.get("project_name"))
        if advertiser_id and project_key:
            projects_by_account.setdefault(advertiser_id, set()).add(project_key)
    return {advertiser_id: len(projects) for advertiser_id, projects in projects_by_account.items()}


def _source_suggestions(source_preview: dict[str, Any]) -> list[dict[str, Any]]:
    rows = source_preview.get("source_suggestions")
    if isinstance(rows, list):
        return [dict(row) for row in rows if isinstance(row, dict)]
    rows = source_preview.get("suggestions")
    if isinstance(rows, list):
        return [dict(row) for row in rows if isinstance(row, dict)]
    return []


def _source_strategy_ids(source_preview: dict[str, Any]) -> list[str]:
    strategy_ids: list[str] = []
    for group in source_preview.get("suggestion_groups") or []:
        if isinstance(group, dict):
            strategy_ids.extend(_text(item) for item in group.get("strategy_ids") or [] if _text(item))
    for suggestion in _source_suggestions(source_preview):
        strategy_ids.append(_text(suggestion.get("strategy_id") or suggestion.get("rule_id")))
    return _unique(strategy_ids)


def _metric_number(suggestion: dict[str, Any], *keys: str) -> float:
    found, value = _metric_value(suggestion, *keys)
    return value if found else 0.0


def _metric_value(suggestion: dict[str, Any], *keys: str) -> tuple[bool, float]:
    metrics = suggestion.get("metrics") if isinstance(suggestion.get("metrics"), dict) else {}
    evidence = suggestion.get("evidence") if isinstance(suggestion.get("evidence"), dict) else {}
    for key in keys:
        if key in metrics and metrics.get(key) not in (None, ""):
            return True, _number(metrics.get(key))
        if key in evidence and evidence.get(key) not in (None, ""):
            return True, _number(evidence.get(key))
    return False, 0.0


def _has_roi_goal(details: dict[str, Any]) -> bool:
    if bool(details.get("_has_roi_goal")):
        return True
    request = details
    for key in ("roi_coefficient", "roi_goal", "deep_external_action_roi"):
        if _text(request.get(key)):
            return True
    return False


def _plan_has_roi_goal(plan: dict[str, Any]) -> bool:
    request = plan.get("create_request") if isinstance(plan.get("create_request"), dict) else {}
    defaults = request.get("field_defaults") if isinstance(request.get("field_defaults"), dict) else {}
    for key in ("roi_coefficient", "roi_goal", "deep_external_action_roi"):
        if _text(request.get(key)) or _text(defaults.get(key)):
            return True
    return False


def _is_7r_mode(mode_key: str) -> bool:
    return "7r" in mode_key.lower()


def _resolve_path(root: Path, path: str) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return root / candidate


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _unique(values: Any) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _text(value)
        if text and text not in seen:
            output.append(text)
            seen.add(text)
    return output


def _text(value: Any) -> str:
    return str(value or "").strip()


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _number(value: Any) -> float:
    try:
        if value in (None, ""):
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0
