from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from roibang_v2.runs import write_run_artifact


def _config(request: dict[str, Any]) -> dict[str, Any]:
    value = request.get("material_profile_coverage")
    return dict(value) if isinstance(value, dict) else dict(request)


def _date_filter_sql(cfg: dict[str, Any]) -> tuple[str, list[Any]]:
    value = cfg.get("date_range") if isinstance(cfg.get("date_range"), dict) else {}
    start = str(value.get("start") or "").strip()
    end = str(value.get("end") or "").strip()
    if not start and not end:
        return "", []
    if not start or not end:
        raise ValueError("material_profile_coverage.date_range requires both start and end")
    return " AND metric_date BETWEEN ? AND ? ", [start, end]


def _source_account_ids(cfg: dict[str, Any]) -> set[str]:
    rows = cfg.get("source_accounts")
    if not isinstance(rows, list):
        return set()
    ids: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        value = str(row.get("source_advertiser_id") or row.get("advertiser_id") or "").strip()
        if value:
            ids.add(value)
    return ids


def _coverage_sql(date_sql: str) -> str:
    return f"""
    WITH history AS (
      SELECT
        material_id,
        ROUND(COALESCE(SUM(stat_cost), 0), 4) AS stat_cost,
        COUNT(DISTINCT advertiser_id) AS account_count,
        MIN(metric_date) AS first_seen_date,
        MAX(metric_date) AS last_seen_date
      FROM material_daily_metrics
      WHERE TRIM(material_id) != ''
        {date_sql}
      GROUP BY material_id
    )
    SELECT
      h.material_id,
      h.stat_cost,
      h.account_count,
      h.first_seen_date,
      h.last_seen_date,
      CASE WHEN mp.material_id IS NULL THEN 0 ELSE 1 END AS has_profile,
      COALESCE(mp.source_advertiser_id, '') AS source_advertiser_id
    FROM history h
    LEFT JOIN material_profiles mp
      ON mp.material_id = h.material_id
    ORDER BY h.stat_cost DESC, h.material_id
    """


def _top_missing_accounts_sql(date_sql: str) -> str:
    return f"""
    WITH missing AS (
      SELECT
        mdm.advertiser_id,
        mdm.material_id,
        ROUND(COALESCE(SUM(mdm.stat_cost), 0), 4) AS stat_cost
      FROM material_daily_metrics mdm
      LEFT JOIN material_profiles mp
        ON mp.material_id = mdm.material_id
      WHERE TRIM(mdm.material_id) != ''
        AND TRIM(mdm.advertiser_id) != ''
        AND mp.material_id IS NULL
        {date_sql}
      GROUP BY mdm.advertiser_id, mdm.material_id
    )
    SELECT
      advertiser_id,
      COUNT(DISTINCT material_id) AS missing_material_count,
      ROUND(COALESCE(SUM(stat_cost), 0), 4) AS missing_stat_cost
    FROM missing
    GROUP BY advertiser_id
    ORDER BY missing_stat_cost DESC, missing_material_count DESC, advertiser_id
    """


def build_material_profile_coverage_report(
    request: dict[str, Any],
    *,
    db_path: str | Path,
) -> dict[str, Any]:
    cfg = _config(request)
    date_sql, params = _date_filter_sql(cfg)
    source_account_ids = _source_account_ids(cfg)
    top_missing_limit = int(cfg.get("top_missing_limit") or 50)
    if top_missing_limit < 0:
        raise ValueError("material_profile_coverage.top_missing_limit must be non-negative")

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(_coverage_sql(date_sql), tuple(params)).fetchall()
        account_rows = conn.execute(_top_missing_accounts_sql(date_sql), tuple(params)).fetchall()

    history_material_count = len(rows)
    profiled_material_count = sum(1 for row in rows if int(row[5] or 0) == 1)
    missing_rows = [row for row in rows if int(row[5] or 0) == 0]
    source_profiled_material_count = (
        sum(1 for row in rows if str(row[6] or "") in source_account_ids) if source_account_ids else 0
    )
    history_stat_cost = round(sum(float(row[1] or 0) for row in rows), 4)
    missing_stat_cost = round(sum(float(row[1] or 0) for row in missing_rows), 4)
    coverage_rate = round(profiled_material_count / history_material_count, 4) if history_material_count else 0.0
    source_coverage_rate = (
        round(source_profiled_material_count / history_material_count, 4) if history_material_count else 0.0
    )
    missing_cost_rate = round(missing_stat_cost / history_stat_cost, 4) if history_stat_cost else 0.0

    top_missing_materials = [
        {
            "material_id": str(row[0]),
            "stat_cost": float(row[1] or 0),
            "account_count": int(row[2] or 0),
            "first_seen_date": str(row[3] or ""),
            "last_seen_date": str(row[4] or ""),
        }
        for row in missing_rows[:top_missing_limit]
    ]
    top_missing_accounts = [
        {
            "advertiser_id": str(row[0]),
            "missing_material_count": int(row[1] or 0),
            "missing_stat_cost": float(row[2] or 0),
        }
        for row in account_rows[:top_missing_limit]
    ]
    return {
        "ok": True,
        "workflow": "material_profile_coverage",
        "phase": "phase1",
        "execution_enabled": False,
        "external_api_calls": 0,
        "summary": {
            "history_material_count": history_material_count,
            "profiled_material_count": profiled_material_count,
            "missing_profile_count": len(missing_rows),
            "coverage_rate": coverage_rate,
            "source_profiled_material_count": source_profiled_material_count,
            "source_coverage_rate": source_coverage_rate,
            "history_stat_cost": history_stat_cost,
            "missing_stat_cost": missing_stat_cost,
            "missing_cost_rate": missing_cost_rate,
        },
        "top_missing_materials": top_missing_materials,
        "top_missing_accounts": top_missing_accounts,
    }


def run_material_profile_coverage_request(
    request: dict[str, Any],
    *,
    db_path: str | Path,
    runs_dir: str | Path,
) -> dict[str, Any]:
    payload = build_material_profile_coverage_report(request, db_path=db_path)
    artifact_path = write_run_artifact(runs_dir, "material_profile_coverage", payload)
    return {**payload, "artifact_path": str(artifact_path)}
