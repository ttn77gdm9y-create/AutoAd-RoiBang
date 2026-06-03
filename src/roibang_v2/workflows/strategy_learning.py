from __future__ import annotations

import json
import re
import sqlite3
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from roibang_v2.runs import write_snapshot_artifact
from roibang_v2.workflows.product_automation_job import load_product_configs


WORKFLOW = "strategy_learning"

GUARDRAILS = [
    "策略学习脚本只读历史指标和操作日志，不执行真实投放动作。",
    "学习结果只生成候选策略；所有候选策略默认未启用，必须人工确认后才可进入建议生成。",
    "建议运行时必须使用实时巡检快照；历史数据只作为学习和证据来源。",
    "高风险暂停/删除动作样本不足时只能输出只读诊断，不能用默认阈值兜底。",
]

RUNTIME_CONTRACT = {
    "strategy_source": "learned_strategy_only",
    "runtime_metric_source": "realtime_patrol_snapshot",
    "historical_data_usage": "learning_and_evidence_only",
    "allow_builtin_default_project_actions": False,
    "execution_enabled": False,
}

ACTION_CATALOG: dict[str, dict[str, str]] = {
    "suggest_create_project": {"label": "创建项目建议", "risk_level": "medium", "rule_family": "create_project"},
    "suggest_lower_budget": {"label": "下调预算", "risk_level": "medium", "rule_family": "project_budget"},
    "suggest_lower_bid": {"label": "下调出价", "risk_level": "medium", "rule_family": "project_bid"},
    "pause_project": {"label": "暂停项目", "risk_level": "high", "rule_family": "project_status"},
    "suggest_delete_project": {"label": "删除项目", "risk_level": "critical", "rule_family": "project_delete"},
}

DEFAULT_SAMPLE_STANDARDS: dict[str, dict[str, Any]] = {
    "read_only_diagnostic": {"min_total_samples": 5, "min_product_samples": 1, "max_false_positive_rate": 0.5},
    "suggest_create_project": {"min_total_samples": 30, "min_product_samples": 5, "max_false_positive_rate": 0.2},
    "suggest_lower_budget": {"min_total_samples": 30, "min_product_samples": 5, "max_false_positive_rate": 0.2},
    "suggest_lower_bid": {"min_total_samples": 30, "min_product_samples": 5, "max_false_positive_rate": 0.2},
    "pause_project": {"min_total_samples": 80, "min_product_samples": 10, "max_false_positive_rate": 0.1},
    "suggest_delete_project": {"min_total_samples": 100, "min_product_samples": 15, "max_false_positive_rate": 0.1},
}

DEFAULT_SECOND_STAGE_LEARNING: dict[str, Any] = {
    "enabled": False,
    "min_backtest_samples": 5,
    "min_backtest_positive_rate": 0.5,
    "min_metric_available_rate": 0.5,
    "budget_decrease_percent_default": 20,
    "bid_decrease_percent_default": 10,
    "min_cost_floor": 100,
}

PROJECT_RULE_BY_ACTION = {
    "suggest_lower_budget": "adjust_project_budget_low_roi",
    "suggest_lower_bid": "adjust_project_bid_high_cpa",
    "pause_project": "pause_project_low_first_day_roi",
    "suggest_delete_project": "delete_project_closed_low_recent",
}

HIGH_RISK_ACTIONS = {"pause_project", "suggest_delete_project"}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _rounded(value: Any, digits: int = 4) -> float:
    number = _number(value)
    rounded = round(number, digits)
    return int(rounded) if rounded == int(rounded) else rounded


def _date_value(value: Any, *, today: date | None = None) -> str:
    text = _text(value)
    base = today or date.today()
    if text == "today" or not text:
        return base.isoformat()
    if text == "yesterday":
        return (base - timedelta(days=1)).isoformat()
    return text


def _parse_date(value: str) -> date:
    return date.fromisoformat(value[:10])


def _date_range(policy: dict[str, Any]) -> tuple[str, str, str]:
    target_date = _date_value(policy.get("target_date") or "yesterday")
    explicit_start = _text(policy.get("start_date"))
    explicit_end = _text(policy.get("end_date"))
    if explicit_start or explicit_end:
        start = _date_value(explicit_start or target_date)
        end = _date_value(explicit_end or target_date)
        return target_date, start, end
    lookback_days = max(int(_number(policy.get("lookback_days"), 45)), 1)
    end_date = _parse_date(target_date)
    start_date = end_date - timedelta(days=lookback_days - 1)
    return target_date, start_date.isoformat(), end_date.isoformat()


def _strategy_learning_config(request: dict[str, Any]) -> dict[str, Any]:
    value = request.get("strategy_learning")
    return dict(value) if isinstance(value, dict) else dict(request)


def _product_key(product: dict[str, Any]) -> str:
    return _text(product.get("product_key"))


def _product_name(product: dict[str, Any]) -> str:
    return _text(product.get("product")) or _text(product.get("product_name")) or _product_key(product)


def _load_products(products_dir: str | Path, product_keys: list[str]) -> list[dict[str, Any]]:
    rows = load_product_configs(products_dir)
    if product_keys:
        allowed = {item for item in product_keys if item}
        rows = [row for row in rows if _product_key(row) in allowed]
    return rows


def _sample_standards(policy: dict[str, Any]) -> dict[str, dict[str, Any]]:
    standards = {key: dict(value) for key, value in DEFAULT_SAMPLE_STANDARDS.items()}
    overrides = policy.get("sample_standards")
    if isinstance(overrides, dict):
        for action, value in overrides.items():
            if isinstance(value, dict):
                base = standards.setdefault(_text(action), {})
                base.update(value)
    return standards


def _second_stage_learning_config(policy: dict[str, Any]) -> dict[str, Any]:
    config = dict(DEFAULT_SECOND_STAGE_LEARNING)
    value = policy.get("second_stage_learning")
    if isinstance(value, dict):
        config.update(value)
    return config


def _operation_rows(
    conn: sqlite3.Connection,
    *,
    start_date: str,
    end_date: str,
    product_names: set[str],
) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT
          ol.operation_id,
          ol.occurred_at,
          ol.advertiser_id,
          ol.entity_type,
          ol.entity_id,
          ol.action,
          ol.operator,
          ol.detail,
          ol.before_json,
          ol.after_json,
          ol.payload_json,
          ap.account_name,
          ap.product,
          ap.platform
        FROM operation_logs ol
        LEFT JOIN account_pool ap ON ap.advertiser_id = ol.advertiser_id
        WHERE substr(ol.occurred_at, 1, 10) BETWEEN ? AND ?
        ORDER BY ol.occurred_at ASC, ol.operation_id ASC
        """,
        (start_date, end_date),
    ).fetchall()
    if not product_names:
        return rows
    return [row for row in rows if _text(row["product"]) in product_names]


def _parse_arrow_numbers(text: str) -> tuple[float | None, float | None]:
    match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*->\s*([0-9]+(?:\.[0-9]+)?)", text)
    if not match:
        return None, None
    return float(match.group(1)), float(match.group(2))


def _is_create_project_action(action: str) -> bool:
    return "新建" in action or "复制" in action


def _has_field_arrow(detail: str, field_name: str) -> bool:
    return re.search(rf"{re.escape(field_name)}\s*:\s*[0-9]+(?:\.[0-9]+)?\s*->\s*[0-9]+(?:\.[0-9]+)?", detail) is not None


def _classify_operation(row: sqlite3.Row) -> dict[str, Any] | None:
    entity_type = _text(row["entity_type"]).lower()
    action = _text(row["action"])
    detail = _text(row["detail"])
    combined = f"{action}\n{detail}"
    is_project = entity_type in {"project", "项目"}
    if not is_project:
        return None

    if "删除" in action:
        return {"standard_action": "suggest_delete_project", "action_label": "删除项目"}
    if _is_create_project_action(action):
        return {"standard_action": "suggest_create_project", "action_label": "创建项目"}
    if "启用 -> 暂停" in combined or "正常 -> 暂停" in combined or "暂停项目" in combined or "关停" in combined:
        return {"standard_action": "pause_project", "action_label": "暂停项目"}
    if _has_field_arrow(detail, "项目预算") or action in {"修改预算", "update_budget"}:
        before, after = _parse_arrow_numbers(combined)
        if before is not None and after is not None and after > before:
            return None
        return {"standard_action": "suggest_lower_budget", "action_label": "下调预算"}
    if _has_field_arrow(detail, "项目出价") or _has_field_arrow(detail, "出价") or _has_field_arrow(detail, "cpa_bid"):
        before, after = _parse_arrow_numbers(combined)
        if before is not None and after is not None and after > before:
            return None
        return {"standard_action": "suggest_lower_bid", "action_label": "下调出价"}
    return None


def _operation_datetime_parts(value: str) -> tuple[str, int]:
    match = re.search(r"(\d{4}-\d{2}-\d{2})(?:[ T](\d{2}))?", value)
    if not match:
        return "", 23
    return match.group(1), int(match.group(2) or 23)


def _hourly_metrics_before(
    conn: sqlite3.Connection,
    *,
    advertiser_id: str,
    project_id: str,
    metric_date: str,
    metric_hour: int,
) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT
          metric_date,
          metric_hour,
          project_name,
          stat_cost,
          show_cnt,
          click_cnt,
          convert_cnt,
          roi_1day
        FROM project_hourly_metrics
        WHERE advertiser_id = ?
          AND project_id = ?
          AND metric_date = ?
          AND metric_hour <= ?
        ORDER BY metric_hour DESC
        LIMIT 1
        """,
        (advertiser_id, project_id, metric_date, metric_hour),
    ).fetchone()
    if row is None:
        return None
    stat_cost = float(row["stat_cost"] or 0)
    convert_cnt = float(row["convert_cnt"] or 0)
    return {
        "available": True,
        "source": "project_hourly_metrics",
        "metric_date": _text(row["metric_date"]),
        "metric_hour": int(row["metric_hour"]),
        "project_name": _text(row["project_name"]),
        "stat_cost": _rounded(stat_cost),
        "show_cnt": _rounded(row["show_cnt"]),
        "click_cnt": _rounded(row["click_cnt"]),
        "convert_cnt": _rounded(convert_cnt),
        "roi_1day": _rounded(row["roi_1day"]),
        "cpa": _rounded(stat_cost / convert_cnt) if convert_cnt > 0 else None,
    }


def _daily_metrics(
    conn: sqlite3.Connection,
    *,
    advertiser_id: str,
    project_id: str,
    start_date: str,
    end_date: str,
    order: str,
) -> dict[str, Any] | None:
    direction = "DESC" if order == "desc" else "ASC"
    row = conn.execute(
        f"""
        SELECT
          metric_date,
          COALESCE(MAX(NULLIF(project_name, '')), ?) AS project_name,
          COUNT(DISTINCT promotion_id) AS promotion_count,
          COALESCE(SUM(stat_cost), 0) AS stat_cost,
          COALESCE(SUM(show_cnt), 0) AS show_cnt,
          COALESCE(SUM(click_cnt), 0) AS click_cnt,
          COALESCE(SUM(convert_cnt), 0) AS convert_cnt,
          COALESCE(SUM(CASE WHEN stat_cost > 0 THEN stat_cost * roi_1day ELSE 0 END), 0) AS roi_weighted_sum
        FROM material_daily_metrics
        WHERE advertiser_id = ?
          AND project_id = ?
          AND metric_date BETWEEN ? AND ?
        GROUP BY metric_date
        ORDER BY metric_date {direction}
        LIMIT 1
        """,
        (project_id, advertiser_id, project_id, start_date, end_date),
    ).fetchone()
    if row is None:
        return None
    stat_cost = float(row["stat_cost"] or 0)
    convert_cnt = float(row["convert_cnt"] or 0)
    roi = float(row["roi_weighted_sum"] or 0) / stat_cost if stat_cost > 0 else None
    return {
        "available": True,
        "source": "material_daily_metrics",
        "metric_date": _text(row["metric_date"]),
        "project_name": _text(row["project_name"]),
        "promotion_count": int(row["promotion_count"] or 0),
        "stat_cost": _rounded(stat_cost),
        "show_cnt": _rounded(row["show_cnt"]),
        "click_cnt": _rounded(row["click_cnt"]),
        "convert_cnt": _rounded(convert_cnt),
        "roi_1day": _rounded(roi) if roi is not None else None,
        "cpa": _rounded(stat_cost / convert_cnt) if convert_cnt > 0 else None,
    }


def _project_name(conn: sqlite3.Connection, *, advertiser_id: str, project_id: str, fallback: str = "") -> str:
    row = conn.execute(
        """
        SELECT name
        FROM projects
        WHERE advertiser_id = ? AND project_id = ?
        LIMIT 1
        """,
        (advertiser_id, project_id),
    ).fetchone()
    return _text(row["name"] if row else "") or fallback or project_id


def _project_metrics_around_operation(
    conn: sqlite3.Connection,
    *,
    advertiser_id: str,
    project_id: str,
    occurred_at: str,
    metric_lookback_days: int,
    post_days: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    op_date_text, op_hour = _operation_datetime_parts(occurred_at)
    if not op_date_text:
        return {"available": False, "warning": "操作时间无法解析，无法对齐操作前指标。"}, {"available": False}
    op_date = _parse_date(op_date_text)

    pre = _hourly_metrics_before(
        conn,
        advertiser_id=advertiser_id,
        project_id=project_id,
        metric_date=op_date.isoformat(),
        metric_hour=op_hour,
    )
    if pre is None:
        previous_start = (op_date - timedelta(days=max(metric_lookback_days, 1))).isoformat()
        previous_end = (op_date - timedelta(days=1)).isoformat()
        pre = _daily_metrics(
            conn,
            advertiser_id=advertiser_id,
            project_id=project_id,
            start_date=previous_start,
            end_date=previous_end,
            order="desc",
        )
    if pre is None:
        pre = _daily_metrics(
            conn,
            advertiser_id=advertiser_id,
            project_id=project_id,
            start_date=op_date.isoformat(),
            end_date=op_date.isoformat(),
            order="desc",
        )
        if pre is not None:
            pre["warning"] = "只找到操作当天日表，可能包含操作后的消耗。"
    if pre is None:
        pre = {"available": False, "warning": "没有找到操作前项目指标。"}

    post_start = (op_date + timedelta(days=1)).isoformat()
    post_end = (op_date + timedelta(days=max(post_days, 1))).isoformat()
    post = _daily_metrics(
        conn,
        advertiser_id=advertiser_id,
        project_id=project_id,
        start_date=post_start,
        end_date=post_end,
        order="asc",
    )
    if post is None:
        post = {"available": False, "warning": "没有找到操作后复盘指标。"}
    return pre, post


def _sample_summary(sample: dict[str, Any]) -> str:
    account = f"{sample['account_name']}（{sample['advertiser_id']}）" if sample.get("account_name") else sample["advertiser_id"]
    project = f"{sample['project_name']}（{sample['project_id']}）" if sample.get("project_name") else sample["project_id"]
    pre = sample.get("pre_metrics") if isinstance(sample.get("pre_metrics"), dict) else {}
    if pre.get("available"):
        metrics = (
            f"操作前消耗 {_rounded(pre.get('stat_cost'))}，"
            f"转化 {_rounded(pre.get('convert_cnt'))}，"
            f"ROI {pre.get('roi_1day') if pre.get('roi_1day') is not None else '无'}"
        )
    else:
        metrics = "操作前指标缺失"
    return f"{sample['occurred_at']}，{sample['product']}账户 {account}，项目 {project}，真实操作：{sample['action_label']}；{metrics}。"


def _build_samples(
    conn: sqlite3.Connection,
    *,
    rows: list[sqlite3.Row],
    products_by_name: dict[str, dict[str, Any]],
    metric_lookback_days: int,
    post_days: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    samples: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for row in rows:
        classified = _classify_operation(row)
        if classified is None:
            skipped.append(
                {
                    "operation_id": _text(row["operation_id"]),
                    "reason": "暂不支持该操作类型或不是项目级动作。",
                    "action": _text(row["action"]),
                    "entity_type": _text(row["entity_type"]),
                }
            )
            continue
        advertiser_id = _text(row["advertiser_id"])
        project_id = _text(row["entity_id"])
        product_name = _text(row["product"]) or "未归属产品"
        product = products_by_name.get(product_name, {})
        project_name = _project_name(conn, advertiser_id=advertiser_id, project_id=project_id)
        pre_metrics, post_metrics = _project_metrics_around_operation(
            conn,
            advertiser_id=advertiser_id,
            project_id=project_id,
            occurred_at=_text(row["occurred_at"]),
            metric_lookback_days=metric_lookback_days,
            post_days=post_days,
        )
        if pre_metrics.get("project_name") and not project_name:
            project_name = _text(pre_metrics.get("project_name"))
        warnings = []
        for metrics in [pre_metrics, post_metrics]:
            warning = _text(metrics.get("warning")) if isinstance(metrics, dict) else ""
            if warning:
                warnings.append(warning)
        sample = {
            "sample_id": f"{_text(row['operation_id'])}:{classified['standard_action']}",
            "operation_id": _text(row["operation_id"]),
            "occurred_at": _text(row["occurred_at"]),
            "operator": _text(row["operator"]),
            "product_key": _product_key(product),
            "product": product_name,
            "platform": _text(row["platform"]) or _text(product.get("platform")),
            "advertiser_id": advertiser_id,
            "account_name": _text(row["account_name"]),
            "entity_type": _text(row["entity_type"]),
            "entity_id": _text(row["entity_id"]),
            "project_id": project_id,
            "project_name": project_name or project_id,
            "raw_action": _text(row["action"]),
            "action_label": classified["action_label"],
            "standard_action": classified["standard_action"],
            "risk_level": ACTION_CATALOG[classified["standard_action"]]["risk_level"],
            "detail_excerpt": _text(row["detail"])[:300],
            "pre_metrics": pre_metrics,
            "post_metrics": post_metrics,
            "data_quality": {
                "pre_metric_available": bool(pre_metrics.get("available")),
                "post_metric_available": bool(post_metrics.get("available")),
                "warnings": warnings,
            },
        }
        sample["中文摘要"] = _sample_summary(sample)
        samples.append(sample)
    return samples, skipped


def _percentile(values: list[float], percent: float) -> float | None:
    numbers = sorted(value for value in values if value is not None)
    if not numbers:
        return None
    index = round((len(numbers) - 1) * percent)
    return _rounded(numbers[index])


def _metric_distribution(samples: list[dict[str, Any]], key: str) -> dict[str, Any]:
    values: list[float] = []
    for sample in samples:
        metrics = sample.get("pre_metrics") if isinstance(sample.get("pre_metrics"), dict) else {}
        if metrics.get("available") and metrics.get(key) is not None:
            values.append(float(metrics[key]))
    return {
        "count": len(values),
        "p25": _percentile(values, 0.25),
        "median": _percentile(values, 0.5),
        "p75": _percentile(values, 0.75),
    }


def _learned_conditions(samples: list[dict[str, Any]], *, action: str) -> dict[str, Any]:
    sources = sorted(
        {
            _text((sample.get("pre_metrics") or {}).get("source"))
            for sample in samples
            if isinstance(sample.get("pre_metrics"), dict) and (sample.get("pre_metrics") or {}).get("available")
        }
    )
    conditions = {
        "metric_sources": sources,
        "stat_cost": _metric_distribution(samples, "stat_cost"),
        "convert_cnt": _metric_distribution(samples, "convert_cnt"),
        "roi_1day": _metric_distribution(samples, "roi_1day"),
        "cpa": _metric_distribution(samples, "cpa"),
        "interpretation": "",
        "forbidden_runtime_conditions": [
            "实时巡检为 continue_running 或 running_good",
            "实时数据与历史日表口径明显不一致",
            "缺少账户名或项目名",
        ],
    }
    if action in {"pause_project", "suggest_delete_project"}:
        converting = [
            sample
            for sample in samples
            if (sample.get("pre_metrics") or {}).get("available") and _number((sample.get("pre_metrics") or {}).get("convert_cnt")) > 0
        ]
        conditions["interpretation"] = "高风险动作只生成候选规律；如果样本中存在有转化项目，不能自动推导为暂停/删除阈值。"
        conditions["positive_conversion_sample_count"] = len(converting)
    elif action in {"suggest_lower_budget", "suggest_lower_bid"}:
        conditions["interpretation"] = "中风险调控动作用于学习有转化低回收时的处理边界，运行时仍需实时巡检确认。"
    elif action == "suggest_create_project":
        conditions["interpretation"] = "创建建议只学习历史创建前后的账户和素材状态，运行时仍只生成创建计划预览。"
    return conditions


def _sample_segments(samples: list[dict[str, Any]]) -> dict[str, Any]:
    with_pre = [
        sample
        for sample in samples
        if isinstance(sample.get("pre_metrics"), dict) and (sample.get("pre_metrics") or {}).get("available")
    ]
    positive_conversion = [
        sample for sample in with_pre if _number((sample.get("pre_metrics") or {}).get("convert_cnt")) > 0
    ]
    zero_conversion = [
        sample for sample in with_pre if _number((sample.get("pre_metrics") or {}).get("convert_cnt")) <= 0
    ]
    with_post = [
        sample
        for sample in samples
        if isinstance(sample.get("post_metrics"), dict) and (sample.get("post_metrics") or {}).get("available")
    ]
    return {
        "total": len(samples),
        "with_pre_metrics": len(with_pre),
        "missing_pre_metrics": max(len(samples) - len(with_pre), 0),
        "with_post_metrics": len(with_post),
        "positive_conversion_count": len(positive_conversion),
        "zero_conversion_count": len(zero_conversion),
        "positive_conversion_rate": _rounded(len(positive_conversion) / len(with_pre)) if with_pre else None,
        "metric_available_rate": _rounded(len(with_pre) / len(samples)) if samples else None,
    }


def _post_outcome_positive(sample: dict[str, Any], *, action: str) -> bool | None:
    pre = sample.get("pre_metrics") if isinstance(sample.get("pre_metrics"), dict) else {}
    post = sample.get("post_metrics") if isinstance(sample.get("post_metrics"), dict) else {}
    if not pre.get("available") or not post.get("available"):
        return None
    pre_cost = _number(pre.get("stat_cost"))
    post_cost = _number(post.get("stat_cost"))
    pre_roi = pre.get("roi_1day")
    post_roi = post.get("roi_1day")
    roi_improved = pre_roi is not None and post_roi is not None and _number(post_roi) >= _number(pre_roi)
    cost_reduced = post_cost < pre_cost
    if action in HIGH_RISK_ACTIONS:
        return cost_reduced or roi_improved
    if action in {"suggest_lower_budget", "suggest_lower_bid"}:
        return cost_reduced or roi_improved
    if action == "suggest_create_project":
        return post_cost > 0
    return None


def _backtest_summary(
    samples: list[dict[str, Any]],
    *,
    action: str,
    standard: dict[str, Any],
    second_stage: dict[str, Any],
) -> dict[str, Any]:
    outcomes = [_post_outcome_positive(sample, action=action) for sample in samples]
    evaluated = [value for value in outcomes if value is not None]
    positive = sum(1 for value in evaluated if value is True)
    evaluable_count = len(evaluated)
    min_backtest_samples = int(second_stage.get("min_backtest_samples") or 0)
    min_positive_rate = _number(second_stage.get("min_backtest_positive_rate"), 0.5)
    max_false_positive_rate = _number(standard.get("max_false_positive_rate"), 0.2)
    positive_rate = positive / evaluable_count if evaluable_count else None
    false_positive_rate = (1 - positive_rate) if positive_rate is not None else None
    status = "insufficient_backtest_samples"
    reasons: list[str] = []
    if evaluable_count < min_backtest_samples:
        reasons.append(f"可回测样本 {evaluable_count} 条，低于最低 {min_backtest_samples} 条。")
    elif positive_rate is not None and positive_rate < min_positive_rate:
        status = "failed_positive_rate"
        reasons.append(f"正向复盘率 {_rounded(positive_rate)}，低于最低 {_rounded(min_positive_rate)}。")
    elif false_positive_rate is not None and false_positive_rate > max_false_positive_rate:
        status = "failed_false_positive_rate"
        reasons.append(f"估算误伤率 {_rounded(false_positive_rate)}，高于上限 {_rounded(max_false_positive_rate)}。")
    else:
        status = "passed"
    return {
        "status": status,
        "evaluable_sample_count": evaluable_count,
        "positive_outcome_count": positive,
        "positive_outcome_rate": _rounded(positive_rate) if positive_rate is not None else None,
        "estimated_false_positive_rate": _rounded(false_positive_rate) if false_positive_rate is not None else None,
        "min_backtest_samples": min_backtest_samples,
        "min_positive_outcome_rate": _rounded(min_positive_rate),
        "max_allowed_false_positive_rate": standard.get("max_false_positive_rate"),
        "blocking_reasons": reasons,
        "中文摘要": (
            f"二阶段回测：可回测 {evaluable_count} 条，正向 {positive} 条，"
            f"正向率 {(_rounded(positive_rate) if positive_rate is not None else '无')}。"
        ),
    }


def _metric_threshold(samples: list[dict[str, Any]], key: str, percentile_key: str, default: float) -> float:
    distribution = _metric_distribution(samples, key)
    value = distribution.get(percentile_key) or distribution.get("median") or default
    return _rounded(max(_number(value, default), 0))


def _decrease_percent(samples: list[dict[str, Any]], default: float) -> float:
    values: list[float] = []
    for sample in samples:
        before, after = _parse_arrow_numbers(_text(sample.get("detail_excerpt")))
        if before and after is not None and before > 0 and after < before:
            values.append((before - after) / before * 100)
    if not values:
        return _rounded(default)
    median = _percentile(values, 0.5)
    return _rounded(max(_number(median, default), 1))


def _control_rule_preview(
    *,
    action: str,
    samples: list[dict[str, Any]],
    second_stage: dict[str, Any],
) -> dict[str, Any] | None:
    rule_id = PROJECT_RULE_BY_ACTION.get(action)
    if not rule_id:
        return None
    min_cost_floor = _number(second_stage.get("min_cost_floor"), 100)
    with_pre = [
        sample
        for sample in samples
        if isinstance(sample.get("pre_metrics"), dict) and (sample.get("pre_metrics") or {}).get("available")
    ]
    if not with_pre:
        return None
    if action == "suggest_lower_budget":
        parameters = {
            "min_cost": _rounded(max(_metric_threshold(with_pre, "stat_cost", "p25", min_cost_floor), min_cost_floor)),
            "min_conversions": _rounded(max(_metric_threshold(with_pre, "convert_cnt", "p25", 1), 1)),
            "max_roi_1day": _metric_threshold(with_pre, "roi_1day", "p75", 0.2),
            "budget_decrease_percent": _decrease_percent(
                with_pre,
                _number(second_stage.get("budget_decrease_percent_default"), 20),
            ),
        }
    elif action == "suggest_lower_bid":
        cpa_threshold = _metric_threshold(with_pre, "cpa", "p25", 300)
        parameters = {
            "min_cost": _rounded(max(_metric_threshold(with_pre, "stat_cost", "p25", min_cost_floor), min_cost_floor)),
            "min_conversions": _rounded(max(_metric_threshold(with_pre, "convert_cnt", "p25", 1), 1)),
            "max_cpa": _rounded(max(cpa_threshold, 1)),
            "bid_decrease_percent": _decrease_percent(
                with_pre,
                _number(second_stage.get("bid_decrease_percent_default"), 10),
            ),
        }
    elif action == "pause_project":
        parameters = {
            "min_cost": _rounded(max(_metric_threshold(with_pre, "stat_cost", "p25", min_cost_floor), min_cost_floor)),
            "min_conversions": _rounded(max(_metric_threshold(with_pre, "convert_cnt", "p25", 0), 0)),
            "max_roi_1day": _metric_threshold(with_pre, "roi_1day", "p75", 0.05),
        }
    else:
        return None
    return {
        "rule_id": rule_id,
        "enabled": False,
        "review_required": True,
        "parameters": parameters,
        "中文摘要": f"二阶段学习生成「{ACTION_CATALOG[action]['label']}」待复核规则；默认未启用，不能直接进入建议工作台。",
    }


def _apply_second_stage_learning(
    candidate: dict[str, Any],
    *,
    selected_samples: list[dict[str, Any]],
    standard: dict[str, Any],
    second_stage: dict[str, Any],
) -> dict[str, Any]:
    if not _bool(second_stage.get("enabled"), False):
        candidate["second_stage_learning"] = {
            "enabled": False,
            "status": "disabled",
            "中文摘要": "二阶段学习未启用；本次只输出一阶段候选统计。",
        }
        return candidate

    action = _text(candidate.get("action"))
    segments = _sample_segments(selected_samples)
    backtest = _backtest_summary(
        selected_samples,
        action=action,
        standard=standard,
        second_stage=second_stage,
    )
    second_stage_payload = {
        "enabled": True,
        "status": "candidate_requires_review",
        "sample_segments": segments,
        "backtest": backtest,
        "control_strategy_rule_preview": None,
        "中文摘要": "",
    }
    candidate.setdefault("blocking_reasons", [])

    if candidate["status"] == "insufficient_samples_readonly":
        second_stage_payload["status"] = "insufficient_samples_readonly"
        second_stage_payload["中文摘要"] = "样本未达到一阶段门槛，二阶段只记录分层和回测摘要。"
        candidate["second_stage_learning"] = second_stage_payload
        return candidate

    if action in HIGH_RISK_ACTIONS and int(segments["positive_conversion_count"]) > 0:
        reason = (
            f"高风险动作样本中有 {segments['positive_conversion_count']} 条操作前已有转化，"
            "不能自动推导为暂停/删除规则。"
        )
        candidate["status"] = "blocked_mixed_high_risk_samples"
        candidate["blocking_reasons"].append(reason)
        second_stage_payload["status"] = "blocked_mixed_high_risk_samples"
        second_stage_payload["中文摘要"] = "暂停/删除样本混有有转化项目，已阻断为人工建模复核。"
        candidate["second_stage_learning"] = second_stage_payload
        return candidate

    metric_rate = segments.get("metric_available_rate")
    min_metric_rate = _number(second_stage.get("min_metric_available_rate"), 0.5)
    if metric_rate is not None and _number(metric_rate) < min_metric_rate:
        reason = f"操作前指标可用率 {_rounded(metric_rate)}，低于最低 {_rounded(min_metric_rate)}。"
        candidate["blocking_reasons"].append(reason)
        second_stage_payload["status"] = "candidate_requires_review"
        second_stage_payload["中文摘要"] = "指标覆盖不足，只能保留为候选待复核。"
        candidate["second_stage_learning"] = second_stage_payload
        return candidate

    if action == "suggest_create_project":
        second_stage_payload["status"] = "candidate_requires_review"
        second_stage_payload["中文摘要"] = "创建项目建议需要继续学习账户容量、素材资格和批次节奏，本次不生成项目管理规则。"
        candidate["second_stage_learning"] = second_stage_payload
        return candidate

    if backtest["status"] != "passed":
        candidate["blocking_reasons"].extend(backtest["blocking_reasons"])
        second_stage_payload["status"] = "candidate_requires_review"
        second_stage_payload["中文摘要"] = "二阶段回测未通过，只保留为候选待复核。"
        candidate["second_stage_learning"] = second_stage_payload
        return candidate

    rule_preview = _control_rule_preview(action=action, samples=selected_samples, second_stage=second_stage)
    if rule_preview is None:
        second_stage_payload["status"] = "candidate_requires_review"
        second_stage_payload["中文摘要"] = "暂未找到可映射的项目管理规则，只保留为候选待复核。"
        candidate["second_stage_learning"] = second_stage_payload
        return candidate

    candidate["status"] = "candidate_passed_backtest"
    candidate["control_strategy_rule"] = rule_preview
    second_stage_payload["status"] = "candidate_passed_backtest"
    second_stage_payload["control_strategy_rule_preview"] = rule_preview
    second_stage_payload["中文摘要"] = "二阶段回测通过，已生成待人工复核的项目管理规则；默认未启用。"
    candidate["second_stage_learning"] = second_stage_payload
    return candidate


def _candidate_status(
    *,
    action: str,
    scope_type: str,
    total_count: int,
    product_count: int,
    standards: dict[str, dict[str, Any]],
) -> tuple[str, list[str]]:
    standard = standards.get(action, standards["read_only_diagnostic"])
    min_total = int(standard.get("min_total_samples") or 0)
    min_product = int(standard.get("min_product_samples") or 0)
    reasons: list[str] = []
    if total_count < min_total:
        reasons.append(f"跨产品样本 {total_count} 条，低于最低 {min_total} 条。")
    if scope_type == "product" and product_count < min_product:
        reasons.append(f"本产品样本 {product_count} 条，低于最低 {min_product} 条。")
    if reasons:
        return "insufficient_samples_readonly", reasons
    return "candidate_requires_review", []


def _candidate_summary(candidate: dict[str, Any]) -> str:
    scope = "跨产品" if candidate["scope"]["type"] == "cross_product" else f"产品 {candidate['scope'].get('product')}"
    counts = candidate["sample_counts"]
    status_value = _text(candidate.get("status"))
    if status_value == "candidate_passed_backtest":
        status = "二阶段回测通过，但仍需人工确认后才能启用"
    elif status_value == "candidate_requires_review":
        status = "样本数达到候选门槛，但仍需人工确认后才能启用"
    elif status_value == "blocked_mixed_high_risk_samples":
        status = "高风险样本混有有转化项目，已阻断为人工复核"
    else:
        status = "样本数不足，只能作为只读诊断"
    return (
        f"{scope}学习到「{candidate['action_label']}」候选规律："
        f"跨产品样本 {counts['total']} 条，本产品样本 {counts.get('product', 0)} 条；{status}。"
    )


def _build_candidate(
    *,
    action: str,
    scope: dict[str, Any],
    total_samples: list[dict[str, Any]],
    product_samples: list[dict[str, Any]],
    standards: dict[str, dict[str, Any]],
    target_date: str,
    start_date: str,
    end_date: str,
    second_stage: dict[str, Any],
) -> dict[str, Any]:
    scope_type = _text(scope.get("type")) or "cross_product"
    selected_samples = total_samples if scope_type == "cross_product" else product_samples
    status, blocking_reasons = _candidate_status(
        action=action,
        scope_type=scope_type,
        total_count=len(total_samples),
        product_count=len(product_samples),
        standards=standards,
    )
    standard = standards.get(action, standards["read_only_diagnostic"])
    candidate = {
        "strategy_id": f"{scope.get('id')}:{action}:{target_date}",
        "strategy_version": target_date,
        "status": status,
        "enabled": False,
        "action": action,
        "action_label": ACTION_CATALOG[action]["label"],
        "risk_level": ACTION_CATALOG[action]["risk_level"],
        "rule_family": ACTION_CATALOG[action]["rule_family"],
        "scope": scope,
        "sample_counts": {
            "total": len(total_samples),
            "product": len(product_samples),
            "with_pre_metrics": sum(
                1
                for sample in selected_samples
                if isinstance(sample.get("pre_metrics"), dict) and (sample.get("pre_metrics") or {}).get("available")
            ),
        },
        "sample_standards": {
            "min_total_samples": int(standard.get("min_total_samples") or 0),
            "min_product_samples": int(standard.get("min_product_samples") or 0),
            "max_false_positive_rate": standard.get("max_false_positive_rate"),
        },
        "learned_conditions": _learned_conditions(selected_samples, action=action),
        "backtest": {
            "status": "pending_runtime_backtest",
            "note": "第一版策略学习先做样本门槛和可解释统计；进入主建议前仍需基于实时巡检快照回测误伤。",
            "max_allowed_false_positive_rate": standard.get("max_false_positive_rate"),
        },
        "runtime_contract": dict(RUNTIME_CONTRACT),
        "blocking_reasons": blocking_reasons,
        "evidence_samples": [
            {
                "sample_id": sample["sample_id"],
                "occurred_at": sample["occurred_at"],
                "product": sample["product"],
                "account_name": sample["account_name"],
                "advertiser_id": sample["advertiser_id"],
                "project_name": sample["project_name"],
                "project_id": sample["project_id"],
                "pre_metrics": sample["pre_metrics"],
                "中文摘要": sample["中文摘要"],
            }
            for sample in selected_samples[:5]
        ],
    }
    _apply_second_stage_learning(
        candidate,
        selected_samples=selected_samples,
        standard=standard,
        second_stage=second_stage,
    )
    candidate["中文摘要"] = _candidate_summary(candidate)
    return candidate


def _build_candidates(
    *,
    samples: list[dict[str, Any]],
    products: list[dict[str, Any]],
    standards: dict[str, dict[str, Any]],
    target_date: str,
    start_date: str,
    end_date: str,
    second_stage: dict[str, Any],
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for action in ACTION_CATALOG:
        total_samples = [sample for sample in samples if sample.get("standard_action") == action]
        if not total_samples:
            continue
        candidates.append(
            _build_candidate(
                action=action,
                scope={"type": "cross_product", "id": "cross-product", "product_key": "", "product": "跨产品"},
                total_samples=total_samples,
                product_samples=[],
                standards=standards,
                target_date=target_date,
                start_date=start_date,
                end_date=end_date,
                second_stage=second_stage,
            )
        )
        for product in products:
            product_key = _product_key(product)
            product_name = _product_name(product)
            product_samples = [
                sample for sample in total_samples if sample.get("product_key") == product_key or sample.get("product") == product_name
            ]
            if not product_samples:
                continue
            candidates.append(
                _build_candidate(
                    action=action,
                    scope={"type": "product", "id": product_key, "product_key": product_key, "product": product_name},
                    total_samples=total_samples,
                    product_samples=product_samples,
                    standards=standards,
                    target_date=target_date,
                    start_date=start_date,
                    end_date=end_date,
                    second_stage=second_stage,
                )
            )
    return candidates


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / f".{path.name}.tmp"
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _write_candidate_configs(
    *,
    output_dir: Path,
    candidates: list[dict[str, Any]],
    target_date: str,
) -> list[str]:
    paths: list[str] = []
    by_scope: dict[str, list[dict[str, Any]]] = {}
    for candidate in candidates:
        scope = candidate.get("scope") if isinstance(candidate.get("scope"), dict) else {}
        scope_id = _text(scope.get("product_key")) if _text(scope.get("type")) == "product" else "cross-product"
        by_scope.setdefault(scope_id, []).append(candidate)

    for scope_id, rows in sorted(by_scope.items()):
        path = output_dir / f"{scope_id}.learned.local.json"
        status_counts: dict[str, int] = {}
        action_counts: dict[str, int] = {}
        for row in rows:
            status = _text(row.get("status"))
            action = _text(row.get("action"))
            status_counts[status] = status_counts.get(status, 0) + 1
            action_counts[action] = action_counts.get(action, 0) + 1
        payload = {
            "workflow": WORKFLOW,
            "strategy_version": target_date,
            "generated_from": "historical_operation_logs_and_metrics",
            "enabled": False,
            "runtime_contract": dict(RUNTIME_CONTRACT),
            "summary": {
                "strategy_version": target_date,
                "strategy_count": len(rows),
                "enabled_strategy_count": sum(1 for row in rows if bool(row.get("enabled", False))),
                "candidate_passed_backtest_count": status_counts.get("candidate_passed_backtest", 0),
                "candidate_requires_review_count": status_counts.get("candidate_requires_review", 0),
                "insufficient_samples_readonly_count": status_counts.get("insufficient_samples_readonly", 0),
                "blocked_mixed_high_risk_samples_count": status_counts.get("blocked_mixed_high_risk_samples", 0),
                "action_counts": action_counts,
                "中文摘要": f"{scope_id} 本次生成 {len(rows)} 条候选策略，默认未启用。",
            },
            "中文摘要": f"{scope_id} 候选策略由策略学习脚本生成，默认未启用；人工确认前不能进入项目管理建议。",
            "strategies": rows,
        }
        _atomic_write_json(path, payload)
        paths.append(str(path))
    return paths


def build_strategy_learning_artifact(
    *,
    db_path: str | Path,
    policy: dict[str, Any],
) -> dict[str, Any]:
    target_date, start_date, end_date = _date_range(policy)
    products_dir = Path(policy.get("products_dir") or "configs/products")
    product_keys = [_text(item) for item in policy.get("product_keys") or [] if _text(item)]
    products = _load_products(products_dir, product_keys)
    products_by_name = {_product_name(product): product for product in products if _product_name(product)}
    product_names = set(products_by_name)
    metric_lookback_days = max(int(_number(policy.get("metric_lookback_days"), 3)), 1)
    post_days = max(int(_number(policy.get("post_days"), 1)), 1)
    standards = _sample_standards(policy)
    second_stage = _second_stage_learning_config(policy)

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        operation_rows = _operation_rows(conn, start_date=start_date, end_date=end_date, product_names=product_names)
        samples, skipped = _build_samples(
            conn,
            rows=operation_rows,
            products_by_name=products_by_name,
            metric_lookback_days=metric_lookback_days,
            post_days=post_days,
        )

    candidates = _build_candidates(
        samples=samples,
        products=products,
        standards=standards,
        target_date=target_date,
        start_date=start_date,
        end_date=end_date,
        second_stage=second_stage,
    )
    action_counts: dict[str, int] = {}
    for sample in samples:
        action = _text(sample.get("standard_action"))
        action_counts[action] = action_counts.get(action, 0) + 1
    status_counts: dict[str, int] = {}
    for candidate in candidates:
        status = _text(candidate.get("status"))
        status_counts[status] = status_counts.get(status, 0) + 1

    summary = {
        "target_date": target_date,
        "window": {"start_date": start_date, "end_date": end_date},
        "product_count": len(products),
        "operation_log_count": len(operation_rows),
        "learning_sample_count": len(samples),
        "skipped_operation_count": len(skipped),
        "candidate_strategy_count": len(candidates),
        "candidate_requires_review_count": status_counts.get("candidate_requires_review", 0),
        "insufficient_samples_readonly_count": status_counts.get("insufficient_samples_readonly", 0),
        "candidate_passed_backtest_count": status_counts.get("candidate_passed_backtest", 0),
        "blocked_mixed_high_risk_samples_count": status_counts.get("blocked_mixed_high_risk_samples", 0),
        "action_counts": action_counts,
        "second_stage_learning_enabled": _bool(second_stage.get("enabled"), False),
        "runtime_metric_source": RUNTIME_CONTRACT["runtime_metric_source"],
        "allow_builtin_default_project_actions": False,
        "中文摘要": (
            f"策略学习完成：窗口 {start_date} 至 {end_date}，"
            f"读取 {len(operation_rows)} 条操作日志，形成 {len(samples)} 条学习样本，"
            f"生成 {len(candidates)} 条候选策略；候选策略默认未启用，建议运行时仍以实时巡检快照为准。"
        ),
    }
    return {
        "ok": True,
        "workflow": WORKFLOW,
        "phase": "readonly_learning",
        "execution_enabled": False,
        "external_api_calls": 0,
        "summary": summary,
        "runtime_contract": dict(RUNTIME_CONTRACT),
        "sample_standards": standards,
        "second_stage_learning": second_stage,
        "samples": samples,
        "skipped_operations": skipped[:100],
        "candidate_strategies": candidates,
        "guardrails": GUARDRAILS,
        "message": summary["中文摘要"],
    }


def run_strategy_learning_request(
    request: dict[str, Any],
    *,
    db_path: str | Path,
    runs_dir: str | Path,
) -> dict[str, Any]:
    policy = _strategy_learning_config(request)
    artifact_payload = build_strategy_learning_artifact(db_path=db_path, policy=policy)
    generated_configs: list[str] = []
    if _bool(policy.get("write_candidate_configs"), False):
        output_dir = Path(policy.get("output_strategy_dir") or "configs/learned-strategies")
        generated_configs = _write_candidate_configs(
            output_dir=output_dir,
            candidates=artifact_payload["candidate_strategies"],
            target_date=artifact_payload["summary"]["target_date"],
        )
        artifact_payload["generated_strategy_config_paths"] = generated_configs
    artifact = write_snapshot_artifact(runs_dir, WORKFLOW, artifact_payload)
    artifact_payload["artifact_path"] = str(artifact)
    return {
        "ok": True,
        "workflow": WORKFLOW,
        "phase": "readonly_learning",
        "execution_enabled": False,
        "external_api_calls": 0,
        "summary": artifact_payload["summary"],
        "artifact": json.loads(json.dumps(artifact_payload, ensure_ascii=False)),
        "artifact_path": str(artifact),
        "generated_strategy_config_paths": generated_configs,
    }
