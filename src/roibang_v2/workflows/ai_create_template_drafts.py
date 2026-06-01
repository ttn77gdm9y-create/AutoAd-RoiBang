from __future__ import annotations

import json
import sqlite3
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from roibang_v2.runs import write_run_artifact


def _cfg(request: dict[str, Any]) -> dict[str, Any]:
    value = request.get("ai_create_template_drafts")
    return dict(value) if isinstance(value, dict) else dict(request)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _float(value: Any, default: float = 0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _manual_modes(mode_dir: str | Path) -> list[dict[str, Any]]:
    path = Path(mode_dir)
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for item in sorted(path.glob("*.json")):
        mode = _load_json(item)
        if not mode:
            continue
        rows.append(
            {
                "path": str(item),
                "mode_key": _text(mode.get("mode_key") or item.stem.replace(".example", "")),
                "display_name": _text(mode.get("display_name")),
                "template_key": _text(mode.get("template_key")),
                "template_name_suffix": _text(mode.get("template_name_suffix")),
                "defaults": mode.get("defaults") if isinstance(mode.get("defaults"), dict) else {},
                "material_requirements": mode.get("material_requirements")
                if isinstance(mode.get("material_requirements"), dict)
                else {},
                "material_selection": mode.get("material_selection")
                if isinstance(mode.get("material_selection"), dict)
                else {},
            }
        )
    return rows


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ? LIMIT 1",
        (table,),
    ).fetchone()
    return row is not None


def _latest_period(conn: sqlite3.Connection, *, product: str, source_advertiser_id: str, window_key: str) -> dict[str, str]:
    row = conn.execute(
        """
        SELECT period_start, period_end
        FROM product_source_material_metric_rollups
        WHERE product = ?
          AND source_advertiser_id = ?
          AND window_key = ?
        ORDER BY period_end DESC, period_start DESC
        LIMIT 1
        """,
        (product, source_advertiser_id, window_key),
    ).fetchone()
    if not row:
        return {"period_start": "", "period_end": ""}
    return {"period_start": str(row[0] or ""), "period_end": str(row[1] or "")}


def _pool_stats(
    conn: sqlite3.Connection,
    *,
    product: str,
    source_advertiser_id: str,
    window_key: str,
    where_sql: str = "",
    params: list[Any] | None = None,
) -> dict[str, Any]:
    period = _latest_period(conn, product=product, source_advertiser_id=source_advertiser_id, window_key=window_key)
    if not period["period_end"]:
        return {
            "window_key": window_key,
            "period_start": "",
            "period_end": "",
            "candidate_count": 0,
            "stat_cost": 0.0,
            "convert_cnt": 0.0,
            "active_register": 0.0,
            "avg_roi_1day": 0.0,
            "top_materials": [],
        }
    extra = f" AND {where_sql}" if where_sql else ""
    query_params = [
        product,
        source_advertiser_id,
        window_key,
        period["period_start"],
        period["period_end"],
        *(params or []),
    ]
    summary = conn.execute(
        f"""
        SELECT
          COUNT(*) AS candidate_count,
          COALESCE(SUM(stat_cost), 0) AS stat_cost,
          COALESCE(SUM(convert_cnt), 0) AS convert_cnt,
          COALESCE(SUM(active_register), 0) AS active_register,
          COALESCE(AVG(NULLIF(roi_1day_cost_weighted, 0)), 0) AS avg_roi_1day
        FROM product_source_material_metric_rollups
        WHERE product = ?
          AND source_advertiser_id = ?
          AND window_key = ?
          AND period_start = ?
          AND period_end = ?
          AND material_type = 'video'
          AND COALESCE(source_video_id, '') <> ''
          {extra}
        """,
        tuple(query_params),
    ).fetchone()
    top_rows = conn.execute(
        f"""
        SELECT material_id, source_video_id, name, stat_cost, convert_cnt, active_register,
               roi_1day_cost_weighted, effective_create_date, create_time
        FROM product_source_material_metric_rollups
        WHERE product = ?
          AND source_advertiser_id = ?
          AND window_key = ?
          AND period_start = ?
          AND period_end = ?
          AND material_type = 'video'
          AND COALESCE(source_video_id, '') <> ''
          {extra}
        ORDER BY stat_cost DESC, material_id ASC
        LIMIT 10
        """,
        tuple(query_params),
    ).fetchall()
    return {
        "window_key": window_key,
        "period_start": period["period_start"],
        "period_end": period["period_end"],
        "candidate_count": int(summary[0] or 0) if summary else 0,
        "stat_cost": round(float(summary[1] or 0), 4) if summary else 0.0,
        "convert_cnt": round(float(summary[2] or 0), 4) if summary else 0.0,
        "active_register": round(float(summary[3] or 0), 4) if summary else 0.0,
        "avg_roi_1day": round(float(summary[4] or 0), 4) if summary else 0.0,
        "top_materials": [
            {
                "material_id": str(row[0] or ""),
                "source_video_id": str(row[1] or ""),
                "name": str(row[2] or ""),
                "stat_cost": round(float(row[3] or 0), 4),
                "convert_cnt": round(float(row[4] or 0), 4),
                "active_register": round(float(row[5] or 0), 4),
                "roi_1day_cost_weighted": round(float(row[6] or 0), 4),
                "effective_create_date": str(row[7] or ""),
                "create_time": str(row[8] or ""),
            }
            for row in top_rows
        ],
    }


def _material_pool_evidence(conn: sqlite3.Connection, *, product: str, source_advertiser_id: str) -> dict[str, Any]:
    recent_scale = _pool_stats(
        conn,
        product=product,
        source_advertiser_id=source_advertiser_id,
        window_key="last_7d",
        where_sql="stat_cost >= ?",
        params=[200],
    )
    history_scale = _pool_stats(
        conn,
        product=product,
        source_advertiser_id=source_advertiser_id,
        window_key="last_30d",
        where_sql="stat_cost >= ?",
        params=[1000],
    )
    test_new_end = recent_scale.get("period_end") or ""
    if test_new_end:
        min_effective_date = (date.fromisoformat(str(test_new_end)) - timedelta(days=6)).isoformat()
    else:
        min_effective_date = ""
    test_new = _pool_stats(
        conn,
        product=product,
        source_advertiser_id=source_advertiser_id,
        window_key="last_7d",
        where_sql="COALESCE(effective_create_date, create_time, '') >= ?",
        params=[min_effective_date],
    )
    low_conversion_retest = _pool_stats(
        conn,
        product=product,
        source_advertiser_id=source_advertiser_id,
        window_key="last_30d",
        where_sql="convert_cnt BETWEEN ? AND ?",
        params=[1, 5],
    )
    no_conversion_retest = _pool_stats(
        conn,
        product=product,
        source_advertiser_id=source_advertiser_id,
        window_key="last_30d",
        where_sql="convert_cnt = 0 AND stat_cost <= ? AND COALESCE(effective_create_date, create_time, '') <= ?",
        params=[500, (date.fromisoformat(test_new_end) - timedelta(days=7)).isoformat() if test_new_end else ""],
    )
    return {
        "recent_scale": recent_scale,
        "history_scale": history_scale,
        "test_new": {**test_new, "min_effective_create_date": min_effective_date},
        "low_conversion_retest": low_conversion_retest,
        "no_conversion_retest": no_conversion_retest,
    }


def _manual_mode_index(modes: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(row.get("mode_key") or ""): row for row in modes if str(row.get("mode_key") or "")}


def _draft_mode(
    *,
    draft_key: str,
    draft_name: str,
    product: str,
    base_mode: dict[str, Any],
    draft_type: str,
    material_selection: dict[str, Any],
    material_requirements: dict[str, Any],
    evidence: dict[str, Any],
    differences: list[str],
    risk_notes: list[str],
) -> dict[str, Any]:
    defaults = dict(base_mode.get("defaults") if isinstance(base_mode.get("defaults"), dict) else {})
    return {
        "draft_key": draft_key,
        "draft_name": draft_name,
        "draft_source": "ai_create_template_drafts",
        "draft_type": draft_type,
        "status": "draft_only",
        "human_review_required": True,
        "base_manual_mode_key": str(base_mode.get("mode_key") or ""),
        "base_family": str(base_mode.get("template_key") or ""),
        "proposed_create_mode": {
            "mode_key": draft_key,
            "display_name": draft_name,
            "product": product,
            "platform": "WECHAT_GAME",
            "template_key": str(base_mode.get("template_key") or ""),
            "template_name_suffix": f"AI{draft_name}",
            "defaults": defaults,
            "material_requirements": material_requirements,
            "material_selection": material_selection,
            "initial_status": {"project_operation": "ENABLE", "unit_operation": "ENABLE"},
            "fixed_cover": {"mode": "template_fixed"},
        },
        "evidence": evidence,
        "differences_from_manual_template": differences,
        "risk_notes": risk_notes,
        "usage_blocking_reasons": [
            "draft_not_approved",
            "not_in_manual_create_modes",
            "cannot_be_used_by_run_create_mode_directly",
        ],
    }


def _build_drafts(
    *,
    product: str,
    manual_modes: list[dict[str, Any]],
    pools: dict[str, Any],
    max_drafts: int,
) -> list[dict[str, Any]]:
    modes = _manual_mode_index(manual_modes)
    drafts: list[dict[str, Any]] = []
    recent_base = modes.get("wx_pay_general_recent_scale") or modes.get("wx_pay_male_recent_scale") or {}
    history_base = modes.get("wx_pay_general_scale") or modes.get("wx_pay_male_scale") or {}
    test_new_base = modes.get("wx_pay_general_test_new") or modes.get("wx_pay_male_test_new") or {}

    recent_pool = pools.get("recent_scale") if isinstance(pools.get("recent_scale"), dict) else {}
    history_pool = pools.get("history_scale") if isinstance(pools.get("history_scale"), dict) else {}
    test_new_pool = pools.get("test_new") if isinstance(pools.get("test_new"), dict) else {}
    low_pool = pools.get("low_conversion_retest") if isinstance(pools.get("low_conversion_retest"), dict) else {}
    no_pool = pools.get("no_conversion_retest") if isinstance(pools.get("no_conversion_retest"), dict) else {}

    if recent_base and int(recent_pool.get("candidate_count") or 0) >= 30:
        base_selection = dict(recent_base.get("material_selection") if isinstance(recent_base.get("material_selection"), dict) else {})
        base_requirements = dict(recent_base.get("material_requirements") if isinstance(recent_base.get("material_requirements"), dict) else {})
        drafts.append(
            _draft_mode(
                draft_key="ai_wx_pay_general_recent_scale_cost500_v1",
                draft_name="AI 每付通投近期放量 消耗500草稿",
                product=product,
                base_mode=recent_base,
                draft_type="scale",
                material_selection={**base_selection, "min_stat_cost": 500, "lookback_days": 7, "selection_type": "high_spend"},
                material_requirements=base_requirements,
                evidence=recent_pool,
                differences=["min_stat_cost（最低消耗）从人工近期放量的 200 提高到 500"],
                risk_notes=["候选素材会减少，适合源素材池近期消耗较充足时使用"],
            )
        )

    if history_base and int(history_pool.get("candidate_count") or 0) >= 50:
        base_selection = dict(history_base.get("material_selection") if isinstance(history_base.get("material_selection"), dict) else {})
        base_requirements = dict(history_base.get("material_requirements") if isinstance(history_base.get("material_requirements"), dict) else {})
        drafts.append(
            _draft_mode(
                draft_key="ai_wx_pay_general_history_scale_30d_stable_v1",
                draft_name="AI 每付通投历史放量 稳定池草稿",
                product=product,
                base_mode=history_base,
                draft_type="scale",
                material_selection={**base_selection, "lookback_days": 30, "min_stat_cost": 1000, "selection_type": "high_spend"},
                material_requirements=base_requirements,
                evidence=history_pool,
                differences=["保持人工历史放量核心参数，但明确作为稳定素材池草稿"],
                risk_notes=["历史高消耗素材可能偏老，需要结合近期衰减情况人工判断"],
            )
        )

    if test_new_base and int(test_new_pool.get("candidate_count") or 0) >= 20:
        base_selection = dict(test_new_base.get("material_selection") if isinstance(test_new_base.get("material_selection"), dict) else {})
        base_requirements = dict(test_new_base.get("material_requirements") if isinstance(test_new_base.get("material_requirements"), dict) else {})
        drafts.append(
            _draft_mode(
                draft_key="ai_wx_pay_general_test_new_recent_first_seen_v1",
                draft_name="AI 每付通投测新 近7天新素材草稿",
                product=product,
                base_mode=test_new_base,
                draft_type="test_new",
                material_selection={
                    **base_selection,
                    "lookback_days": 7,
                    "first_seen_days": 7,
                    "sort_by": "effective_create_date_desc",
                    "candidate_pool_limit": 200,
                },
                material_requirements=base_requirements,
                evidence=test_new_pool,
                differences=["强化 effective_create_date（有效创建日期）近 7 天，避免老素材进入测新池"],
                risk_notes=["新素材数量不足时容易复用，需要人工看候选池数量"],
            )
        )

    if test_new_base and int(low_pool.get("candidate_count") or 0) >= 20:
        base_requirements = dict(test_new_base.get("material_requirements") if isinstance(test_new_base.get("material_requirements"), dict) else {})
        drafts.append(
            _draft_mode(
                draft_key="ai_wx_pay_general_low_conversion_retest_v1",
                draft_name="AI 每付通投低转化复测草稿",
                product=product,
                base_mode=test_new_base,
                draft_type="retest_low_conversion",
                material_selection={
                    "source_scope": "source_material_account",
                    "lookback_days": 30,
                    "selection_type": "low_conversion_retest",
                    "min_convert_cnt": 1,
                    "max_convert_cnt": 5,
                    "sort_by": "effective_create_date_desc",
                    "random_shuffle": True,
                },
                material_requirements=base_requirements,
                evidence=low_pool,
                differences=["从测新逻辑转为低转化素材复测，筛选 convert_cnt（转化数）1-5"],
                risk_notes=["低转化不代表高潜力，需要结合素材质量和账户状态人工判断"],
            )
        )

    if test_new_base and int(no_pool.get("candidate_count") or 0) >= 20:
        base_requirements = dict(test_new_base.get("material_requirements") if isinstance(test_new_base.get("material_requirements"), dict) else {})
        drafts.append(
            _draft_mode(
                draft_key="ai_wx_pay_general_no_conversion_retest_v1",
                draft_name="AI 每付通投无转化复测草稿",
                product=product,
                base_mode=test_new_base,
                draft_type="retest_no_conversion",
                material_selection={
                    "source_scope": "source_material_account",
                    "lookback_days": 30,
                    "selection_type": "no_conversion_retest",
                    "convert_cnt": 0,
                    "max_stat_cost": 500,
                    "min_create_age_days": 7,
                    "sort_by": "effective_create_date_desc",
                    "random_shuffle": True,
                },
                material_requirements=base_requirements,
                evidence=no_pool,
                differences=["从测新逻辑转为无转化复测，筛选 30 天内无转化且消耗不超过 500 的素材"],
                risk_notes=["无转化素材风险较高，应限制批量规模并观察首日数据"],
            )
        )
    return drafts[: max(max_drafts, 0)]


def run_ai_create_template_drafts_request(
    request: dict[str, Any],
    *,
    db_path: str | Path,
    runs_dir: str | Path,
) -> dict[str, Any]:
    cfg = _cfg(request)
    product = _text(cfg.get("product") or "勇者突进")
    source_advertiser_id = _text(cfg.get("source_advertiser_id"))
    mode_dir = _text(cfg.get("manual_mode_dir") or "configs/create-modes")
    max_drafts = _int(cfg.get("max_drafts"), 3)
    blocking_reasons: list[str] = []
    if not source_advertiser_id:
        blocking_reasons.append("missing source_advertiser_id")
    manual_modes = _manual_modes(mode_dir)
    if not manual_modes:
        blocking_reasons.append("manual create mode catalog is empty")

    pools: dict[str, Any] = {}
    if not blocking_reasons:
        with sqlite3.connect(db_path) as conn:
            if not _table_exists(conn, "product_source_material_metric_rollups"):
                blocking_reasons.append("missing product_source_material_metric_rollups table")
            else:
                pools = _material_pool_evidence(conn, product=product, source_advertiser_id=source_advertiser_id)
    drafts = [] if blocking_reasons else _build_drafts(product=product, manual_modes=manual_modes, pools=pools, max_drafts=max_drafts)
    status = "blocked" if blocking_reasons else ("drafted" if drafts else "no_drafts")
    payload = {
        "ok": not blocking_reasons,
        "workflow": "ai_create_template_drafts",
        "phase": "analysis",
        "execution_enabled": False,
        "external_api_calls": 0,
        "status": status,
        "blocking_reasons": blocking_reasons,
        "summary": {
            "product": product,
            "source_advertiser_id": source_advertiser_id,
            "manual_mode_dir": mode_dir,
            "manual_template_count": len(manual_modes),
            "draft_count": len(drafts),
            "max_drafts": max_drafts,
        },
        "manual_template_boundary": {
            "status": "separate",
            "writes_manual_template": False,
            "generates_create_plan": False,
            "can_execute_business_action": False,
            "requires_human_promotion": True,
            "read_only_manual_mode_dir": mode_dir,
            "forbidden_write_paths": ["configs/create-modes", "configs/create-mode-requests"],
            "draft_output_only": "data/runs/ai_create_template_drafts",
        },
        "evidence": {
            "manual_modes": manual_modes,
            "material_pools": pools,
        },
        "drafts": drafts,
        "actions": [],
    }
    artifact = write_run_artifact(runs_dir, "ai_create_template_drafts", payload)
    return {**payload, "artifact_path": str(artifact)}
