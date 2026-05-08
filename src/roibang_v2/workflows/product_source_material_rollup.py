from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from roibang_v2.runs import write_run_artifact
from roibang_v2.workflows.material_history_backfill import _date_range


def _config(request: dict[str, Any]) -> dict[str, Any]:
    value = request.get("product_source_material_rollup")
    return dict(value) if isinstance(value, dict) else dict(request)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _date_range_config(cfg: dict[str, Any]) -> dict[str, str]:
    value = cfg.get("date_range") if isinstance(cfg.get("date_range"), dict) else {}
    start = str(value.get("start") or "").strip()
    end = str(value.get("end") or "").strip()
    if not start or not end:
        raise ValueError("product_source_material_rollup requires date_range.start and date_range.end")
    return {"start": start, "end": end}


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
            raise ValueError("product_source_material_rollup.windows values must be positive")
        windows.append(days)
    return windows


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


def _source_material_count(
    *,
    conn: sqlite3.Connection,
    product: str,
    source_advertiser_id: str,
    organization_id: str,
) -> int:
    params: list[Any] = [product, source_advertiser_id]
    org_filter = ""
    if organization_id:
        org_filter = "AND organization_id = ?"
        params.append(organization_id)
    return int(
        conn.execute(
            f"""
            SELECT COUNT(*)
            FROM product_source_materials
            WHERE product = ?
              AND source_advertiser_id = ?
              AND is_active = 1
              {org_filter}
            """,
            tuple(params),
        ).fetchone()[0]
        or 0
    )


def _write_source_rollup_window(
    *,
    conn: sqlite3.Connection,
    product: str,
    source_advertiser_id: str,
    organization_id: str,
    period: dict[str, Any],
    source: str,
    synced_at: str,
) -> int:
    delete_params: list[Any] = [
        product,
        source_advertiser_id,
        period["window_key"],
        period["period_start"],
        period["period_end"],
    ]
    org_delete = ""
    if organization_id:
        org_delete = "AND organization_id = ?"
        delete_params.append(organization_id)
    conn.execute(
        f"""
        DELETE FROM product_source_material_metric_rollups
        WHERE product = ?
          AND source_advertiser_id = ?
          AND window_key = ?
          AND period_start = ?
          AND period_end = ?
          {org_delete}
        """,
        tuple(delete_params),
    )

    source_params: list[Any] = [product, source_advertiser_id]
    org_filter = ""
    if organization_id:
        org_filter = "AND psm.organization_id = ?"
        source_params.append(organization_id)

    rows = conn.execute(
        f"""
        WITH source_materials AS (
          SELECT *
          FROM product_source_materials psm
          WHERE psm.product = ?
            AND psm.source_advertiser_id = ?
            AND psm.is_active = 1
            {org_filter}
        ),
        daily AS (
          SELECT
            mdm.*
          FROM material_daily_metrics mdm
          JOIN source_materials psm
            ON psm.material_id = mdm.material_id
          WHERE mdm.metric_date BETWEEN ? AND ?
            AND mdm.stat_cost > 0
            AND mdm.advertiser_id != ?
        )
        SELECT
          psm.organization_id,
          psm.material_id,
          psm.material_type,
          psm.video_id AS source_video_id,
          psm.name,
          psm.review_status,
          psm.signature,
          psm.duration,
          psm.file_size,
          psm.create_time,
          psm.tag_ids_json,
          COUNT(DISTINCT daily.advertiser_id) AS account_count,
          COUNT(DISTINCT daily.project_id) AS project_count,
          COUNT(DISTINCT daily.promotion_id) AS promotion_count,
          ROUND(COALESCE(SUM(daily.stat_cost), 0), 4) AS stat_cost,
          ROUND(COALESCE(SUM(daily.show_cnt), 0), 4) AS show_cnt,
          ROUND(COALESCE(SUM(daily.click_cnt), 0), 4) AS click_cnt,
          ROUND(COALESCE(SUM(daily.convert_cnt), 0), 4) AS convert_cnt,
          ROUND(COALESCE(SUM(daily.active_register), 0), 4) AS active_register,
          ROUND(
            CASE
              WHEN COALESCE(SUM(daily.stat_cost), 0) > 0 THEN SUM(daily.stat_cost * daily.roi_1day) / SUM(daily.stat_cost)
              ELSE 0
            END,
            4
          ) AS roi_1day_cost_weighted,
          ROUND(
            CASE
              WHEN COALESCE(SUM(daily.stat_cost), 0) > 0 THEN SUM(daily.stat_cost * daily.roi_7days) / SUM(daily.stat_cost)
              ELSE 0
            END,
            4
          ) AS roi_7days_cost_weighted
        FROM source_materials psm
        JOIN daily
          ON daily.material_id = psm.material_id
        GROUP BY
          psm.organization_id,
          psm.material_id,
          psm.material_type,
          psm.video_id,
          psm.name,
          psm.review_status,
          psm.signature,
          psm.duration,
          psm.file_size,
          psm.create_time,
          psm.tag_ids_json
        ORDER BY stat_cost DESC, psm.material_id ASC
        """,
        tuple([*source_params, period["period_start"], period["period_end"], source_advertiser_id]),
    ).fetchall()
    for row in rows:
        conn.execute(
            """
            INSERT INTO product_source_material_metric_rollups (
              product, source_advertiser_id, organization_id, window_key,
              window_days, period_start, period_end, material_id,
              material_type, source_video_id, name, review_status, signature,
              duration, file_size, create_time, tag_ids_json, account_count,
              project_count, promotion_count, stat_cost, show_cnt, click_cnt,
              convert_cnt, active_register, roi_1day_cost_weighted,
              roi_7days_cost_weighted, source, synced_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(product, source_advertiser_id, window_key, period_start, period_end, material_id)
            DO UPDATE SET
              organization_id=excluded.organization_id,
              window_days=excluded.window_days,
              material_type=excluded.material_type,
              source_video_id=excluded.source_video_id,
              name=excluded.name,
              review_status=excluded.review_status,
              signature=excluded.signature,
              duration=excluded.duration,
              file_size=excluded.file_size,
              create_time=excluded.create_time,
              tag_ids_json=excluded.tag_ids_json,
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
                product,
                source_advertiser_id,
                str(row[0] or ""),
                period["window_key"],
                int(period["window_days"]),
                period["period_start"],
                period["period_end"],
                str(row[1] or ""),
                str(row[2] or ""),
                str(row[3] or ""),
                str(row[4] or ""),
                str(row[5] or ""),
                str(row[6] or ""),
                float(row[7] or 0),
                float(row[8] or 0),
                str(row[9] or ""),
                str(row[10] or "[]"),
                int(row[11] or 0),
                int(row[12] or 0),
                int(row[13] or 0),
                float(row[14] or 0),
                float(row[15] or 0),
                float(row[16] or 0),
                float(row[17] or 0),
                float(row[18] or 0),
                float(row[19] or 0),
                float(row[20] or 0),
                source,
                synced_at,
            ),
        )
    return len(rows)


def run_product_source_material_rollup_request(
    request: dict[str, Any],
    *,
    db_path: str | Path,
    runs_dir: str | Path,
) -> dict[str, Any]:
    cfg = _config(request)
    product = str(cfg.get("product") or "").strip()
    source_advertiser_id = str(cfg.get("source_advertiser_id") or "").strip()
    organization_id = str(cfg.get("organization_id") or "").strip()
    if not product:
        raise ValueError("product_source_material_rollup requires product")
    if not source_advertiser_id:
        raise ValueError("product_source_material_rollup requires source_advertiser_id")
    date_range = _date_range_config(cfg)
    dates = _date_range(date_range["start"], date_range["end"])
    synced_at = _utc_now()
    rollup_rows_written = 0
    rollups: list[dict[str, Any]] = []
    with sqlite3.connect(db_path) as conn:
        source_material_count = _source_material_count(
            conn=conn,
            product=product,
            source_advertiser_id=source_advertiser_id,
            organization_id=organization_id,
        )
        for window in _windows(cfg):
            period = _window_period(start=date_range["start"], end=date_range["end"], window=window)
            rows_written = _write_source_rollup_window(
                conn=conn,
                product=product,
                source_advertiser_id=source_advertiser_id,
                organization_id=organization_id,
                period=period,
                source="product_source_material_rollup",
                synced_at=synced_at,
            )
            rollup_rows_written += rows_written
            rollups.append({**period, "rows_written": rows_written})

    payload = {
        "ok": True,
        "workflow": "product_source_material_rollup",
        "phase": "phase1",
        "execution_enabled": False,
        "external_api_calls": 0,
        "product": product,
        "source_advertiser_id": source_advertiser_id,
        "organization_id": organization_id,
        "date_range": date_range,
        "summary": {
            "date_count": len(dates),
            "source_material_count": source_material_count,
            "rollup_rows_written": rollup_rows_written,
            "window_count": len(rollups),
        },
        "rollups": rollups,
        "guardrails": {
            "external_api_calls": 0,
            "business_actions": [],
            "writes": ["product_source_material_metric_rollups", "run_artifact"],
            "spend_source": "material_daily_metrics",
        },
    }
    artifact_path = write_run_artifact(runs_dir, "product_source_material_rollup", payload)
    payload["artifact_path"] = str(artifact_path)
    return payload
