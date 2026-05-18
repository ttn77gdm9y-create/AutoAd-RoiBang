from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from roibang_v2.runs import write_run_artifact


def _load_local_json(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _number(value: Any) -> float:
    try:
        return float(str(value or "0").replace(",", "").replace("%", ""))
    except ValueError:
        return 0.0


def _metrics(item: dict[str, Any]) -> dict[str, Any]:
    metrics = item.get("metrics") if isinstance(item.get("metrics"), dict) else {}
    today = metrics.get("today") if isinstance(metrics.get("today"), dict) else {}
    return today


def _window_metrics(item: dict[str, Any], window: str) -> dict[str, Any]:
    metrics = item.get("metrics") if isinstance(item.get("metrics"), dict) else {}
    value = metrics.get(window) if isinstance(metrics.get(window), dict) else {}
    return value


def _enabled_rule(rules: dict[str, Any], name: str, defaults: dict[str, Any]) -> dict[str, Any]:
    raw = rules.get(name) if isinstance(rules.get(name), dict) else {}
    rule = {**defaults, **raw}
    rule["enabled"] = bool(rule.get("enabled", True))
    return rule


def _entity_ref(entity_type: str, item: dict[str, Any]) -> dict[str, Any]:
    if entity_type == "account":
        return {
            "advertiser_id": str(item.get("advertiser_id") or ""),
            "entity_type": "account",
            "entity_id": str(item.get("advertiser_id") or ""),
            "entity_name": str(item.get("account_name") or item.get("advertiser_id") or ""),
        }
    if entity_type == "project":
        return {
            "advertiser_id": str(item.get("advertiser_id") or ""),
            "entity_type": "project",
            "entity_id": str(item.get("project_id") or ""),
            "project_id": str(item.get("project_id") or ""),
            "entity_name": str(item.get("project_name") or item.get("project_id") or ""),
        }
    return {
        "advertiser_id": str(item.get("advertiser_id") or ""),
        "entity_type": "promotion",
        "entity_id": str(item.get("promotion_id") or ""),
        "project_id": str(item.get("project_id") or ""),
        "promotion_id": str(item.get("promotion_id") or ""),
        "entity_name": str(item.get("promotion_name") or item.get("promotion_id") or ""),
    }


def _suggestion(
    *,
    suggestion_type: str,
    rule_id: str,
    target_date: str,
    entity_type: str,
    item: dict[str, Any],
    reason: str,
) -> dict[str, Any]:
    metrics = _metrics(item)
    return {
        "suggestion_type": suggestion_type,
        "rule_id": rule_id,
        "target_date": target_date,
        **_entity_ref(entity_type, item),
        "status": str(item.get("status") or ""),
        "reason": reason,
        "metrics": {
            "stat_cost": _number(metrics.get("stat_cost")),
            "billing_convert_cnt": _number(metrics.get("billing_convert_cnt")),
            "billing_conversion_cost": metrics.get("billing_conversion_cost"),
            "billing_1day_pay_roi": metrics.get("billing_1day_pay_roi"),
        },
        "execution": {"enabled": False, "status": "suggestion_only"},
    }


def _rule(rules: dict[str, Any], name: str, defaults: dict[str, Any]) -> dict[str, Any]:
    value = rules.get(name) if isinstance(rules.get(name), dict) else {}
    merged = {**defaults, **value}
    merged["enabled"] = bool(merged.get("enabled", True))
    return merged


def _date_diff_days(start: str, end: str) -> int | None:
    try:
        start_date = datetime.strptime(start[:10], "%Y-%m-%d").date()
        end_date = datetime.strptime(end[:10], "%Y-%m-%d").date()
    except ValueError:
        return None
    return (end_date - start_date).days + 1


def _action_family(action: str, detail: str) -> str:
    text = f"{action} {detail}"
    if action == "删除":
        return "delete_project"
    if action == "新建":
        return "create_project"
    if "启用 -> 暂停" in text:
        return "pause_project"
    if "暂停 -> 启用" in text:
        return "enable_project"
    if "预算" in text:
        return "budget_update"
    if "出价" in text:
        return "bid_update"
    return str(action or "unknown")


def _operation_history(
    conn: sqlite3.Connection | None,
    *,
    advertiser_id: str,
    entity_type: str,
    entity_id: str,
    sample_limit: int,
) -> dict[str, Any]:
    if conn is None or entity_type != "project" or not advertiser_id or not entity_id:
        return {"source": "operation_logs", "same_entity_operation_count": 0, "action_counts": {}, "samples": []}
    rows = conn.execute(
        """
        SELECT occurred_at, action, detail
        FROM operation_logs
        WHERE advertiser_id = ?
          AND entity_type = 'project'
          AND entity_id = ?
        ORDER BY occurred_at DESC, operation_id DESC
        """,
        (advertiser_id, entity_id),
    ).fetchall()
    counts: dict[str, int] = {}
    samples: list[dict[str, Any]] = []
    for row in rows:
        action = str(row["action"] or "")
        detail = str(row["detail"] or "")
        family = _action_family(action, detail)
        counts[family] = counts.get(family, 0) + 1
        if len(samples) < sample_limit:
            samples.append(
                {
                    "occurred_at": str(row["occurred_at"] or ""),
                    "action": action,
                    "action_family": family,
                    "detail": detail[:200],
                }
            )
    return {
        "source": "operation_logs",
        "same_entity_operation_count": len(rows),
        "action_counts": dict(sorted(counts.items())),
        "samples": samples,
    }


def _project_lifecycle(
    conn: sqlite3.Connection | None,
    *,
    target_date: str,
    advertiser_id: str,
    project_id: str,
) -> dict[str, Any]:
    if conn is None or not advertiser_id or not project_id:
        return {"source": "material_daily_metrics", "available": False}
    row = conn.execute(
        """
        SELECT
          MIN(metric_date) AS first_active_date,
          MAX(metric_date) AS last_active_date,
          COUNT(DISTINCT metric_date) AS active_days,
          SUM(stat_cost) AS stat_cost,
          SUM(convert_cnt) AS convert_cnt,
          SUM(stat_cost * COALESCE(roi_1day, 0)) AS pay_amount
        FROM material_daily_metrics
        WHERE advertiser_id = ?
          AND project_id = ?
          AND material_kind = 'video'
          AND stat_cost > 0
          AND metric_date <= ?
        """,
        (advertiser_id, project_id, target_date),
    ).fetchone()
    first_active_date = str(row["first_active_date"] or "") if row else ""
    stat_cost = _number(row["stat_cost"] if row else 0)
    pay_amount = _number(row["pay_amount"] if row else 0)
    return {
        "source": "material_daily_metrics",
        "available": bool(first_active_date),
        "first_active_date": first_active_date,
        "last_active_date": str(row["last_active_date"] or "") if row else "",
        "project_age_days": _date_diff_days(first_active_date, target_date) if first_active_date else None,
        "active_days": int(row["active_days"] or 0) if row else 0,
        "stat_cost": round(stat_cost, 4),
        "convert_cnt": round(_number(row["convert_cnt"] if row else 0), 4),
        "roi_1day": round(pay_amount / stat_cost, 4) if stat_cost > 0 else None,
    }


def _suggestion_id(
    *,
    target_date: str,
    entity_type: str,
    advertiser_id: str,
    entity_id: str,
    suggested_action: str,
) -> str:
    return f"{target_date}:{entity_type}:{advertiser_id}:{entity_id}:{suggested_action}"


def _new_suggestion(
    *,
    target_date: str,
    entity_type: str,
    item: dict[str, Any],
    suggested_action: str,
    rule_id: str,
    confidence: str,
    reason: str,
    conn: sqlite3.Connection | None,
    evidence_cfg: dict[str, Any],
    adjustment: dict[str, Any] | None = None,
) -> dict[str, Any]:
    advertiser_id = str(item.get("advertiser_id") or "")
    ref = _entity_ref(entity_type, item)
    entity_id = str(ref.get("entity_id") or "")
    operation_cfg = evidence_cfg.get("operation_logs") if isinstance(evidence_cfg.get("operation_logs"), dict) else {}
    lifecycle_cfg = evidence_cfg.get("project_lifecycle") if isinstance(evidence_cfg.get("project_lifecycle"), dict) else {}
    operation_history = (
        _operation_history(
            conn,
            advertiser_id=advertiser_id,
            entity_type=entity_type,
            entity_id=entity_id,
            sample_limit=int(operation_cfg.get("sample_limit") or 3),
        )
        if bool(operation_cfg.get("enabled", True))
        else {"source": "operation_logs", "same_entity_operation_count": 0, "action_counts": {}, "samples": []}
    )
    lifecycle = (
        _project_lifecycle(conn, target_date=target_date, advertiser_id=advertiser_id, project_id=entity_id)
        if entity_type == "project" and bool(lifecycle_cfg.get("enabled", True))
        else {"source": "material_daily_metrics", "available": False}
    )
    payload = {
        "suggestion_id": _suggestion_id(
            target_date=target_date,
            entity_type=entity_type,
            advertiser_id=advertiser_id,
            entity_id=entity_id,
            suggested_action=suggested_action,
        ),
        "suggestion_type": suggested_action,
        "suggested_action": suggested_action,
        "rule_id": rule_id,
        "target_date": target_date,
        **ref,
        "status": str(item.get("status") or ""),
        "business_status": str(item.get("business_status") or ""),
        "severity": str(item.get("severity") or ""),
        "confidence": confidence,
        "reason": reason,
        "metrics": {
            "today": dict(_window_metrics(item, "today")),
            "yesterday": dict(_window_metrics(item, "yesterday")),
        },
        "evidence": {
            "patrol_status": {
                "business_status": str(item.get("business_status") or ""),
                "severity": str(item.get("severity") or ""),
                "status_reasons": list(item.get("status_reasons") or []),
            },
            "operation_history": operation_history,
            "lifecycle": lifecycle,
        },
        "execution": {"enabled": False, "status": "suggestion_only"},
    }
    if adjustment is not None:
        payload["adjustment"] = adjustment
    return payload


def _two_day_values(item: dict[str, Any]) -> dict[str, float]:
    today = _window_metrics(item, "today")
    yesterday = _window_metrics(item, "yesterday")
    return {
        "stat_cost": _number(today.get("stat_cost")) + _number(yesterday.get("stat_cost")),
        "billing_convert_cnt": _number(today.get("billing_convert_cnt")) + _number(yesterday.get("billing_convert_cnt")),
    }


def _roi_value(metrics: dict[str, Any]) -> float | None:
    raw = metrics.get("billing_1day_pay_roi")
    if raw is not None:
        return _number(raw)
    return 0.0 if _number(metrics.get("stat_cost")) > 0 else None


def _project_age_days(conn: sqlite3.Connection | None, target_date: str, item: dict[str, Any]) -> int | None:
    lifecycle = _project_lifecycle(
        conn,
        target_date=target_date,
        advertiser_id=str(item.get("advertiser_id") or ""),
        project_id=str(item.get("project_id") or ""),
    )
    value = lifecycle.get("project_age_days")
    return int(value) if isinstance(value, int) else None


def _project_suggestion(
    *,
    target_date: str,
    item: dict[str, Any],
    rules: dict[str, Any],
    conn: sqlite3.Connection | None,
    evidence_cfg: dict[str, Any],
) -> dict[str, Any] | None:
    today = _window_metrics(item, "today")
    yesterday = _window_metrics(item, "yesterday")
    stat_cost = _number(today.get("stat_cost"))
    billing_convert_cnt = _number(today.get("billing_convert_cnt"))
    billing_conversion_cost = _number(today.get("billing_conversion_cost"))
    roi = _roi_value(today)
    two_day = _two_day_values(item)
    status = str(item.get("status") or "")

    delete_rule = _rule(
        rules,
        "delete_inactive_closed",
        {
            "enabled": True,
            "max_today_stat_cost": 100,
            "max_yesterday_stat_cost": 100,
            "max_two_day_billing_convert_cnt": 0,
            "min_project_age_days": 3,
        },
    )
    age_days = _project_age_days(conn, target_date, item)
    if (
        delete_rule["enabled"]
        and status == "PROJECT_STATUS_DISABLE"
        and stat_cost <= _number(delete_rule.get("max_today_stat_cost"))
        and _number(yesterday.get("stat_cost")) <= _number(delete_rule.get("max_yesterday_stat_cost"))
        and two_day["billing_convert_cnt"] <= _number(delete_rule.get("max_two_day_billing_convert_cnt"))
        and (age_days is None or age_days >= int(delete_rule.get("min_project_age_days") or 0))
    ):
        return _new_suggestion(
            target_date=target_date,
            entity_type="project",
            item=item,
            suggested_action="suggest_delete_project",
            rule_id="project_delete_inactive_closed",
            confidence="medium",
            reason="项目已关闭，今天和昨天低消耗且无计费时间转化，建议作为项目数量清理候选。",
            conn=conn,
            evidence_cfg=evidence_cfg,
        )

    close_zero = _rule(
        rules,
        "close_zero_convert",
        {"enabled": True, "min_two_day_stat_cost": 1000, "max_two_day_billing_convert_cnt": 0},
    )
    if (
        close_zero["enabled"]
        and status == "PROJECT_STATUS_ENABLE"
        and two_day["stat_cost"] >= _number(close_zero.get("min_two_day_stat_cost"))
        and two_day["billing_convert_cnt"] <= _number(close_zero.get("max_two_day_billing_convert_cnt"))
    ):
        return _new_suggestion(
            target_date=target_date,
            entity_type="project",
            item=item,
            suggested_action="suggest_close_project",
            rule_id="project_close_zero_convert",
            confidence="high",
            reason="今天和昨天累计消耗达到阈值，但计费时间转化数为 0，建议关闭项目。",
            conn=conn,
            evidence_cfg=evidence_cfg,
        )

    close_low_roi = _rule(
        rules,
        "close_low_roi",
        {"enabled": True, "min_stat_cost": 800, "roi_lt": 0.05, "max_billing_convert_cnt": 0},
    )
    if (
        close_low_roi["enabled"]
        and status == "PROJECT_STATUS_ENABLE"
        and stat_cost >= _number(close_low_roi.get("min_stat_cost"))
        and billing_convert_cnt <= _number(close_low_roi.get("max_billing_convert_cnt"))
        and roi is not None
        and roi < _number(close_low_roi.get("roi_lt"))
    ):
        return _new_suggestion(
            target_date=target_date,
            entity_type="project",
            item=item,
            suggested_action="suggest_close_project",
            rule_id="project_close_low_roi",
            confidence="high",
            reason="项目今天消耗达到阈值，计费时间转化不足且计费当日 ROI 低于阈值，建议关闭项目。",
            conn=conn,
            evidence_cfg=evidence_cfg,
        )

    lower_bid = _rule(
        rules,
        "lower_bid",
        {"enabled": True, "min_stat_cost": 1000, "min_billing_convert_cnt": 2, "min_billing_conversion_cost": 400, "adjustment_ratio": -0.1},
    )
    if (
        lower_bid["enabled"]
        and stat_cost >= _number(lower_bid.get("min_stat_cost"))
        and billing_convert_cnt >= _number(lower_bid.get("min_billing_convert_cnt"))
        and billing_conversion_cost >= _number(lower_bid.get("min_billing_conversion_cost"))
    ):
        return _new_suggestion(
            target_date=target_date,
            entity_type="project",
            item=item,
            suggested_action="suggest_lower_bid",
            rule_id="project_lower_bid_high_cpa",
            confidence="medium",
            reason="计费时间转化成本高于阈值，建议只输出下调出价比例。",
            conn=conn,
            evidence_cfg=evidence_cfg,
            adjustment={"type": "ratio", "value": _number(lower_bid.get("adjustment_ratio"))},
        )

    lower_budget = _rule(
        rules,
        "lower_budget",
        {"enabled": True, "min_stat_cost": 1000, "min_billing_convert_cnt": 1, "roi_lt": 0.05, "adjustment_ratio": -0.2},
    )
    if (
        lower_budget["enabled"]
        and stat_cost >= _number(lower_budget.get("min_stat_cost"))
        and billing_convert_cnt >= _number(lower_budget.get("min_billing_convert_cnt"))
        and roi is not None
        and roi < _number(lower_budget.get("roi_lt"))
    ):
        return _new_suggestion(
            target_date=target_date,
            entity_type="project",
            item=item,
            suggested_action="suggest_lower_budget",
            rule_id="project_lower_budget_low_roi",
            confidence="medium",
            reason="项目有计费时间转化但计费当日 ROI 低于阈值，建议只输出下调预算比例。",
            conn=conn,
            evidence_cfg=evidence_cfg,
            adjustment={"type": "ratio", "value": _number(lower_budget.get("adjustment_ratio"))},
        )

    continue_rule = _rule(
        rules,
        "continue_running",
        {"enabled": True, "min_stat_cost": 500, "min_billing_convert_cnt": 1, "min_billing_1day_pay_roi": 0.05},
    )
    if (
        continue_rule["enabled"]
        and stat_cost >= _number(continue_rule.get("min_stat_cost"))
        and billing_convert_cnt >= _number(continue_rule.get("min_billing_convert_cnt"))
        and roi is not None
        and roi >= _number(continue_rule.get("min_billing_1day_pay_roi"))
    ):
        return _new_suggestion(
            target_date=target_date,
            entity_type="project",
            item=item,
            suggested_action="continue_running",
            rule_id="project_continue_running",
            confidence="medium",
            reason="今天有消耗、有计费时间转化，且计费当日 ROI 达到继续观察阈值。",
            conn=conn,
            evidence_cfg=evidence_cfg,
        )

    watch_rule = _rule(rules, "watch", {"enabled": True, "min_stat_cost": 300, "max_stat_cost": 800, "max_billing_convert_cnt": 0})
    if (
        watch_rule["enabled"]
        and stat_cost >= _number(watch_rule.get("min_stat_cost"))
        and stat_cost <= _number(watch_rule.get("max_stat_cost"))
        and billing_convert_cnt <= _number(watch_rule.get("max_billing_convert_cnt"))
    ):
        return _new_suggestion(
            target_date=target_date,
            entity_type="project",
            item=item,
            suggested_action="watch",
            rule_id="project_watch_zero_convert",
            confidence="low",
            reason="项目已有一定消耗但还没到强关闭阈值，建议继续观察。",
            conn=conn,
            evidence_cfg=evidence_cfg,
        )
    return None


def _promotion_suggestion(
    *,
    target_date: str,
    item: dict[str, Any],
    rules: dict[str, Any],
    conn: sqlite3.Connection | None,
    evidence_cfg: dict[str, Any],
) -> dict[str, Any] | None:
    today = _window_metrics(item, "today")
    stat_cost = _number(today.get("stat_cost"))
    billing_convert_cnt = _number(today.get("billing_convert_cnt"))
    roi = _roi_value(today)
    bad_rule = _rule(rules, "bad_signal", {"enabled": True, "min_stat_cost": 300, "max_billing_convert_cnt": 0})
    if (
        bad_rule["enabled"]
        and stat_cost >= _number(bad_rule.get("min_stat_cost"))
        and billing_convert_cnt <= _number(bad_rule.get("max_billing_convert_cnt"))
    ):
        return _new_suggestion(
            target_date=target_date,
            entity_type="promotion",
            item=item,
            suggested_action="unit_bad_signal",
            rule_id="promotion_bad_signal",
            confidence="medium",
            reason="单元已有消耗但计费时间转化数为 0，建议作为项目诊断依据。",
            conn=conn,
            evidence_cfg=evidence_cfg,
        )
    good_rule = _rule(
        rules,
        "good_signal",
        {"enabled": True, "min_stat_cost": 300, "min_billing_convert_cnt": 1, "min_billing_1day_pay_roi": 0.05},
    )
    if (
        good_rule["enabled"]
        and stat_cost >= _number(good_rule.get("min_stat_cost"))
        and billing_convert_cnt >= _number(good_rule.get("min_billing_convert_cnt"))
        and roi is not None
        and roi >= _number(good_rule.get("min_billing_1day_pay_roi"))
    ):
        return _new_suggestion(
            target_date=target_date,
            entity_type="promotion",
            item=item,
            suggested_action="unit_good_signal",
            rule_id="promotion_good_signal",
            confidence="medium",
            reason="单元有消耗、有计费时间转化，且计费当日 ROI 达到阈值。",
            conn=conn,
            evidence_cfg=evidence_cfg,
        )
    return None


def _account_health_item(account: dict[str, Any], rules: dict[str, Any]) -> dict[str, Any]:
    today = _window_metrics(account, "today")
    stat_cost = _number(today.get("stat_cost"))
    roi = _roi_value(today)
    can_scale = _rule(rules, "can_scale", {"enabled": True, "min_stat_cost": 1000, "min_billing_1day_pay_roi": 0.05})
    pause_creation = _rule(rules, "pause_creation", {"enabled": True, "min_stat_cost": 1000, "roi_lt": 0.05})
    if (
        can_scale["enabled"]
        and stat_cost >= _number(can_scale.get("min_stat_cost"))
        and roi is not None
        and roi >= _number(can_scale.get("min_billing_1day_pay_roi"))
    ):
        health_status = "can_scale"
        reason = "账户今日消耗和计费当日 ROI 达到可放量观察阈值。"
    elif (
        pause_creation["enabled"]
        and stat_cost >= _number(pause_creation.get("min_stat_cost"))
        and roi is not None
        and roi < _number(pause_creation.get("roi_lt"))
    ):
        health_status = "pause_creation"
        reason = "账户今日消耗达到阈值但计费当日 ROI 偏低，建议暂停新建观察。"
    else:
        health_status = "watch_only"
        reason = "账户暂不满足放量或暂停创建阈值，建议只观察。"
    return {
        "advertiser_id": str(account.get("advertiser_id") or ""),
        "account_name": str(account.get("account_name") or account.get("advertiser_id") or ""),
        "health_status": health_status,
        "reason": reason,
        "metrics": {"today": dict(today), "yesterday": dict(_window_metrics(account, "yesterday"))},
    }


def _build_rule_based_suggestions(
    *,
    patrol_artifact: dict[str, Any],
    cfg: dict[str, Any],
    target_date: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rules = cfg.get("rules") if isinstance(cfg.get("rules"), dict) else {}
    evidence_cfg = cfg.get("evidence") if isinstance(cfg.get("evidence"), dict) else {}
    db_path = str(cfg.get("db_path") or "").strip()
    conn: sqlite3.Connection | None = None
    if db_path and Path(db_path).exists():
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
    try:
        suggestions: list[dict[str, Any]] = []
        project_rules = rules.get("project") if isinstance(rules.get("project"), dict) else {}
        promotion_rules = rules.get("promotion") if isinstance(rules.get("promotion"), dict) else {}
        for project in [item for item in patrol_artifact.get("projects", []) if isinstance(item, dict)]:
            suggestion = _project_suggestion(
                target_date=target_date,
                item=project,
                rules=project_rules,
                conn=conn,
                evidence_cfg=evidence_cfg,
            )
            if suggestion is not None:
                suggestions.append(suggestion)
        for promotion in [item for item in patrol_artifact.get("promotions", []) if isinstance(item, dict)]:
            suggestion = _promotion_suggestion(
                target_date=target_date,
                item=promotion,
                rules=promotion_rules,
                conn=conn,
                evidence_cfg=evidence_cfg,
            )
            if suggestion is not None:
                suggestions.append(suggestion)
        account_rules = cfg.get("account_health") if isinstance(cfg.get("account_health"), dict) else {}
        account_health = [
            _account_health_item(account, account_rules)
            for account in [item for item in patrol_artifact.get("accounts", []) if isinstance(item, dict)]
        ]
        return suggestions, account_health
    finally:
        if conn is not None:
            conn.close()


def _collect_entity_suggestions(
    *,
    target_date: str,
    entity_type: str,
    items: list[dict[str, Any]],
    rules: dict[str, Any],
) -> list[dict[str, Any]]:
    zero_convert = _enabled_rule(rules, "zero_billing_convert", {"enabled": True, "min_stat_cost": 500})
    low_roi = _enabled_rule(rules, "low_billing_roi", {"enabled": True, "min_stat_cost": 800, "roi_lt": 0.05})
    suggestions: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        metrics = _metrics(item)
        stat_cost = _number(metrics.get("stat_cost"))
        billing_convert_cnt = _number(metrics.get("billing_convert_cnt"))
        roi = metrics.get("billing_1day_pay_roi")
        roi_value = None if roi is None else _number(roi)
        if zero_convert["enabled"] and stat_cost >= _number(zero_convert.get("min_stat_cost")) and billing_convert_cnt <= 0:
            suggestions.append(
                _suggestion(
                    suggestion_type="attention_zero_billing_convert",
                    rule_id=f"{entity_type}_zero_billing_convert",
                    target_date=target_date,
                    entity_type=entity_type,
                    item=item,
                    reason="今天已有明显消耗，但计费时间转化数为 0，建议人工重点检查是否需要暂停或删除。",
                )
            )
            continue
        if (
            low_roi["enabled"]
            and stat_cost >= _number(low_roi.get("min_stat_cost"))
            and roi_value is not None
            and roi_value < _number(low_roi.get("roi_lt"))
        ):
            suggestions.append(
                _suggestion(
                    suggestion_type="attention_low_billing_roi",
                    rule_id=f"{entity_type}_low_billing_roi",
                    target_date=target_date,
                    entity_type=entity_type,
                    item=item,
                    reason="今天计费当日付费 ROI 低于阈值，建议人工重点检查是否需要控量。",
                )
            )
    return suggestions


def build_delivery_patrol_suggestions(patrol_artifact: dict[str, Any], request: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = dict(request or {})
    windows = patrol_artifact.get("windows") if isinstance(patrol_artifact.get("windows"), dict) else {}
    target_date = str(cfg.get("target_date") or windows.get("today") or "")
    rules = cfg.get("rules") if isinstance(cfg.get("rules"), dict) else {}
    uses_nested_rules = any(isinstance(rules.get(key), dict) for key in ("project", "promotion"))
    if uses_nested_rules:
        suggestions, account_health = _build_rule_based_suggestions(
            patrol_artifact=patrol_artifact,
            cfg=cfg,
            target_date=target_date,
        )
    else:
        suggestions = []
        suggestions.extend(
            _collect_entity_suggestions(
                target_date=target_date,
                entity_type="account",
                items=[item for item in patrol_artifact.get("accounts", []) if isinstance(item, dict)],
                rules=rules,
            )
        )
        suggestions.extend(
            _collect_entity_suggestions(
                target_date=target_date,
                entity_type="project",
                items=[item for item in patrol_artifact.get("projects", []) if isinstance(item, dict)],
                rules=rules,
            )
        )
        suggestions.extend(
            _collect_entity_suggestions(
                target_date=target_date,
                entity_type="promotion",
                items=[item for item in patrol_artifact.get("promotions", []) if isinstance(item, dict)],
                rules=rules,
            )
        )
        account_health = []
    suggestions = sorted(
        suggestions,
        key=lambda item: (
            str(item.get("entity_type") or ""),
            -_number((item.get("metrics") or {}).get("stat_cost") or (item.get("metrics") or {}).get("today", {}).get("stat_cost")),
            str(item.get("entity_id") or ""),
        ),
    )
    action_counts: dict[str, int] = {}
    for suggestion in suggestions:
        action = str(suggestion.get("suggested_action") or suggestion.get("suggestion_type") or "")
        if action:
            action_counts[action] = action_counts.get(action, 0) + 1
    return {
        "ok": True,
        "workflow": "delivery_patrol_suggestions",
        "phase": "control_analysis",
        "execution_enabled": False,
        "external_api_calls": 0,
        "summary": {
            "target_date": target_date,
            "suggestion_count": len(suggestions),
            "account_suggestion_count": sum(1 for item in suggestions if item["entity_type"] == "account"),
            "project_suggestion_count": sum(1 for item in suggestions if item["entity_type"] == "project"),
            "promotion_suggestion_count": sum(1 for item in suggestions if item["entity_type"] == "promotion"),
            "suggest_close_project_count": action_counts.get("suggest_close_project", 0),
            "suggest_delete_project_count": action_counts.get("suggest_delete_project", 0),
            "suggest_lower_budget_count": action_counts.get("suggest_lower_budget", 0),
            "suggest_lower_bid_count": action_counts.get("suggest_lower_bid", 0),
            "continue_running_count": action_counts.get("continue_running", 0),
            "watch_count": action_counts.get("watch", 0),
            "unit_good_signal_count": action_counts.get("unit_good_signal", 0),
            "unit_bad_signal_count": action_counts.get("unit_bad_signal", 0),
            "account_health_count": len(account_health),
        },
        "source": {
            "workflow": str(patrol_artifact.get("workflow") or ""),
            "artifact_path": str(patrol_artifact.get("artifact_path") or ""),
        },
        "rules": rules,
        "account_health": account_health,
        "suggestions": suggestions,
        "guardrails": [
            "Suggestion only: no project or promotion API is called.",
            "Suggestions must be converted to a project_update JSON and confirmed before execution.",
        ],
    }


def run_delivery_patrol_suggestions_request(
    request: dict[str, Any],
    *,
    runs_dir: str | Path,
) -> dict[str, Any]:
    patrol = request.get("patrol_artifact") if isinstance(request.get("patrol_artifact"), dict) else None
    if patrol is None:
        path = str(request.get("patrol_artifact_path") or "").strip()
        if not path:
            raise ValueError("delivery patrol suggestions requires patrol_artifact or patrol_artifact_path")
        patrol = _load_local_json(path)
    result = build_delivery_patrol_suggestions(patrol, request)
    artifact_path = write_run_artifact(runs_dir, "delivery_patrol_suggestions", result)
    return {**result, "artifact_path": str(artifact_path)}
