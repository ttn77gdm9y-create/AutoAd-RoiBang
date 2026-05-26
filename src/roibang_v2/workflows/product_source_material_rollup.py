from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from roibang_v2.runs import write_run_artifact
from roibang_v2.workflows.material_history_backfill import _date_range


def _config(request: dict[str, Any]) -> dict[str, Any]:
    value = request.get("product_source_material_rollup")
    return dict(value) if isinstance(value, dict) else dict(request)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _resolve_date_value(value: Any, *, tz_name: str) -> str:
    raw = str(value or "").strip()
    if raw in {"today", "yesterday"}:
        today = datetime.now(ZoneInfo(tz_name)).date()
        if raw == "yesterday":
            today -= timedelta(days=1)
        return today.isoformat()
    return raw


def _date_range_config(cfg: dict[str, Any]) -> dict[str, str]:
    value = cfg.get("date_range") if isinstance(cfg.get("date_range"), dict) else {}
    tz_name = str(cfg.get("timezone") or "Asia/Shanghai")
    start = _resolve_date_value(value.get("start"), tz_name=tz_name)
    end = _resolve_date_value(value.get("end"), tz_name=tz_name)
    if not start or not end:
        raise ValueError("product_source_material_rollup requires date_range.start and date_range.end")
    # Validate after resolving dynamic tokens like "yesterday".
    date.fromisoformat(start)
    date.fromisoformat(end)
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


def _parse_target_video_local_key(local_key: str) -> tuple[str, str] | None:
    prefix = "target_video:"
    if not local_key.startswith(prefix):
        return None
    rest = local_key[len(prefix) :]
    target_advertiser_id, sep, source_video_id = rest.partition(":")
    if not sep or not target_advertiser_id or not source_video_id:
        return None
    return target_advertiser_id, source_video_id


def _backfill_material_source_mappings_from_create_ledger(
    *,
    conn: sqlite3.Connection,
    product: str,
    source_advertiser_id: str,
    source: str,
    synced_at: str,
) -> int:
    rows = conn.execute(
        """
        SELECT local_key, provider_id, source_workflow, first_seen_at, last_seen_at
        FROM create_provider_id_ledger
        WHERE entity_type = 'target_video'
          AND status = 'active'
          AND provider_id <> ''
          AND provider_id NOT LIKE 'mock_%'
        """
    ).fetchall()
    written = 0
    for local_key, target_video_id, source_workflow, first_seen_at, last_seen_at in rows:
        parsed = _parse_target_video_local_key(str(local_key or ""))
        if parsed is None:
            continue
        target_advertiser_id, source_video_id = parsed
        source_material = conn.execute(
            """
            SELECT material_id
            FROM product_source_materials
            WHERE product = ?
              AND source_advertiser_id = ?
              AND video_id = ?
              AND is_active = 1
            ORDER BY material_id
            LIMIT 1
            """,
            (product, source_advertiser_id, source_video_id),
        ).fetchone()
        if source_material is None:
            continue
        target_material = conn.execute(
            """
            SELECT material_id
            FROM account_materials
            WHERE advertiser_id = ?
              AND video_id = ?
              AND material_type = 'video'
            ORDER BY material_id
            LIMIT 1
            """,
            (target_advertiser_id, str(target_video_id or "")),
        ).fetchone()
        if target_material is None:
            continue
        cursor = conn.execute(
            """
            INSERT INTO material_source_mappings (
              product, source_advertiser_id, source_material_id, source_video_id,
              target_advertiser_id, target_material_id, target_video_id,
              source_workflow, payload_json, first_seen_at, last_seen_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, '{}', ?, ?)
            ON CONFLICT(product, source_advertiser_id, target_advertiser_id, target_material_id)
            DO UPDATE SET
              source_material_id=excluded.source_material_id,
              source_video_id=excluded.source_video_id,
              target_video_id=excluded.target_video_id,
              source_workflow=excluded.source_workflow,
              last_seen_at=excluded.last_seen_at
            """,
            (
                product,
                source_advertiser_id,
                str(source_material[0] or ""),
                source_video_id,
                target_advertiser_id,
                str(target_material[0] or ""),
                str(target_video_id or ""),
                str(source_workflow or source),
                str(first_seen_at or synced_at),
                str(last_seen_at or synced_at),
            ),
        )
        written += int(cursor.rowcount or 0)
    return written


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

    rows = conn.execute(
        """
        WITH
        source_material_ids AS (
          SELECT material_id
          FROM product_source_materials
          WHERE product = ?
            AND source_advertiser_id = ?
            AND is_active = 1
          GROUP BY material_id
        ),
        source_video_materials AS (
          SELECT video_id, MIN(material_id) AS material_id
          FROM product_source_materials
          WHERE product = ?
            AND source_advertiser_id = ?
            AND is_active = 1
            AND TRIM(video_id) != ''
          GROUP BY video_id
        ),
        daily AS (
          SELECT
            mdm.*,
            COALESCE(msm.source_material_id, smi.material_id, svm.material_id, mdm.material_id) AS canonical_source_material_id
          FROM material_daily_metrics mdm
          LEFT JOIN material_source_mappings msm
            ON msm.product = ?
           AND msm.source_advertiser_id = ?
           AND msm.target_advertiser_id = mdm.advertiser_id
           AND msm.target_material_id = mdm.material_id
          LEFT JOIN source_material_ids smi
            ON smi.material_id = mdm.material_id
          LEFT JOIN account_materials daily_am
            ON daily_am.advertiser_id = mdm.advertiser_id
           AND daily_am.material_id = mdm.material_id
          LEFT JOIN source_video_materials svm
            ON svm.video_id = daily_am.video_id
          WHERE mdm.metric_date BETWEEN ? AND ?
            AND mdm.stat_cost > 0
        ),
        account_material_meta AS (
          SELECT
            material_id,
            MAX(video_id) AS video_id,
            MAX(material_type) AS material_type,
            MAX(review_status) AS review_status
          FROM account_materials
          GROUP BY material_id
        ),
        binding_material_meta AS (
          SELECT
            material_id,
            MIN(material_kind) AS material_kind
          FROM material_bindings
          WHERE TRIM(material_id) != ''
            AND TRIM(material_kind) != ''
          GROUP BY material_id
          HAVING COUNT(DISTINCT material_kind) = 1
        )
        SELECT
          COALESCE(NULLIF(psm.organization_id, ''), ?) AS organization_id,
          daily.canonical_source_material_id AS material_id,
          COALESCE(NULLIF(psm.material_type, ''), NULLIF(am.material_type, ''), NULLIF(mp.material_kind, ''), NULLIF(bm.material_kind, ''), NULLIF(daily.material_kind, ''), '') AS resolved_material_type,
          COALESCE(NULLIF(psm.video_id, ''), NULLIF(am.video_id, ''), NULLIF(mp.video_id, ''), '') AS resolved_source_video_id,
          COALESCE(NULLIF(psm.name, ''), NULLIF(mp.name, ''), '') AS name,
          COALESCE(NULLIF(psm.review_status, ''), NULLIF(am.review_status, ''), NULLIF(mp.review_status, ''), '') AS review_status,
          COALESCE(psm.signature, '') AS signature,
          COALESCE(psm.duration, mp.duration, 0) AS duration,
          COALESCE(psm.file_size, 0) AS file_size,
          COALESCE(NULLIF(psm.create_time, ''), NULLIF(mp.create_time, ''), '') AS create_time,
          MIN(daily.metric_date) AS first_seen_metric_date,
          MIN(daily.metric_date) AS effective_create_date,
          'material_daily_metrics' AS effective_create_date_source,
          COALESCE(psm.tag_ids_json, '[]') AS tag_ids_json,
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
        FROM daily
        LEFT JOIN product_source_materials psm
          ON psm.product = ?
         AND psm.source_advertiser_id = ?
         AND psm.material_id = daily.canonical_source_material_id
         AND psm.is_active = 1
        LEFT JOIN account_material_meta am
          ON am.material_id = daily.material_id
        LEFT JOIN material_profiles mp
          ON mp.material_id = daily.canonical_source_material_id
        LEFT JOIN binding_material_meta bm
          ON bm.material_id = daily.material_id
        GROUP BY
          daily.canonical_source_material_id,
          psm.organization_id,
          psm.material_type,
          psm.video_id,
          psm.name,
          psm.review_status,
          psm.signature,
          psm.duration,
          psm.file_size,
          psm.create_time,
          psm.tag_ids_json,
          am.material_type,
          am.video_id,
          am.review_status,
          mp.material_kind,
          mp.video_id,
          mp.name,
          mp.review_status,
          mp.duration,
          mp.create_time,
          bm.material_kind,
          daily.material_kind
        HAVING resolved_material_type = 'video'
           AND resolved_source_video_id <> ''
        ORDER BY stat_cost DESC, daily.canonical_source_material_id ASC
        """,
        (
            product,
            source_advertiser_id,
            product,
            source_advertiser_id,
            product,
            source_advertiser_id,
            period["period_start"],
            period["period_end"],
            organization_id,
            product,
            source_advertiser_id,
        ),
    ).fetchall()
    for row in rows:
        conn.execute(
            """
            INSERT INTO product_source_material_metric_rollups (
              product, source_advertiser_id, organization_id, window_key,
              window_days, period_start, period_end, material_id,
              material_type, source_video_id, name, review_status, signature,
              duration, file_size, create_time, first_seen_metric_date,
              effective_create_date, effective_create_date_source,
              tag_ids_json, account_count, project_count, promotion_count,
              stat_cost, show_cnt, click_cnt, convert_cnt, active_register,
              roi_1day_cost_weighted, roi_7days_cost_weighted, source, synced_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
              first_seen_metric_date=excluded.first_seen_metric_date,
              effective_create_date=excluded.effective_create_date,
              effective_create_date_source=excluded.effective_create_date_source,
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
                str(row[10] or ""),
                str(row[11] or ""),
                str(row[12] or ""),
                str(row[13] or "[]"),
                int(row[14] or 0),
                int(row[15] or 0),
                int(row[16] or 0),
                float(row[17] or 0),
                float(row[18] or 0),
                float(row[19] or 0),
                float(row[20] or 0),
                float(row[21] or 0),
                float(row[22] or 0),
                float(row[23] or 0),
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
        material_source_mappings_backfilled = _backfill_material_source_mappings_from_create_ledger(
            conn=conn,
            product=product,
            source_advertiser_id=source_advertiser_id,
            source="product_source_material_rollup",
            synced_at=synced_at,
        )
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
            "material_source_mappings_backfilled": material_source_mappings_backfilled,
            "rollup_rows_written": rollup_rows_written,
            "window_count": len(rollups),
        },
        "rollups": rollups,
        "guardrails": {
            "external_api_calls": 0,
            "business_actions": [],
            "writes": ["material_source_mappings", "product_source_material_metric_rollups", "run_artifact"],
            "spend_source": "material_daily_metrics",
        },
    }
    artifact_path = write_run_artifact(runs_dir, "product_source_material_rollup", payload)
    payload["artifact_path"] = str(artifact_path)
    return payload
