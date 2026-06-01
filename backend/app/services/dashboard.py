from __future__ import annotations

from datetime import date
from datetime import datetime
from datetime import timedelta
from pathlib import Path
from typing import Any

from backend.app.services.accounts_store import load_accounts
from backend.app.services.artifacts import find_latest_artifact
from backend.app.services.artifacts import read_json

HEALTHY_PROJECT_STATUSES = {
    "",
    "healthy",
    "normal",
    "running",
    "continue_running",
    "good",
    "stable",
}


def build_dashboard_filters(configs_dir: str | Path) -> dict[str, Any]:
    accounts = load_accounts(configs_dir)
    rows = []
    product_seen: set[str] = set()
    for account in accounts:
        product_key = str(account.get("product_key") or "")
        if product_key and product_key not in product_seen:
            rows.append({"类型": "产品", "显示名称": str(account.get("product_name") or product_key), "值": product_key})
            product_seen.add(product_key)
    rows.extend(_filter_rows(accounts, "渠道", "channel"))
    rows.extend(_filter_rows(accounts, "负责人", "owner"))
    rows.extend(
        [
            {"类型": "状态", "显示名称": "active", "值": "active"},
            {"类型": "状态", "显示名称": "paused", "值": "paused"},
            {"类型": "状态", "显示名称": "disabled", "值": "disabled"},
        ]
    )
    return {
        "summary": {
            "title": "看板筛选项",
            "status": "loaded",
            "risk_level": "low",
            "execution_enabled": False,
            "items": [
                {"label": "产品数", "value": len(product_seen)},
                {"label": "筛选项", "value": len(rows)},
            ],
            "warnings": [] if accounts else ["产品账户库为空，请先在产品账户库导入账户归属。"],
            "blocking_reasons": [],
        },
        "table": {"columns": ["类型", "显示名称", "值"], "rows": rows},
        "artifact_path": "",
        "raw": {"filters": rows},
    }


def build_dashboard_overview(
    runs_dir: str | Path,
    configs_dir: str | Path,
    *,
    product_key: str = "",
    channel: str = "",
    owner: str = "",
    status: str = "",
    start_date: str = "",
    end_date: str = "",
    date_range: str = "",
) -> dict[str, Any]:
    context = _load_dashboard_context(
        runs_dir,
        configs_dir,
        product_key=product_key,
        channel=channel,
        owner=owner,
        status=status,
        start_date=start_date,
        end_date=end_date,
        date_range=date_range,
    )
    products = _build_product_rows(context)
    metric_totals = _sum_product_rows(products)
    active_accounts = sum(1 for account in context["accounts"] if account.get("status") == "active")
    if not context["accounts"]:
        active_accounts = _int(context["patrol"].get("summary", {}).get("account_count"))

    abnormal_projects = sum(1 for project in context["projects"] if _is_abnormal_project(project))
    suggestion_count = _suggestion_count(context["suggestions_payload"], context["suggestions"])
    warnings = []
    if context["patrol_path"] is None:
        warnings.append("未找到最近巡检结果，首页只展示账户库中的静态信息。")

    return {
        "summary": {
            "title": "首页数据看板",
            "status": "loaded",
            "risk_level": "medium" if abnormal_projects or suggestion_count else "low",
            "execution_enabled": False,
            "items": [
                {"label": "数据日期", "value": _context_target_date(context)},
                {"label": "今日消耗", "value": metric_totals["消耗"]},
                {"label": "计费转化", "value": metric_totals["计费转化"]},
                {"label": "转化成本", "value": metric_totals["转化成本"]},
                {"label": "付费 ROI", "value": metric_totals["付费 ROI"]},
                {"label": "活跃账户", "value": active_accounts},
                {"label": "活跃项目", "value": len(context["projects"])},
                {"label": "异常项目", "value": abnormal_projects},
                {"label": "建议事项", "value": suggestion_count},
            ],
            "warnings": warnings,
            "blocking_reasons": [],
        },
        "table": {
            "columns": ["产品", "账户数", "消耗", "计费转化", "转化成本", "付费 ROI", "异常项目", "建议事项"],
            "rows": products,
        },
        "artifact_path": str(context["patrol_path"] or ""),
        "raw": {
            "patrol_artifact_path": str(context["patrol_path"] or ""),
            "suggestions_artifact_path": str(context["suggestions_path"] or ""),
            "product_rows": products,
        },
    }


def build_dashboard_products(
    runs_dir: str | Path,
    configs_dir: str | Path,
    *,
    product_key: str = "",
    channel: str = "",
    owner: str = "",
    status: str = "",
    start_date: str = "",
    end_date: str = "",
    date_range: str = "",
) -> dict[str, Any]:
    context = _load_dashboard_context(
        runs_dir,
        configs_dir,
        product_key=product_key,
        channel=channel,
        owner=owner,
        status=status,
        start_date=start_date,
        end_date=end_date,
        date_range=date_range,
    )
    rows = _build_product_rows(context)
    return {
        "summary": {
            "title": "产品看板",
            "status": "loaded",
            "risk_level": "medium" if any(_num(row.get("异常项目")) for row in rows) else "low",
            "execution_enabled": False,
            "items": [
                {"label": "产品数", "value": len(rows)},
                {"label": "账户数", "value": len(context["accounts"])},
                {"label": "项目数", "value": len(context["projects"])},
                {"label": "建议事项", "value": _suggestion_count(context["suggestions_payload"], context["suggestions"])},
            ],
            "warnings": [],
            "blocking_reasons": [],
        },
        "table": {
            "columns": ["产品", "账户数", "消耗", "计费转化", "转化成本", "付费 ROI", "异常项目", "建议事项"],
            "rows": rows,
        },
        "artifact_path": str(context["patrol_path"] or ""),
        "raw": {"product_rows": rows},
    }


def build_dashboard_product_detail(
    runs_dir: str | Path,
    configs_dir: str | Path,
    product_key: str,
    *,
    start_date: str = "",
    end_date: str = "",
    date_range: str = "",
) -> dict[str, Any] | None:
    context = _load_dashboard_context(
        runs_dir,
        configs_dir,
        product_key=product_key,
        start_date=start_date,
        end_date=end_date,
        date_range=date_range,
    )
    if not context["accounts"] and not context["patrol_accounts"] and not context["projects"]:
        return None
    product_rows = _build_product_rows(context)
    product_row = product_rows[0] if product_rows else _unknown_product_row("")
    product_name = str(product_row.get("产品") or product_key)
    account_rows = _build_account_rows(context)
    active_accounts = sum(1 for account in context["accounts"] if account.get("status") == "active")
    abnormal_projects = sum(1 for project in context["projects"] if _is_abnormal_project(project))
    detail_rows = _product_detail_rows(
        product_name=product_name,
        account_rows=account_rows,
        project_rows=context["projects"],
        promotion_rows=context["promotions"],
        suggestion_rows=context["suggestions"],
    )
    return {
        "summary": {
            "title": "产品详情",
            "status": "loaded",
            "risk_level": "medium" if abnormal_projects or context["suggestions"] else "low",
            "execution_enabled": False,
            "items": [
                {"label": "产品", "value": product_name},
                {"label": "产品 Key", "value": product_key},
                {"label": "账户数", "value": len(account_rows)},
                {"label": "活跃账户", "value": active_accounts},
                {"label": "消耗", "value": product_row.get("消耗")},
                {"label": "计费转化", "value": product_row.get("计费转化")},
                {"label": "转化成本", "value": product_row.get("转化成本")},
                {"label": "付费 ROI", "value": product_row.get("付费 ROI")},
                {"label": "项目数", "value": len(context["projects"])},
                {"label": "异常项目", "value": abnormal_projects},
                {"label": "单元素材数", "value": len(context["promotions"])},
                {"label": "建议事项", "value": len(context["suggestions"])},
            ],
            "warnings": [] if context["patrol_path"] else ["未找到最近巡检结果，产品详情可能缺少投放指标。"],
            "blocking_reasons": [],
        },
        "table": {
            "columns": ["类型", "产品", "账户 ID", "关联 ID", "名称", "状态/动作", "消耗", "计费转化", "说明"],
            "rows": detail_rows,
        },
        "artifact_path": str(context["patrol_path"] or ""),
        "raw": {
            "product_key": product_key,
            "accounts": account_rows,
            "projects": context["projects"],
            "promotions": context["promotions"],
            "suggestions": context["suggestions"],
            "patrol_artifact_path": str(context["patrol_path"] or ""),
            "suggestions_artifact_path": str(context["suggestions_path"] or ""),
        },
    }


def build_dashboard_projects(
    runs_dir: str | Path,
    configs_dir: str | Path,
    *,
    product_key: str = "",
    channel: str = "",
    owner: str = "",
    status: str = "",
    start_date: str = "",
    end_date: str = "",
    date_range: str = "",
) -> dict[str, Any]:
    context = _load_dashboard_context(
        runs_dir,
        configs_dir,
        product_key=product_key,
        channel=channel,
        owner=owner,
        status=status,
        start_date=start_date,
        end_date=end_date,
        date_range=date_range,
    )
    rows = []
    suggestion_reasons = _suggestion_reason_by_project(context["suggestions"])
    for project in context["projects"]:
        advertiser_id = str(project.get("advertiser_id") or "")
        metrics = _today_metrics(project)
        project_id = str(project.get("project_id") or "")
        rows.append(
            {
                "产品": context["product_by_advertiser"].get(advertiser_id, "未归档产品"),
                "账户 ID": advertiser_id,
                "项目 ID": project_id,
                "项目名": str(project.get("project_name") or project.get("name") or ""),
                "状态": str(project.get("business_status") or project.get("status") or ""),
                "消耗": _round(_num(metrics.get("stat_cost"))),
                "计费转化": _round(_num(metrics.get("billing_convert_cnt"))),
                "异常原因": suggestion_reasons.get((advertiser_id, project_id), _project_status_reason(project)),
            }
        )

    abnormal_projects = sum(1 for project in context["projects"] if _is_abnormal_project(project))
    return {
        "summary": {
            "title": "项目看板",
            "status": "loaded",
            "risk_level": "medium" if abnormal_projects else "low",
            "execution_enabled": False,
            "items": [
                {"label": "项目数", "value": len(rows)},
                {"label": "异常项目", "value": abnormal_projects},
            ],
            "warnings": [],
            "blocking_reasons": [],
        },
        "table": {
            "columns": ["产品", "账户 ID", "项目 ID", "项目名", "状态", "消耗", "计费转化", "异常原因"],
            "rows": rows,
        },
        "artifact_path": str(context["patrol_path"] or ""),
        "raw": {"projects": context["projects"]},
    }


def build_dashboard_project_detail(
    runs_dir: str | Path,
    configs_dir: str | Path,
    project_id: str,
    *,
    start_date: str = "",
    end_date: str = "",
    date_range: str = "",
) -> dict[str, Any] | None:
    context = _load_dashboard_context(runs_dir, configs_dir, start_date=start_date, end_date=end_date, date_range=date_range)
    project = next((row for row in context["projects"] if str(row.get("project_id") or "") == project_id), None)
    if project is None:
        return None
    advertiser_id = str(project.get("advertiser_id") or "")
    product_name = context["product_by_advertiser"].get(advertiser_id, "未归档产品")
    promotion_rows = [
        row
        for row in context["promotions"]
        if str(row.get("advertiser_id") or "") == advertiser_id and str(row.get("project_id") or "") == project_id
    ]
    suggestion_rows = [
        row
        for row in context["suggestions"]
        if str(row.get("advertiser_id") or "") == advertiser_id and str(row.get("project_id") or "") == project_id
    ]
    metrics = _today_metrics(project)
    status = str(project.get("business_status") or project.get("status") or "")
    return {
        "summary": {
            "title": "项目详情",
            "status": "loaded",
            "risk_level": "medium" if _is_abnormal_project(project) or suggestion_rows else "low",
            "execution_enabled": False,
            "items": [
                {"label": "产品", "value": product_name},
                {"label": "账户 ID", "value": advertiser_id},
                {"label": "项目 ID", "value": project_id},
                {"label": "项目名", "value": str(project.get("project_name") or project.get("name") or "")},
                {"label": "状态", "value": status},
                {"label": "消耗", "value": _round(_num(metrics.get("stat_cost")))},
                {"label": "计费转化", "value": _round(_num(metrics.get("billing_convert_cnt")))},
                {"label": "单元素材数", "value": len(promotion_rows)},
                {"label": "建议事项", "value": len(suggestion_rows)},
            ],
            "warnings": [] if context["patrol_path"] else ["未找到最近巡检结果，项目详情可能缺少投放指标。"],
            "blocking_reasons": [],
        },
        "table": {
            "columns": ["类型", "产品", "账户 ID", "关联 ID", "名称", "状态/动作", "消耗", "计费转化", "说明"],
            "rows": _account_detail_rows(
                advertiser_id=advertiser_id,
                product_name=product_name,
                project_rows=[project],
                promotion_rows=promotion_rows,
                suggestion_rows=suggestion_rows,
            ),
        },
        "artifact_path": str(context["patrol_path"] or ""),
        "raw": {
            "project": project,
            "promotions": promotion_rows,
            "suggestions": suggestion_rows,
            "patrol_artifact_path": str(context["patrol_path"] or ""),
            "suggestions_artifact_path": str(context["suggestions_path"] or ""),
        },
    }


def build_dashboard_accounts(
    runs_dir: str | Path,
    configs_dir: str | Path,
    *,
    product_key: str = "",
    channel: str = "",
    owner: str = "",
    status: str = "",
    start_date: str = "",
    end_date: str = "",
    date_range: str = "",
) -> dict[str, Any]:
    context = _load_dashboard_context(
        runs_dir,
        configs_dir,
        product_key=product_key,
        channel=channel,
        owner=owner,
        status=status,
        start_date=start_date,
        end_date=end_date,
        date_range=date_range,
    )
    rows = _build_account_rows(context)
    abnormal_accounts = sum(1 for row in rows if _num(row.get("异常项目")) or _num(row.get("建议事项")))
    metric_totals = _sum_account_rows(rows)
    return {
        "summary": {
            "title": "账户看板",
            "status": "loaded",
            "risk_level": "medium" if abnormal_accounts else "low",
            "execution_enabled": False,
            "items": [
                {"label": "账户数", "value": len(rows)},
                {"label": "消耗", "value": metric_totals["消耗"]},
                {"label": "计费转化", "value": metric_totals["计费转化"]},
                {"label": "异常账户", "value": abnormal_accounts},
            ],
            "warnings": [],
            "blocking_reasons": [],
        },
        "table": {
            "columns": [
                "产品",
                "账户 ID",
                "账户名",
                "渠道",
                "负责人",
                "状态",
                "消耗",
                "计费转化",
                "转化成本",
                "付费 ROI",
                "项目数",
                "异常项目",
                "建议事项",
            ],
            "rows": rows,
        },
        "artifact_path": str(context["patrol_path"] or ""),
        "raw": {"accounts": rows},
    }


def build_dashboard_account_detail(
    runs_dir: str | Path,
    configs_dir: str | Path,
    advertiser_id: str,
    *,
    start_date: str = "",
    end_date: str = "",
    date_range: str = "",
) -> dict[str, Any] | None:
    context = _load_dashboard_context(runs_dir, configs_dir, start_date=start_date, end_date=end_date, date_range=date_range)
    account_rows = _build_account_rows(context)
    account_row = next((row for row in account_rows if str(row.get("账户 ID") or "") == advertiser_id), None)
    project_rows = [project for project in context["projects"] if str(project.get("advertiser_id") or "") == advertiser_id]
    promotion_rows = [
        promotion for promotion in context["promotions"] if str(promotion.get("advertiser_id") or "") == advertiser_id
    ]
    suggestion_rows = [
        suggestion for suggestion in context["suggestions"] if str(suggestion.get("advertiser_id") or "") == advertiser_id
    ]
    if account_row is None and not project_rows and not promotion_rows and not suggestion_rows:
        return None
    if account_row is None:
        account_row = _minimal_account_row(advertiser_id, context)

    product_name = str(account_row.get("产品") or "未归档产品")
    detail_rows = _account_detail_rows(
        advertiser_id=advertiser_id,
        product_name=product_name,
        project_rows=project_rows,
        promotion_rows=promotion_rows,
        suggestion_rows=suggestion_rows,
    )
    warnings = []
    if not any(str(account.get("advertiser_id") or "") == advertiser_id for account in context["accounts"]):
        warnings.append("该账户未在产品账户库归档，详情来自最近巡检结果。")
    if context["patrol_path"] is None:
        warnings.append("未找到最近巡检结果，账户详情可能缺少投放指标。")

    risk_level = "medium" if account_row.get("异常项目") or account_row.get("建议事项") else "low"
    return {
        "summary": {
            "title": "账户详情",
            "status": "loaded",
            "risk_level": risk_level,
            "execution_enabled": False,
            "items": [
                {"label": "产品", "value": product_name},
                {"label": "账户 ID", "value": advertiser_id},
                {"label": "账户名", "value": account_row.get("账户名")},
                {"label": "渠道", "value": account_row.get("渠道")},
                {"label": "负责人", "value": account_row.get("负责人")},
                {"label": "状态", "value": account_row.get("状态")},
                {"label": "消耗", "value": account_row.get("消耗")},
                {"label": "计费转化", "value": account_row.get("计费转化")},
                {"label": "转化成本", "value": account_row.get("转化成本")},
                {"label": "付费 ROI", "value": account_row.get("付费 ROI")},
                {"label": "项目数", "value": len(project_rows)},
                {"label": "异常项目", "value": sum(1 for project in project_rows if _is_abnormal_project(project))},
                {"label": "单元素材数", "value": len(promotion_rows)},
                {"label": "建议事项", "value": len(suggestion_rows)},
            ],
            "warnings": warnings,
            "blocking_reasons": [],
        },
        "table": {
            "columns": ["类型", "产品", "账户 ID", "关联 ID", "名称", "状态/动作", "消耗", "计费转化", "说明"],
            "rows": detail_rows,
        },
        "artifact_path": str(context["patrol_path"] or ""),
        "raw": {
            "account": account_row,
            "projects": project_rows,
            "promotions": promotion_rows,
            "suggestions": suggestion_rows,
            "patrol_artifact_path": str(context["patrol_path"] or ""),
            "suggestions_artifact_path": str(context["suggestions_path"] or ""),
        },
    }


def build_dashboard_suggestions(
    runs_dir: str | Path,
    configs_dir: str | Path,
    *,
    product_key: str = "",
    channel: str = "",
    owner: str = "",
    status: str = "",
    start_date: str = "",
    end_date: str = "",
    date_range: str = "",
) -> dict[str, Any]:
    context = _load_dashboard_context(
        runs_dir,
        configs_dir,
        product_key=product_key,
        channel=channel,
        owner=owner,
        status=status,
        start_date=start_date,
        end_date=end_date,
        date_range=date_range,
    )
    rows = []
    account_name_by_advertiser = _dashboard_account_names(context)
    for suggestion in context["suggestions"]:
        advertiser_id = str(suggestion.get("advertiser_id") or "")
        action = str(suggestion.get("suggested_action") or suggestion.get("action") or suggestion.get("suggestion_type") or "")
        action_info = _suggestion_action_info(action)
        rows.append(
            {
                "优先级": action_info["priority"],
                "产品": context["product_by_advertiser"].get(advertiser_id, "未归档产品"),
                "账户 ID": advertiser_id,
                "账户名": account_name_by_advertiser.get(advertiser_id, ""),
                "层级": str(suggestion.get("target_level") or suggestion.get("level") or ""),
                "项目 ID": str(suggestion.get("project_id") or ""),
                "建议动作": action,
                "中文解释": _suggestion_explanation(suggestion),
                "可生成配置": action_info["config_hint"],
            }
        )

    suggestion_count = _suggestion_count(context["suggestions_payload"], context["suggestions"])
    configurable_count = sum(1 for row in rows if str(row.get("可生成配置") or "").startswith("可生成"))
    return {
        "summary": {
            "title": "异常与建议中心",
            "status": "loaded",
            "risk_level": "medium" if suggestion_count else "low",
            "execution_enabled": False,
            "items": [
                {"label": "建议事项", "value": suggestion_count},
                {"label": "可生成配置", "value": configurable_count},
            ],
            "warnings": [] if context["suggestions_path"] else ["未找到最近建议结果，当前显示为空。"],
            "blocking_reasons": [],
        },
        "table": {
            "columns": ["优先级", "产品", "账户 ID", "账户名", "层级", "项目 ID", "建议动作", "中文解释", "可生成配置"],
            "rows": rows,
        },
        "artifact_path": str(context["suggestions_path"] or ""),
        "raw": {"suggestions": context["suggestions"]},
    }


def _dashboard_account_names(context: dict[str, Any]) -> dict[str, str]:
    names: dict[str, str] = {}
    for account in context["accounts"]:
        advertiser_id = str(account.get("advertiser_id") or "").strip()
        account_name = str(account.get("advertiser_name") or account.get("account_name") or "").strip()
        if advertiser_id and account_name:
            names[advertiser_id] = account_name
    for account in context["patrol_accounts"]:
        advertiser_id = str(account.get("advertiser_id") or "").strip()
        account_name = str(account.get("advertiser_name") or account.get("account_name") or "").strip()
        if advertiser_id and account_name:
            names.setdefault(advertiser_id, account_name)
    for suggestion in context["suggestions"]:
        advertiser_id = str(suggestion.get("advertiser_id") or "").strip()
        account_name = str(suggestion.get("advertiser_name") or suggestion.get("account_name") or "").strip()
        if advertiser_id and account_name:
            names.setdefault(advertiser_id, account_name)
    return names


def build_dashboard_materials(
    runs_dir: str | Path,
    configs_dir: str | Path,
    *,
    product_key: str = "",
    channel: str = "",
    owner: str = "",
    status: str = "",
    start_date: str = "",
    end_date: str = "",
    date_range: str = "",
) -> dict[str, Any]:
    context = _load_dashboard_context(
        runs_dir,
        configs_dir,
        product_key=product_key,
        channel=channel,
        owner=owner,
        status=status,
        start_date=start_date,
        end_date=end_date,
        date_range=date_range,
    )
    rows = []
    for promotion in context["promotions"]:
        advertiser_id = str(promotion.get("advertiser_id") or "")
        metrics = _today_metrics(promotion)
        rows.append(
            {
                "产品": context["product_by_advertiser"].get(advertiser_id, "未归档产品"),
                "账户 ID": advertiser_id,
                "项目 ID": str(promotion.get("project_id") or ""),
                "单元 ID": str(promotion.get("promotion_id") or promotion.get("unit_id") or ""),
                "单元名": str(promotion.get("promotion_name") or promotion.get("name") or ""),
                "状态": str(promotion.get("business_status") or promotion.get("status") or ""),
                "消耗": _round(_num(metrics.get("stat_cost"))),
                "计费转化": _round(_num(metrics.get("billing_convert_cnt"))),
                "付费 ROI": _round(_num(metrics.get("billing_1day_pay_roi"))) if metrics.get("billing_1day_pay_roi") is not None else None,
            }
        )

    attention_count = sum(1 for row in rows if str(row.get("状态") or "").lower() not in HEALTHY_PROJECT_STATUSES)
    return {
        "summary": {
            "title": "单元素材看板",
            "status": "loaded",
            "risk_level": "medium" if attention_count else "low",
            "execution_enabled": False,
            "items": [
                {"label": "单元素材数", "value": len(rows)},
                {"label": "需关注", "value": attention_count},
            ],
            "warnings": [] if rows else ["最近巡检结果中没有单元/素材明细。"],
            "blocking_reasons": [],
        },
        "table": {
            "columns": ["产品", "账户 ID", "项目 ID", "单元 ID", "单元名", "状态", "消耗", "计费转化", "付费 ROI"],
            "rows": rows,
        },
        "artifact_path": str(context["patrol_path"] or ""),
        "raw": {"promotions": context["promotions"]},
    }


def build_dashboard_material_detail(
    runs_dir: str | Path,
    configs_dir: str | Path,
    promotion_id: str,
    *,
    start_date: str = "",
    end_date: str = "",
    date_range: str = "",
) -> dict[str, Any] | None:
    context = _load_dashboard_context(runs_dir, configs_dir, start_date=start_date, end_date=end_date, date_range=date_range)
    promotion = next(
        (
            row
            for row in context["promotions"]
            if str(row.get("promotion_id") or row.get("unit_id") or "") == promotion_id
        ),
        None,
    )
    if promotion is None:
        return None
    advertiser_id = str(promotion.get("advertiser_id") or "")
    project_id = str(promotion.get("project_id") or "")
    product_name = context["product_by_advertiser"].get(advertiser_id, "未归档产品")
    project = next(
        (
            row
            for row in context["projects"]
            if str(row.get("advertiser_id") or "") == advertiser_id and str(row.get("project_id") or "") == project_id
        ),
        None,
    )
    project_rows = [project] if project else []
    suggestion_rows = [
        row
        for row in context["suggestions"]
        if str(row.get("advertiser_id") or "") == advertiser_id and str(row.get("project_id") or "") == project_id
    ]
    metrics = _today_metrics(promotion)
    status = str(promotion.get("business_status") or promotion.get("status") or "")
    return {
        "summary": {
            "title": "单元素材详情",
            "status": "loaded",
            "risk_level": "medium" if status.strip().lower() not in HEALTHY_PROJECT_STATUSES or suggestion_rows else "low",
            "execution_enabled": False,
            "items": [
                {"label": "产品", "value": product_name},
                {"label": "账户 ID", "value": advertiser_id},
                {"label": "项目 ID", "value": project_id},
                {"label": "单元 ID", "value": promotion_id},
                {"label": "单元名", "value": str(promotion.get("promotion_name") or promotion.get("name") or "")},
                {"label": "状态", "value": status},
                {"label": "消耗", "value": _round(_num(metrics.get("stat_cost")))},
                {"label": "计费转化", "value": _round(_num(metrics.get("billing_convert_cnt")))},
                {
                    "label": "付费 ROI",
                    "value": _round(_num(metrics.get("billing_1day_pay_roi"))) if metrics.get("billing_1day_pay_roi") is not None else None,
                },
                {"label": "关联建议", "value": len(suggestion_rows)},
            ],
            "warnings": [] if context["patrol_path"] else ["未找到最近巡检结果，单元素材详情可能缺少投放指标。"],
            "blocking_reasons": [],
        },
        "table": {
            "columns": ["类型", "产品", "账户 ID", "关联 ID", "名称", "状态/动作", "消耗", "计费转化", "说明"],
            "rows": _account_detail_rows(
                advertiser_id=advertiser_id,
                product_name=product_name,
                project_rows=project_rows,
                promotion_rows=[promotion],
                suggestion_rows=suggestion_rows,
            ),
        },
        "artifact_path": str(context["patrol_path"] or ""),
        "raw": {
            "promotion": promotion,
            "project": project or {},
            "suggestions": suggestion_rows,
            "patrol_artifact_path": str(context["patrol_path"] or ""),
            "suggestions_artifact_path": str(context["suggestions_path"] or ""),
        },
    }


def _load_dashboard_context(
    runs_dir: str | Path,
    configs_dir: str | Path,
    *,
    product_key: str = "",
    channel: str = "",
    owner: str = "",
    status: str = "",
    start_date: str = "",
    end_date: str = "",
    date_range: str = "",
) -> dict[str, Any]:
    resolved_start_date, resolved_end_date = _resolve_date_range(
        date_range=date_range,
        start_date=start_date,
        end_date=end_date,
    )
    accounts = [
        account
        for account in load_accounts(configs_dir)
        if _account_matches(account, product_key=product_key, channel=channel, owner=owner, status=status)
    ]
    has_filters = bool(product_key or channel or owner or status)
    account_scope_ids = {str(account.get("advertiser_id") or "") for account in accounts if account.get("advertiser_id")}
    patrol_path = _find_dashboard_patrol_artifact(
        runs_dir,
        start_date=resolved_start_date,
        end_date=resolved_end_date,
        account_scope_ids=account_scope_ids,
    )
    has_date_filter = bool(resolved_start_date or resolved_end_date)
    patrol = read_json(patrol_path) if patrol_path else {}
    suggestions_path = _linked_suggestions_artifact_path(runs_dir, patrol)
    suggestions_payload = read_json(suggestions_path) if suggestions_path else {}
    if not suggestions_payload and isinstance(patrol.get("delivery_patrol_suggestions"), dict):
        suggestions_payload = dict(patrol["delivery_patrol_suggestions"])
    if not suggestions_payload:
        suggestions_path = _find_artifact_by_target_date(
            runs_dir,
            "delivery_patrol_suggestions",
            start_date=resolved_start_date,
            end_date=resolved_end_date,
            fallback_to_latest=not has_date_filter,
        )
        suggestions_payload = read_json(suggestions_path) if suggestions_path else {}
    fact_advertiser_ids = {
        str(row.get("advertiser_id") or "")
        for row in [
            *_list(patrol.get("accounts")),
            *_list(patrol.get("projects")),
            *_list(patrol.get("promotions")),
            *_list(suggestions_payload.get("suggestions")),
        ]
        if row.get("advertiser_id")
    }
    if has_date_filter and not has_filters:
        scoped_advertiser_ids = fact_advertiser_ids
        accounts = [account for account in accounts if str(account.get("advertiser_id") or "") in scoped_advertiser_ids]
    else:
        scoped_advertiser_ids = {str(account.get("advertiser_id") or "") for account in accounts}
    if not scoped_advertiser_ids and not has_filters:
        scoped_advertiser_ids = fact_advertiser_ids
    product_by_advertiser = {
        str(account.get("advertiser_id") or ""): str(account.get("product_name") or "未命名产品")
        for account in accounts
    }
    patrol_accounts = [
        account for account in _list(patrol.get("accounts")) if _in_scope(account, scoped_advertiser_ids)
    ]
    projects = [project for project in _list(patrol.get("projects")) if _in_scope(project, scoped_advertiser_ids)]
    promotions = [promotion for promotion in _list(patrol.get("promotions")) if _in_scope(promotion, scoped_advertiser_ids)]
    suggestions = [
        suggestion for suggestion in _list(suggestions_payload.get("suggestions")) if _in_scope(suggestion, scoped_advertiser_ids)
    ]
    return {
        "patrol_path": patrol_path,
        "suggestions_path": suggestions_path,
        "patrol": patrol,
        "suggestions_payload": suggestions_payload,
        "accounts": accounts,
        "patrol_accounts": patrol_accounts,
        "projects": projects,
        "promotions": promotions,
        "suggestions": suggestions,
        "product_by_advertiser": product_by_advertiser,
        "start_date": resolved_start_date,
        "end_date": resolved_end_date,
    }


def _build_product_rows(context: dict[str, Any]) -> list[dict[str, Any]]:
    products: dict[str, dict[str, Any]] = {}
    advertiser_to_product_key: dict[str, str] = {}
    for account in context["accounts"]:
        product_key = str(account.get("product_key") or "unknown")
        advertiser_id = str(account.get("advertiser_id") or "")
        advertiser_to_product_key[advertiser_id] = product_key
        products.setdefault(
            product_key,
            {
                "产品": str(account.get("product_name") or "未命名产品"),
                "账户数": 0,
                "消耗": 0.0,
                "计费转化": 0.0,
                "转化成本": None,
                "付费 ROI": None,
                "异常项目": 0,
                "建议事项": 0,
                "_roi_total": 0.0,
                "_roi_weight": 0.0,
            },
        )
        products[product_key]["账户数"] += 1

    for account in context["patrol_accounts"]:
        advertiser_id = str(account.get("advertiser_id") or "")
        product_key = advertiser_to_product_key.get(advertiser_id, f"unknown:{advertiser_id}")
        if product_key not in products:
            products[product_key] = _unknown_product_row(advertiser_id)
        metrics = _today_metrics(account)
        _add_metrics(products[product_key], metrics)

    for project in context["projects"]:
        advertiser_id = str(project.get("advertiser_id") or "")
        product_key = advertiser_to_product_key.get(advertiser_id, f"unknown:{advertiser_id}")
        if product_key not in products:
            products[product_key] = _unknown_product_row(advertiser_id)
        if _is_abnormal_project(project):
            products[product_key]["异常项目"] += 1

    for suggestion in context["suggestions"]:
        advertiser_id = str(suggestion.get("advertiser_id") or "")
        product_key = advertiser_to_product_key.get(advertiser_id, f"unknown:{advertiser_id}")
        if product_key not in products:
            products[product_key] = _unknown_product_row(advertiser_id)
        products[product_key]["建议事项"] += 1

    rows = []
    for product_key in sorted(products):
        row = dict(products[product_key])
        if row["_roi_weight"]:
            row["付费 ROI"] = _round(row["_roi_total"] / row["_roi_weight"])
        row["消耗"] = _round(row["消耗"])
        row["计费转化"] = _round(row["计费转化"])
        row["转化成本"] = _round(row["消耗"] / row["计费转化"]) if row["计费转化"] else None
        row.pop("_roi_total", None)
        row.pop("_roi_weight", None)
        rows.append(row)
    return rows


def _build_account_rows(context: dict[str, Any]) -> list[dict[str, Any]]:
    accounts_by_id = {str(account.get("advertiser_id") or ""): account for account in context["accounts"]}
    patrol_by_id = {str(account.get("advertiser_id") or ""): account for account in context["patrol_accounts"]}
    advertiser_ids = sorted({*accounts_by_id, *patrol_by_id})
    rows = []
    for advertiser_id in advertiser_ids:
        account = accounts_by_id.get(advertiser_id, {})
        patrol_account = patrol_by_id.get(advertiser_id, {})
        metrics = _today_metrics(patrol_account)
        project_rows = [project for project in context["projects"] if str(project.get("advertiser_id") or "") == advertiser_id]
        suggestion_rows = [
            suggestion for suggestion in context["suggestions"] if str(suggestion.get("advertiser_id") or "") == advertiser_id
        ]
        cost = _num(metrics.get("stat_cost"))
        conversions = _num(metrics.get("billing_convert_cnt"))
        rows.append(
            {
                "产品": str(account.get("product_name") or context["product_by_advertiser"].get(advertiser_id) or "未归档产品"),
                "账户 ID": advertiser_id,
                "账户名": str(account.get("advertiser_name") or patrol_account.get("advertiser_name") or ""),
                "渠道": str(account.get("channel") or ""),
                "负责人": str(account.get("owner") or ""),
                "状态": str(account.get("status") or ""),
                "消耗": _round(cost),
                "计费转化": _round(conversions),
                "转化成本": _round(cost / conversions) if conversions else None,
                "付费 ROI": _round(_num(metrics.get("billing_1day_pay_roi"))) if metrics.get("billing_1day_pay_roi") is not None else None,
                "项目数": len(project_rows),
                "异常项目": sum(1 for project in project_rows if _is_abnormal_project(project)),
                "建议事项": len(suggestion_rows),
            }
        )
    return rows


def _product_detail_rows(
    *,
    product_name: str,
    account_rows: list[dict[str, Any]],
    project_rows: list[dict[str, Any]],
    promotion_rows: list[dict[str, Any]],
    suggestion_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows = []
    for account in account_rows:
        advertiser_id = str(account.get("账户 ID") or "")
        description_parts = []
        if account.get("负责人"):
            description_parts.append(f"负责人：{account.get('负责人')}")
        if account.get("渠道"):
            description_parts.append(f"渠道：{account.get('渠道')}")
        rows.append(
            {
                "类型": "账户",
                "产品": product_name,
                "账户 ID": advertiser_id,
                "关联 ID": advertiser_id,
                "名称": str(account.get("账户名") or ""),
                "状态/动作": str(account.get("状态") or ""),
                "消耗": account.get("消耗"),
                "计费转化": account.get("计费转化"),
                "说明": "；".join(description_parts),
            }
        )
    rows.extend(
        _account_detail_rows(
            advertiser_id="",
            product_name=product_name,
            project_rows=project_rows,
            promotion_rows=promotion_rows,
            suggestion_rows=suggestion_rows,
        )
    )
    return rows


def _account_detail_rows(
    *,
    advertiser_id: str,
    product_name: str,
    project_rows: list[dict[str, Any]],
    promotion_rows: list[dict[str, Any]],
    suggestion_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows = []
    for project in project_rows:
        metrics = _today_metrics(project)
        status = str(project.get("business_status") or project.get("status") or "")
        rows.append(
            {
                "类型": "项目",
                "产品": product_name,
                "账户 ID": advertiser_id or str(project.get("advertiser_id") or ""),
                "关联 ID": str(project.get("project_id") or ""),
                "名称": str(project.get("project_name") or project.get("name") or ""),
                "状态/动作": status,
                "消耗": _round(_num(metrics.get("stat_cost"))),
                "计费转化": _round(_num(metrics.get("billing_convert_cnt"))),
                "说明": "异常项目" if _is_abnormal_project(project) else "",
            }
        )
    for promotion in promotion_rows:
        metrics = _today_metrics(promotion)
        rows.append(
            {
                "类型": "单元素材",
                "产品": product_name,
                "账户 ID": advertiser_id or str(promotion.get("advertiser_id") or ""),
                "关联 ID": str(promotion.get("promotion_id") or promotion.get("unit_id") or ""),
                "名称": str(promotion.get("promotion_name") or promotion.get("name") or ""),
                "状态/动作": str(promotion.get("business_status") or promotion.get("status") or ""),
                "消耗": _round(_num(metrics.get("stat_cost"))),
                "计费转化": _round(_num(metrics.get("billing_convert_cnt"))),
                "说明": f"项目 ID：{promotion.get('project_id') or ''}",
            }
        )
    for suggestion in suggestion_rows:
        rows.append(
            {
                "类型": "建议",
                "产品": product_name,
                "账户 ID": advertiser_id or str(suggestion.get("advertiser_id") or ""),
                "关联 ID": str(suggestion.get("project_id") or suggestion.get("promotion_id") or ""),
                "名称": str(suggestion.get("target_level") or suggestion.get("level") or ""),
                "状态/动作": str(suggestion.get("action") or suggestion.get("suggestion_type") or ""),
                "消耗": None,
                "计费转化": None,
                "说明": str(suggestion.get("reason") or suggestion.get("message") or ""),
            }
        )
    return rows


def _minimal_account_row(advertiser_id: str, context: dict[str, Any]) -> dict[str, Any]:
    patrol_account = next(
        (account for account in context["patrol_accounts"] if str(account.get("advertiser_id") or "") == advertiser_id),
        {},
    )
    metrics = _today_metrics(patrol_account)
    return {
        "产品": context["product_by_advertiser"].get(advertiser_id, "未归档产品"),
        "账户 ID": advertiser_id,
        "账户名": str(patrol_account.get("advertiser_name") or ""),
        "渠道": "",
        "负责人": "",
        "状态": "",
        "消耗": _round(_num(metrics.get("stat_cost"))),
        "计费转化": _round(_num(metrics.get("billing_convert_cnt"))),
        "转化成本": None,
        "付费 ROI": _round(_num(metrics.get("billing_1day_pay_roi"))) if metrics.get("billing_1day_pay_roi") is not None else None,
        "项目数": 0,
        "异常项目": 0,
        "建议事项": 0,
    }


def _sum_product_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    cost = sum(_num(row.get("消耗")) for row in rows)
    conversions = sum(_num(row.get("计费转化")) for row in rows)
    roi_total = 0.0
    roi_weight = 0.0
    for row in rows:
        roi = row.get("付费 ROI")
        if roi is not None:
            weight = _num(row.get("消耗")) or 1.0
            roi_total += _num(roi) * weight
            roi_weight += weight
    return {
        "消耗": _round(cost),
        "计费转化": _round(conversions),
        "转化成本": _round(cost / conversions) if conversions else None,
        "付费 ROI": _round(roi_total / roi_weight) if roi_weight else None,
    }


def _sum_account_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    cost = sum(_num(row.get("消耗")) for row in rows)
    conversions = sum(_num(row.get("计费转化")) for row in rows)
    return {
        "消耗": _round(cost),
        "计费转化": _round(conversions),
        "转化成本": _round(cost / conversions) if conversions else None,
    }


def _filter_rows(accounts: list[dict[str, str]], label: str, field: str) -> list[dict[str, str]]:
    values = sorted({str(account.get(field) or "") for account in accounts if account.get(field)})
    return [{"类型": label, "显示名称": value, "值": value} for value in values]


def _account_matches(
    account: dict[str, Any],
    *,
    product_key: str,
    channel: str,
    owner: str,
    status: str,
) -> bool:
    return (
        (not product_key or account.get("product_key") == product_key)
        and (not channel or account.get("channel") == channel)
        and (not owner or account.get("owner") == owner)
        and (not status or account.get("status") == status)
    )


def _in_scope(row: dict[str, Any], scoped_advertiser_ids: set[str]) -> bool:
    if not scoped_advertiser_ids:
        return False
    return str(row.get("advertiser_id") or "") in scoped_advertiser_ids


def _unknown_product_row(advertiser_id: str) -> dict[str, Any]:
    return {
        "产品": f"未归档产品({advertiser_id})" if advertiser_id else "未归档产品",
        "账户数": 0,
        "消耗": 0.0,
        "计费转化": 0.0,
        "转化成本": None,
        "付费 ROI": None,
        "异常项目": 0,
        "建议事项": 0,
        "_roi_total": 0.0,
        "_roi_weight": 0.0,
    }


def _add_metrics(row: dict[str, Any], metrics: dict[str, Any]) -> None:
    cost = _num(metrics.get("stat_cost"))
    conversions = _num(metrics.get("billing_convert_cnt"))
    roi = metrics.get("billing_1day_pay_roi")
    row["消耗"] += cost
    row["计费转化"] += conversions
    if roi is not None:
        weight = cost or 1.0
        row["_roi_total"] += _num(roi) * weight
        row["_roi_weight"] += weight


def _today_metrics(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    metrics = payload.get("metrics")
    if isinstance(metrics, dict) and isinstance(metrics.get("today"), dict):
        return metrics["today"]
    overall = payload.get("overall_metrics")
    if isinstance(overall, dict) and isinstance(overall.get("today"), dict):
        return overall["today"]
    today = payload.get("today")
    return today if isinstance(today, dict) else payload


def _is_abnormal_project(project: dict[str, Any]) -> bool:
    status = str(project.get("business_status") or project.get("status") or "").strip().lower()
    return status not in HEALTHY_PROJECT_STATUSES


def _project_status_reason(project: dict[str, Any]) -> str:
    if not _is_abnormal_project(project):
        return ""
    status = str(project.get("business_status") or project.get("status") or "").strip()
    return f"项目状态异常：{status}" if status else "项目状态异常"


def _suggestion_reason_by_project(suggestions: list[dict[str, Any]]) -> dict[tuple[str, str], str]:
    reasons = {}
    for suggestion in suggestions:
        advertiser_id = str(suggestion.get("advertiser_id") or "")
        project_id = str(suggestion.get("project_id") or "")
        reason = _suggestion_explanation(suggestion)
        if advertiser_id and project_id and reason:
            reasons[(advertiser_id, project_id)] = reason
    return reasons


def _suggestion_explanation(suggestion: dict[str, Any]) -> str:
    return str(suggestion.get("reason") or suggestion.get("message") or "需要人工复核该建议。")


def _suggestion_action_info(action: str) -> dict[str, str]:
    normalized = action.strip().lower()
    if normalized in {"delete", "delete_project", "remove_project", "suggest_delete_project"}:
        return {"priority": "高", "config_hint": "可生成删除项目配置"}
    if normalized in {"pause", "pause_project", "stop", "stop_project", "status_update", "disable_project", "suggest_close_project"}:
        return {"priority": "高", "config_hint": "可生成暂停项目配置"}
    if normalized in {"lower_budget", "budget_down", "decrease_budget", "budget_update", "suggest_lower_budget", "adjust_project_budget"}:
        return {"priority": "中", "config_hint": "可生成调预算配置"}
    if normalized in {"lower_bid", "bid_down", "decrease_bid", "bid_update", "suggest_lower_bid", "adjust_project_bid"}:
        return {"priority": "中", "config_hint": "可生成调出价配置"}
    if normalized in {"watch", "observe", "keep_watch"}:
        return {"priority": "低", "config_hint": "观察，无需生成执行配置"}
    return {"priority": "中", "config_hint": "需要人工复核后再生成配置"}


def _suggestion_count(payload: dict[str, Any], suggestions: list[dict[str, Any]]) -> int:
    if isinstance(payload, dict) and isinstance(payload.get("suggestions"), list):
        return len(suggestions)
    summary = payload.get("summary") if isinstance(payload, dict) else {}
    if isinstance(summary, dict) and summary.get("suggestion_count") is not None:
        return _int(summary.get("suggestion_count"))
    return len(suggestions)


def _find_dashboard_patrol_artifact(
    runs_dir: str | Path,
    *,
    start_date: str,
    end_date: str,
    account_scope_ids: set[str],
) -> Path | None:
    candidates = _artifact_candidates_by_target_date(
        runs_dir,
        "delivery_patrol",
        start_date=start_date,
        end_date=end_date,
    )
    if not candidates:
        return find_latest_artifact(runs_dir, "delivery_patrol")

    payloads = [(path, read_json(path)) for path in candidates]
    if account_scope_ids:
        scoped_payloads = [
            (path, payload)
            for path, payload in payloads
            if _artifact_advertiser_ids(payload) & account_scope_ids
        ]
        if scoped_payloads:
            payloads = scoped_payloads
        else:
            return candidates[-1]

    best_index = 0
    best_score: tuple[float, ...] | None = None
    for index, (_path, payload) in enumerate(payloads):
        business_score, *activity_score = _dashboard_patrol_score(payload, account_scope_ids)
        score = (business_score, float(index), *activity_score)
        if best_score is None or score > best_score:
            best_score = score
            best_index = index
    return payloads[best_index][0]


def _artifact_candidates_by_target_date(
    runs_dir: str | Path,
    workflow: str,
    *,
    start_date: str,
    end_date: str,
) -> list[Path]:
    base = Path(runs_dir) / workflow
    if not base.exists():
        return []
    candidates = sorted(path for path in base.glob("*.json") if path.name != "latest.json")
    if not start_date and not end_date:
        return candidates

    start = _parse_date(start_date) if start_date else None
    end = _parse_date(end_date) if end_date else start
    if start and end and start > end:
        start, end = end, start
    output = []
    for path in candidates:
        target = _artifact_target_date(read_json(path))
        if target and (start is None or target >= start) and (end is None or target <= end):
            output.append(path)
    return output


def _dashboard_patrol_score(payload: dict[str, Any], account_scope_ids: set[str]) -> tuple[float, ...]:
    summary = payload.get("summary") if isinstance(payload, dict) else {}
    if not isinstance(summary, dict):
        summary = {}
    today_metrics = _today_metrics(summary)
    account_count = max(_int(summary.get("account_count")), len(_list(payload.get("accounts"))))
    project_count = max(_int(summary.get("project_count")), len(_list(payload.get("projects"))))
    promotion_count = max(_int(summary.get("promotion_count")), len(_list(payload.get("promotions"))))
    stat_cost = _num(today_metrics.get("stat_cost"))
    has_business_data = bool(account_count or project_count or promotion_count or stat_cost)
    return (
        1.0 if has_business_data else 0.0,
        float(project_count + promotion_count + account_count),
        stat_cost,
    )


def _artifact_advertiser_ids(payload: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    for key in ["accounts", "projects", "promotions", "suggestions"]:
        for row in _list(payload.get(key)):
            advertiser_id = str(row.get("advertiser_id") or row.get("account_id") or "")
            if advertiser_id:
                ids.add(advertiser_id)
    embedded_suggestions = payload.get("delivery_patrol_suggestions")
    if isinstance(embedded_suggestions, dict):
        ids.update(_artifact_advertiser_ids(embedded_suggestions))
    return ids


def _linked_suggestions_artifact_path(runs_dir: str | Path, patrol: dict[str, Any]) -> Path | None:
    summary = patrol.get("summary") if isinstance(patrol, dict) else {}
    if not isinstance(summary, dict):
        summary = {}
    embedded = patrol.get("delivery_patrol_suggestions") if isinstance(patrol, dict) else {}
    if not isinstance(embedded, dict):
        embedded = {}
    for value in [
        summary.get("suggestion_artifact_path"),
        patrol.get("suggestion_artifact_path") if isinstance(patrol, dict) else "",
        embedded.get("artifact_path"),
    ]:
        resolved = _resolve_artifact_path(runs_dir, value)
        if resolved:
            return resolved
    return None


def _resolve_artifact_path(runs_dir: str | Path, value: Any) -> Path | None:
    text = str(value or "").strip()
    if not text:
        return None
    path = Path(text)
    if path.is_absolute():
        return path if path.exists() else None
    root = Path(runs_dir).parent.parent
    for candidate in [root / path, Path(runs_dir) / path, path]:
        if candidate.exists():
            return candidate
    return None


def _find_artifact_by_target_date(
    runs_dir: str | Path,
    workflow: str,
    *,
    start_date: str,
    end_date: str,
    fallback_to_latest: bool = False,
) -> Path | None:
    candidates = _artifact_candidates_by_target_date(
        runs_dir,
        workflow,
        start_date=start_date,
        end_date=end_date,
    )
    if candidates:
        return candidates[-1]
    return find_latest_artifact(runs_dir, workflow) if fallback_to_latest else None


def _resolve_date_range(*, date_range: str, start_date: str, end_date: str) -> tuple[str, str]:
    if start_date or end_date:
        return start_date, end_date or start_date
    today = date.today()
    if date_range == "today":
        return today.isoformat(), today.isoformat()
    if date_range == "yesterday":
        value = today - timedelta(days=1)
        return value.isoformat(), value.isoformat()
    range_days = {"last_3_days": 3, "last_7_days": 7, "last_30_days": 30}.get(date_range)
    if range_days:
        start = today - timedelta(days=range_days - 1)
        return start.isoformat(), today.isoformat()
    return "", ""


def _artifact_target_date(payload: dict[str, Any]) -> date | None:
    summary = payload.get("summary") if isinstance(payload, dict) else {}
    candidates = []
    if isinstance(summary, dict):
        candidates.append(summary.get("target_date"))
        candidates.append(summary.get("date"))
    candidates.append(payload.get("target_date"))
    for value in candidates:
        parsed = _parse_date(value)
        if parsed:
            return parsed
    return None


def _context_target_date(context: dict[str, Any]) -> str:
    target = _artifact_target_date(context.get("patrol", {}))
    if target:
        return target.isoformat()
    if context.get("start_date") or context.get("end_date"):
        return f"{context.get('start_date') or ''} 至 {context.get('end_date') or ''}"
    return "最近一次"


def _parse_date(value: Any) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _list(value: Any) -> list[dict[str, Any]]:
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def _num(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _int(value: Any) -> int:
    return int(_num(value))


def _round(value: float) -> float:
    return round(value, 2)
