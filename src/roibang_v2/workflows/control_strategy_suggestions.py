from __future__ import annotations

import json
import sqlite3
from datetime import date
from datetime import timedelta
from pathlib import Path
from typing import Any

from roibang_v2.runs import write_run_artifact


def _connect(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _number(value: Any, default: float = 0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _rounded(value: float) -> float:
    rounded = round(float(value), 6)
    if rounded == int(rounded):
        return int(rounded)
    return rounded


def _date_from_text(value: Any) -> date:
    text = str(value or "").strip()
    if len(text) < 10:
        raise ValueError(f"invalid date value: {value!r}")
    return date.fromisoformat(text[:10])


def _target_date(cfg: dict[str, Any]) -> str:
    value = str(cfg.get("target_date") or "").strip()
    if not value:
        raise ValueError("control_strategy_suggestions requires target_date")
    return value


def _rule(cfg: dict[str, Any], rule_id: str) -> dict[str, Any]:
    rules = cfg.get("rules") if isinstance(cfg.get("rules"), dict) else {}
    value = rules.get(rule_id) if isinstance(rules.get(rule_id), dict) else {}
    return dict(value)


def _json_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [dict(item) for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ["allowed_target_accounts", "accounts", "rows"]:
            value = payload.get(key)
            if isinstance(value, list):
                return [dict(item) for item in value if isinstance(item, dict)]
    return []


def _bool_enabled(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "enabled"}


def _allowed_account_ids(cfg: dict[str, Any]) -> set[str]:
    path_text = str(cfg.get("allowed_target_accounts_path") or "").strip()
    if not path_text:
        return set()
    path = Path(path_text)
    if not path.exists():
        raise ValueError(f"allowed_target_accounts_path not found: {path}")
    rows = _json_rows(json.loads(path.read_text(encoding="utf-8")))
    allowed: set[str] = set()
    for row in rows:
        advertiser_id = str(row.get("advertiser_id") or row.get("account_id") or "").strip()
        if advertiser_id and _bool_enabled(row.get("enable", row.get("enabled", True))):
            allowed.add(advertiser_id)
    return allowed


def _split_by_allowlist(
    suggestions: list[dict[str, Any]],
    *,
    allowed_account_ids: set[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not allowed_account_ids:
        return suggestions, []
    allowed: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    for suggestion in suggestions:
        if str(suggestion.get("advertiser_id") or "") in allowed_account_ids:
            allowed.append(suggestion)
        else:
            blocked.append({**suggestion, "blocked_reason": "target account is not in allowlist"})
    return allowed, blocked


def _scope_sql(product_keyword: str) -> tuple[str, dict[str, Any]]:
    keyword = str(product_keyword or "").strip()
    if not keyword:
        return "mdm.advertiser_id <> ''", {}
    return (
        """
        mdm.advertiser_id <> ''
        AND EXISTS (
          SELECT 1
          FROM account_pool ap
          WHERE ap.advertiser_id = mdm.advertiser_id
            AND (
              ap.account_name LIKE :product_keyword_like
              OR ap.product = :product_keyword_exact
              OR ap.product LIKE :product_keyword_like
            )
        )
        """,
        {
            "product_keyword_like": f"%{keyword}%",
            "product_keyword_exact": keyword,
        },
    )


def _account_pool_scope_sql(account_expr: str, product_keyword: str) -> tuple[str, dict[str, Any]]:
    keyword = str(product_keyword or "").strip()
    if not keyword:
        return f"{account_expr} <> ''", {}
    return (
        """
        {account_expr} <> ''
        AND EXISTS (
          SELECT 1
          FROM account_pool ap
          WHERE ap.advertiser_id = {account_expr}
            AND (
              ap.account_name LIKE :product_keyword_like
              OR ap.product = :product_keyword_exact
              OR ap.product LIKE :product_keyword_like
            )
        )
        """.format(account_expr=account_expr),
        {
            "product_keyword_like": f"%{keyword}%",
            "product_keyword_exact": keyword,
        },
    )


def _project_day_rows(
    conn: sqlite3.Connection,
    *,
    cfg: dict[str, Any],
    target_date: str,
    min_cost: float,
    min_conversions: float,
    extra_having_sql: str,
    extra_params: dict[str, Any],
) -> list[sqlite3.Row]:
    where_sql, params = _scope_sql(str(cfg.get("product_keyword") or ""))
    params.update(
        {
            "target_date": target_date,
            "min_cost": min_cost,
            "min_conversions": min_conversions,
            **extra_params,
        }
    )
    return conn.execute(
        f"""
        SELECT
          mdm.advertiser_id,
          mdm.project_id,
          COUNT(DISTINCT mdm.promotion_id) AS promotion_count,
          COALESCE(SUM(mdm.stat_cost), 0) AS stat_cost,
          COALESCE(SUM(mdm.convert_cnt), 0) AS convert_cnt,
          COALESCE(SUM(CASE WHEN mdm.stat_cost > 0 THEN mdm.stat_cost * mdm.roi_1day ELSE 0 END), 0)
            AS roi_1day_weighted_sum
        FROM material_daily_metrics mdm
        WHERE {where_sql}
          AND mdm.metric_date = :target_date
          AND mdm.project_id <> ''
        GROUP BY mdm.advertiser_id, mdm.project_id
        HAVING COALESCE(SUM(mdm.stat_cost), 0) >= :min_cost
          AND COALESCE(SUM(mdm.convert_cnt), 0) >= :min_conversions
          {extra_having_sql}
        ORDER BY stat_cost DESC, mdm.advertiser_id, mdm.project_id
        """,
        params,
    ).fetchall()


def _pause_project_low_first_day_roi_suggestions(
    conn: sqlite3.Connection,
    *,
    cfg: dict[str, Any],
    target_date: str,
) -> list[dict[str, Any]]:
    rule_id = "pause_project_low_first_day_roi"
    rule = _rule(cfg, rule_id)
    if not bool(rule.get("enabled", False)):
        return []

    min_cost = _number(rule.get("min_cost"), 500)
    min_conversions = _number(rule.get("min_conversions"), 2)
    max_roi_1day = _number(rule.get("max_roi_1day"), 0.25)
    where_sql, params = _scope_sql(str(cfg.get("product_keyword") or ""))
    params.update(
        {
            "target_date": target_date,
            "min_cost": min_cost,
            "min_conversions": min_conversions,
            "max_roi_1day": max_roi_1day,
        }
    )
    rows = conn.execute(
        f"""
        SELECT
          mdm.advertiser_id,
          mdm.project_id,
          COUNT(DISTINCT mdm.promotion_id) AS promotion_count,
          COALESCE(SUM(mdm.stat_cost), 0) AS stat_cost,
          COALESCE(SUM(mdm.convert_cnt), 0) AS convert_cnt,
          COALESCE(SUM(CASE WHEN mdm.stat_cost > 0 THEN mdm.stat_cost * mdm.roi_1day ELSE 0 END), 0)
            AS roi_1day_weighted_sum
        FROM material_daily_metrics mdm
        WHERE {where_sql}
          AND mdm.metric_date = :target_date
          AND mdm.project_id <> ''
        GROUP BY mdm.advertiser_id, mdm.project_id
        HAVING COALESCE(SUM(mdm.stat_cost), 0) >= :min_cost
          AND COALESCE(SUM(mdm.convert_cnt), 0) >= :min_conversions
          AND (
            COALESCE(SUM(CASE WHEN mdm.stat_cost > 0 THEN mdm.stat_cost * mdm.roi_1day ELSE 0 END), 0)
            / COALESCE(SUM(mdm.stat_cost), 0)
          ) < :max_roi_1day
        ORDER BY stat_cost DESC, mdm.advertiser_id, mdm.project_id
        """,
        params,
    ).fetchall()

    suggestions: list[dict[str, Any]] = []
    for row in rows:
        stat_cost = float(row["stat_cost"] or 0)
        roi_1day = float(row["roi_1day_weighted_sum"] or 0) / stat_cost if stat_cost > 0 else 0
        suggestions.append(
            {
                "suggestion_type": "pause_project",
                "rule_id": rule_id,
                "target_date": target_date,
                "advertiser_id": str(row["advertiser_id"]),
                "entity_type": "project",
                "entity_id": str(row["project_id"]),
                "reason": "首日 ROI 低于阈值且消耗/转化达到观察门槛",
                "metrics": {
                    "stat_cost": _rounded(stat_cost),
                    "convert_cnt": _rounded(float(row["convert_cnt"] or 0)),
                    "roi_1day": _rounded(roi_1day),
                    "promotion_count": int(row["promotion_count"] or 0),
                },
                "thresholds": {
                    "min_cost": _rounded(min_cost),
                    "min_conversions": _rounded(min_conversions),
                    "max_roi_1day": _rounded(max_roi_1day),
                },
                "execution": {
                    "enabled": False,
                    "note": "建议文件只供复核；不会调用暂停、改预算、改时段接口。",
                },
            }
        )
    return suggestions


def _adjust_project_budget_low_roi_suggestions(
    conn: sqlite3.Connection,
    *,
    cfg: dict[str, Any],
    target_date: str,
) -> list[dict[str, Any]]:
    rule_id = "adjust_project_budget_low_roi"
    rule = _rule(cfg, rule_id)
    if not bool(rule.get("enabled", False)):
        return []

    min_cost = _number(rule.get("min_cost"), 800)
    min_conversions = _number(rule.get("min_conversions"), 3)
    max_roi_1day = _number(rule.get("max_roi_1day"), 0.35)
    decrease_percent = _number(rule.get("budget_decrease_percent"), 20)
    rows = _project_day_rows(
        conn,
        cfg=cfg,
        target_date=target_date,
        min_cost=min_cost,
        min_conversions=min_conversions,
        extra_having_sql="""
          AND (
            COALESCE(SUM(CASE WHEN mdm.stat_cost > 0 THEN mdm.stat_cost * mdm.roi_1day ELSE 0 END), 0)
            / COALESCE(SUM(mdm.stat_cost), 0)
          ) < :max_roi_1day
        """,
        extra_params={"max_roi_1day": max_roi_1day},
    )

    suggestions: list[dict[str, Any]] = []
    for row in rows:
        stat_cost = float(row["stat_cost"] or 0)
        convert_cnt = float(row["convert_cnt"] or 0)
        roi_1day = float(row["roi_1day_weighted_sum"] or 0) / stat_cost if stat_cost > 0 else 0
        suggestions.append(
            {
                "suggestion_type": "adjust_project_budget",
                "rule_id": rule_id,
                "target_date": target_date,
                "advertiser_id": str(row["advertiser_id"]),
                "entity_type": "project",
                "entity_id": str(row["project_id"]),
                "reason": "首日 ROI 低于预算调整阈值，建议按配置下调项目预算，不猜具体预算金额",
                "metrics": {
                    "stat_cost": _rounded(stat_cost),
                    "convert_cnt": _rounded(convert_cnt),
                    "roi_1day": _rounded(roi_1day),
                    "cpa": _rounded(stat_cost / convert_cnt) if convert_cnt > 0 else None,
                    "promotion_count": int(row["promotion_count"] or 0),
                },
                "thresholds": {
                    "min_cost": _rounded(min_cost),
                    "min_conversions": _rounded(min_conversions),
                    "max_roi_1day": _rounded(max_roi_1day),
                },
                "adjustment": {
                    "field": "budget",
                    "direction": "decrease",
                    "decrease_percent": _rounded(decrease_percent),
                    "requires_current_budget_from_config": True,
                    "suggested_budget": None,
                },
                "execution": {
                    "enabled": False,
                    "note": "建议文件只供复核；不会调用暂停、改预算、改时段接口。",
                },
            }
        )
    return suggestions


def _adjust_project_bid_high_cpa_suggestions(
    conn: sqlite3.Connection,
    *,
    cfg: dict[str, Any],
    target_date: str,
) -> list[dict[str, Any]]:
    rule_id = "adjust_project_bid_high_cpa"
    rule = _rule(cfg, rule_id)
    if not bool(rule.get("enabled", False)):
        return []

    min_cost = _number(rule.get("min_cost"), 1000)
    min_conversions = _number(rule.get("min_conversions"), 2)
    max_cpa = _number(rule.get("max_cpa"), 300)
    decrease_percent = _number(rule.get("bid_decrease_percent"), 10)
    rows = _project_day_rows(
        conn,
        cfg=cfg,
        target_date=target_date,
        min_cost=min_cost,
        min_conversions=min_conversions,
        extra_having_sql="""
          AND (
            COALESCE(SUM(mdm.stat_cost), 0)
            / COALESCE(SUM(mdm.convert_cnt), 0)
          ) > :max_cpa
        """,
        extra_params={"max_cpa": max_cpa},
    )

    suggestions: list[dict[str, Any]] = []
    for row in rows:
        stat_cost = float(row["stat_cost"] or 0)
        convert_cnt = float(row["convert_cnt"] or 0)
        roi_1day = float(row["roi_1day_weighted_sum"] or 0) / stat_cost if stat_cost > 0 else 0
        suggestions.append(
            {
                "suggestion_type": "adjust_project_bid",
                "rule_id": rule_id,
                "target_date": target_date,
                "advertiser_id": str(row["advertiser_id"]),
                "entity_type": "project",
                "entity_id": str(row["project_id"]),
                "reason": "转化成本高于配置阈值，建议按配置下调项目出价，不猜当前出价",
                "metrics": {
                    "stat_cost": _rounded(stat_cost),
                    "convert_cnt": _rounded(convert_cnt),
                    "roi_1day": _rounded(roi_1day),
                    "cpa": _rounded(stat_cost / convert_cnt) if convert_cnt > 0 else None,
                    "promotion_count": int(row["promotion_count"] or 0),
                },
                "thresholds": {
                    "min_cost": _rounded(min_cost),
                    "min_conversions": _rounded(min_conversions),
                    "max_cpa": _rounded(max_cpa),
                },
                "adjustment": {
                    "field": "bid",
                    "direction": "decrease",
                    "decrease_percent": _rounded(decrease_percent),
                    "requires_current_bid_from_config": True,
                    "suggested_bid": None,
                },
                "execution": {
                    "enabled": False,
                    "note": "建议文件只供复核；不会调用暂停、改预算、改时段接口。",
                },
            }
        )
    return suggestions


def _restore_date(target_date: str) -> str:
    return (date.fromisoformat(target_date) + timedelta(days=1)).isoformat()


def _schedule_hollow_low_realtime_hour_roi_suggestions(
    conn: sqlite3.Connection,
    *,
    cfg: dict[str, Any],
    target_date: str,
) -> tuple[list[dict[str, Any]], bool, list[str]]:
    rule_id = "schedule_hollow_low_realtime_hour_roi"
    rule = _rule(cfg, rule_id)
    if not bool(rule.get("enabled", False)):
        return [], False, []

    min_cost = _number(rule.get("min_cost"), 200)
    max_roi_1day = _number(rule.get("max_roi_1day"), 0.2)
    min_fresh_synced_at = str(rule.get("min_fresh_synced_at") or "").strip()
    where_sql, params = _account_pool_scope_sql("phm.advertiser_id", str(cfg.get("product_keyword") or ""))
    params.update(
        {
            "target_date": target_date,
            "min_cost": min_cost,
            "max_roi_1day": max_roi_1day,
        }
    )
    fresh_sql = ""
    if min_fresh_synced_at:
        fresh_sql = "AND phm.synced_at >= :min_fresh_synced_at"
        params["min_fresh_synced_at"] = min_fresh_synced_at

    ready_count = conn.execute(
        f"""
        SELECT COUNT(*)
        FROM project_hourly_metrics phm
        WHERE phm.metric_date = :target_date
          AND {where_sql}
          {fresh_sql}
        """,
        params,
    ).fetchone()[0]
    if int(ready_count or 0) <= 0:
        return [], False, ["project_hourly_metrics has no realtime rows for target_date"]

    rows = conn.execute(
        f"""
        SELECT
          phm.advertiser_id,
          phm.project_id,
          GROUP_CONCAT(phm.metric_hour) AS hours,
          COALESCE(SUM(phm.stat_cost), 0) AS stat_cost,
          COALESCE(SUM(phm.convert_cnt), 0) AS convert_cnt,
          COALESCE(SUM(CASE WHEN phm.stat_cost > 0 THEN phm.stat_cost * phm.roi_1day ELSE 0 END), 0)
            AS roi_1day_weighted_sum
        FROM project_hourly_metrics phm
        WHERE phm.metric_date = :target_date
          AND {where_sql}
          AND phm.project_id <> ''
          AND phm.stat_cost >= :min_cost
          AND phm.roi_1day < :max_roi_1day
          {fresh_sql}
        GROUP BY phm.advertiser_id, phm.project_id
        ORDER BY stat_cost DESC, phm.advertiser_id, phm.project_id
        """,
        params,
    ).fetchall()

    suggestions: list[dict[str, Any]] = []
    for row in rows:
        stat_cost = float(row["stat_cost"] or 0)
        roi_1day = float(row["roi_1day_weighted_sum"] or 0) / stat_cost if stat_cost > 0 else 0
        hours = sorted({int(item) for item in str(row["hours"] or "").split(",") if str(item).strip()})
        suggestions.append(
            {
                "suggestion_type": "schedule_hollow",
                "rule_id": rule_id,
                "target_date": target_date,
                "advertiser_id": str(row["advertiser_id"]),
                "entity_type": "project",
                "entity_id": str(row["project_id"]),
                "hollow_hours": hours,
                "reason": "当天实时小时数据 ROI 低于阈值，建议临时拉空这些小时",
                "metrics": {
                    "stat_cost": _rounded(stat_cost),
                    "convert_cnt": _rounded(float(row["convert_cnt"] or 0)),
                    "roi_1day": _rounded(roi_1day),
                },
                "thresholds": {
                    "min_cost": _rounded(min_cost),
                    "max_roi_1day": _rounded(max_roi_1day),
                    "min_fresh_synced_at": min_fresh_synced_at,
                },
                "restore": {
                    "required": True,
                    "restore_date": _restore_date(target_date),
                    "reason": "当天临时拉空时段，第二天必须恢复原始时段，避免长期影响投放节奏。",
                },
                "execution": {
                    "enabled": False,
                    "note": "建议文件只供复核；不会调用暂停、改预算、改时段接口。",
                },
            }
        )
    return suggestions, True, []


def _operation_evidence_enabled(cfg: dict[str, Any]) -> bool:
    value = cfg.get("operation_evidence") if isinstance(cfg.get("operation_evidence"), dict) else {}
    return bool(value.get("enabled", False))


def _operation_evidence_rule_keywords(cfg: dict[str, Any], rule_id: str) -> list[str]:
    rule = _rule(cfg, rule_id)
    values = rule.get("operation_action_keywords")
    if isinstance(values, list):
        return [str(item).strip() for item in values if str(item).strip()]
    defaults = {
        "pause_project_low_first_day_roi": ["暂停", "关停"],
        "schedule_hollow_low_realtime_hour_roi": ["拉空", "投放时段", "时段"],
        "adjust_project_budget_low_roi": ["预算"],
        "adjust_project_bid_high_cpa": ["出价"],
    }
    return defaults.get(rule_id, [])


def _aggregate_project_window(
    conn: sqlite3.Connection,
    *,
    advertiser_id: str,
    project_id: str,
    start_date: date,
    end_date: date,
    product_keyword: str,
) -> dict[str, Any]:
    if start_date > end_date:
        return {"stat_cost": 0, "convert_cnt": 0, "roi_1day": None}
    where_sql, params = _scope_sql(product_keyword)
    params.update(
        {
            "advertiser_id": advertiser_id,
            "project_id": project_id,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        }
    )
    row = conn.execute(
        f"""
        SELECT
          COALESCE(SUM(mdm.stat_cost), 0) AS stat_cost,
          COALESCE(SUM(mdm.convert_cnt), 0) AS convert_cnt,
          COALESCE(SUM(CASE WHEN mdm.stat_cost > 0 THEN mdm.stat_cost * mdm.roi_1day ELSE 0 END), 0)
            AS roi_1day_weighted_sum
        FROM material_daily_metrics mdm
        WHERE {where_sql}
          AND mdm.advertiser_id = :advertiser_id
          AND mdm.project_id = :project_id
          AND mdm.metric_date BETWEEN :start_date AND :end_date
        """,
        params,
    ).fetchone()
    stat_cost = float(row["stat_cost"] or 0)
    convert_cnt = float(row["convert_cnt"] or 0)
    return {
        "stat_cost": _rounded(stat_cost),
        "convert_cnt": _rounded(convert_cnt),
        "roi_1day": _rounded(float(row["roi_1day_weighted_sum"] or 0) / stat_cost) if stat_cost > 0 else None,
    }


def _historical_operation_evidence(
    conn: sqlite3.Connection,
    *,
    cfg: dict[str, Any],
    target_date: str,
    rule_id: str,
) -> dict[str, Any] | None:
    evidence_cfg = cfg.get("operation_evidence") if isinstance(cfg.get("operation_evidence"), dict) else {}
    if not bool(evidence_cfg.get("enabled", False)):
        return None
    keywords = _operation_evidence_rule_keywords(cfg, rule_id)
    if not keywords:
        return None

    window_days = int(evidence_cfg.get("window_days") or 3)
    sample_limit = int(evidence_cfg.get("sample_limit") or 3)
    lookback_start = str(evidence_cfg.get("lookback_start") or "1970-01-01")[:10]
    lookback_end = str(evidence_cfg.get("lookback_end") or target_date)[:10]
    keyword_sql = " OR ".join(f"op.action LIKE :keyword_{idx}" for idx, _keyword in enumerate(keywords))
    params: dict[str, Any] = {
        "lookback_start": f"{lookback_start} 00:00:00",
        "lookback_end": f"{lookback_end} 23:59:59",
    }
    for idx, keyword in enumerate(keywords):
        params[f"keyword_{idx}"] = f"%{keyword}%"
    scope_sql, scope_params = _account_pool_scope_sql("op.advertiser_id", str(cfg.get("product_keyword") or ""))
    params.update(scope_params)

    operations = conn.execute(
        f"""
        SELECT
          op.operation_id,
          op.occurred_at,
          op.advertiser_id,
          op.entity_type,
          op.entity_id,
          op.action,
          op.detail
        FROM operation_logs op
        WHERE op.occurred_at BETWEEN :lookback_start AND :lookback_end
          AND {scope_sql}
          AND op.entity_id <> ''
          AND op.entity_type IN ('project', '项目')
          AND ({keyword_sql})
        ORDER BY op.occurred_at DESC, op.operation_id DESC
        """,
        params,
    ).fetchall()

    included_operation_count = 0
    roi_deltas: list[float] = []
    cost_deltas: list[float] = []
    samples: list[dict[str, Any]] = []
    positive_count = 0
    keyword = str(cfg.get("product_keyword") or "").strip()
    for operation in operations:
        occurred_date = _date_from_text(operation["occurred_at"])
        before = _aggregate_project_window(
            conn,
            advertiser_id=str(operation["advertiser_id"]),
            project_id=str(operation["entity_id"]),
            start_date=occurred_date - timedelta(days=window_days),
            end_date=occurred_date - timedelta(days=1),
            product_keyword=keyword,
        )
        after = _aggregate_project_window(
            conn,
            advertiser_id=str(operation["advertiser_id"]),
            project_id=str(operation["entity_id"]),
            start_date=occurred_date + timedelta(days=1),
            end_date=occurred_date + timedelta(days=window_days),
            product_keyword=keyword,
        )
        if (
            float(before.get("stat_cost") or 0) <= 0
            and float(after.get("stat_cost") or 0) <= 0
            and float(before.get("convert_cnt") or 0) <= 0
            and float(after.get("convert_cnt") or 0) <= 0
        ):
            continue
        included_operation_count += 1
        before_roi = before.get("roi_1day")
        after_roi = after.get("roi_1day")
        roi_delta = (float(after_roi) - float(before_roi)) if before_roi is not None and after_roi is not None else None
        cost_delta = float(after["stat_cost"] or 0) - float(before["stat_cost"] or 0)
        if roi_delta is not None:
            roi_deltas.append(roi_delta)
        cost_deltas.append(cost_delta)
        if (roi_delta is not None and roi_delta > 0) or cost_delta < 0:
            positive_count += 1
        if len(samples) < sample_limit:
            samples.append(
                {
                    "operation_id": str(operation["operation_id"]),
                    "operation_date": occurred_date.isoformat(),
                    "advertiser_id": str(operation["advertiser_id"]),
                    "entity_id": str(operation["entity_id"]),
                    "action": str(operation["action"]),
                    "before": before,
                    "after": after,
                }
            )

    if included_operation_count <= 0:
        return {
            "source": "operation_logs + material_daily_metrics",
            "window_days": window_days,
            "operation_count": 0,
            "positive_count": 0,
            "avg_roi_1day_delta": None,
            "avg_stat_cost_delta": None,
            "samples": [],
        }
    return {
        "source": "operation_logs + material_daily_metrics",
        "window_days": window_days,
        "operation_count": included_operation_count,
        "positive_count": positive_count,
        "avg_roi_1day_delta": _rounded(sum(roi_deltas) / len(roi_deltas)) if roi_deltas else None,
        "avg_stat_cost_delta": _rounded(sum(cost_deltas) / len(cost_deltas)) if cost_deltas else None,
        "samples": samples,
    }


def _attach_historical_operation_evidence(
    suggestions: list[dict[str, Any]],
    *,
    conn: sqlite3.Connection,
    cfg: dict[str, Any],
    target_date: str,
) -> list[dict[str, Any]]:
    if not _operation_evidence_enabled(cfg):
        return suggestions
    evidence_by_rule: dict[str, dict[str, Any] | None] = {}
    enriched: list[dict[str, Any]] = []
    for suggestion in suggestions:
        rule_id = str(suggestion.get("rule_id") or "")
        if rule_id not in evidence_by_rule:
            evidence_by_rule[rule_id] = _historical_operation_evidence(
                conn,
                cfg=cfg,
                target_date=target_date,
                rule_id=rule_id,
            )
        evidence = evidence_by_rule[rule_id]
        enriched.append({**suggestion, "historical_operation_evidence": evidence} if evidence is not None else suggestion)
    return enriched


def build_control_strategy_suggestions(db_path: str | Path, request: dict[str, Any] | None) -> dict[str, Any]:
    cfg = dict(request or {})
    target_date = _target_date(cfg)
    allowed_account_ids = _allowed_account_ids(cfg)
    with _connect(db_path) as conn:
        pause_suggestions = _pause_project_low_first_day_roi_suggestions(conn, cfg=cfg, target_date=target_date)
        budget_suggestions = _adjust_project_budget_low_roi_suggestions(conn, cfg=cfg, target_date=target_date)
        bid_suggestions = _adjust_project_bid_high_cpa_suggestions(conn, cfg=cfg, target_date=target_date)
        schedule_suggestions, realtime_ready, violations = _schedule_hollow_low_realtime_hour_roi_suggestions(
            conn,
            cfg=cfg,
            target_date=target_date,
        )
        all_suggestions = _attach_historical_operation_evidence(
            [*pause_suggestions, *budget_suggestions, *bid_suggestions, *schedule_suggestions],
            conn=conn,
            cfg=cfg,
            target_date=target_date,
        )
    suggestions, blocked = _split_by_allowlist(
        all_suggestions,
        allowed_account_ids=allowed_account_ids,
    )
    return {
        "ok": True,
        "workflow": "control_strategy_suggestions",
        "phase": "control_analysis",
        "execution_enabled": False,
        "external_api_calls": 0,
        "summary": {
            "target_date": target_date,
            "filter": {"product_keyword": str(cfg.get("product_keyword") or "").strip()}
            if str(cfg.get("product_keyword") or "").strip()
            else {},
            "suggestion_count": len(suggestions),
            "pause_project_suggestion_count": sum(
                1 for item in suggestions if item.get("suggestion_type") == "pause_project"
            ),
            "schedule_hollow_suggestion_count": sum(
                1 for item in suggestions if item.get("suggestion_type") == "schedule_hollow"
            ),
            "adjust_project_budget_suggestion_count": sum(
                1 for item in suggestions if item.get("suggestion_type") == "adjust_project_budget"
            ),
            "adjust_project_bid_suggestion_count": sum(
                1 for item in suggestions if item.get("suggestion_type") == "adjust_project_bid"
            ),
            "operation_evidence_suggestion_count": sum(
                1
                for item in suggestions
                if int((item.get("historical_operation_evidence") or {}).get("operation_count") or 0) > 0
            ),
            "blocked_by_allowlist_count": len(blocked),
            "allowed_account_count": len(allowed_account_ids),
            "realtime_hourly_data_ready": realtime_ready,
        },
        "suggestions": suggestions,
        "blocked_suggestions": blocked,
        "violations": violations,
        "guardrails": [
            "Readonly only: this workflow reads local SQLite data.",
            "No create/update/delete/pause/budget/schedule API is called.",
        ],
    }


def run_control_strategy_suggestions_request(
    request: dict[str, Any] | None,
    *,
    db_path: str | Path,
    runs_dir: str | Path,
) -> dict[str, Any]:
    payload = build_control_strategy_suggestions(db_path, request)
    payload["artifact_path"] = str(write_run_artifact(runs_dir, "control_strategy_suggestions", payload))
    return payload
