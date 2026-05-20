from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from roibang_v2.runs import write_latest_artifact
from roibang_v2.runs import write_run_artifact


ACTION_LABELS = {
    "suggest_close_project": "建议关闭项目",
    "suggest_delete_project": "建议删除项目",
    "suggest_lower_budget": "建议下调预算",
    "suggest_lower_bid": "建议下调出价",
    "watch": "继续观察",
    "unit_bad_signal": "单元差信号",
    "unit_good_signal": "单元好信号",
}

STATUS_LABELS = {
    "pending_future_data": "等待后续数据",
    "supported": "支持建议",
    "needs_review": "需要复核",
    "not_evaluated_no_execution": "未执行，暂不评估",
    "execution_observed": "已观察到执行",
    "no_future_data": "无后续数据",
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


def _metric_window(item: dict[str, Any], window: str = "today") -> dict[str, Any]:
    metrics = item.get("metrics") if isinstance(item.get("metrics"), dict) else {}
    return dict(metrics.get(window) if isinstance(metrics.get(window), dict) else {})


def _format_money(value: Any) -> str:
    return f"{_number(value):.2f}"


def _format_ratio(value: Any) -> str:
    if value in (None, ""):
        return "无"
    return f"{_number(value):.4f}".rstrip("0").rstrip(".")


def _top_items(items: list[dict[str, Any]], *, limit: int, name_key: str, id_key: str) -> list[dict[str, Any]]:
    ranked = sorted(
        items,
        key=lambda item: (
            0 if _text(item.get("severity")) == "high" else 1,
            -_number(_metric_window(item).get("stat_cost")),
        ),
    )
    result = []
    for item in ranked[:limit]:
        today = _metric_window(item)
        result.append(
            {
                "name": _text(item.get(name_key)),
                "id": _text(item.get(id_key)),
                "advertiser_id": _text(item.get("advertiser_id")),
                "business_status": _text(item.get("business_status")),
                "severity": _text(item.get("severity")),
                "stat_cost": round(_number(today.get("stat_cost")), 4),
                "billing_convert_cnt": _number(today.get("billing_convert_cnt")),
                "billing_1day_pay_roi": today.get("billing_1day_pay_roi"),
                "status_reasons": item.get("status_reasons") if isinstance(item.get("status_reasons"), list) else [],
            }
        )
    return result


def _suggestion_counts(suggestions: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for suggestion in suggestions:
        action = _text(suggestion.get("suggested_action") or suggestion.get("suggestion_type"))
        if not action:
            continue
        counts[action] = counts.get(action, 0) + 1
    return counts


def _actionable_suggestions(suggestions: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    priority = {
        "suggest_lower_bid": 0,
        "suggest_lower_budget": 1,
        "suggest_close_project": 2,
        "suggest_delete_project": 3,
        "watch": 4,
    }
    ranked = sorted(
        suggestions,
        key=lambda item: (
            priority.get(_text(item.get("suggested_action")), 99),
            -_number(_metric_window(item).get("stat_cost")),
        ),
    )
    result = []
    for item in ranked[:limit]:
        action = _text(item.get("suggested_action") or item.get("suggestion_type"))
        today = _metric_window(item)
        result.append(
            {
                "suggestion_id": _text(item.get("suggestion_id")),
                "suggested_action": action,
                "suggested_action_label": ACTION_LABELS.get(action, action),
                "entity_type": _text(item.get("entity_type")),
                "advertiser_id": _text(item.get("advertiser_id")),
                "project_id": _text(item.get("project_id") or item.get("entity_id")),
                "entity_name": _text(item.get("entity_name")),
                "reason": _text(item.get("reason")),
                "stat_cost": round(_number(today.get("stat_cost")), 4),
                "billing_convert_cnt": _number(today.get("billing_convert_cnt")),
                "billing_1day_pay_roi": today.get("billing_1day_pay_roi"),
                "adjustment": item.get("adjustment") if isinstance(item.get("adjustment"), dict) else {},
            }
        )
    return result


def _backtest_summary(backtest: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(backtest, dict):
        return {
            "available": False,
            "summary": {},
            "status_counts": {},
            "message": "没有提供建议回测结果。",
        }
    summary = backtest.get("summary") if isinstance(backtest.get("summary"), dict) else {}
    status_counts = dict(summary.get("status_counts") if isinstance(summary.get("status_counts"), dict) else {})
    labeled = {STATUS_LABELS.get(key, key): value for key, value in status_counts.items()}
    return {
        "available": True,
        "summary": summary,
        "status_counts": status_counts,
        "status_counts_labeled": labeled,
        "message": " / ".join(f"{label} {count}" for label, count in labeled.items()) or "暂无可回测建议",
    }


def _create_batch_review_summary(create_batch_review: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(create_batch_review, dict):
        return {
            "available": False,
            "summary": {},
            "mode_summary": [],
            "top_batches": [],
            "message": "没有提供创建批次复盘结果。",
        }
    summary = create_batch_review.get("summary") if isinstance(create_batch_review.get("summary"), dict) else {}
    modes = _rows(create_batch_review.get("mode_summary"))
    batches = _rows(create_batch_review.get("batches"))
    return {
        "available": True,
        "summary": summary,
        "mode_summary": [
            {
                "mode_label": _text(item.get("mode_label") or item.get("key")),
                "project_count": int(_number(item.get("project_count"))),
                "stat_cost": round(_number(item.get("stat_cost")), 4),
                "convert_cnt": _number(item.get("convert_cnt")),
                "conversion_cost": item.get("conversion_cost"),
                "roi_1day": item.get("roi_1day"),
            }
            for item in modes[:8]
        ],
        "top_batches": [
            {
                "batch_date_code": _text(item.get("batch_date_code")),
                "mode_label": _text(item.get("mode_label")),
                "batch_id": _text(item.get("batch_id")),
                "project_count": int(_number(item.get("project_count"))),
                "stat_cost": round(_number(item.get("stat_cost")), 4),
                "convert_cnt": _number(item.get("convert_cnt")),
                "conversion_cost": item.get("conversion_cost"),
                "roi_1day": item.get("roi_1day"),
            }
            for item in batches[:8]
        ],
        "message": (
            f"批次 {int(_number(summary.get('batch_count')))} 个，"
            f"项目 {int(_number(summary.get('project_count')))} 个，"
            f"消耗 {_format_money(summary.get('stat_cost'))}，"
            f"ROI {_format_ratio(summary.get('roi_1day'))}"
        ),
    }


def _next_actions(suggestions: list[dict[str, Any]], backtest: dict[str, Any]) -> list[dict[str, Any]]:
    counts = _suggestion_counts(suggestions)
    actions = []
    for key in ["suggest_lower_bid", "suggest_lower_budget", "suggest_close_project", "suggest_delete_project"]:
        count = counts.get(key, 0)
        if count:
            actions.append(
                {
                    "type": key,
                    "label": ACTION_LABELS.get(key, key),
                    "count": count,
                    "next_step": "可用固定脚本生成项目管理配置，真实执行前仍需人工确认。",
                }
            )
    status_counts = backtest.get("status_counts") if isinstance(backtest.get("status_counts"), dict) else {}
    pending = int(status_counts.get("pending_future_data", 0) or 0)
    if pending:
        actions.append(
            {
                "type": "wait_backtest",
                "label": "等待建议回测",
                "count": pending,
                "next_step": "本地数据未覆盖完整后续窗口，等明日数据同步后再复盘建议准确率。",
            }
        )
    return actions


def _message(report: dict[str, Any]) -> str:
    overall_today = report["overall"]["today"]
    overall_yesterday = report["overall"]["yesterday"]
    suggestion_counts = report["suggestions_today"]["counts_labeled"]
    lines = [
        f"RoiBang-V2 业务日报 {report['target_date']}",
        "",
        (
            f"整体：账户 {report['summary']['account_count']} 个，项目 {report['summary']['project_count']} 个，"
            f"单元 {report['summary']['promotion_count']} 个"
        ),
        (
            f"今日消耗 {_format_money(overall_today.get('stat_cost'))}，"
            f"计费转化 {_format_ratio(overall_today.get('billing_convert_cnt'))}，"
            f"计费当日ROI {_format_ratio(overall_today.get('billing_1day_pay_roi'))}；"
            f"昨日消耗 {_format_money(overall_yesterday.get('stat_cost'))}，"
            f"计费当日ROI {_format_ratio(overall_yesterday.get('billing_1day_pay_roi'))}"
        ),
        "",
        "今日建议：" + (" / ".join(f"{key} {value}" for key, value in suggestion_counts.items()) or "无"),
        "建议回测：" + report["suggestion_backtest"]["message"],
    ]
    if report["create_batch_review"]["available"]:
        lines.append("创建批次：" + report["create_batch_review"]["message"])
    if report["next_actions"]:
        lines.append("")
        lines.append("下一步")
        for item in report["next_actions"][:5]:
            lines.append(f"- {item['label']} {item['count']}：{item['next_step']}")
    return "\n".join(lines)


def build_delivery_business_report(
    *,
    patrol: dict[str, Any],
    suggestions: dict[str, Any],
    backtest: dict[str, Any] | None = None,
    create_batch_review: dict[str, Any] | None = None,
) -> dict[str, Any]:
    patrol_summary = patrol.get("summary") if isinstance(patrol.get("summary"), dict) else {}
    target_date = _text(patrol_summary.get("target_date") or suggestions.get("summary", {}).get("target_date"))
    suggestion_rows = _rows(suggestions.get("suggestions"))
    counts = _suggestion_counts(suggestion_rows)
    backtest_info = _backtest_summary(backtest)
    create_batch_info = _create_batch_review_summary(create_batch_review)
    report = {
        "ok": True,
        "workflow": "delivery_business_report",
        "phase": "readonly_report",
        "execution_enabled": False,
        "external_api_calls": 0,
        "target_date": target_date,
        "summary": {
            "account_count": int(patrol_summary.get("account_count") or 0),
            "project_count": int(patrol_summary.get("project_count") or 0),
            "promotion_count": int(patrol_summary.get("promotion_count") or 0),
            "attention_count": int(patrol_summary.get("attention_count") or 0),
            "suggestion_count": len(suggestion_rows),
        },
        "overall": patrol_summary.get("overall_metrics") if isinstance(patrol_summary.get("overall_metrics"), dict) else {},
        "account_health": {
            "status_counts": patrol_summary.get("business_status_counts", {}).get("accounts", {})
            if isinstance(patrol_summary.get("business_status_counts"), dict)
            else {},
            "top_accounts": _top_items(_rows(patrol.get("accounts")), limit=5, name_key="account_name", id_key="advertiser_id"),
        },
        "project_focus": _top_items(_rows(patrol.get("projects")), limit=8, name_key="project_name", id_key="project_id"),
        "unit_focus": _top_items(_rows(patrol.get("promotions")), limit=8, name_key="promotion_name", id_key="promotion_id"),
        "suggestions_today": {
            "summary": suggestions.get("summary") if isinstance(suggestions.get("summary"), dict) else {},
            "counts": counts,
            "counts_labeled": {ACTION_LABELS.get(key, key): value for key, value in counts.items()},
            "top_suggestions": _actionable_suggestions(suggestion_rows, limit=12),
        },
        "suggestion_backtest": backtest_info,
        "create_batch_review": create_batch_info,
    }
    report["next_actions"] = _next_actions(suggestion_rows, backtest_info)
    report["message"] = _message(report)
    return report


def run_delivery_business_report_request(
    request: dict[str, Any] | None,
    *,
    runs_dir: str | Path,
) -> dict[str, Any]:
    cfg = dict(request or {})
    patrol_path = _text(cfg.get("patrol_artifact_path") or cfg.get("patrol_artifact"))
    suggestions_path = _text(cfg.get("suggestions_artifact_path") or cfg.get("suggestions_artifact"))
    backtest_path = _text(cfg.get("backtest_artifact_path") or cfg.get("backtest_artifact"))
    create_batch_review_path = _text(
        cfg.get("create_batch_review_artifact_path") or cfg.get("create_batch_review_artifact")
    )
    if not patrol_path or not suggestions_path:
        raise ValueError("delivery business report requires patrol_artifact_path and suggestions_artifact_path")
    payload = build_delivery_business_report(
        patrol=_load_json(patrol_path),
        suggestions=_load_json(suggestions_path),
        backtest=_load_json(backtest_path) if backtest_path else None,
        create_batch_review=_load_json(create_batch_review_path) if create_batch_review_path else None,
    )
    payload["source"] = {
        "patrol_artifact_path": patrol_path,
        "suggestions_artifact_path": suggestions_path,
        "backtest_artifact_path": backtest_path,
        "create_batch_review_artifact_path": create_batch_review_path,
    }
    payload["artifact_path"] = str(write_run_artifact(runs_dir, "delivery_business_report", payload))
    payload["latest_artifact_path"] = str(Path(runs_dir) / "delivery_business_report" / "latest.json")
    write_latest_artifact(runs_dir, "delivery_business_report", payload)
    return payload
