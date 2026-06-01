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


def _target_account_ids(cfg: dict[str, Any]) -> set[str] | None:
    if "target_account_ids" not in cfg:
        return None
    raw = cfg.get("target_account_ids")
    if isinstance(raw, str):
        values = [item.strip() for item in raw.split(",") if item.strip()]
    elif isinstance(raw, list):
        values = []
        for item in raw:
            if isinstance(item, dict):
                account_id = str(item.get("advertiser_id") or item.get("account_id") or "").strip()
            else:
                account_id = str(item or "").strip()
            if account_id:
                values.append(account_id)
    else:
        values = []
    return set(values)


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
        if suggestion.get("allowlist_exception") is True or str(suggestion.get("advertiser_id") or "") in allowed_account_ids:
            allowed.append(suggestion)
        else:
            blocked.append({**suggestion, "blocked_reason": "target account is not in allowlist"})
    return allowed, blocked


def _split_by_target_accounts(
    suggestions: list[dict[str, Any]],
    *,
    target_account_ids: set[str] | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if target_account_ids is None:
        return suggestions, []
    allowed: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    for suggestion in suggestions:
        if suggestion.get("allowlist_exception") is True or str(suggestion.get("advertiser_id") or "") in target_account_ids:
            allowed.append(suggestion)
        else:
            blocked.append({**suggestion, "blocked_reason": "target account is not in today's patrol spent allowlist"})
    return allowed, blocked


def _suggestion_id(
    *,
    target_date: str,
    suggestion_type: str,
    advertiser_id: str,
    entity_type: str,
    entity_id: str,
) -> str:
    return f"{target_date}:{entity_type}:{advertiser_id}:{entity_id}:{suggestion_type}"


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
          COALESCE(MAX(NULLIF(mdm.project_name, '')), mdm.project_id) AS project_name,
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


def _delete_project_closed_low_recent_suggestions(
    conn: sqlite3.Connection,
    *,
    cfg: dict[str, Any],
    target_date: str,
) -> list[dict[str, Any]]:
    rule_id = "delete_project_closed_low_recent"
    rule = _rule(cfg, rule_id)
    if not bool(rule.get("enabled", False)):
        return []

    lookback_days = max(int(rule.get("lookback_days") or 2), 1)
    max_stat_cost = _number(rule.get("max_stat_cost"), 100)
    max_convert_cnt = _number(rule.get("max_convert_cnt"), 0)
    disabled_statuses = rule.get("disabled_statuses")
    if not isinstance(disabled_statuses, list) or not disabled_statuses:
        disabled_statuses = ["PROJECT_STATUS_DISABLE", "PROJECT_STATUS_DISABLED", "DISABLE", "DISABLED"]
    start_date = (date.fromisoformat(target_date) - timedelta(days=lookback_days - 1)).isoformat()
    where_sql, params = _account_pool_scope_sql("p.advertiser_id", str(cfg.get("product_keyword") or ""))
    params.update(
        {
            "start_date": start_date,
            "target_date": target_date,
            "max_stat_cost": max_stat_cost,
            "max_convert_cnt": max_convert_cnt,
        }
    )
    status_placeholders: list[str] = []
    for index, status in enumerate(disabled_statuses):
        key = f"disabled_status_{index}"
        status_placeholders.append(f":{key}")
        params[key] = str(status)

    rows = conn.execute(
        f"""
        SELECT
          p.advertiser_id,
          COALESCE(MAX(ap.account_name), '') AS account_name,
          p.project_id,
          COALESCE(NULLIF(p.name, ''), MAX(mdm.project_name), p.project_id) AS project_name,
          p.status,
          COALESCE(SUM(mdm.stat_cost), 0) AS stat_cost,
          COALESCE(SUM(mdm.convert_cnt), 0) AS convert_cnt,
          COUNT(DISTINCT mdm.metric_date) AS active_days
        FROM projects p
        LEFT JOIN material_daily_metrics mdm
          ON mdm.advertiser_id = p.advertiser_id
          AND mdm.project_id = p.project_id
          AND mdm.metric_date BETWEEN :start_date AND :target_date
        LEFT JOIN account_pool ap
          ON ap.advertiser_id = p.advertiser_id
        WHERE {where_sql}
          AND p.project_id <> ''
          AND p.status IN ({", ".join(status_placeholders)})
        GROUP BY p.advertiser_id, p.project_id, p.name, p.status
        HAVING COALESCE(SUM(mdm.stat_cost), 0) <= :max_stat_cost
          AND COALESCE(SUM(mdm.convert_cnt), 0) <= :max_convert_cnt
        ORDER BY stat_cost ASC, p.advertiser_id, p.project_id
        """,
        params,
    ).fetchall()

    suggestions: list[dict[str, Any]] = []
    for row in rows:
        advertiser_id = str(row["advertiser_id"] or "")
        project_id = str(row["project_id"] or "")
        suggestions.append(
            {
                "suggestion_id": _suggestion_id(
                    target_date=target_date,
                    suggestion_type="suggest_delete_project",
                    advertiser_id=advertiser_id,
                    entity_type="project",
                    entity_id=project_id,
                ),
                "suggestion_type": "suggest_delete_project",
                "suggested_action": "suggest_delete_project",
                "rule_id": rule_id,
                "target_date": target_date,
                "advertiser_id": advertiser_id,
                "account_name": str(row["account_name"] or ""),
                "entity_type": "project",
                "entity_id": project_id,
                "project_id": project_id,
                "entity_name": str(row["project_name"] or project_id),
                "project_name": str(row["project_name"] or project_id),
                "status": str(row["status"] or ""),
                "reason": "项目已明确关闭，近两天低消耗且无转化，建议作为项目数量清理候选。",
                "metrics": {
                    "stat_cost": _rounded(float(row["stat_cost"] or 0)),
                    "convert_cnt": _rounded(float(row["convert_cnt"] or 0)),
                    "active_days": int(row["active_days"] or 0),
                },
                "thresholds": {
                    "lookback_days": lookback_days,
                    "max_stat_cost": _rounded(max_stat_cost),
                    "max_convert_cnt": _rounded(max_convert_cnt),
                    "disabled_statuses": list(disabled_statuses),
                },
                "execution": {
                    "enabled": False,
                    "note": "建议文件只供复核；不会调用删除项目接口。",
                },
            }
        )
    return suggestions


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
          COALESCE(MAX(NULLIF(mdm.project_name, '')), mdm.project_id) AS project_name,
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
        project_id = str(row["project_id"] or "")
        project_name = str(row["project_name"] or project_id)
        suggestions.append(
            {
                "suggestion_type": "pause_project",
                "rule_id": rule_id,
                "target_date": target_date,
                "advertiser_id": str(row["advertiser_id"]),
                "entity_type": "project",
                "entity_id": project_id,
                "project_id": project_id,
                "entity_name": project_name,
                "project_name": project_name,
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
        project_id = str(row["project_id"] or "")
        project_name = str(row["project_name"] or project_id)
        suggestions.append(
            {
                "suggestion_type": "adjust_project_budget",
                "rule_id": rule_id,
                "target_date": target_date,
                "advertiser_id": str(row["advertiser_id"]),
                "entity_type": "project",
                "entity_id": project_id,
                "project_id": project_id,
                "entity_name": project_name,
                "project_name": project_name,
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
        project_id = str(row["project_id"] or "")
        project_name = str(row["project_name"] or project_id)
        suggestions.append(
            {
                "suggestion_type": "adjust_project_bid",
                "rule_id": rule_id,
                "target_date": target_date,
                "advertiser_id": str(row["advertiser_id"]),
                "entity_type": "project",
                "entity_id": project_id,
                "project_id": project_id,
                "entity_name": project_name,
                "project_name": project_name,
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


def _material_reuse_risk_suggestions(
    conn: sqlite3.Connection,
    *,
    cfg: dict[str, Any],
    target_date: str,
) -> list[dict[str, Any]]:
    rule_id = "material_reuse_risk"
    rule = _rule(cfg, rule_id)
    if not bool(rule.get("enabled", False)):
        return []

    product_keyword = str(cfg.get("product_keyword") or "").strip()
    window_key = str(rule.get("window_key") or "last_7d").strip()
    min_account_count = int(rule.get("min_account_count") or 0)
    min_project_count = int(rule.get("min_project_count") or 5)
    min_promotion_count = int(rule.get("min_promotion_count") or 10)
    min_stat_cost = _number(rule.get("min_stat_cost"), 1000)
    max_roi_1day = _number(rule.get("max_roi_1day"), 0.05)
    product_filter = "psmr.product <> ''"
    params: dict[str, Any] = {
        "window_key": window_key,
        "target_date": target_date,
        "min_account_count": min_account_count,
        "min_project_count": min_project_count,
        "min_promotion_count": min_promotion_count,
        "min_stat_cost": min_stat_cost,
        "max_roi_1day": max_roi_1day,
    }
    if product_keyword:
        product_filter = "(psmr.product = :product_keyword OR psmr.product LIKE :product_keyword_like)"
        params["product_keyword"] = product_keyword
        params["product_keyword_like"] = f"%{product_keyword}%"

    rows = conn.execute(
        f"""
        SELECT
          psmr.product,
          psmr.source_advertiser_id,
          psmr.material_id,
          psmr.name,
          psmr.window_key,
          psmr.period_start,
          psmr.period_end,
          psmr.account_count,
          psmr.project_count,
          psmr.promotion_count,
          psmr.stat_cost,
          psmr.convert_cnt,
          psmr.roi_1day_cost_weighted
        FROM product_source_material_metric_rollups psmr
        WHERE {product_filter}
          AND psmr.window_key = :window_key
          AND psmr.period_end = (
            SELECT MAX(inner_psmr.period_end)
            FROM product_source_material_metric_rollups inner_psmr
            WHERE inner_psmr.window_key = psmr.window_key
              AND inner_psmr.product = psmr.product
              AND inner_psmr.period_end <= :target_date
          )
          AND psmr.stat_cost >= :min_stat_cost
          AND psmr.roi_1day_cost_weighted < :max_roi_1day
          AND (
            psmr.account_count >= :min_account_count
            OR psmr.project_count >= :min_project_count
            OR psmr.promotion_count >= :min_promotion_count
          )
        ORDER BY psmr.stat_cost DESC, psmr.project_count DESC, psmr.material_id
        LIMIT 50
        """,
        params,
    ).fetchall()

    suggestions: list[dict[str, Any]] = []
    for row in rows:
        advertiser_id = str(row["source_advertiser_id"] or "")
        material_id = str(row["material_id"] or "")
        suggestions.append(
            {
                "suggestion_id": _suggestion_id(
                    target_date=target_date,
                    suggestion_type="material_reuse_risk",
                    advertiser_id=advertiser_id,
                    entity_type="material",
                    entity_id=material_id,
                ),
                "suggestion_type": "material_reuse_risk",
                "suggested_action": "material_reuse_risk",
                "rule_id": rule_id,
                "target_date": target_date,
                "advertiser_id": advertiser_id,
                "entity_type": "material",
                "entity_id": material_id,
                "entity_name": str(row["name"] or material_id),
                "allowlist_exception": True,
                "reason": "素材在多个账户、项目或单元中高频复用，但近 7 天 ROI 偏低，建议人工复核复用风险。",
                "metrics": {
                    "window_key": str(row["window_key"] or ""),
                    "period_start": str(row["period_start"] or ""),
                    "period_end": str(row["period_end"] or ""),
                    "account_count": int(row["account_count"] or 0),
                    "project_count": int(row["project_count"] or 0),
                    "promotion_count": int(row["promotion_count"] or 0),
                    "stat_cost": _rounded(float(row["stat_cost"] or 0)),
                    "convert_cnt": _rounded(float(row["convert_cnt"] or 0)),
                    "roi_1day": _rounded(float(row["roi_1day_cost_weighted"] or 0)),
                },
                "thresholds": {
                    "window_key": window_key,
                    "min_account_count": min_account_count,
                    "min_project_count": min_project_count,
                    "min_promotion_count": min_promotion_count,
                    "min_stat_cost": _rounded(min_stat_cost),
                    "max_roi_1day": _rounded(max_roi_1day),
                },
                "execution": {
                    "enabled": False,
                    "note": "素材复用风险只读展示，不生成项目动作配置。",
                },
            }
        )
    return suggestions


def _account_spent_outside_allowlist_suggestions(
    conn: sqlite3.Connection,
    *,
    cfg: dict[str, Any],
    target_date: str,
    allowed_account_ids: set[str],
) -> list[dict[str, Any]]:
    rule_id = "account_spent_outside_allowlist"
    rule = _rule(cfg, rule_id)
    if not bool(rule.get("enabled", False)) or not allowed_account_ids:
        return []

    min_stat_cost = _number(rule.get("min_stat_cost"), 100)
    where_sql, params = _scope_sql(str(cfg.get("product_keyword") or ""))
    params.update({"target_date": target_date, "min_stat_cost": min_stat_cost})
    placeholders: list[str] = []
    for index, account_id in enumerate(sorted(allowed_account_ids)):
        key = f"allowed_account_{index}"
        placeholders.append(f":{key}")
        params[key] = account_id
    rows = conn.execute(
        f"""
        SELECT
          mdm.advertiser_id,
          COALESCE(MAX(ap.account_name), '') AS account_name,
          COALESCE(SUM(mdm.stat_cost), 0) AS stat_cost,
          COALESCE(SUM(mdm.convert_cnt), 0) AS convert_cnt,
          COUNT(DISTINCT mdm.project_id) AS project_count,
          COUNT(DISTINCT mdm.promotion_id) AS promotion_count
        FROM material_daily_metrics mdm
        LEFT JOIN account_pool ap
          ON ap.advertiser_id = mdm.advertiser_id
        WHERE {where_sql}
          AND mdm.metric_date = :target_date
          AND mdm.advertiser_id NOT IN ({", ".join(placeholders)})
        GROUP BY mdm.advertiser_id
        HAVING COALESCE(SUM(mdm.stat_cost), 0) >= :min_stat_cost
        ORDER BY stat_cost DESC, mdm.advertiser_id
        """,
        params,
    ).fetchall()

    suggestions: list[dict[str, Any]] = []
    for row in rows:
        advertiser_id = str(row["advertiser_id"] or "")
        suggestions.append(
            {
                "suggestion_id": _suggestion_id(
                    target_date=target_date,
                    suggestion_type="account_spent_outside_allowlist",
                    advertiser_id=advertiser_id,
                    entity_type="account",
                    entity_id=advertiser_id,
                ),
                "suggestion_type": "account_spent_outside_allowlist",
                "suggested_action": "account_spent_outside_allowlist",
                "rule_id": rule_id,
                "target_date": target_date,
                "advertiser_id": advertiser_id,
                "account_name": str(row["account_name"] or ""),
                "entity_type": "account",
                "entity_id": advertiser_id,
                "entity_name": str(row["account_name"] or advertiser_id),
                "allowlist_exception": True,
                "reason": "该账户在目标日期有消耗，但不在产品允许创建账户名单中，建议人工复核账户归属或名单配置。",
                "metrics": {
                    "stat_cost": _rounded(float(row["stat_cost"] or 0)),
                    "convert_cnt": _rounded(float(row["convert_cnt"] or 0)),
                    "project_count": int(row["project_count"] or 0),
                    "promotion_count": int(row["promotion_count"] or 0),
                },
                "thresholds": {"min_stat_cost": _rounded(min_stat_cost)},
                "execution": {
                    "enabled": False,
                    "note": "账户异常只读展示，不生成项目动作配置。",
                },
            }
        )
    return suggestions


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
    target_account_ids = _target_account_ids(cfg)
    with _connect(db_path) as conn:
        delete_suggestions = _delete_project_closed_low_recent_suggestions(conn, cfg=cfg, target_date=target_date)
        pause_suggestions = _pause_project_low_first_day_roi_suggestions(conn, cfg=cfg, target_date=target_date)
        budget_suggestions = _adjust_project_budget_low_roi_suggestions(conn, cfg=cfg, target_date=target_date)
        bid_suggestions = _adjust_project_bid_high_cpa_suggestions(conn, cfg=cfg, target_date=target_date)
        schedule_suggestions, realtime_ready, violations = _schedule_hollow_low_realtime_hour_roi_suggestions(
            conn,
            cfg=cfg,
            target_date=target_date,
        )
        material_suggestions = _material_reuse_risk_suggestions(conn, cfg=cfg, target_date=target_date)
        account_anomaly_suggestions = _account_spent_outside_allowlist_suggestions(
            conn,
            cfg=cfg,
            target_date=target_date,
            allowed_account_ids=allowed_account_ids,
        )
        all_suggestions = _attach_historical_operation_evidence(
            [
                *delete_suggestions,
                *pause_suggestions,
                *budget_suggestions,
                *bid_suggestions,
                *schedule_suggestions,
                *material_suggestions,
                *account_anomaly_suggestions,
            ],
            conn=conn,
            cfg=cfg,
            target_date=target_date,
        )
    target_filtered_suggestions, blocked_by_target = _split_by_target_accounts(
        all_suggestions,
        target_account_ids=target_account_ids,
    )
    suggestions, blocked_by_allowlist = _split_by_allowlist(
        target_filtered_suggestions,
        allowed_account_ids=allowed_account_ids,
    )
    blocked = [*blocked_by_target, *blocked_by_allowlist]
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
            "suggest_delete_project_count": sum(
                1 for item in suggestions if item.get("suggestion_type") == "suggest_delete_project"
            ),
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
            "material_reuse_risk_count": sum(
                1 for item in suggestions if item.get("suggestion_type") == "material_reuse_risk"
            ),
            "account_anomaly_count": sum(
                1 for item in suggestions if item.get("suggestion_type") == "account_spent_outside_allowlist"
            ),
            "blocked_by_target_account_count": len(blocked_by_target),
            "blocked_by_allowlist_count": len(blocked_by_allowlist),
            "target_account_count": len(target_account_ids) if target_account_ids is not None else None,
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
