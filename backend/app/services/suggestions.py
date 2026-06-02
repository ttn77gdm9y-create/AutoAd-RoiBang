from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date
from datetime import datetime
from pathlib import Path
from typing import Any

from roibang_v2.runs import write_run_artifact
from roibang_v2.runs import write_latest_artifact
from roibang_v2.ui.background_tasks import build_runner_command
from roibang_v2.ui.background_tasks import build_task_record
from roibang_v2.ui.background_tasks import start_runner
from roibang_v2.ui.background_tasks import write_task_record
from roibang_v2.ui.script_runner import build_project_update_from_suggestions_command
from roibang_v2.ui.script_runner import build_suggestions_refresh_command
from roibang_v2.workflows.control_strategy_suggestions import build_control_strategy_suggestions
from roibang_v2.workflows.create_suggestion_lifecycle import build_create_suggestion_lifecycle
from roibang_v2.workflows.create_suggestion_strategy_review import run_create_suggestion_strategy_review_request
from roibang_v2.workflows.create_plan_from_suggestions import run_create_plan_from_suggestions_request
from roibang_v2.workflows.create_project_suggestions import build_create_project_suggestions
from roibang_v2.workflows.delivery_suggestion_backtest import run_delivery_suggestion_backtest_request
from roibang_v2.workflows.project_update_from_suggestions import build_project_update_from_suggestions

from backend.app.services.account_names import account_name_for
from backend.app.services.account_names import load_account_name_map
from backend.app.services.accounts_store import load_accounts
from backend.app.services.artifacts import find_latest_artifact
from backend.app.services.artifacts import read_json
from backend.app.services.create_plans import build_create_plan_generate_preview
from backend.app.services.realtime_snapshots import RealtimeSnapshot
from backend.app.services.realtime_snapshots import find_realtime_patrol_snapshot
from backend.app.services.realtime_snapshots import linked_suggestions_artifact
from backend.app.services.realtime_snapshots import realtime_account_ids
from backend.app.services.realtime_snapshots import realtime_account_names
from roibang_v2.workflows.product_automation_job import load_product_configs


@dataclass(frozen=True)
class SuggestionsSource:
    payload: dict[str, Any]
    path: Path | None
    warnings: list[str]


DATA_SOURCE_JOBS: list[tuple[str, str]] = [
    ("每日有消耗账户", "product_automation_job_daily_report_sync"),
    ("每日报表同步", "product_automation_job_daily_report_sync"),
    ("每日素材明细同步", "product_automation_job_material_daily_sync"),
    ("操作日志同步", "product_automation_job_operation_log_sync"),
    ("源素材表现汇总", "product_automation_job_source_material_rollup"),
    ("投放巡检建议", "delivery_patrol_suggestions"),
]

ACTION_INFO: dict[str, dict[str, str]] = {
    "suggest_delete_project": {"label": "删除项目", "priority": "高", "config_hint": "可生成项目删除配置"},
    "delete_project": {"label": "删除项目", "priority": "高", "config_hint": "可生成项目删除配置"},
    "suggest_close_project": {"label": "暂停项目", "priority": "高", "config_hint": "可生成项目暂停配置"},
    "pause_project": {"label": "暂停项目", "priority": "高", "config_hint": "可生成项目暂停配置"},
    "close_project": {"label": "暂停项目", "priority": "高", "config_hint": "可生成项目暂停配置"},
    "suggest_lower_budget": {"label": "调预算", "priority": "中", "config_hint": "可生成项目预算配置"},
    "adjust_project_budget": {"label": "调预算", "priority": "中", "config_hint": "可生成项目预算配置"},
    "suggest_lower_bid": {"label": "调出价", "priority": "中", "config_hint": "可生成项目出价配置"},
    "adjust_project_bid": {"label": "调出价", "priority": "中", "config_hint": "可生成项目出价配置"},
    "schedule_hollow": {"label": "调整时段", "priority": "中", "config_hint": "可生成项目时段配置"},
    "watch": {"label": "观察", "priority": "低", "config_hint": "观察建议，不生成动作配置"},
    "continue_running": {"label": "继续观察", "priority": "低", "config_hint": "观察建议，不生成动作配置"},
    "unit_bad_signal": {"label": "素材复用风险", "priority": "中", "config_hint": "只读诊断，不生成动作配置"},
    "unit_good_signal": {"label": "好素材", "priority": "低", "config_hint": "只读诊断，不生成动作配置"},
    "material_reuse_risk": {"label": "素材复用风险", "priority": "中", "config_hint": "只读诊断，不生成动作配置"},
    "account_spent_outside_allowlist": {"label": "账户异常", "priority": "中", "config_hint": "只读诊断，不生成动作配置"},
    "suggest_create_project": {"label": "建议创建项目", "priority": "中", "config_hint": "创建机会，进入创建计划，不生成项目管理配置"},
}

ACTION_FILTER_ALIASES: dict[str, tuple[str, ...]] = {
    "suggest_delete_project": ("suggest_delete_project", "delete_project"),
    "delete_project": ("delete_project", "suggest_delete_project"),
    "suggest_close_project": ("suggest_close_project", "pause_project", "close_project"),
    "pause_project": ("pause_project", "suggest_close_project", "close_project"),
    "close_project": ("close_project", "suggest_close_project", "pause_project"),
    "suggest_lower_budget": ("suggest_lower_budget", "adjust_project_budget"),
    "adjust_project_budget": ("adjust_project_budget", "suggest_lower_budget"),
    "suggest_lower_bid": ("suggest_lower_bid", "adjust_project_bid"),
    "adjust_project_bid": ("adjust_project_bid", "suggest_lower_bid"),
}


def build_suggestions_overview(
    *,
    project_root: str | Path,
    configs_dir: str | Path,
    runs_dir: str | Path,
    product_key: str = "",
) -> dict[str, Any]:
    products = _load_products(configs_dir, product_key=product_key)
    accounts = load_accounts(configs_dir)
    source = _load_suggestions_source(project_root, configs_dir, runs_dir, product_key=product_key)
    suggestions_path = source.path
    suggestions_payload = source.payload
    suggestions = _suggestions_in_scope(suggestions_payload, accounts, product_key=product_key)
    lifecycle = build_create_suggestion_lifecycle(
        runs_dir=runs_dir,
        project_root=project_root,
        suggestions_artifact={**suggestions_payload, "suggestions": suggestions},
        suggestions_artifact_path=str(suggestions_path or ""),
        product_key=product_key,
    )
    historical_date = _historical_evidence_date(suggestions_payload)
    patrol_date = _today_patrol_date(suggestions_payload)
    generated_at = _artifact_generated_at(suggestions_path, suggestions_payload)
    warnings = list(source.warnings or [])
    if not suggestions_path:
        warnings.append("未找到最近建议结果，当前只展示产品数据源状态。")
    warnings.extend(_suggestion_freshness_warnings(historical_date, today_patrol_date=patrol_date))
    product_rows = []
    source_rows: list[dict[str, Any]] = []

    for product in products:
        key = _text(product.get("product_key"))
        product_accounts = [account for account in accounts if _text(account.get("product_key")) == key]
        product_suggestions = _suggestions_in_scope(suggestions_payload, accounts, product_key=key)
        allowed_count = _allowed_account_count(project_root, product)
        source_path = str(suggestions_path or "")
        product_rows.append(
            {
                "产品": _text(product.get("product")) or key,
                "产品 Key": key,
                "允许创建账户": allowed_count,
                "产品账户库账户": len(product_accounts),
                "建议事项": len(product_suggestions),
                "可生成管理配置": sum(1 for item in product_suggestions if _can_convert_to_project_update(item)),
                "最近建议来源": source_path,
            }
        )
        source_rows.extend(_product_source_rows(runs_dir, product))

    if not products and suggestions:
        product_rows.append(
            {
                "产品": "未归档产品",
                "产品 Key": "",
                "允许创建账户": 0,
                "产品账户库账户": 0,
                "建议事项": len(suggestions),
                "可生成管理配置": sum(1 for item in suggestions if _can_convert_to_project_update(item)),
                "最近建议来源": str(suggestions_path or ""),
            }
        )

    return {
        "summary": {
            "title": "投放建议工作台",
            "status": "loaded",
            "risk_level": "medium" if suggestions else "low",
            "execution_enabled": False,
            "items": [
                {"label": "产品数", "value": len(product_rows)},
                {"label": "建议事项", "value": len(suggestions)},
                {"label": "可生成管理配置", "value": sum(1 for item in suggestions if _can_convert_to_project_update(item))},
                {"label": "已锁定创建建议", "value": int(lifecycle.get("summary", {}).get("locked_suggestion_count") or 0)},
                *_suggestion_context_items(suggestions_payload, generated_at=generated_at),
            ],
            "warnings": warnings,
            "blocking_reasons": [],
        },
        "table": {
            "columns": ["产品", "产品 Key", "允许创建账户", "产品账户库账户", "建议事项", "可生成管理配置", "最近建议来源"],
            "rows": product_rows,
        },
        "sections": [
            {
                "title": "产品数据源",
                "table": {"columns": ["产品", "产品 Key", "数据源", "workflow", "状态", "最近文件"], "rows": source_rows},
            }
        ],
        "artifact_path": str(suggestions_path or ""),
        "raw": {
            "products": products,
            "suggestions_artifact_path": str(suggestions_path or ""),
            "suggestions": suggestions,
        },
    }


def build_suggestions_list(
    *,
    project_root: str | Path,
    configs_dir: str | Path,
    runs_dir: str | Path,
    product_key: str = "",
) -> dict[str, Any]:
    accounts = load_accounts(configs_dir)
    account_names = _latest_account_name_map(project_root, configs_dir)
    account_names.update(_latest_patrol_account_name_map(project_root, configs_dir, runs_dir, product_key=product_key))
    source = _load_suggestions_source(project_root, configs_dir, runs_dir, product_key=product_key)
    suggestion_account_names = _account_names_from_suggestions(_rows(source.payload.get("suggestions")))
    product_by_account = {str(account.get("advertiser_id") or ""): str(account.get("product_name") or "") for account in accounts}
    suggestions_path = source.path
    suggestions_payload = source.payload
    suggestions = _suggestions_in_scope(suggestions_payload, accounts, product_key=product_key)
    lifecycle = build_create_suggestion_lifecycle(
        runs_dir=runs_dir,
        project_root=project_root,
        suggestions_artifact={**suggestions_payload, "suggestions": suggestions},
        suggestions_artifact_path=str(suggestions_path or ""),
        product_key=product_key,
    )
    lifecycle_by_id = lifecycle.get("by_suggestion_id") if isinstance(lifecycle.get("by_suggestion_id"), dict) else {}
    historical_date = _historical_evidence_date(suggestions_payload)
    patrol_date = _today_patrol_date(suggestions_payload)
    generated_at = _artifact_generated_at(suggestions_path, suggestions_payload)
    warnings = list(source.warnings or [])
    if not suggestions_path:
        warnings.append("未找到最近建议结果，当前显示为空。")
    warnings.extend(_suggestion_freshness_warnings(historical_date, today_patrol_date=patrol_date))
    rows = []
    for suggestion in suggestions:
        advertiser_id = _text(suggestion.get("advertiser_id"))
        action = _suggestion_action(suggestion)
        action_info = _action_info(action)
        lifecycle_record = lifecycle_by_id.get(_text(suggestion.get("suggestion_id")))
        lifecycle_record = lifecycle_record if isinstance(lifecycle_record, dict) else {}
        rows.append(
            _suggestion_list_row(
                suggestion,
                action_info=action_info,
                lifecycle_record=lifecycle_record,
                product_name=_text(suggestion.get("product_name")) or product_by_account.get(advertiser_id, "未归档产品"),
                account_name=account_name_for(account_names, advertiser_id, fallback="")
                or suggestion_account_names.get(advertiser_id, "")
                or _text(suggestion.get("account_name") or suggestion.get("advertiser_name")),
                suggestions_path=suggestions_path,
            )
        )
    return {
        "summary": {
            "title": "建议列表",
            "status": "loaded",
            "risk_level": "medium" if rows else "low",
            "execution_enabled": False,
            "items": [
                {"label": "建议事项", "value": len(rows)},
                {"label": "可生成管理配置", "value": sum(1 for item in suggestions if _can_convert_to_project_update(item))},
                {"label": "已锁定创建建议", "value": int(lifecycle.get("summary", {}).get("locked_suggestion_count") or 0)},
                *_suggestion_context_items(suggestions_payload, generated_at=generated_at),
            ],
            "warnings": warnings,
            "blocking_reasons": [],
        },
        "table": {
            "columns": [
                "建议内容",
                "建议对象",
                "建议类型",
                "下一步",
                "证据摘要",
                "优先级",
                "产品",
                "账户名",
                "账户 ID",
                "层级",
                "项目名",
                "项目 ID",
                "建议动作",
                "推荐模式",
                "命中策略",
                "中文解释",
                "关键指标",
                "创建状态",
                "计划预览",
                "执行前复核",
                "执行任务",
                "最近事件",
                "数据来源",
                "可生成管理配置",
                "建议 ID",
                "来源文件",
            ],
            "rows": rows,
        },
        "artifact_path": str(suggestions_path or ""),
        "raw": {
            "suggestions": suggestions,
            "suggestions_artifact_path": str(suggestions_path or ""),
            "lifecycle": lifecycle,
        },
    }


def _suggestion_list_row(
    suggestion: dict[str, Any],
    *,
    action_info: dict[str, str],
    lifecycle_record: dict[str, Any],
    product_name: str,
    account_name: str,
    suggestions_path: Path | None,
) -> dict[str, Any]:
    advertiser_id = _text(suggestion.get("advertiser_id"))
    entity_type = _entity_type_label(_text(suggestion.get("entity_type") or suggestion.get("target_level") or suggestion.get("level")))
    project_id = _text(suggestion.get("project_id") or suggestion.get("entity_id"))
    project_name = _text(suggestion.get("project_name") or suggestion.get("entity_name"))
    action = _suggestion_action(suggestion)
    action_label = action_info["label"]
    mode_key = _text(suggestion.get("mode_key") or suggestion.get("recommended_mode_key"))
    category = _suggestion_category_label(suggestion)
    return {
        "建议内容": _suggestion_title(
            action_label=action_label,
            product_name=product_name,
            account_name=account_name,
            project_name=project_name,
            project_id=project_id,
            mode_key=mode_key,
        ),
        "建议对象": _suggestion_target_text(
            entity_type=entity_type,
            account_name=account_name,
            advertiser_id=advertiser_id,
            project_name=project_name,
            project_id=project_id,
        ),
        "建议类型": category,
        "下一步": _suggestion_next_step(suggestion, lifecycle_record),
        "证据摘要": _suggestion_evidence_summary(suggestion),
        "建议 ID": _text(suggestion.get("suggestion_id")),
        "创建状态": _text(lifecycle_record.get("lifecycle_label")) or "未处理",
        "计划预览": _text(lifecycle_record.get("plan_preview_path")),
        "执行前复核": _text(lifecycle_record.get("execution_review_path")),
        "执行任务": _text(lifecycle_record.get("execution_task_id")),
        "最近事件": _text(lifecycle_record.get("last_event_at")),
        "创建建议锁定": bool(lifecycle_record.get("locked_for_create_plan")),
        "优先级": action_info["priority"],
        "产品": product_name,
        "账户 ID": advertiser_id,
        "账户名": account_name,
        "层级": entity_type,
        "项目 ID": project_id,
        "项目名": project_name,
        "建议动作": action_label,
        "推荐模式": mode_key,
        "命中策略": _text(suggestion.get("strategy_id") or suggestion.get("rule_id")),
        "中文解释": _text(suggestion.get("reason") or suggestion.get("message") or "需要人工复核该建议。"),
        "关键指标": _metrics_text(suggestion.get("metrics")),
        "数据来源": _source_label(suggestion),
        "可生成管理配置": action_info["config_hint"],
        "可转动作 JSON": action_info["config_hint"],
        "来源文件": str(suggestions_path or ""),
    }


def _suggestion_title(
    *,
    action_label: str,
    product_name: str,
    account_name: str,
    project_name: str,
    project_id: str,
    mode_key: str,
) -> str:
    target = project_name or project_id or account_name
    parts = [part for part in [action_label, product_name, target] if part]
    if mode_key and action_label == "建议创建项目":
        parts.append(mode_key)
    return "｜".join(parts) or "需要人工复核的建议"


def _suggestion_target_text(
    *,
    entity_type: str,
    account_name: str,
    advertiser_id: str,
    project_name: str,
    project_id: str,
) -> str:
    account = _name_with_id(account_name, advertiser_id)
    project = _name_with_id(project_name, project_id)
    if entity_type == "账户" or not project:
        return f"账户：{account}" if account else "账户：未识别"
    suffix = f"｜账户：{account}" if account else ""
    return f"{entity_type or '对象'}：{project}{suffix}"


def _name_with_id(name: str, value_id: str) -> str:
    if name and value_id and name != value_id:
        return f"{name}（{value_id}）"
    return name or value_id


def _suggestion_category_label(suggestion: dict[str, Any]) -> str:
    action = _suggestion_action(suggestion).strip().lower()
    if action == "suggest_create_project":
        return "扩量机会"
    if _can_convert_to_project_update(suggestion):
        return "项目管理建议"
    return "只读诊断"


def _suggestion_next_step(suggestion: dict[str, Any], lifecycle_record: dict[str, Any]) -> str:
    if bool(lifecycle_record.get("locked_for_create_plan")):
        return "已进入执行链路"
    action = _suggestion_action(suggestion).strip().lower()
    if action == "suggest_create_project":
        return "生成创建项目计划"
    if _can_convert_to_project_update(suggestion):
        return "生成项目管理配置"
    return "只读观察"


def _suggestion_evidence_summary(suggestion: dict[str, Any]) -> str:
    parts = [_metrics_text(suggestion.get("metrics"))]
    evidence = suggestion.get("evidence") if isinstance(suggestion.get("evidence"), dict) else {}
    if evidence:
        evidence_parts = []
        for label, key in [
            ("当前项目", "current_project_count"),
            ("项目容量", "project_capacity"),
            ("合格素材", "qualified_material_count"),
        ]:
            if key in evidence and evidence.get(key) not in (None, ""):
                evidence_parts.append(f"{label} {evidence.get(key)}")
        if evidence_parts:
            parts.append("，".join(evidence_parts))
    blocking_reasons = [_text(item) for item in suggestion.get("blocking_reasons") or [] if _text(item)]
    if blocking_reasons:
        parts.append(f"阻断：{'；'.join(blocking_reasons)}")
    reason = _text(suggestion.get("reason") or suggestion.get("message"))
    parts = [part for part in parts if part]
    if parts:
        return "；".join(parts)
    return reason or "等待人工复核"


def build_suggestions_lifecycle(
    *,
    project_root: str | Path,
    configs_dir: str | Path,
    runs_dir: str | Path,
    product_key: str = "",
) -> dict[str, Any]:
    accounts = load_accounts(configs_dir)
    source = _load_suggestions_source(project_root, configs_dir, runs_dir, product_key=product_key)
    suggestions = _suggestions_in_scope(source.payload, accounts, product_key=product_key)
    lifecycle = build_create_suggestion_lifecycle(
        runs_dir=runs_dir,
        project_root=project_root,
        suggestions_artifact={**source.payload, "suggestions": suggestions},
        suggestions_artifact_path=str(source.path or ""),
        product_key=product_key,
    )
    rows = [_lifecycle_table_row(row) for row in _rows(lifecycle.get("lifecycle"))]
    return {
        "summary": {
            "title": "创建建议生命周期",
            "status": "loaded",
            "risk_level": "medium" if any(row["锁定"] == "是" for row in rows) else "low",
            "execution_enabled": False,
            "items": [
                {"label": "创建建议", "value": len(rows)},
                {"label": "已锁定", "value": int(lifecycle.get("summary", {}).get("locked_suggestion_count") or 0)},
                {"label": "来源建议文件", "value": str(source.path or "")},
            ],
            "warnings": [
                "生命周期只读取本地 artifact；已进入真实执行链路的创建建议会被锁定，不能重复生成创建计划。"
            ],
            "blocking_reasons": [],
        },
        "table": {
            "columns": ["建议 ID", "创建状态", "锁定", "计划预览", "执行前复核", "执行任务", "最近事件", "阻断原因", "警告"],
            "rows": rows,
        },
        "artifact_path": str(source.path or ""),
        "raw": lifecycle,
    }


def build_suggestions_create_strategy_review(
    *,
    project_root: str | Path,
    configs_dir: str | Path,
    runs_dir: str | Path,
    product_key: str = "",
) -> dict[str, Any]:
    root = Path(project_root)
    realtime_snapshot = find_realtime_patrol_snapshot(
        project_root=root,
        configs_dir=configs_dir,
        runs_dir=runs_dir,
        product_key=product_key,
        purpose="suggestions",
    )
    target_account_ids = realtime_account_ids(realtime_snapshot) if realtime_snapshot.required else None
    target_account_names = realtime_account_names(realtime_snapshot) if realtime_snapshot.required else None
    result = run_create_suggestion_strategy_review_request(
        {
            "db_path": str(root / "data" / "roibang_v2.sqlite3"),
            "project_root": str(root),
            "products_dir": str(Path(configs_dir) / "products"),
            "mode_dir": str(Path(configs_dir) / "create-modes"),
            "template_dir": str(Path(configs_dir) / "create-templates"),
            "strategy_dir": str(Path(configs_dir) / "create-suggestion-strategies"),
            "product_key": product_key,
            "include_examples": True,
            "target_account_ids": target_account_ids,
            "target_account_names": target_account_names or {},
        },
        runs_dir=runs_dir,
    )
    rows = [_create_strategy_review_row(row) for row in _rows(result.get("strategy_reviews"))]
    summary = result.get("summary") if isinstance(result.get("summary"), dict) else {}
    warning_count = int(summary.get("warning_strategy_count") or 0)
    blocked_count = int(summary.get("blocked_strategy_count") or 0)
    disabled_count = int(summary.get("disabled_strategy_count") or 0)
    estimated_suggestion_count = int(summary.get("estimated_suggestion_count") or 0)
    warnings = [
        "这里只读扫描账户容量、素材门槛和转化/ROI 规则；不修改策略、不生成创建计划、不执行真实创建。"
    ]
    warnings.extend(realtime_snapshot.warnings)
    if disabled_count:
        warnings.append("存在未启用或示例策略；示例策略不会被自动建议生成器加载。")
    if estimated_suggestion_count == 0:
        warnings.append("当前命中预估为 0；请先查看阻断原因、修复建议和数据源状态。")
    blocking_reasons = [
        _text(item) for item in result.get("blocking_reasons") or [] if _text(item)
    ]
    status = "blocked" if blocked_count or blocking_reasons else ("warning" if warning_count or disabled_count else "loaded")
    return {
        "summary": {
            "title": "扩量机会扫描",
            "status": status,
            "risk_level": "medium" if blocked_count or warning_count else "low",
            "execution_enabled": False,
            "items": [
                {"label": "策略配置", "value": int(summary.get("strategy_count") or 0)},
                {"label": "检查行", "value": int(summary.get("review_count") or 0)},
                {"label": "启用策略", "value": int(summary.get("enabled_strategy_count") or 0)},
                {"label": "健康策略", "value": int(summary.get("healthy_strategy_count") or 0)},
                {"label": "需关注策略", "value": warning_count},
                {"label": "阻断策略", "value": blocked_count},
                {"label": "预计候选账户", "value": int(summary.get("estimated_candidate_account_count") or 0)},
                {"label": "预计创建建议", "value": estimated_suggestion_count},
            ],
            "warnings": warnings,
            "blocking_reasons": blocking_reasons,
        },
        "table": {
            "columns": [
                "策略 ID",
                "版本",
                "状态",
                "启用",
                "来源",
                "产品",
                "产品 Key",
                "推荐模式",
                "模式配置",
                "模板",
                "策略文件",
                "允许账户",
                "账户池",
                "候选账户",
                "合格素材",
                "预计建议",
                "阻断候选",
                "账户阈值",
                "素材阈值",
                "推荐创建",
                "阻断原因",
                "警告",
                "修复建议",
            ],
            "rows": rows,
        },
        "artifact_path": _text(result.get("artifact_path")),
        "raw": result,
    }


def start_suggestions_refresh_task(
    request: dict[str, Any],
    *,
    project_root: str | Path,
) -> dict[str, Any]:
    root = Path(project_root)
    runs_dir = root / "data" / "runs"
    product_key = _text(request.get("product_key"))
    target_date = _text(request.get("target_date")) or "today"
    normalized_request = {
        "product_key": product_key,
        "target_date": target_date,
        "enable_readonly": True,
    }
    command = build_suggestions_refresh_command(
        product_key=product_key,
        target_date=target_date,
        enable_readonly=True,
    )
    task = build_task_record(
        runs_dir=runs_dir,
        operation_type="suggestions_refresh",
        command=command,
        cwd=str(root),
        request=normalized_request,
    )
    task_path = write_task_record(runs_dir, task)
    pid = start_runner(build_runner_command(task_path), cwd=root)
    task["pid"] = pid
    write_task_record(runs_dir, task)
    rows = [
        {"步骤": "1", "内容": "每日报表同步", "真实执行": "否，只读同步"},
        {"步骤": "2", "内容": "每日素材明细同步", "真实执行": "否，只读同步"},
        {"步骤": "3", "内容": "操作日志同步", "真实执行": "否，只读同步"},
        {"步骤": "4", "内容": "源素材表现汇总", "真实执行": "否，本地重算"},
        {"步骤": "5", "内容": "小时投放巡检", "真实执行": "否，只读同步"},
        {"步骤": "6", "内容": "规则建议重算", "真实执行": "否，本地重算"},
    ]
    return {
        "summary": {
            "title": "同步数据并重算建议任务",
            "status": "queued",
            "risk_level": "medium",
            "execution_enabled": False,
            "items": [
                {"label": "产品", "value": product_key or "全部产品"},
                {"label": "目标日期", "value": target_date},
                {"label": "任务 ID", "value": task["task_id"]},
                {"label": "任务状态", "value": task["status"]},
            ],
            "warnings": ["该任务只跑固定只读同步和本地建议重算，不执行删除、暂停、预算、出价或创建动作。"],
            "blocking_reasons": [],
        },
        "table": {"columns": ["步骤", "内容", "真实执行"], "rows": rows},
        "artifact_path": str(task_path),
        "task": task,
        "raw": {"task": task, "request": normalized_request},
    }


def build_suggestions_project_update_preview(
    request: dict[str, Any],
    *,
    project_root: str | Path,
) -> dict[str, Any]:
    root = Path(project_root)
    suggestions_path = _resolve_path(root, _text(request.get("suggestions_artifact_path")))
    if not suggestions_path.exists():
        return _blocked_project_update_preview(request, f"建议来源文件不存在：{request.get('suggestions_artifact_path') or ''}")
    normalized_request = dict(request)
    project_update_id = _text(normalized_request.get("project_update_id")) or _default_project_update_id()
    normalized_request["project_update_id"] = project_update_id
    normalized_request["output_path"] = _text(normalized_request.get("output_path")) or _default_project_update_path(project_update_id)
    suggestions_artifact = read_json(suggestions_path)
    configs_dir = root / "configs"
    accounts = load_accounts(configs_dir)
    account_names = load_account_name_map(configs_dir)
    selected_suggestions = _filter_suggestions_for_project_update_request(
        _rows(suggestions_artifact.get("suggestions")),
        normalized_request,
    )
    account_names.update(_account_names_from_suggestions(selected_suggestions))
    product_key, product_name = _project_update_product_metadata(configs_dir, accounts, selected_suggestions, normalized_request)
    blocking_reasons = _project_update_validation_reasons(selected_suggestions, normalized_request, account_names)
    blocking_reasons.extend(
        _realtime_scope_validation_reasons(
            project_root=root,
            configs_dir=configs_dir,
            runs_dir=root / "data" / "runs",
            product_key=product_key,
            suggestions=selected_suggestions,
        )
    )
    if blocking_reasons:
        return _blocked_project_update_preview(normalized_request, blocking_reasons)
    build_request = dict(normalized_request)
    build_request["suggestions_artifact_path"] = str(suggestions_path)
    build_request["product_key"] = product_key
    build_request["product_name"] = product_name
    build_request["account_names"] = account_names
    try:
        payload = build_project_update_from_suggestions(suggestions_artifact, build_request)
    except ValueError as exc:
        return _blocked_project_update_preview(request, str(exc))

    actions = [action for action in payload["project_update"].get("actions", []) if isinstance(action, dict)]
    rows = [_project_action_row(action, account_names) for action in actions]
    return {
        "summary": {
            "title": "项目管理配置预览",
            "status": "planned",
            "risk_level": "high" if any(_text(action.get("action_type")) == "delete_project" for action in actions) else "medium",
            "execution_enabled": False,
            "items": [
                {"label": "配置 ID", "value": _text(normalized_request.get("project_update_id"))},
                {"label": "来源建议", "value": payload["summary"]["selected_suggestion_count"]},
                {"label": "动作数", "value": payload["summary"]["action_count"]},
                {"label": "输出配置", "value": _text(normalized_request.get("output_path"))},
            ],
            "warnings": ["这里只生成项目管理配置，不执行删除、暂停、预算、出价或时段调整。"],
            "blocking_reasons": [],
        },
        "table": {"columns": ["账户 ID", "账户名", "项目 ID", "项目名", "动作", "原因"], "rows": rows},
        "artifact_path": str(suggestions_path),
        "raw": {
            "request": normalized_request,
            "summary": payload["summary"],
            "project_update": payload["project_update"],
        },
    }


def build_suggestions_create_plan_preview(
    request: dict[str, Any],
    *,
    project_root: str | Path,
    configs_dir: str | Path,
    runs_dir: str | Path,
) -> dict[str, Any]:
    root = Path(project_root)
    suggestions_path = _resolve_path(root, _text(request.get("suggestions_artifact_path")))
    if not _text(request.get("suggestions_artifact_path")):
        source = _load_suggestions_source(project_root, configs_dir, runs_dir, product_key=_text(request.get("product_key")))
        suggestions_path = source.path if source.path else suggestions_path
    if not suggestions_path.is_file():
        return _blocked_create_plan_preview(request, f"建议来源文件不存在：{request.get('suggestions_artifact_path') or ''}")

    normalized_request = dict(request)
    normalized_request["suggestions_artifact_path"] = str(suggestions_path)
    suggestions_artifact = read_json(suggestions_path)
    lifecycle = build_create_suggestion_lifecycle(
        runs_dir=runs_dir,
        project_root=root,
        suggestions_artifact=suggestions_artifact,
        suggestions_artifact_path=str(suggestions_path),
        product_key=_text(normalized_request.get("product_key")),
    )
    locked_reasons = _locked_create_suggestion_reasons(lifecycle, _request_selected_suggestion_ids(normalized_request))
    if locked_reasons:
        return _blocked_create_plan_preview(normalized_request, locked_reasons)
    result = run_create_plan_from_suggestions_request(
        {
            **normalized_request,
            "project_root": str(root),
            "template_dir": str(Path(configs_dir) / "create-templates"),
        },
        runs_dir=runs_dir,
    )
    create_plan_request = result.get("create_plan_request") if isinstance(result.get("create_plan_request"), dict) else {}
    generate_preview = build_create_plan_generate_preview(create_plan_request, project_root=root) if create_plan_request else {}
    generate_summary = generate_preview.get("summary") if isinstance(generate_preview.get("summary"), dict) else {}
    blocking_reasons = list(result.get("blocking_reasons") or [])
    blocking_reasons.extend(str(item) for item in generate_summary.get("blocking_reasons") or [] if str(item))
    workflow_status = _text(result.get("status"))
    status = "blocked" if blocking_reasons else ("split_required" if workflow_status == "split_required" else "planned")
    rows = generate_preview.get("table", {}).get("rows", []) if isinstance(generate_preview.get("table"), dict) else []
    group_rows = _create_plan_group_rows(result)
    table = (
        generate_preview.get("table")
        if isinstance(generate_preview.get("table"), dict) and workflow_status != "split_required"
        else {
            "columns": ["批次", "产品", "推荐模式", "账户数", "来源建议", "命中策略", "模板", "证据", "状态"],
            "rows": group_rows,
        }
    )
    warnings = [
        "这里只生成创建计划请求预览，不生成创建计划 JSON，不执行真实创建。",
        "下一步必须进入创建计划页重新核对并人工确认。",
    ]
    warnings.extend(str(item) for item in generate_summary.get("warnings") or [] if str(item))
    warnings.extend(str(item) for item in result.get("split_reasons") or [] if str(item))
    summary = result.get("summary") if isinstance(result.get("summary"), dict) else {}
    account_count = len(rows) if rows else int(summary.get("account_count") or 0)
    return {
        "summary": {
            "title": "生成创建项目计划预览",
            "status": status,
            "risk_level": "medium",
            "execution_enabled": False,
            "items": [
                {"label": "来源建议", "value": int(summary.get("source_suggestion_count") or 0)},
                {"label": "建议批次", "value": int(summary.get("suggestion_group_count") or 0)},
                {"label": "账户数", "value": account_count},
                {"label": "需拆分", "value": "是" if bool(summary.get("split_required")) else "否"},
                {"label": "产品", "value": _text(create_plan_request.get("product_name"))},
                {"label": "推荐模式", "value": _text(create_plan_request.get("mode"))},
                {"label": "目标日期", "value": _text(create_plan_request.get("target_date"))},
                {"label": "创建预览", "value": _text(result.get("artifact_path"))},
            ],
            "warnings": warnings,
            "blocking_reasons": blocking_reasons,
        },
        "table": table,
        "sections": _create_plan_preview_sections(result),
        "artifact_path": _text(result.get("artifact_path")),
        "raw": {
            "request": normalized_request,
            "create_plan_request": create_plan_request,
            "suggestion_groups": _rows(result.get("suggestion_groups")),
            "split_reasons": [str(item) for item in result.get("split_reasons") or [] if str(item)],
            "create_plan_from_suggestions": result,
            "generate_preview": generate_preview,
        },
    }


def start_suggestions_project_update_task(
    request: dict[str, Any],
    *,
    project_root: str | Path,
) -> dict[str, Any]:
    preview = build_suggestions_project_update_preview(request, project_root=project_root)
    if preview["summary"]["status"] == "blocked":
        return preview

    root = Path(project_root)
    runs_dir = root / "data" / "runs"
    project_update = preview["raw"]["project_update"] if isinstance(preview.get("raw"), dict) else {}
    preview_request = preview["raw"].get("request") if isinstance(preview.get("raw"), dict) else request
    preview_request = preview_request if isinstance(preview_request, dict) else request
    command = build_project_update_from_suggestions_command(
        suggestions_artifact_path=_text(preview.get("artifact_path")) or _text(preview_request.get("suggestions_artifact_path")),
        project_update_id=_text(preview_request.get("project_update_id")),
        operator=_text(preview_request.get("operator")),
        product_key=_text(project_update.get("product_key")),
        product_name=_text(project_update.get("product_name")),
        allowed_target_accounts_path=_text(preview_request.get("allowed_target_accounts_path")),
        selected_suggestion_ids=[_text(item) for item in preview_request.get("selected_suggestion_ids", []) if _text(item)],
        suggested_actions=[_text(item) for item in preview_request.get("suggested_actions", []) if _text(item)],
        account_names=_account_names_from_project_update(project_update),
        output_path=_text(preview_request.get("output_path")),
    )
    task = build_task_record(
        runs_dir=runs_dir,
        operation_type="suggestions_project_update_generate",
        command=command,
        cwd=str(root),
        request=preview_request,
    )
    task_path = write_task_record(runs_dir, task)
    pid = start_runner(build_runner_command(task_path), cwd=root)
    task["pid"] = pid
    write_task_record(runs_dir, task)
    return {
        "summary": {
            "title": "项目管理配置生成任务",
            "status": "queued",
            "risk_level": preview["summary"]["risk_level"],
            "execution_enabled": False,
            "items": [
                *preview["summary"]["items"],
                {"label": "任务 ID", "value": task["task_id"]},
                {"label": "任务状态", "value": task["status"]},
            ],
            "warnings": ["生成任务已提交；任务只写项目管理配置，不执行真实业务动作。"],
            "blocking_reasons": [],
        },
        "table": preview["table"],
        "artifact_path": str(task_path),
        "task": task,
        "raw": {"preview": preview, "task": task},
    }


def build_suggestions_ai_draft(
    request: dict[str, Any],
    *,
    project_root: str | Path,
    configs_dir: str | Path,
    runs_dir: str | Path,
) -> dict[str, Any]:
    root = Path(project_root)
    suggestions_path = _resolve_path(root, _text(request.get("suggestions_artifact_path")))
    if not _text(request.get("suggestions_artifact_path")):
        source = _load_suggestions_source(project_root, configs_dir, runs_dir, product_key=_text(request.get("product_key")))
        suggestions_path = source.path if source.path else suggestions_path
    if not suggestions_path.exists():
        return _blocked_ai_draft(f"建议来源文件不存在：{request.get('suggestions_artifact_path') or ''}")

    accounts = load_accounts(configs_dir)
    account_names = load_account_name_map(configs_dir)
    suggestions_artifact = read_json(suggestions_path)
    scoped_suggestions = _suggestions_in_scope(suggestions_artifact, accounts, product_key=_text(request.get("product_key")))
    selected_suggestions = _filter_suggestions_for_project_update_request(scoped_suggestions, request)
    account_names.update(_account_names_from_suggestions(selected_suggestions))
    product_key, product_name = _project_update_product_metadata(configs_dir, accounts, selected_suggestions, request)
    product_by_account = {str(account.get("advertiser_id") or ""): str(account.get("product_name") or "") for account in accounts}

    build_request = dict(request)
    build_request["project_update_id"] = _text(build_request.get("project_update_id")) or "ai-suggestions-draft"
    build_request["suggestions_artifact_path"] = str(suggestions_path)
    build_request["product_key"] = product_key
    build_request["product_name"] = product_name
    build_request["account_names"] = account_names
    convertible_suggestions = [suggestion for suggestion in selected_suggestions if _can_convert_to_project_update(suggestion)]
    build_request["selected_suggestion_ids"] = []
    build_request["suggested_actions"] = []
    draft_payload = build_project_update_from_suggestions(
        {**suggestions_artifact, "suggestions": convertible_suggestions},
        build_request,
    )
    draft_project_update = draft_payload["project_update"]
    draft_project_update["draft_only"] = True

    rows = [
        _ai_draft_row(
            suggestion,
            account_names=account_names,
            product_by_account=product_by_account,
        )
        for suggestion in selected_suggestions
    ]
    action_count = len([action for action in draft_project_update.get("actions", []) if isinstance(action, dict)])
    readonly_count = sum(1 for suggestion in selected_suggestions if not _can_convert_to_project_update(suggestion))
    summary = {
        "title": "AI 建议草稿",
        "status": "draft_only",
        "risk_level": "medium" if selected_suggestions else "low",
        "execution_enabled": False,
        "items": [
            {"label": "来源建议", "value": len(selected_suggestions)},
            {"label": "项目管理配置草稿", "value": action_count},
            {"label": "只读建议", "value": readonly_count},
        ],
        "warnings": ["AI 建议只生成解释和草稿；真实执行仍需项目管理页人工确认。"],
        "blocking_reasons": [],
    }
    raw = {
        "中文摘要": f"AI 建议草稿整理了 {len(selected_suggestions)} 条规则建议，生成 {action_count} 个项目管理配置草稿；不执行真实业务动作。",
        "workflow": "ai_suggestion_drafts",
        "source_artifact": str(suggestions_path),
        "ai_policy": {
            "draft_only": True,
            "external_api_calls": 0,
            "execution_enabled": False,
            "note": "AI 建议只解释和生成草稿，不执行真实业务动作。",
        },
        "draft_project_update": draft_project_update,
        "suggestions": selected_suggestions,
    }
    result = {
        "summary": summary,
        "table": {
            "columns": [
                "建议 ID",
                "产品",
                "账户名",
                "账户 ID",
                "项目名",
                "项目 ID",
                "建议动作",
                "AI 中文解释",
                "复核点",
                "草稿状态",
            ],
            "rows": rows,
        },
        "artifact_path": "",
        "raw": raw,
    }
    artifact_path = write_run_artifact(runs_dir, "ai_suggestion_drafts", result)
    result["artifact_path"] = str(artifact_path)
    return result


def build_suggestions_backtest(
    request: dict[str, Any],
    *,
    project_root: str | Path,
    configs_dir: str | Path,
    runs_dir: str | Path,
) -> dict[str, Any]:
    root = Path(project_root)
    db_path = root / "data" / "roibang_v2.sqlite3"
    if not db_path.exists():
        return _blocked_backtest_preview(f"本地回测数据库不存在：{db_path}")

    suggestions_path = _resolve_path(root, _text(request.get("suggestions_artifact_path")))
    if not _text(request.get("suggestions_artifact_path")):
        source = _load_suggestions_source(project_root, configs_dir, runs_dir, product_key=_text(request.get("product_key")))
        suggestions_path = source.path if source.path else suggestions_path
    if not suggestions_path.exists():
        return _blocked_backtest_preview(f"建议来源文件不存在：{request.get('suggestions_artifact_path') or ''}")

    accounts = load_accounts(configs_dir)
    account_names = load_account_name_map(configs_dir)
    suggestions_artifact = read_json(suggestions_path)
    scoped_suggestions = _suggestions_in_scope(suggestions_artifact, accounts, product_key=_text(request.get("product_key")))
    scoped_artifact = {**suggestions_artifact, "suggestions": scoped_suggestions}
    result = run_delivery_suggestion_backtest_request(
        {
            "suggestions_artifact": scoped_artifact,
            "suggestions_artifact_paths": [],
            "db_path": str(db_path),
            "project_root": str(root),
            "lookahead_days": int(request.get("lookahead_days") or 1),
            "max_after_stat_cost": float(request.get("max_after_stat_cost") or 100),
            "max_after_convert_cnt": float(request.get("max_after_convert_cnt") or 0),
        },
        runs_dir=runs_dir,
    )
    return _suggestions_backtest_response(
        result,
        accounts=accounts,
        account_names=account_names,
        title="建议回测",
        warnings=["建议回测只读取本地历史数据，不执行真实业务动作。"],
    )


def build_suggestions_effect_review(
    *,
    project_root: str | Path,
    configs_dir: str | Path,
    runs_dir: str | Path,
    product_key: str = "",
) -> dict[str, Any]:
    root = Path(project_root)
    db_path = root / "data" / "roibang_v2.sqlite3"
    if not db_path.exists():
        return _blocked_effect_review(f"本地复盘数据库不存在：{db_path}")

    source = _load_suggestions_source(project_root, configs_dir, runs_dir, product_key=product_key)
    if not source.payload:
        return _blocked_effect_review("未找到可复盘的建议结果。")

    accounts = load_accounts(configs_dir)
    account_names = load_account_name_map(configs_dir)
    scoped_suggestions = _suggestions_in_scope(source.payload, accounts, product_key=product_key)
    scoped_artifact = {**source.payload, "suggestions": scoped_suggestions}
    result = run_delivery_suggestion_backtest_request(
        {
            "suggestions_artifact": scoped_artifact,
            "suggestions_artifact_paths": [],
            "db_path": str(db_path),
            "project_root": str(root),
            "lookahead_days": 1,
            "max_after_stat_cost": 100,
            "max_after_convert_cnt": 0,
        },
        runs_dir=runs_dir,
    )
    response = _suggestions_backtest_response(
        result,
        accounts=accounts,
        account_names=account_names,
        title="建议效果复盘",
        warnings=[
            "自动复盘只读取本地建议、生命周期和历史数据；不修改配置、不执行真实业务动作。",
            *source.warnings,
        ],
    )
    response["raw"] = {
        **result,
        "source_suggestions_artifact_path": str(source.path or ""),
        "scoped_suggestion_count": len(scoped_suggestions),
    }
    response["sections"] = [
        {
            "title": "复盘口径",
            "table": {
                "columns": ["项目", "值"],
                "rows": [
                    {"项目": "建议来源", "值": str(source.path or "本地实时结果")},
                    {"项目": "产品范围", "值": product_key or "全部产品"},
                    {"项目": "后续观察天数", "值": "1"},
                    {"项目": "关闭/删除类有效阈值", "值": "后续消耗 <= 100 且后续转化 = 0"},
                ],
            },
        }
    ]
    return response


def build_suggestions_daily_operations(
    *,
    project_root: str | Path,
    configs_dir: str | Path,
    runs_dir: str | Path,
    product_key: str = "",
) -> dict[str, Any]:
    overview = build_suggestions_overview(
        project_root=project_root,
        configs_dir=configs_dir,
        runs_dir=runs_dir,
        product_key=product_key,
    )
    lifecycle = build_suggestions_lifecycle(
        project_root=project_root,
        configs_dir=configs_dir,
        runs_dir=runs_dir,
        product_key=product_key,
    )
    root = Path(project_root)
    realtime_snapshot = find_realtime_patrol_snapshot(
        project_root=root,
        configs_dir=configs_dir,
        runs_dir=runs_dir,
        product_key=product_key,
        purpose="suggestions",
    )
    target_account_ids = realtime_account_ids(realtime_snapshot) if realtime_snapshot.required else None
    target_account_names = realtime_account_names(realtime_snapshot) if realtime_snapshot.required else None
    strategy_review = run_create_suggestion_strategy_review_request(
        {
            "db_path": str(root / "data" / "roibang_v2.sqlite3"),
            "project_root": str(root),
            "products_dir": str(Path(configs_dir) / "products"),
            "mode_dir": str(Path(configs_dir) / "create-modes"),
            "template_dir": str(Path(configs_dir) / "create-templates"),
            "strategy_dir": str(Path(configs_dir) / "create-suggestion-strategies"),
            "product_key": product_key,
            "include_examples": True,
            "target_account_ids": target_account_ids,
            "target_account_names": target_account_names or {},
        },
        runs_dir=runs_dir,
    )
    effect_path = find_latest_artifact(runs_dir, "delivery_suggestion_backtest")
    effect_payload = read_json(effect_path) if effect_path else {}
    overview_summary = overview.get("summary") if isinstance(overview.get("summary"), dict) else {}
    lifecycle_summary = lifecycle.get("summary") if isinstance(lifecycle.get("summary"), dict) else {}
    strategy_summary = strategy_review.get("summary") if isinstance(strategy_review.get("summary"), dict) else {}
    effect_summary = effect_payload.get("summary") if isinstance(effect_payload.get("summary"), dict) else {}
    suggestions = _rows(overview.get("raw", {}).get("suggestions") if isinstance(overview.get("raw"), dict) else [])
    create_suggestion_count = sum(1 for suggestion in suggestions if _suggestion_action(suggestion) == "suggest_create_project")
    suggestion_count = int(_summary_item_value(overview_summary, "建议事项") or 0)
    locked_count = int(lifecycle_summary.get("locked_suggestion_count") or 0)
    enabled_strategy_count = int(strategy_summary.get("enabled_strategy_count") or 0)
    blocked_strategy_count = int(strategy_summary.get("blocked_strategy_count") or 0)
    estimated_create_count = int(strategy_summary.get("estimated_suggestion_count") or 0)
    effect_evaluated_count = int(effect_summary.get("evaluated_suggestion_count") or 0)
    rows = [
        {
            "步骤": "数据同步与建议重算",
            "状态": "已有建议" if suggestion_count else "待重算",
            "关键结果": f"当前建议 {suggestion_count} 条；来源 {overview.get('artifact_path') or '未找到'}",
            "下一步": "需要更新数据时点击页面顶部“同步数据并重算建议”。",
        },
        {
            "步骤": "扩量机会扫描",
            "状态": "阻断" if blocked_strategy_count else ("已启用" if enabled_strategy_count else "待启用"),
            "关键结果": f"启用策略 {enabled_strategy_count} 个；预计创建建议 {estimated_create_count} 条；阻断策略 {blocked_strategy_count} 个",
            "下一步": "查看“扩量机会扫描”的阻断原因和修复建议。",
        },
        {
            "步骤": "生成创建项目计划",
            "状态": "可进入计划预览" if create_suggestion_count else "暂无创建建议",
            "关键结果": f"创建建议 {create_suggestion_count} 条；已锁定 {locked_count} 条",
            "下一步": "选择未锁定扩量机会，先检查创建计划，再去创建计划页人工确认。",
        },
        {
            "步骤": "效果复盘",
            "状态": "已有复盘" if effect_evaluated_count else "待复盘",
            "关键结果": f"已评估 {effect_evaluated_count} 条；最近复盘 {effect_path or '未找到'}",
            "下一步": "查看“建议效果复盘”卡片，必要时刷新只读复盘。",
        },
    ]
    warning_count = sum(1 for row in rows if row["状态"] in {"待重算", "待启用", "暂无创建建议", "待复盘", "阻断"})
    return {
        "summary": {
            "title": "数据更新与建议状态",
            "status": "warning" if warning_count else "loaded",
            "risk_level": "medium" if warning_count else "low",
            "execution_enabled": False,
            "items": [
                {"label": "产品范围", "value": product_key or "全部产品"},
                {"label": "建议事项", "value": suggestion_count},
                {"label": "创建建议", "value": create_suggestion_count},
                {"label": "已锁定创建建议", "value": locked_count},
                {"label": "启用创建策略", "value": enabled_strategy_count},
                {"label": "预计创建建议", "value": estimated_create_count},
                {"label": "已复盘建议", "value": effect_evaluated_count},
            ],
            "warnings": [
                "该总览只读聚合本地建议、策略、生命周期和复盘结果；不会执行真实业务动作。"
            ],
            "blocking_reasons": [],
        },
        "table": {
            "columns": ["步骤", "状态", "关键结果", "下一步"],
            "rows": rows,
        },
        "artifact_path": _text(overview.get("artifact_path")),
        "raw": {
            "overview": overview,
            "lifecycle": lifecycle,
            "strategy_review": strategy_review,
            "effect_review_artifact_path": str(effect_path or ""),
            "effect_review_summary": effect_summary,
        },
    }


def _load_products(configs_dir: str | Path, *, product_key: str) -> list[dict[str, Any]]:
    products = load_product_configs(Path(configs_dir) / "products", product_key=product_key)
    return products


def _summary_item_value(summary: dict[str, Any], label: str) -> Any:
    for item in summary.get("items") or []:
        if isinstance(item, dict) and _text(item.get("label")) == label:
            return item.get("value")
    return None


def _load_suggestions_source(
    project_root: str | Path,
    configs_dir: str | Path,
    runs_dir: str | Path,
    *,
    product_key: str,
) -> SuggestionsSource:
    realtime_snapshot = find_realtime_patrol_snapshot(
        project_root=project_root,
        configs_dir=configs_dir,
        runs_dir=runs_dir,
        product_key=product_key,
        purpose="suggestions",
    )
    if realtime_snapshot.required and not realtime_snapshot.payload:
        return SuggestionsSource(
            payload=_empty_suggestions_payload(product_key, source="realtime_snapshot_missing"),
            path=None,
            warnings=list(realtime_snapshot.warnings),
        )
    if realtime_snapshot.required:
        patrol_path = linked_suggestions_artifact(project_root, realtime_snapshot.payload)
        embedded = realtime_snapshot.payload.get("delivery_patrol_suggestions")
        patrol_payload = read_json(patrol_path) if patrol_path else {}
        if not patrol_payload and isinstance(embedded, dict):
            patrol_payload = dict(embedded)
    else:
        patrol_path = find_latest_artifact(runs_dir, "delivery_patrol_suggestions")
        patrol_payload = read_json(patrol_path) if patrol_path else {}
    local_payload = _build_local_rule_suggestions(
        project_root=project_root,
        configs_dir=configs_dir,
        runs_dir=runs_dir,
        product_key=product_key,
        realtime_snapshot=realtime_snapshot,
    )
    patrol_rows = _rows(patrol_payload.get("suggestions"))
    local_rows = _rows(local_payload.get("suggestions"))
    if local_rows:
        payload = _merge_suggestions_payloads(local_payload, patrol_payload)
        path = write_latest_artifact(runs_dir, "rule_suggestions", payload)
        payload["artifact_path"] = str(path)
        return SuggestionsSource(payload=payload, path=path, warnings=list(realtime_snapshot.warnings))
    if local_payload:
        return SuggestionsSource(
            payload=local_payload,
            path=None,
            warnings=[*realtime_snapshot.warnings, "本地数据库已读取，但当前规则没有生成建议。"],
        )
    return SuggestionsSource(
        payload=patrol_payload,
        path=patrol_path,
        warnings=[*realtime_snapshot.warnings] if patrol_path else [*realtime_snapshot.warnings, "未找到最近建议结果，当前只展示产品数据源状态。"],
    )


def _empty_suggestions_payload(product_key: str, *, source: str) -> dict[str, Any]:
    return {
        "ok": True,
        "workflow": "rule_suggestions",
        "phase": "control_analysis",
        "execution_enabled": False,
        "external_api_calls": 0,
        "summary": {
            "source": source,
            "product_key": product_key,
            "suggestion_count": 0,
            "convertible_project_action_count": 0,
            "create_project_suggestion_count": 0,
        },
        "suggestions": [],
        "blocked_suggestions": [],
        "guardrails": [
            "没有匹配实时快照时不生成可执行建议。",
            "历史数据只作为证据，不单独触发当前建议。",
        ],
    }


def _build_local_rule_suggestions(
    *,
    project_root: str | Path,
    configs_dir: str | Path,
    runs_dir: str | Path,
    product_key: str,
    realtime_snapshot: RealtimeSnapshot | None = None,
) -> dict[str, Any]:
    root = Path(project_root)
    db_path = root / "data" / "roibang_v2.sqlite3"
    if not db_path.exists():
        return {}
    target_date = _local_target_date(db_path)
    if not target_date:
        return {}
    products = _load_products(configs_dir, product_key=product_key)
    if not products:
        return {}

    account_names = load_account_name_map(configs_dir)
    account_names.update(_local_account_names(db_path))
    suggestions: list[dict[str, Any]] = []
    blocked_suggestions: list[dict[str, Any]] = []
    source_summaries: list[dict[str, Any]] = []
    target_scope_summaries: list[dict[str, Any]] = []
    for product in products:
        product_name = _text(product.get("product")) or _text(product.get("product_name")) or _text(product.get("product_key"))
        source_advertiser_id = _text(product.get("source_advertiser_id"))
        source_advertiser_name = _text(product.get("source_advertiser_name"))
        if source_advertiser_id and source_advertiser_name:
            account_names.setdefault(source_advertiser_id, source_advertiser_name)
        target_scope = _suggestion_target_account_scope(
            root,
            Path(runs_dir),
            product,
            realtime_snapshot=realtime_snapshot,
        )
        account_names.update(target_scope.get("account_names") if isinstance(target_scope.get("account_names"), dict) else {})
        target_scope_summaries.append(target_scope)
        request = _control_strategy_request(
            root,
            product,
            target_date=target_date,
            target_account_ids=target_scope["target_account_ids"],
        )
        result = build_control_strategy_suggestions(db_path, request)
        source_summaries.append(
            {
                "product_key": _text(product.get("product_key")),
                "product_name": product_name,
                "summary": result.get("summary", {}),
            }
        )
        for suggestion in _rows(result.get("suggestions")):
            normalized = _normalize_suggestion_for_center(
                suggestion,
                product_key=_text(product.get("product_key")),
                product_name=product_name,
                account_names=account_names,
                source_label="本地控制策略",
            )
            normalized["realtime_scope"] = _suggestion_scope_payload(target_scope)
            suggestions.append(normalized)
        for suggestion in _rows(result.get("blocked_suggestions")):
            normalized = _normalize_suggestion_for_center(
                suggestion,
                product_key=_text(product.get("product_key")),
                product_name=product_name,
                account_names=account_names,
                source_label="本地控制策略",
            )
            normalized["realtime_scope"] = _suggestion_scope_payload(target_scope)
            blocked_suggestions.append(normalized)
    create_suggestions_payload = _build_create_project_rule_suggestions(
        project_root=root,
        configs_dir=configs_dir,
        product_key=product_key,
        target_date=target_date,
        target_account_ids=_first_summary_list(target_scope_summaries, "target_account_ids"),
        target_account_names=_merged_scope_account_names(target_scope_summaries),
    )
    for suggestion in _rows(create_suggestions_payload.get("suggestions")):
        normalized = dict(suggestion)
        normalized["source_label"] = "本地创建策略"
        suggestions.append(normalized)
    for suggestion in _rows(create_suggestions_payload.get("blocked_suggestions")):
        normalized = dict(suggestion)
        normalized["source_label"] = "本地创建策略"
        blocked_suggestions.append(normalized)
    if create_suggestions_payload:
        source_summaries.append(
            {
                "product_key": product_key,
                "product_name": "",
                "summary": create_suggestions_payload.get("summary", {}),
            }
        )

    action_counts: dict[str, int] = {}
    for suggestion in suggestions:
        action = _suggestion_action(suggestion)
        if action:
            action_counts[action] = action_counts.get(action, 0) + 1
    return {
        "ok": True,
        "workflow": "rule_suggestions",
        "phase": "control_analysis",
        "execution_enabled": False,
        "external_api_calls": 0,
        "summary": {
            "target_date": target_date,
            "historical_evidence_date": target_date,
            "source": "local_sqlite",
            "product_count": len(products),
            "suggestion_count": len(suggestions),
            "convertible_project_action_count": sum(1 for item in suggestions if _can_convert_to_project_update(item)),
            "action_counts": action_counts,
            "blocked_suggestion_count": len(blocked_suggestions),
            "create_project_suggestion_count": sum(
                1 for item in suggestions if _suggestion_action(item) == "suggest_create_project"
            ),
            "today_patrol_date": _first_summary_value(target_scope_summaries, "today_patrol_date"),
            "today_patrol_spent_account_count": sum(int(item.get("today_patrol_spent_account_count") or 0) for item in target_scope_summaries),
            "target_account_count": sum(int(item.get("target_account_count") or 0) for item in target_scope_summaries),
            "allowed_account_count": sum(int(item.get("allowed_account_count") or 0) for item in target_scope_summaries),
        },
        "source": {
            "workflow": "control_strategy_suggestions",
            "db_path": str(db_path),
        },
        "source_summaries": source_summaries,
        "target_account_scope": target_scope_summaries,
        "suggestions": suggestions,
        "blocked_suggestions": blocked_suggestions,
        "guardrails": [
            "只读取本地 SQLite 数据，不调用外部接口。",
            "只生成中文建议和动作 JSON，真实动作必须回到固定脚本确认入口。",
            "创建项目建议只读展示，不生成创建计划，不执行真实创建。",
        ],
    }


def _build_create_project_rule_suggestions(
    *,
    project_root: str | Path,
    configs_dir: str | Path,
    product_key: str,
    target_date: str,
    target_account_ids: list[str] | None = None,
    target_account_names: dict[str, str] | None = None,
) -> dict[str, Any]:
    root = Path(project_root)
    strategy_dir = Path(configs_dir) / "create-suggestion-strategies"
    if not strategy_dir.exists() or not list(strategy_dir.glob("*.local.json")):
        return {}
    try:
        return build_create_project_suggestions(
            db_path=root / "data" / "roibang_v2.sqlite3",
            project_root=root,
            products_dir=Path(configs_dir) / "products",
            mode_dir=Path(configs_dir) / "create-modes",
            strategy_dir=strategy_dir,
            product_key=product_key,
            target_date=target_date,
            target_account_ids=target_account_ids,
            target_account_names=target_account_names,
        )
    except Exception as exc:  # noqa: BLE001 - suggestions page should surface config/data problems, not crash.
        return {
            "ok": False,
            "workflow": "create_project_suggestions",
            "execution_enabled": False,
            "external_api_calls": 0,
            "summary": {"suggestion_count": 0, "blocked_suggestion_count": 1},
            "suggestions": [],
            "blocked_suggestions": [
                {
                    "suggestion_id": "create-project-suggestions-blocked",
                    "suggested_action": "suggest_create_project",
                    "suggestion_type": "suggest_create_project",
                    "entity_type": "account",
                    "reason": "创建项目建议生成失败。",
                    "blocking_reasons": [str(exc)],
                }
            ],
        }


def _control_strategy_request(
    root: Path,
    product: dict[str, Any],
    *,
    target_date: str,
    target_account_ids: list[str],
) -> dict[str, Any]:
    allowed_path = _text(product.get("allowed_target_accounts_path"))
    return {
        "product_keyword": _text(product.get("product")),
        "target_date": target_date,
        "allowed_target_accounts_path": str(_resolve_path(root, allowed_path)) if allowed_path else "",
        "target_account_ids": sorted({_text(item) for item in target_account_ids if _text(item)}),
        "rules": {
            "delete_project_closed_low_recent": {
                "enabled": True,
                "lookback_days": 2,
                "max_stat_cost": 100,
                "max_convert_cnt": 0,
            },
            "pause_project_low_first_day_roi": {
                "enabled": True,
                "min_cost": 500,
                "min_conversions": 2,
                "max_roi_1day": 0.25,
            },
            "adjust_project_budget_low_roi": {
                "enabled": True,
                "min_cost": 800,
                "min_conversions": 3,
                "max_roi_1day": 0.35,
                "budget_decrease_percent": 20,
            },
            "adjust_project_bid_high_cpa": {
                "enabled": True,
                "min_cost": 1000,
                "min_conversions": 2,
                "max_cpa": 300,
                "bid_decrease_percent": 10,
            },
            "schedule_hollow_low_realtime_hour_roi": {"enabled": False},
            "material_reuse_risk": {
                "enabled": True,
                "window_key": "last_7d",
                "min_project_count": 5,
                "min_promotion_count": 10,
                "min_stat_cost": 1000,
                "max_roi_1day": 0.05,
            },
            "account_spent_outside_allowlist": {
                "enabled": True,
                "min_stat_cost": 100,
            },
        },
    }


def _local_target_date(db_path: Path) -> str:
    try:
        with sqlite3.connect(db_path) as conn:
            row = conn.execute("SELECT MAX(metric_date) FROM material_daily_metrics").fetchone()
    except sqlite3.Error:
        return ""
    return _text(row[0] if row else "")


def _latest_account_name_map(project_root: str | Path, configs_dir: str | Path) -> dict[str, str]:
    account_names = load_account_name_map(configs_dir)
    account_names.update(_local_account_names(Path(project_root) / "data" / "roibang_v2.sqlite3"))
    return account_names


def _latest_patrol_account_name_map(
    project_root: str | Path,
    configs_dir: str | Path,
    runs_dir: str | Path,
    *,
    product_key: str,
) -> dict[str, str]:
    root = Path(project_root)
    names: dict[str, str] = {}
    for product in _load_products(configs_dir, product_key=product_key):
        patrol_payload, _ = _latest_product_delivery_patrol(root, Path(runs_dir), product)
        names.update(_patrol_account_names(patrol_payload))
    return names


def _local_account_names(db_path: Path) -> dict[str, str]:
    try:
        with sqlite3.connect(db_path) as conn:
            rows = conn.execute(
                """
                SELECT advertiser_id, account_name
                FROM account_pool
                WHERE advertiser_id <> ''
                ORDER BY COALESCE(synced_at, '') ASC
                """
            ).fetchall()
    except sqlite3.Error:
        return {}
    names: dict[str, str] = {}
    for advertiser_id, account_name in rows:
        account_id = _text(advertiser_id)
        name = _text(account_name)
        if account_id and name:
            names[account_id] = name
    return names


def _first_summary_value(rows: list[dict[str, Any]], key: str) -> Any:
    for row in rows:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return ""


def _first_summary_list(rows: list[dict[str, Any]], key: str) -> list[str] | None:
    for row in rows:
        value = row.get(key)
        if isinstance(value, list):
            return [_text(item) for item in value if _text(item)]
    return None


def _merged_scope_account_names(rows: list[dict[str, Any]]) -> dict[str, str]:
    names: dict[str, str] = {}
    for row in rows:
        value = row.get("account_names")
        if isinstance(value, dict):
            for advertiser_id, account_name in value.items():
                account_id = _text(advertiser_id)
                name = _text(account_name)
                if account_id and name:
                    names[account_id] = name
    return names


def _suggestion_scope_payload(scope: dict[str, Any]) -> dict[str, Any]:
    account_scope = scope.get("account_scope") if isinstance(scope.get("account_scope"), dict) else {}
    return {
        "patrol_artifact_path": _text(scope.get("patrol_artifact_path")),
        "today_patrol_date": _text(scope.get("today_patrol_date")),
        "account_scope": dict(account_scope),
        "target_account_count": int(scope.get("target_account_count") or 0),
    }


def _suggestion_target_account_scope(
    project_root: Path,
    runs_dir: Path,
    product: dict[str, Any],
    *,
    realtime_snapshot: RealtimeSnapshot | None = None,
) -> dict[str, Any]:
    allowed_account_ids = _allowed_account_ids_for_product(project_root, product)
    product_key = _text(product.get("product_key"))
    if realtime_snapshot and realtime_snapshot.required and _text(realtime_snapshot.scope.get("_product_key")) == product_key:
        patrol_payload = realtime_snapshot.payload
        patrol_path = realtime_snapshot.path
    else:
        patrol_payload, patrol_path = _latest_product_delivery_patrol(project_root, runs_dir, product)
    today_spent_account_ids = _today_spent_account_ids(patrol_payload)
    account_names = _patrol_account_names(patrol_payload)
    target_account_ids = sorted(allowed_account_ids & today_spent_account_ids)
    patrol_summary = patrol_payload.get("summary") if isinstance(patrol_payload.get("summary"), dict) else {}
    windows = patrol_payload.get("windows") if isinstance(patrol_payload.get("windows"), dict) else {}
    account_scope = patrol_summary.get("account_scope") if isinstance(patrol_summary.get("account_scope"), dict) else {}
    return {
        "product_key": product_key,
        "product_name": _text(product.get("product")) or _text(product.get("product_name")),
        "today_patrol_date": _text(patrol_summary.get("target_date") or windows.get("today")),
        "today_patrol_spent_account_count": len(today_spent_account_ids),
        "allowed_account_count": len(allowed_account_ids),
        "target_account_count": len(target_account_ids),
        "target_account_ids": target_account_ids,
        "account_names": account_names,
        "patrol_artifact_path": str(patrol_path or ""),
        "account_scope": dict(account_scope),
        "realtime_scope_required": bool(realtime_snapshot.required) if realtime_snapshot else False,
    }


def _allowed_account_ids_for_product(project_root: Path, product: dict[str, Any]) -> set[str]:
    path_text = _text(product.get("allowed_target_accounts_path"))
    if not path_text:
        return set()
    payload = read_json(_resolve_path(project_root, path_text))
    rows = payload.get("allowed_target_accounts") if isinstance(payload.get("allowed_target_accounts"), list) else []
    ids: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        advertiser_id = _text(row.get("advertiser_id") or row.get("account_id"))
        if advertiser_id and _enabled(row.get("enable", row.get("enabled", True))):
            ids.add(advertiser_id)
    return ids


def _latest_product_delivery_patrol(
    project_root: Path,
    runs_dir: Path,
    product: dict[str, Any],
) -> tuple[dict[str, Any], Path | None]:
    for path in _recent_json_paths(runs_dir / "product_automation_job_delivery_patrol"):
        payload = read_json(path)
        for result in _rows(payload.get("results")):
            if not _product_job_result_matches(result, product):
                continue
            patrol_payload, patrol_path = _delivery_patrol_payload_from_job_result(project_root, result)
            if patrol_payload:
                return patrol_payload, patrol_path or path

    for path in _recent_json_paths(runs_dir / "delivery_patrol"):
        payload = read_json(path)
        if payload and _delivery_patrol_matches_product(payload, product):
            return payload, path
    return {}, None


def _recent_json_paths(directory: Path, *, limit: int = 80) -> list[Path]:
    if not directory.exists():
        return []
    candidates = sorted((path for path in directory.glob("*.json") if path.name != "latest.json"), reverse=True)
    latest = directory / "latest.json"
    if latest.exists():
        candidates.insert(0, latest)
    return candidates[:limit]


def _product_job_result_matches(result: dict[str, Any], product: dict[str, Any]) -> bool:
    product_key = _text(product.get("product_key"))
    product_name = _text(product.get("product")) or _text(product.get("product_name"))
    if product_key and _text(result.get("product_key")) == product_key:
        return True
    return bool(product_name and _text(result.get("product")) == product_name)


def _delivery_patrol_payload_from_job_result(project_root: Path, result: dict[str, Any]) -> tuple[dict[str, Any], Path | None]:
    parsed = result.get("parsed_stdout") if isinstance(result.get("parsed_stdout"), dict) else {}
    artifact_path_text = _text(parsed.get("artifact_path"))
    if artifact_path_text:
        artifact_path = _resolve_path(project_root, artifact_path_text)
        payload = read_json(artifact_path)
        if payload:
            return payload, artifact_path
    if _text(parsed.get("workflow")) == "delivery_patrol":
        return dict(parsed), None
    return {}, None


def _delivery_patrol_matches_product(payload: dict[str, Any], product: dict[str, Any]) -> bool:
    product_name = _text(product.get("product")) or _text(product.get("product_name"))
    account_remark = _product_account_remark(product)
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    scope = summary.get("account_scope") if isinstance(summary.get("account_scope"), dict) else {}
    if account_remark and _text(scope.get("account_remark_equals")) == account_remark:
        return True
    for account in _rows(payload.get("accounts")):
        if product_name and _text(account.get("product")) == product_name:
            return True
        joined = " ".join([_text(account.get("account_name")), _text(account.get("account_remark"))])
        if product_name and product_name in joined:
            return True
    return False


def _product_account_remark(product: dict[str, Any]) -> str:
    automation = product.get("automation") if isinstance(product.get("automation"), dict) else {}
    discovery = automation.get("account_discovery") if isinstance(automation.get("account_discovery"), dict) else {}
    return _text(discovery.get("account_remark_equals") or product.get("account_remark_pattern"))


def _today_spent_account_ids(patrol_payload: dict[str, Any]) -> set[str]:
    account_ids: set[str] = set()
    for account in _rows(patrol_payload.get("accounts")):
        metrics = account.get("metrics") if isinstance(account.get("metrics"), dict) else {}
        today_metrics = metrics.get("today") if isinstance(metrics.get("today"), dict) else {}
        if _number(today_metrics.get("stat_cost")) > 0:
            advertiser_id = _text(account.get("advertiser_id") or account.get("account_id"))
            if advertiser_id:
                account_ids.add(advertiser_id)
    return account_ids


def _patrol_account_names(patrol_payload: dict[str, Any]) -> dict[str, str]:
    names: dict[str, str] = {}
    for key in ["accounts", "top_accounts"]:
        for account in _rows(patrol_payload.get(key)):
            advertiser_id = _text(account.get("advertiser_id") or account.get("account_id"))
            account_name = _text(account.get("account_name") or account.get("advertiser_name"))
            if advertiser_id and account_name and account_name != advertiser_id:
                names[advertiser_id] = account_name
    return names


def _suggestions_target_date(payload: dict[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    target_date = _text(summary.get("target_date"))
    if target_date:
        return target_date
    dates = sorted({_text(row.get("target_date")) for row in _rows(payload.get("suggestions")) if _text(row.get("target_date"))})
    return dates[-1] if dates else ""


def _historical_evidence_date(payload: dict[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    return _text(summary.get("historical_evidence_date") or _suggestions_target_date(payload))


def _today_patrol_date(payload: dict[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    return _text(summary.get("today_patrol_date"))


def _suggestion_context_items(payload: dict[str, Any], *, generated_at: str) -> list[dict[str, Any]]:
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    items: list[dict[str, Any]] = []
    today_patrol_date = _text(summary.get("today_patrol_date"))
    if today_patrol_date:
        items.append({"label": "今日巡检日期", "value": today_patrol_date})
    if "today_patrol_spent_account_count" in summary:
        items.append({"label": "今日巡检有消耗账户", "value": int(summary.get("today_patrol_spent_account_count") or 0)})
    if "target_account_count" in summary:
        items.append({"label": "建议对象账户", "value": int(summary.get("target_account_count") or 0)})
    if generated_at:
        items.append({"label": "建议生成时间", "value": generated_at})
    historical_date = _historical_evidence_date(payload)
    if historical_date:
        items.append({"label": "历史证据日期", "value": historical_date})
    return items


def _artifact_generated_at(path: Path | None, payload: dict[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    for value in [
        payload.get("generated_at"),
        payload.get("created_at"),
        summary.get("generated_at") if isinstance(summary, dict) else "",
        summary.get("created_at") if isinstance(summary, dict) else "",
    ]:
        text = _text(value)
        if text:
            return text
    if not path:
        return ""
    try:
        return datetime.fromtimestamp(path.stat().st_mtime).astimezone().isoformat(timespec="seconds")
    except OSError:
        return ""


def _default_project_update_id() -> str:
    return f"suggestions-project-update-{datetime.now().strftime('%Y%m%d-%H%M%S')}"


def _default_project_update_path(project_update_id: str) -> str:
    return f"configs/project-updates/{project_update_id}.local.json"


def _suggestion_freshness_warnings(historical_date: str, *, today_patrol_date: str = "") -> list[str]:
    today = date.today().isoformat()
    warnings: list[str] = []
    if historical_date and historical_date < today:
        warnings.append(f"历史证据日期为 {historical_date}，早于今天 {today}；这是日报、素材明细或操作日志的历史数据口径。")
    if today_patrol_date and today_patrol_date < today:
        warnings.append(f"今日巡检日期为 {today_patrol_date}，早于今天 {today}；建议先点击同步数据并重算建议。")
    return warnings


def _merge_suggestions_payloads(local_payload: dict[str, Any], patrol_payload: dict[str, Any]) -> dict[str, Any]:
    suggestions: list[dict[str, Any]] = []
    seen: set[str] = set()
    for payload, source_label in [(local_payload, "本地控制策略"), (patrol_payload, "投放巡检建议")]:
        for suggestion in _rows(payload.get("suggestions")):
            normalized = dict(suggestion)
            normalized.setdefault("source_label", source_label)
            suggestion_id = _text(normalized.get("suggestion_id")) or _fallback_suggestion_id(normalized)
            if suggestion_id in seen:
                continue
            normalized["suggestion_id"] = suggestion_id
            suggestions.append(normalized)
            seen.add(suggestion_id)
    action_counts: dict[str, int] = {}
    for suggestion in suggestions:
        action = _suggestion_action(suggestion)
        if action:
            action_counts[action] = action_counts.get(action, 0) + 1
    return {
        "ok": True,
        "workflow": "rule_suggestions",
        "phase": "control_analysis",
        "execution_enabled": False,
        "external_api_calls": 0,
        "summary": {
            "target_date": _text(local_payload.get("summary", {}).get("target_date"))
            or _text(patrol_payload.get("summary", {}).get("target_date")),
            "historical_evidence_date": _text(local_payload.get("summary", {}).get("historical_evidence_date"))
            or _text(local_payload.get("summary", {}).get("target_date"))
            or _text(patrol_payload.get("summary", {}).get("target_date")),
            "today_patrol_date": _text(local_payload.get("summary", {}).get("today_patrol_date")),
            "today_patrol_spent_account_count": int(local_payload.get("summary", {}).get("today_patrol_spent_account_count") or 0),
            "target_account_count": int(local_payload.get("summary", {}).get("target_account_count") or 0),
            "allowed_account_count": int(local_payload.get("summary", {}).get("allowed_account_count") or 0),
            "suggestion_count": len(suggestions),
            "convertible_project_action_count": sum(1 for item in suggestions if _can_convert_to_project_update(item)),
            "action_counts": action_counts,
            "local_suggestion_count": len(_rows(local_payload.get("suggestions"))),
            "patrol_suggestion_count": len(_rows(patrol_payload.get("suggestions"))),
        },
        "sources": [
            {"label": "本地控制策略", "workflow": _text(local_payload.get("workflow")), "db_path": _text(local_payload.get("source", {}).get("db_path"))},
            {"label": "投放巡检建议", "workflow": _text(patrol_payload.get("workflow")), "artifact_path": _text(patrol_payload.get("artifact_path"))},
        ],
        "suggestions": suggestions,
        "blocked_suggestions": _rows(local_payload.get("blocked_suggestions")),
        "guardrails": [
            "只读建议，不执行真实业务动作。",
            "能转动作 JSON 的建议仍需项目管理页人工确认。",
        ],
    }


def _normalize_suggestion_for_center(
    suggestion: dict[str, Any],
    *,
    product_key: str,
    product_name: str,
    account_names: dict[str, str],
    source_label: str,
) -> dict[str, Any]:
    normalized = dict(suggestion)
    action = _suggestion_action(normalized)
    alias = {
        "adjust_project_budget": "suggest_lower_budget",
        "adjust_project_bid": "suggest_lower_bid",
    }.get(action)
    if alias:
        normalized["suggested_action"] = alias
    advertiser_id = _text(normalized.get("advertiser_id"))
    if advertiser_id and not _text(normalized.get("account_name")):
        account_name = account_names.get(advertiser_id, "")
        if account_name:
            normalized["account_name"] = account_name
    if _text(normalized.get("entity_type")) == "project":
        normalized.setdefault("project_id", _text(normalized.get("entity_id")))
        normalized.setdefault("project_name", _text(normalized.get("entity_name")))
    normalized["product_key"] = product_key
    normalized["product_name"] = product_name
    normalized["source_label"] = source_label
    normalized["suggestion_id"] = _text(normalized.get("suggestion_id")) or _fallback_suggestion_id(normalized)
    return normalized


def _fallback_suggestion_id(suggestion: dict[str, Any]) -> str:
    return ":".join(
        [
            _text(suggestion.get("target_date")) or "unknown-date",
            _text(suggestion.get("entity_type")) or "entity",
            _text(suggestion.get("advertiser_id")) or "account",
            _text(suggestion.get("project_id") or suggestion.get("entity_id")) or "target",
            _suggestion_action(suggestion) or "suggestion",
        ]
    )


def _blocked_backtest_preview(reason: str) -> dict[str, Any]:
    return {
        "summary": {
            "title": "建议回测",
            "status": "blocked",
            "risk_level": "low",
            "execution_enabled": False,
            "items": [
                {"label": "评估建议", "value": 0},
                {"label": "可能有效", "value": 0},
                {"label": "证据不足", "value": 0},
                {"label": "已人工处理", "value": 0},
            ],
            "warnings": [],
            "blocking_reasons": [reason],
        },
        "table": {
            "columns": [
                "建议 ID",
                "产品",
                "账户名",
                "账户 ID",
                "项目名",
                "项目 ID",
                "建议动作",
                "建议日期",
                "后续观察窗口",
                "后续消耗",
                "后续转化",
                "后续 ROI",
                "回测结论",
                "中文原因",
                "数据完整性",
            ],
            "rows": [],
        },
        "artifact_path": "",
        "raw": {},
    }


def _blocked_effect_review(reason: str) -> dict[str, Any]:
    payload = _blocked_backtest_preview(reason)
    payload["summary"]["title"] = "建议效果复盘"
    payload["summary"]["warnings"] = ["自动复盘只读取本地数据，不执行真实业务动作。"]
    return payload


def _suggestions_backtest_response(
    result: dict[str, Any],
    *,
    accounts: list[dict[str, Any]],
    account_names: dict[str, str],
    title: str,
    warnings: list[str],
) -> dict[str, Any]:
    product_by_account = {str(account.get("advertiser_id") or ""): str(account.get("product_name") or "") for account in accounts}
    rows = [
        _backtest_row(evaluation, account_names=account_names, product_by_account=product_by_account)
        for evaluation in result.get("evaluations", [])
        if isinstance(evaluation, dict)
    ]
    conclusion_counts = _backtest_conclusion_counts(rows)
    result_summary = result.get("summary") if isinstance(result.get("summary"), dict) else {}
    return {
        "summary": {
            "title": title,
            "status": "completed",
            "risk_level": "low",
            "execution_enabled": False,
            "items": [
                {"label": "评估建议", "value": len(rows)},
                {"label": "可能有效", "value": conclusion_counts.get("可能有效", 0)},
                {"label": "证据不足", "value": conclusion_counts.get("证据不足", 0)},
                {"label": "需要复核", "value": conclusion_counts.get("需要复核", 0)},
                {"label": "已人工处理", "value": conclusion_counts.get("已被人工处理", 0)},
                {"label": "创建建议", "value": int(result_summary.get("create_suggestion_count") or 0)},
                {"label": "创建已采纳", "value": int(result_summary.get("create_adopted_count") or 0)},
                {"label": "创建已执行", "value": int(result_summary.get("create_executed_count") or 0)},
                {"label": "创建有后续数据", "value": int(result_summary.get("create_with_future_data_count") or 0)},
                {"label": "创建执行失败", "value": int(result_summary.get("create_execution_failed_count") or 0)},
                {"label": "观察天数", "value": result_summary.get("lookahead_days", 1)},
                {"label": "最新数据日期", "value": _text(result_summary.get("max_metric_date"))},
            ],
            "warnings": warnings,
            "blocking_reasons": [],
        },
        "table": {
            "columns": [
                "建议 ID",
                "产品",
                "账户名",
                "账户 ID",
                "项目名",
                "项目 ID",
                "建议动作",
                "创建状态",
                "计划预览",
                "执行前复核",
                "执行任务",
                "创建项目数",
                "建议日期",
                "后续观察窗口",
                "后续消耗",
                "后续转化",
                "后续 ROI",
                "回测结论",
                "中文原因",
                "数据完整性",
            ],
            "rows": rows,
        },
        "artifact_path": _text(result.get("artifact_path")),
        "raw": result,
    }


def _backtest_row(
    evaluation: dict[str, Any],
    *,
    account_names: dict[str, str],
    product_by_account: dict[str, str],
) -> dict[str, Any]:
    advertiser_id = _text(evaluation.get("advertiser_id"))
    window = evaluation.get("after_window") if isinstance(evaluation.get("after_window"), dict) else {}
    after_metrics = evaluation.get("after_metrics") if isinstance(evaluation.get("after_metrics"), dict) else {}
    conclusion = _backtest_conclusion(evaluation)
    project_ids = evaluation.get("project_ids") if isinstance(evaluation.get("project_ids"), list) else []
    project_id = "、".join(_text(item) for item in project_ids if _text(item)) or _text(evaluation.get("project_id"))
    return {
        "建议 ID": _text(evaluation.get("suggestion_id")),
        "产品": product_by_account.get(advertiser_id, "未归档产品"),
        "账户名": account_name_for(account_names, advertiser_id),
        "账户 ID": advertiser_id,
        "项目名": _text(evaluation.get("project_name")),
        "项目 ID": project_id,
        "建议动作": _action_label_for_suggestion(_text(evaluation.get("suggested_action"))),
        "创建状态": _text(evaluation.get("create_lifecycle_label")),
        "计划预览": _text(evaluation.get("plan_preview_path")),
        "执行前复核": _text(evaluation.get("execution_review_path")),
        "执行任务": _text(evaluation.get("execution_task_id")),
        "创建项目数": int(evaluation.get("created_project_count") or 0),
        "建议日期": _text(evaluation.get("target_date")),
        "后续观察窗口": f"{_text(window.get('start_date'))} 至 {_text(window.get('end_date'))}",
        "后续消耗": round(_number(after_metrics.get("stat_cost")), 4),
        "后续转化": round(_number(after_metrics.get("convert_cnt")), 4),
        "后续 ROI": round(_number(after_metrics.get("roi_1day")), 4),
        "回测结论": conclusion,
        "中文原因": _backtest_reason(evaluation, conclusion),
        "数据完整性": _backtest_data_quality(evaluation),
    }


def _backtest_conclusion(evaluation: dict[str, Any]) -> str:
    operation = evaluation.get("operation_after") if isinstance(evaluation.get("operation_after"), dict) else {}
    if operation.get("found"):
        return "已被人工处理"
    status = _text(evaluation.get("evaluation_status"))
    if status == "create_not_adopted":
        return "未采纳"
    if status in {"create_plan_previewed", "create_reviewed_not_submitted"}:
        return "已进入计划预览"
    if status == "create_review_blocked":
        return "复核阻断"
    if status in {"create_adopted_pending_result", "create_adopted_pending_future_data"}:
        return "已采纳待观察"
    if status == "create_adopted_with_future_data":
        return "已采纳有后续数据"
    if status == "create_execution_failed":
        return "执行失败需复核"
    if status in {"create_execution_evidence_missing", "create_adopted_no_future_data"}:
        return "证据不足"
    if status == "supported":
        return "可能有效"
    if status in {"pending_future_data", "no_future_data", "not_evaluated_no_execution"}:
        return "证据不足"
    if status == "needs_review":
        return "需要复核"
    if status == "execution_observed":
        return "已被人工处理"
    return status or "证据不足"


def _backtest_reason(evaluation: dict[str, Any], conclusion: str) -> str:
    reason = _text(evaluation.get("evaluation_reason")) or "需要人工复核该建议。"
    if conclusion == "已被人工处理":
        return f"操作日志显示建议后已有对应人工处理；{reason}"
    return reason


def _backtest_data_quality(evaluation: dict[str, Any]) -> str:
    status = _text(evaluation.get("evaluation_status"))
    if status == "pending_future_data":
        return "后续数据不足"
    if status == "create_adopted_pending_future_data":
        return "后续数据不足"
    if status == "create_execution_evidence_missing":
        return "缺创建台账"
    if status in {"create_not_adopted", "create_plan_previewed", "create_reviewed_not_submitted", "create_review_blocked"}:
        return "无需后续数据"
    after_metrics = evaluation.get("after_metrics") if isinstance(evaluation.get("after_metrics"), dict) else {}
    if _number(after_metrics.get("active_days")) <= 0:
        return "证据不足"
    return "完整"


def _backtest_conclusion_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        conclusion = _text(row.get("回测结论"))
        counts[conclusion] = counts.get(conclusion, 0) + 1
    return counts


def _product_source_rows(runs_dir: str | Path, product: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    product_name = _text(product.get("product"))
    product_key = _text(product.get("product_key"))
    for label, workflow in DATA_SOURCE_JOBS:
        path = find_latest_artifact(runs_dir, workflow)
        rows.append(
            {
                "产品": product_name,
                "产品 Key": product_key,
                "数据源": label,
                "workflow": workflow,
                "状态": "已找到" if path else "未找到",
                "最近文件": str(path or ""),
            }
        )
    return rows


def _suggestions_in_scope(
    suggestions_payload: dict[str, Any],
    accounts: list[dict[str, str]],
    *,
    product_key: str,
) -> list[dict[str, Any]]:
    suggestions = [dict(item) for item in suggestions_payload.get("suggestions", []) if isinstance(item, dict)]
    if not product_key:
        return suggestions
    scoped_ids = {str(account.get("advertiser_id") or "") for account in accounts if str(account.get("product_key") or "") == product_key}
    return [
        suggestion
        for suggestion in suggestions
        if _text(suggestion.get("product_key")) == product_key or _text(suggestion.get("advertiser_id")) in scoped_ids
    ]


def _allowed_account_count(project_root: str | Path, product: dict[str, Any]) -> int:
    path_text = _text(product.get("allowed_target_accounts_path"))
    if not path_text:
        return 0
    path = _resolve_path(Path(project_root), path_text)
    payload = read_json(path)
    rows = payload.get("allowed_target_accounts") if isinstance(payload.get("allowed_target_accounts"), list) else []
    return sum(1 for row in rows if isinstance(row, dict) and _enabled(row.get("enable", row.get("enabled", True))))


def _rows(value: Any) -> list[dict[str, Any]]:
    return [dict(item) for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _request_selected_suggestion_ids(request: dict[str, Any]) -> list[str]:
    raw = request.get("selected_suggestion_ids", request.get("suggestion_ids", request.get("suggestion_id")))
    if isinstance(raw, list):
        return [_text(item) for item in raw if _text(item)]
    if isinstance(raw, str):
        return [item.strip() for item in raw.split(",") if item.strip()]
    return []


def _request_suggested_actions(request: dict[str, Any]) -> list[str]:
    raw = request.get("suggested_actions", request.get("suggested_action"))
    if isinstance(raw, list):
        return [_text(item) for item in raw if _text(item)]
    if isinstance(raw, str):
        return [item.strip() for item in raw.split(",") if item.strip()]
    return []


def _expanded_action_filter(values: list[str]) -> list[str]:
    expanded: list[str] = []
    seen: set[str] = set()
    for value in values:
        for alias in ACTION_FILTER_ALIASES.get(value, (value,)):
            if alias and alias not in seen:
                expanded.append(alias)
                seen.add(alias)
    return expanded


def _filter_suggestions_for_project_update_request(
    suggestions: list[dict[str, Any]],
    request: dict[str, Any],
) -> list[dict[str, Any]]:
    selected_ids = _request_selected_suggestion_ids(request)
    if selected_ids:
        existing_ids = {_text(suggestion.get("suggestion_id")) for suggestion in suggestions}
        suggestions = [
            suggestion for suggestion in suggestions if _text(suggestion.get("suggestion_id")) in set(selected_ids)
        ]
        missing_ids = [suggestion_id for suggestion_id in selected_ids if suggestion_id not in existing_ids]
        suggestions.extend({"suggestion_id": suggestion_id, "_missing": True} for suggestion_id in missing_ids)
    suggested_actions = _request_suggested_actions(request)
    if suggested_actions:
        allowed = set(_expanded_action_filter(suggested_actions))
        suggestions = [
            suggestion
            for suggestion in suggestions
            if suggestion.get("_missing") or _suggestion_action(suggestion) in allowed
        ]
    return suggestions


def _project_update_validation_reasons(
    selected_suggestions: list[dict[str, Any]],
    request: dict[str, Any],
    account_names: dict[str, str],
) -> list[str]:
    reasons: list[str] = []
    convertible_count = 0
    explicit_ids = bool(_request_selected_suggestion_ids(request))
    for suggestion in selected_suggestions:
        suggestion_id = _text(suggestion.get("suggestion_id")) or "未命名建议"
        if suggestion.get("_missing"):
            reasons.append(f"建议 {suggestion_id} 不存在。")
            continue
        if not _can_convert_to_project_update(suggestion):
            if explicit_ids:
                reasons.append(f"建议 {suggestion_id} 是只读建议，不能生成项目管理配置。")
            continue
        convertible_count += 1
        advertiser_id = _text(suggestion.get("advertiser_id"))
        if not advertiser_id:
            reasons.append(f"建议 {suggestion_id} 缺少账户 ID。")
        elif not account_names.get(advertiser_id):
            reasons.append(f"建议 {suggestion_id} 缺少账户名：{advertiser_id}。")
        if not _project_id_from_suggestion(suggestion):
            reasons.append(f"建议 {suggestion_id} 缺少项目 ID。")
        action = _suggestion_action(suggestion).lower()
        if action in {"suggest_lower_budget", "adjust_project_budget", "suggest_lower_bid", "adjust_project_bid"}:
            if _ratio_adjustment(suggestion) is None:
                reasons.append(f"建议 {suggestion_id} 是调预算/调出价动作，但缺少明确比例，不能猜预算或出价。")
        if action == "schedule_hollow":
            hours = suggestion.get("hollow_hours")
            if not isinstance(hours, list) or not hours:
                reasons.append(f"建议 {suggestion_id} 是调整时段动作，但缺少明确小时，不能猜投放时段。")
    if selected_suggestions and convertible_count == 0 and not reasons:
        reasons.append("所选建议没有可生成项目管理配置的项目动作。")
    return reasons


def _realtime_scope_validation_reasons(
    *,
    project_root: str | Path,
    configs_dir: str | Path,
    runs_dir: str | Path,
    product_key: str,
    suggestions: list[dict[str, Any]],
) -> list[str]:
    snapshot = find_realtime_patrol_snapshot(
        project_root=project_root,
        configs_dir=configs_dir,
        runs_dir=runs_dir,
        product_key=product_key,
        purpose="suggestions",
    )
    if not snapshot.required:
        return []
    if not snapshot.payload:
        return list(snapshot.warnings)
    allowed_ids = set(realtime_account_ids(snapshot))
    reasons: list[str] = []
    for suggestion in suggestions:
        if suggestion.get("_missing") or not _can_convert_to_project_update(suggestion):
            continue
        advertiser_id = _text(suggestion.get("advertiser_id"))
        suggestion_id = _text(suggestion.get("suggestion_id")) or "未命名建议"
        if advertiser_id not in allowed_ids:
            reasons.append(f"建议 {suggestion_id} 不属于当前建议实时范围，不能生成项目管理配置。")
    return reasons


def _project_update_product_metadata(
    configs_dir: str | Path,
    accounts: list[dict[str, str]],
    selected_suggestions: list[dict[str, Any]],
    request: dict[str, Any],
) -> tuple[str, str]:
    product_key = _text(request.get("product_key"))
    product_name = _text(request.get("product_name"))
    if not product_key or not product_name:
        advertiser_ids = [_text(suggestion.get("advertiser_id")) for suggestion in selected_suggestions]
        for account in accounts:
            if _text(account.get("advertiser_id")) in advertiser_ids:
                product_key = product_key or _text(account.get("product_key"))
                product_name = product_name or _text(account.get("product_name"))
                break
    if product_key and not product_name:
        products = _load_products(configs_dir, product_key=product_key)
        if products:
            product_name = _text(products[0].get("product")) or product_key
    return product_key, product_name


def _account_names_from_project_update(project_update: dict[str, Any]) -> dict[str, str]:
    rows = project_update.get("accounts")
    names: dict[str, str] = {}
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, dict):
                continue
            account_id = _text(row.get("account_id"))
            account_name = _text(row.get("account_name"))
            if account_id and account_name and account_name != "未配置账户名":
                names[account_id] = account_name
    return names


def _account_names_from_suggestions(suggestions: list[dict[str, Any]]) -> dict[str, str]:
    names: dict[str, str] = {}
    for suggestion in suggestions:
        advertiser_id = _text(suggestion.get("advertiser_id"))
        account_name = _text(suggestion.get("account_name") or suggestion.get("advertiser_name"))
        if advertiser_id and account_name and account_name != advertiser_id:
            names[advertiser_id] = account_name
    return names


def _metrics_text(value: Any) -> str:
    metrics = value if isinstance(value, dict) else {}
    if isinstance(metrics.get("today"), dict):
        metrics = metrics["today"]
    mapping = [
        ("消耗", "stat_cost"),
        ("转化", "billing_convert_cnt"),
        ("转化", "convert_cnt"),
        ("ROI", "billing_1day_pay_roi"),
        ("ROI", "roi_1day"),
        ("项目数", "project_count"),
        ("项目容量", "project_capacity"),
        ("合格素材", "qualified_material_count"),
        ("单元数", "promotion_count"),
        ("账户数", "account_count"),
    ]
    parts: list[str] = []
    seen_labels: set[str] = set()
    for label, key in mapping:
        if label in seen_labels or key not in metrics:
            continue
        raw = metrics.get(key)
        if raw in (None, ""):
            continue
        parts.append(f"{label} {raw}")
        seen_labels.add(label)
    return "，".join(parts)


def _ai_draft_row(
    suggestion: dict[str, Any],
    *,
    account_names: dict[str, str],
    product_by_account: dict[str, str],
) -> dict[str, str]:
    advertiser_id = _text(suggestion.get("advertiser_id"))
    account_name = _text(suggestion.get("account_name") or suggestion.get("advertiser_name")) or account_name_for(
        account_names,
        advertiser_id,
    )
    action = _suggestion_action(suggestion)
    action_label = _action_label_for_suggestion(action)
    project_id = _project_id_from_suggestion(suggestion)
    project_name = _text(suggestion.get("project_name") or suggestion.get("entity_name"))
    product_name = _text(suggestion.get("product_name")) or product_by_account.get(advertiser_id, "未归档产品")
    return {
        "建议 ID": _text(suggestion.get("suggestion_id")),
        "产品": product_name,
        "账户名": account_name,
        "账户 ID": advertiser_id,
        "项目名": project_name,
        "项目 ID": project_id,
        "建议动作": action_label,
        "AI 中文解释": _ai_explanation(
            suggestion,
            account_name=account_name,
            account_id=advertiser_id,
            project_name=project_name,
            project_id=project_id,
            action_label=action_label,
        ),
        "复核点": _ai_review_points(suggestion),
        "草稿状态": "可生成项目管理配置草稿" if _can_convert_to_project_update(suggestion) else "只读建议，不生成项目管理配置草稿",
    }


def _ai_explanation(
    suggestion: dict[str, Any],
    *,
    account_name: str,
    account_id: str,
    project_name: str,
    project_id: str,
    action_label: str,
) -> str:
    source = _source_label(suggestion)
    reason = _text(suggestion.get("reason") or suggestion.get("message") or "规则建议要求人工复核。")
    metrics = _metrics_text(suggestion.get("metrics")) or "未提供关键指标"
    account_text = f"{account_name}（{account_id}）" if account_id else account_name or "未配置账户"
    if project_id or project_name:
        object_text = f"项目{project_name or project_id}（{project_id}）"
    else:
        object_text = f"{_entity_type_label(_text(suggestion.get('entity_type')))}{_text(suggestion.get('entity_name') or suggestion.get('entity_id'))}"
    return (
        f"{action_label}建议来自{source}：账户{account_text}，{object_text}。"
        f"关键指标：{metrics}。规则原因：{reason}。"
        "AI 草稿只解释原因和整理复核点，不执行真实业务动作。"
    )


def _ai_review_points(suggestion: dict[str, Any]) -> str:
    action = _suggestion_action(suggestion).strip().lower()
    points_by_action = {
        "suggest_delete_project": ["确认项目已关闭", "确认近期无有效转化", "确认不是仍需保留的测试项目"],
        "delete_project": ["确认项目已关闭", "确认近期无有效转化", "确认不是仍需保留的测试项目"],
        "suggest_close_project": ["确认不是新建冷启动项目", "确认没有特殊测试目的", "确认暂停后可人工恢复"],
        "pause_project": ["确认不是新建冷启动项目", "确认没有特殊测试目的", "确认暂停后可人工恢复"],
        "close_project": ["确认不是新建冷启动项目", "确认没有特殊测试目的", "确认暂停后可人工恢复"],
        "suggest_lower_budget": ["确认下调比例来自配置", "执行时读取当前预算", "不在草稿里猜预算金额"],
        "adjust_project_budget": ["确认下调比例来自配置", "执行时读取当前预算", "不在草稿里猜预算金额"],
        "suggest_lower_bid": ["确认下调比例来自配置", "执行时读取当前出价", "不在草稿里猜出价金额"],
        "adjust_project_bid": ["确认下调比例来自配置", "执行时读取当前出价", "不在草稿里猜出价金额"],
        "material_reuse_risk": ["复核素材是否过度复用", "复核是否仍有测试价值", "只读诊断不生成项目管理配置"],
        "account_spent_outside_allowlist": ["复核账户归属", "复核允许创建名单", "只读诊断不生成项目管理配置"],
        "watch": ["继续观察后续消耗和转化", "暂不生成项目管理配置"],
        "continue_running": ["继续观察后续消耗和转化", "暂不生成项目管理配置"],
    }
    return "；".join(points_by_action.get(action, ["人工复核建议原因", "确认账户名和项目名", "不直接执行真实业务动作"]))


def _source_label(suggestion: dict[str, Any]) -> str:
    return _text(suggestion.get("source_label")) or "投放巡检建议"


def _project_id_from_suggestion(suggestion: dict[str, Any]) -> str:
    return _text(suggestion.get("project_id") or suggestion.get("entity_id"))


def _ratio_adjustment(suggestion: dict[str, Any]) -> float | None:
    adjustment = suggestion.get("adjustment") if isinstance(suggestion.get("adjustment"), dict) else {}
    if adjustment.get("type") != "ratio":
        direction = _text(adjustment.get("direction"))
        try:
            decrease_percent = float(adjustment.get("decrease_percent"))
        except (TypeError, ValueError):
            return None
        if direction == "decrease":
            return -abs(decrease_percent) / 100
        if direction == "increase":
            return abs(decrease_percent) / 100
        return None
    try:
        return float(adjustment.get("value"))
    except (TypeError, ValueError):
        return None


def _blocked_project_update_preview(request: dict[str, Any], reason: str | list[str]) -> dict[str, Any]:
    reasons = reason if isinstance(reason, list) else [reason]
    return {
        "summary": {
            "title": "项目管理配置预览",
            "status": "blocked",
            "risk_level": "high",
            "execution_enabled": False,
            "items": [
                {"label": "配置 ID", "value": _text(request.get("project_update_id"))},
                {"label": "输出配置", "value": _text(request.get("output_path"))},
            ],
            "warnings": [],
            "blocking_reasons": reasons,
        },
        "table": {"columns": ["账户 ID", "账户名", "项目 ID", "项目名", "动作", "原因"], "rows": []},
        "artifact_path": "",
        "raw": {"request": request},
    }


def _blocked_create_plan_preview(request: dict[str, Any], reason: str | list[str]) -> dict[str, Any]:
    reasons = reason if isinstance(reason, list) else [reason]
    return {
        "summary": {
            "title": "生成创建项目计划预览",
            "status": "blocked",
            "risk_level": "medium",
            "execution_enabled": False,
            "items": [
                {"label": "来源建议", "value": len(_request_selected_suggestion_ids(request))},
                {"label": "产品", "value": _text(request.get("product_name") or request.get("product_key"))},
            ],
            "warnings": [],
            "blocking_reasons": reasons,
        },
        "table": {
            "columns": ["账户 ID", "账户名", "创建模式", "产品", "负责人", "目标日期", "出价", "ROI 系数"],
            "rows": [],
        },
        "artifact_path": "",
        "raw": {"request": request},
    }


def _create_plan_group_rows(result: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for group in _rows(result.get("suggestion_groups")):
        rows.append(
            {
                "批次": _text(group.get("group_id")),
                "产品": _text(group.get("product_name")) or _text(group.get("product_key")),
                "推荐模式": _text(group.get("mode_key")),
                "账户数": int(group.get("account_count") or 0),
                "来源建议": int(group.get("source_suggestion_count") or 0),
                "命中策略": "、".join(_text(item) for item in group.get("strategy_ids") or [] if _text(item)),
                "模板": _text(group.get("template_catalog")),
                "证据": _create_plan_group_evidence_text(group.get("evidence_summary")),
                "状态": "可生成创建计划预览" if bool(group.get("can_generate_single_plan")) else "需补配置",
            }
        )
    return rows


def _create_plan_preview_sections(result: dict[str, Any]) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    group_rows = _create_plan_group_rows(result)
    if group_rows:
        sections.append(
            {
                "title": "建议拆分批次",
                "table": {
                    "columns": ["批次", "产品", "推荐模式", "账户数", "来源建议", "命中策略", "模板", "证据", "状态"],
                    "rows": group_rows,
                },
            }
        )
    evidence_rows = _create_plan_source_evidence_rows(result)
    if evidence_rows:
        sections.append(
            {
                "title": "来源建议证据",
                "table": {
                    "columns": ["建议 ID", "产品", "账户 ID", "账户名", "命中策略", "项目容量", "合格素材", "推荐原因"],
                    "rows": evidence_rows,
                },
            }
        )
    return sections


def _create_plan_source_evidence_rows(result: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for suggestion in _rows(result.get("source_suggestions")):
        metrics = suggestion.get("metrics") if isinstance(suggestion.get("metrics"), dict) else {}
        evidence = suggestion.get("evidence") if isinstance(suggestion.get("evidence"), dict) else {}
        rows.append(
            {
                "建议 ID": _text(suggestion.get("suggestion_id")),
                "产品": _text(suggestion.get("product_name") or suggestion.get("product")),
                "账户 ID": _text(suggestion.get("advertiser_id")),
                "账户名": _text(suggestion.get("account_name") or suggestion.get("advertiser_name")),
                "命中策略": _text(suggestion.get("strategy_id") or suggestion.get("rule_id")),
                "项目容量": _text(metrics.get("project_capacity") or evidence.get("project_capacity")),
                "合格素材": _text(metrics.get("qualified_material_count") or evidence.get("qualified_material_count")),
                "推荐原因": _text(suggestion.get("reason") or suggestion.get("message")),
            }
        )
    return rows


def _create_strategy_review_row(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "策略 ID": _text(record.get("strategy_id")),
        "版本": _text(record.get("strategy_version")),
        "状态": _strategy_review_status_label(_text(record.get("status"))),
        "启用": "是" if bool(record.get("enabled")) else "否",
        "来源": _strategy_source_label(_text(record.get("source_kind"))),
        "产品": _text(record.get("product_name")) or _text(record.get("product_key")),
        "产品 Key": _text(record.get("product_key")),
        "推荐模式": _text(record.get("mode_key")),
        "模式配置": _text(record.get("mode_config_path")),
        "模板": _text(record.get("template_catalog")),
        "策略文件": _text(record.get("config_path")),
        "允许账户": int(record.get("allowed_account_count") or 0),
        "账户池": int(record.get("account_pool_count") or 0),
        "候选账户": int(record.get("candidate_account_count") or 0),
        "合格素材": int(record.get("qualified_material_count") or 0),
        "预计建议": int(record.get("estimated_suggestion_count") or 0),
        "阻断候选": int(record.get("blocked_candidate_count") or 0),
        "账户阈值": _strategy_account_threshold_text(record.get("account_thresholds")),
        "素材阈值": _strategy_material_threshold_text(record.get("material_thresholds")),
        "推荐创建": _strategy_recommendation_text(record.get("recommendation")),
        "阻断原因": _strategy_review_reasons_text(record.get("blocking_reasons"), record.get("top_blocking_reasons")),
        "警告": "；".join(_text(item) for item in record.get("warnings") or [] if _text(item)),
        "修复建议": "；".join(_text(item) for item in record.get("repair_suggestions") or [] if _text(item)),
    }


def _strategy_review_status_label(status: str) -> str:
    return {
        "healthy": "可产出建议",
        "warning": "需关注",
        "blocked": "阻断",
        "disabled": "未启用",
    }.get(status, status or "未知")


def _strategy_source_label(kind: str) -> str:
    return {
        "local": "本地策略",
        "example": "示例模板",
        "json": "策略 JSON",
    }.get(kind, kind or "未知")


def _strategy_account_threshold_text(value: Any) -> str:
    thresholds = value if isinstance(value, dict) else {}
    scope = _text(thresholds.get("candidate_scope")) or "allowed_and_account_pool"
    require_allowed = "必须在允许名单" if bool(thresholds.get("require_allowed_account")) else "允许名单可选"
    recent = ""
    if scope == "allowed_accounts_with_recent_spend":
        recent = (
            f"；近 {int(thresholds.get('recent_window_days') or 1)} 天"
            f"消耗≥{_compact_number(thresholds.get('min_recent_stat_cost'))}"
            f"且转化≥{_compact_number(thresholds.get('min_recent_convert_cnt'))}"
        )
    return (
        f"{require_allowed}{recent}；项目上限 {int(thresholds.get('max_active_projects') or 0)}；"
        f"创建冷却 {int(thresholds.get('cooldown_days_after_create') or 0)} 天"
    )


def _strategy_material_threshold_text(value: Any) -> str:
    thresholds = value if isinstance(value, dict) else {}
    return (
        f"{_text(thresholds.get('window_key')) or 'last_7d'} / {_text(thresholds.get('material_type')) or 'video'}；"
        f"素材≥{int(thresholds.get('min_qualified_material_count') or 0)}；"
        f"消耗≥{_compact_number(thresholds.get('min_stat_cost'))}；"
        f"转化≥{_compact_number(thresholds.get('min_convert_cnt'))}；"
        f"ROI≥{_compact_number(thresholds.get('min_roi_1day'))}"
    )


def _strategy_recommendation_text(value: Any) -> str:
    recommendation = value if isinstance(value, dict) else {}
    return (
        f"项目 {int(recommendation.get('project_count') or 0)}；"
        f"单元/项目 {int(recommendation.get('units_per_project') or 0)}；"
        f"日预算 {_compact_number(recommendation.get('daily_budget'))}"
    )


def _strategy_review_reasons_text(reasons: Any, top_reasons: Any) -> str:
    parts = [_text(item) for item in reasons or [] if _text(item)]
    if isinstance(top_reasons, dict):
        for reason, count in top_reasons.items():
            text = _text(reason)
            if text:
                parts.append(f"{text}（{int(count or 0)} 个候选）")
    seen: set[str] = set()
    result: list[str] = []
    for part in parts:
        if part in seen:
            continue
        seen.add(part)
        result.append(part)
    return "；".join(result)


def _compact_number(value: Any) -> str:
    number = _number(value)
    return str(int(number)) if number.is_integer() else f"{number:.4g}"


def _lifecycle_table_row(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "建议 ID": _text(record.get("suggestion_id")),
        "创建状态": _text(record.get("lifecycle_label")) or "未处理",
        "锁定": "是" if bool(record.get("locked_for_create_plan")) else "否",
        "计划预览": _text(record.get("plan_preview_path")),
        "执行前复核": _text(record.get("execution_review_path")),
        "执行任务": _text(record.get("execution_task_id")),
        "最近事件": _text(record.get("last_event_at")),
        "阻断原因": "；".join(_text(item) for item in record.get("blocking_reasons") or [] if _text(item)),
        "警告": "；".join(_text(item) for item in record.get("warnings") or [] if _text(item)),
    }


def _locked_create_suggestion_reasons(lifecycle: dict[str, Any], suggestion_ids: list[str]) -> list[str]:
    by_id = lifecycle.get("by_suggestion_id") if isinstance(lifecycle.get("by_suggestion_id"), dict) else {}
    reasons: list[str] = []
    for suggestion_id in suggestion_ids:
        record = by_id.get(suggestion_id)
        if not isinstance(record, dict) or not bool(record.get("locked_for_create_plan")):
            continue
        status = _text(record.get("lifecycle_label")) or _text(record.get("lifecycle_status"))
        task_id = _text(record.get("execution_task_id"))
        suffix = f"，执行任务 {task_id}" if task_id else ""
        reasons.append(f"建议 {suggestion_id} 已进入真实执行链路（{status}{suffix}），不能重复生成创建计划。")
    return reasons


def _create_plan_group_evidence_text(value: Any) -> str:
    evidence = value if isinstance(value, dict) else {}
    parts = []
    if "min_project_capacity" in evidence:
        parts.append(f"最小容量 {evidence.get('min_project_capacity')}")
    if "min_qualified_material_count" in evidence:
        parts.append(f"最少合格素材 {evidence.get('min_qualified_material_count')}")
    if "max_current_project_count" in evidence:
        parts.append(f"当前项目最多 {evidence.get('max_current_project_count')}")
    return "，".join(parts)


def _blocked_ai_draft(reason: str) -> dict[str, Any]:
    return {
        "summary": {
            "title": "AI 建议草稿",
            "status": "blocked",
            "risk_level": "low",
            "execution_enabled": False,
            "items": [],
            "warnings": [],
            "blocking_reasons": [reason],
        },
        "table": {
            "columns": [
                "建议 ID",
                "产品",
                "账户名",
                "账户 ID",
                "项目名",
                "项目 ID",
                "建议动作",
                "AI 中文解释",
                "复核点",
                "草稿状态",
            ],
            "rows": [],
        },
        "artifact_path": "",
        "raw": {
            "workflow": "ai_suggestion_drafts",
            "ai_policy": {
                "draft_only": True,
                "external_api_calls": 0,
                "execution_enabled": False,
                "note": "AI 建议只解释和生成草稿，不执行真实业务动作。",
            },
        },
    }


def _project_action_row(action: dict[str, Any], account_names: dict[str, str]) -> dict[str, Any]:
    advertiser_id = _text(action.get("advertiser_id"))
    return {
        "账户 ID": advertiser_id,
        "账户名": account_name_for(account_names, advertiser_id),
        "项目 ID": _text(action.get("project_id")),
        "项目名": _text(action.get("project_name")),
        "动作": _project_action_label(_text(action.get("action_type")), action),
        "原因": _text(action.get("reason")),
    }


def _project_action_label(action_type: str, action: dict[str, Any]) -> str:
    if action_type == "delete_project":
        return "删除项目"
    if action_type == "status_update" and _text(action.get("opt_status")) == "DISABLE":
        return "暂停项目"
    if action_type == "status_update" and _text(action.get("opt_status")) == "ENABLE":
        return "开启项目"
    if action_type == "budget_update":
        return "调预算"
    if action_type == "bid_update":
        return "调出价"
    if action_type == "schedule_hollow":
        return "调整时段"
    return action_type


def _suggestion_action(suggestion: dict[str, Any]) -> str:
    return _text(suggestion.get("suggested_action") or suggestion.get("suggestion_type") or suggestion.get("action"))


def _action_info(action: str) -> dict[str, str]:
    normalized = action.strip().lower()
    return ACTION_INFO.get(normalized, {"label": action or "人工复核", "priority": "中", "config_hint": "需要人工复核后再生成配置"})


def _action_label_for_suggestion(action: str) -> str:
    return _action_info(action).get("label", action or "人工复核")


def _can_convert_to_project_update(suggestion: dict[str, Any]) -> bool:
    action = _suggestion_action(suggestion).strip().lower()
    return action in {
        "suggest_delete_project",
        "delete_project",
        "suggest_close_project",
        "pause_project",
        "close_project",
        "suggest_lower_budget",
        "adjust_project_budget",
        "suggest_lower_bid",
        "adjust_project_bid",
        "schedule_hollow",
    }


def _entity_type_label(value: str) -> str:
    normalized = value.strip().lower()
    if normalized in {"project", "项目"}:
        return "项目"
    if normalized in {"account", "账户"}:
        return "账户"
    if normalized in {"promotion", "unit", "单元"}:
        return "单元"
    if normalized in {"material", "素材"}:
        return "素材"
    return value


def _resolve_path(project_root: Path, path_text: str) -> Path:
    path = Path(path_text)
    return path if path.is_absolute() else project_root / path


def _enabled(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on", "是", "启用"}


def _number(value: Any) -> float:
    try:
        if value in (None, ""):
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _text(value: Any) -> str:
    return str(value or "").strip()
