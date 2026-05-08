from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from roibang_v2.runs import write_run_artifact
from roibang_v2.workflows.material_history_backfill import _date_range


def _config(request: dict[str, Any]) -> dict[str, Any]:
    value = request.get("material_quality_rollup")
    return dict(value) if isinstance(value, dict) else dict(request)


def _date_range_config(cfg: dict[str, Any]) -> dict[str, str]:
    value = cfg.get("date_range") if isinstance(cfg.get("date_range"), dict) else {}
    start = str(value.get("start") or "").strip()
    end = str(value.get("end") or "").strip()
    if not start or not end:
        raise ValueError("material_quality_rollup requires date_range.start and date_range.end")
    return {"start": start, "end": end}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _platform(cfg: dict[str, Any]) -> str:
    return str(cfg.get("platform") or "").strip()


def _product(cfg: dict[str, Any]) -> str:
    return str(cfg.get("product") or "").strip()


def _windows(cfg: dict[str, Any]) -> list[int | str]:
    values = cfg.get("windows")
    if not isinstance(values, list) or not values:
        return [1, 3, 7, 15, 30, "all"]
    windows: list[int | str] = []
    for value in values:
        if str(value).strip() == "all":
            windows.append("all")
            continue
        days = int(value)
        if days < 1:
            raise ValueError("material_quality_rollup.windows values must be positive")
        windows.append(days)
    return windows


def _state_by_date(
    *,
    conn: sqlite3.Connection,
    dates: list[str],
    product: str,
    platform: str,
) -> dict[str, dict[str, Any]]:
    if not dates:
        return {}
    placeholders = ",".join("?" for _ in dates)
    rows = conn.execute(
        f"""
        SELECT sync_date, status, material_row_count, account_count, artifact_path, error_message
        FROM material_sync_state
        WHERE workflow = ?
          AND product = ?
          AND platform = ?
          AND sync_date IN ({placeholders})
        ORDER BY sync_date
        """,
        tuple(["material_history_backfill", product, platform, *dates]),
    ).fetchall()
    return {
        str(sync_date): {
            "status": str(status),
            "material_row_count": int(material_row_count or 0),
            "account_count": int(account_count or 0),
            "artifact_path": str(artifact_path or ""),
            "error_message": str(error_message or ""),
        }
        for sync_date, status, material_row_count, account_count, artifact_path, error_message in rows
    }


def _metric_stats_by_date(
    *,
    conn: sqlite3.Connection,
    dates: list[str],
) -> dict[str, dict[str, Any]]:
    if not dates:
        return {}
    placeholders = ",".join("?" for _ in dates)
    rows = conn.execute(
        f"""
        SELECT
          metric_date,
          COUNT(*) AS row_count,
          COUNT(DISTINCT advertiser_id) AS account_count,
          COUNT(DISTINCT material_id) AS material_count,
          ROUND(COALESCE(SUM(stat_cost), 0), 4) AS stat_cost,
          SUM(CASE WHEN TRIM(advertiser_id) = '' OR TRIM(material_id) = '' THEN 1 ELSE 0 END) AS invalid_key_count,
          SUM(CASE WHEN stat_cost < 0 THEN 1 ELSE 0 END) AS negative_cost_count
        FROM material_daily_metrics
        WHERE metric_date IN ({placeholders})
        GROUP BY metric_date
        ORDER BY metric_date
        """,
        tuple(dates),
    ).fetchall()
    return {
        str(metric_date): {
            "row_count": int(row_count or 0),
            "account_count": int(account_count or 0),
            "material_count": int(material_count or 0),
            "stat_cost": float(stat_cost or 0),
            "invalid_key_count": int(invalid_key_count or 0),
            "negative_cost_count": int(negative_cost_count or 0),
        }
        for metric_date, row_count, account_count, material_count, stat_cost, invalid_key_count, negative_cost_count in rows
    }


def build_material_quality_report(
    request: dict[str, Any],
    *,
    db_path: str | Path,
) -> dict[str, Any]:
    cfg = _config(request)
    product = _product(cfg)
    platform = _platform(cfg)
    date_range = _date_range_config(cfg)
    dates = _date_range(date_range["start"], date_range["end"])

    with sqlite3.connect(db_path) as conn:
        state = _state_by_date(conn=conn, dates=dates, product=product, platform=platform)
        metric_stats = _metric_stats_by_date(conn=conn, dates=dates)

    completed_dates = [target_date for target_date in dates if state.get(target_date, {}).get("status") == "completed"]
    failed_dates = [target_date for target_date in dates if state.get(target_date, {}).get("status") == "failed"]
    missing_dates = [target_date for target_date in dates if target_date not in state]
    state_metric_row_mismatches: list[dict[str, Any]] = []
    metric_dates_without_completed_state: list[str] = []
    invalid_metric_dates: list[dict[str, Any]] = []

    for target_date in dates:
        metrics = metric_stats.get(target_date)
        state_row = state.get(target_date)
        if metrics and (not state_row or state_row.get("status") != "completed"):
            metric_dates_without_completed_state.append(target_date)
        if metrics and state_row and state_row.get("status") == "completed":
            expected_rows = int(state_row.get("material_row_count") or 0)
            actual_rows = int(metrics.get("row_count") or 0)
            if expected_rows != actual_rows:
                state_metric_row_mismatches.append(
                    {
                        "date": target_date,
                        "state_material_row_count": expected_rows,
                        "metric_row_count": actual_rows,
                    }
                )
        if metrics and (int(metrics["invalid_key_count"]) > 0 or int(metrics["negative_cost_count"]) > 0):
            invalid_metric_dates.append(
                {
                    "date": target_date,
                    "invalid_key_count": int(metrics["invalid_key_count"]),
                    "negative_cost_count": int(metrics["negative_cost_count"]),
                }
            )

    metric_row_count = sum(int(item["row_count"]) for item in metric_stats.values())
    metric_material_count = 0
    with sqlite3.connect(db_path) as conn:
        placeholders = ",".join("?" for _ in dates)
        if dates:
            metric_material_count = int(
                conn.execute(
                    f"""
                    SELECT COUNT(DISTINCT material_id)
                    FROM material_daily_metrics
                    WHERE metric_date IN ({placeholders})
                    """,
                    tuple(dates),
                ).fetchone()[0]
                or 0
            )

    ok = not (
        failed_dates
        or missing_dates
        or state_metric_row_mismatches
        or metric_dates_without_completed_state
        or invalid_metric_dates
    )
    return {
        "ok": ok,
        "workflow": "material_quality_report",
        "phase": "phase1",
        "execution_enabled": False,
        "external_api_calls": 0,
        "product": product,
        "platform": platform,
        "date_range": date_range,
        "summary": {
            "expected_date_count": len(dates),
            "completed_date_count": len(completed_dates),
            "failed_date_count": len(failed_dates),
            "missing_date_count": len(missing_dates),
            "metric_date_count": len(metric_stats),
            "metric_row_count": metric_row_count,
            "metric_material_count": metric_material_count,
        },
        "sync_quality": {
            "completed_dates": completed_dates,
            "failed_dates": failed_dates,
            "missing_dates": missing_dates,
        },
        "metric_quality": {
            "state_metric_row_mismatches": state_metric_row_mismatches,
            "metric_dates_without_completed_state": metric_dates_without_completed_state,
            "invalid_metric_dates": invalid_metric_dates,
            "metric_stats_by_date": metric_stats,
        },
    }


def _window_period(*, start: str, end: str, window: int | str) -> dict[str, Any]:
    if window == "all":
        return {
            "window_key": "all_history",
            "window_days": 0,
            "period_start": start,
            "period_end": end,
        }
    days = int(window)
    period_end = date.fromisoformat(end)
    requested_start = period_end - timedelta(days=days - 1)
    floor_start = date.fromisoformat(start)
    period_start = max(requested_start, floor_start)
    return {
        "window_key": f"last_{days}d",
        "window_days": days,
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
    }


def _write_rollup_window(
    *,
    conn: sqlite3.Connection,
    period: dict[str, Any],
    source: str,
    synced_at: str,
) -> int:
    conn.execute(
        """
        DELETE FROM material_metric_rollups
        WHERE window_key = ?
          AND period_start = ?
          AND period_end = ?
        """,
        (period["window_key"], period["period_start"], period["period_end"]),
    )
    rows = conn.execute(
        """
        WITH enriched AS (
          SELECT
            mdm.*,
            COALESCE(
              NULLIF(mp.canonical_material_key, ''),
              'material:' || mdm.material_id
            ) AS canonical_key,
            COALESCE(NULLIF(mdm.material_kind, ''), 'video') AS normalized_material_kind
          FROM material_daily_metrics mdm
          LEFT JOIN material_profiles mp
            ON mp.material_id = mdm.material_id
          WHERE mdm.metric_date BETWEEN ? AND ?
            AND mdm.stat_cost > 0
            AND TRIM(mdm.material_id) != ''
        )
        SELECT
          canonical_key AS canonical_material_key,
          MIN(material_id) AS material_id,
          normalized_material_kind AS material_kind,
          COUNT(DISTINCT advertiser_id) AS account_count,
          COUNT(DISTINCT project_id) AS project_count,
          COUNT(DISTINCT promotion_id) AS promotion_count,
          ROUND(COALESCE(SUM(stat_cost), 0), 4) AS stat_cost,
          ROUND(COALESCE(SUM(show_cnt), 0), 4) AS show_cnt,
          ROUND(COALESCE(SUM(click_cnt), 0), 4) AS click_cnt,
          ROUND(COALESCE(SUM(convert_cnt), 0), 4) AS convert_cnt,
          ROUND(COALESCE(SUM(active_register), 0), 4) AS active_register,
          ROUND(
            CASE
              WHEN COALESCE(SUM(stat_cost), 0) > 0 THEN SUM(stat_cost * roi_1day) / SUM(stat_cost)
              ELSE 0
            END,
            4
          ) AS roi_1day_cost_weighted,
          ROUND(
            CASE
              WHEN COALESCE(SUM(stat_cost), 0) > 0 THEN SUM(stat_cost * roi_7days) / SUM(stat_cost)
              ELSE 0
            END,
            4
          ) AS roi_7days_cost_weighted
        FROM enriched
        GROUP BY
          canonical_key,
          normalized_material_kind
        ORDER BY stat_cost DESC, material_id
        """,
        (period["period_start"], period["period_end"]),
    ).fetchall()
    for row in rows:
        conn.execute(
            """
            INSERT INTO material_metric_rollups (
              window_key, window_days, period_start, period_end,
              canonical_material_key, material_id, material_kind, account_count,
              project_count, promotion_count, stat_cost, show_cnt, click_cnt,
              convert_cnt, active_register, roi_1day_cost_weighted,
              roi_7days_cost_weighted, source, synced_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(window_key, period_start, period_end, material_id)
            DO UPDATE SET
              window_days=excluded.window_days,
              canonical_material_key=excluded.canonical_material_key,
              material_kind=excluded.material_kind,
              account_count=excluded.account_count,
              project_count=excluded.project_count,
              promotion_count=excluded.promotion_count,
              stat_cost=excluded.stat_cost,
              show_cnt=excluded.show_cnt,
              click_cnt=excluded.click_cnt,
              convert_cnt=excluded.convert_cnt,
              active_register=excluded.active_register,
              roi_1day_cost_weighted=excluded.roi_1day_cost_weighted,
              roi_7days_cost_weighted=excluded.roi_7days_cost_weighted,
              source=excluded.source,
              synced_at=excluded.synced_at
            """,
            (
                period["window_key"],
                int(period["window_days"]),
                period["period_start"],
                period["period_end"],
                row[0],
                row[1],
                row[2],
                int(row[3] or 0),
                int(row[4] or 0),
                int(row[5] or 0),
                float(row[6] or 0),
                float(row[7] or 0),
                float(row[8] or 0),
                float(row[9] or 0),
                float(row[10] or 0),
                float(row[11] or 0),
                float(row[12] or 0),
                source,
                synced_at,
            ),
        )
    return len(rows)


def run_material_quality_rollup_request(
    request: dict[str, Any],
    *,
    db_path: str | Path,
    runs_dir: str | Path,
) -> dict[str, Any]:
    cfg = _config(request)
    date_range = _date_range_config(cfg)
    quality_report = build_material_quality_report(request, db_path=db_path)
    require_quality_pass = bool(cfg.get("require_quality_pass", True))
    rollup_rows_written = 0
    rollups: list[dict[str, Any]] = []
    if quality_report["ok"] or not require_quality_pass:
        synced_at = _utc_now()
        with sqlite3.connect(db_path) as conn:
            for window in _windows(cfg):
                period = _window_period(start=date_range["start"], end=date_range["end"], window=window)
                rows_written = _write_rollup_window(
                    conn=conn,
                    period=period,
                    source="material_quality_rollup",
                    synced_at=synced_at,
                )
                rollup_rows_written += rows_written
                rollups.append({**period, "rows_written": rows_written})

    ok = bool(quality_report["ok"])
    payload = {
        "ok": ok,
        "workflow": "material_quality_rollup",
        "phase": "phase1",
        "execution_enabled": False,
        "external_api_calls": 0,
        "summary": {
            **quality_report["summary"],
            "rollup_rows_written": rollup_rows_written,
            "window_count": len(rollups),
        },
        "quality_report": quality_report,
        "rollups": rollups,
        "guardrails": {
            "external_api_calls": 0,
            "business_actions": [],
            "writes": ["material_metric_rollups", "run_artifact"],
            "require_quality_pass": require_quality_pass,
        },
    }
    artifact_path = write_run_artifact(runs_dir, "material_quality_rollup", payload)
    payload["artifact_path"] = str(artifact_path)
    return payload
