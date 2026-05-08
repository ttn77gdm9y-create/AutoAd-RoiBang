from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from roibang_v2.runs import write_run_artifact


def _config(request: dict[str, Any]) -> dict[str, Any]:
    value = request.get("source_material_candidate_pool")
    return dict(value) if isinstance(value, dict) else dict(request)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _source_filter_sql(*, organization_id: str, alias: str = "psm") -> tuple[str, list[Any]]:
    if not organization_id:
        return "", []
    return f"AND {alias}.organization_id = ?", [organization_id]


def _latest_period(
    *,
    conn: sqlite3.Connection,
    product: str,
    source_advertiser_id: str,
    organization_id: str,
    window_key: str,
) -> dict[str, str] | None:
    params: list[Any] = [product, source_advertiser_id, window_key]
    org_filter = ""
    if organization_id:
        org_filter = "AND organization_id = ?"
        params.append(organization_id)
    row = conn.execute(
        f"""
        SELECT period_start, period_end
        FROM product_source_material_metric_rollups
        WHERE product = ?
          AND source_advertiser_id = ?
          AND window_key = ?
          {org_filter}
        ORDER BY period_end DESC, period_start DESC
        LIMIT 1
        """,
        tuple(params),
    ).fetchone()
    if not row:
        return None
    return {"period_start": str(row[0]), "period_end": str(row[1])}


def _source_acceptance(
    *,
    conn: sqlite3.Connection,
    product: str,
    source_advertiser_id: str,
    organization_id: str,
    window_key: str,
    period: dict[str, str] | None,
) -> dict[str, Any]:
    org_filter, org_params = _source_filter_sql(organization_id=organization_id)
    source_row = conn.execute(
        f"""
        SELECT
          COUNT(*) AS active_source_material_count,
          SUM(CASE WHEN material_type = 'video' THEN 1 ELSE 0 END) AS active_video_count,
          SUM(CASE WHEN material_type = 'image' THEN 1 ELSE 0 END) AS active_image_count,
          SUM(CASE WHEN material_type NOT IN ('video', 'image') THEN 1 ELSE 0 END) AS active_other_count,
          SUM(CASE WHEN TRIM(signature) != '' THEN 1 ELSE 0 END) AS with_signature_count,
          SUM(CASE WHEN duration > 0 THEN 1 ELSE 0 END) AS with_duration_count
        FROM product_source_materials psm
        WHERE product = ?
          AND source_advertiser_id = ?
          AND is_active = 1
          {org_filter}
        """,
        tuple([product, source_advertiser_id, *org_params]),
    ).fetchone()

    source_summary = {
        "active_source_material_count": int(source_row[0] or 0),
        "active_video_count": int(source_row[1] or 0),
        "active_image_count": int(source_row[2] or 0),
        "active_other_count": int(source_row[3] or 0),
        "with_signature_count": int(source_row[4] or 0),
        "with_duration_count": int(source_row[5] or 0),
    }

    rollup_summary = {
        "window_key": window_key,
        "period_start": "",
        "period_end": "",
        "matched_source_material_count": 0,
        "matched_video_count": 0,
        "stat_cost": 0.0,
        "convert_cnt": 0.0,
        "account_count_max": 0,
    }
    if period:
        params = [
            product,
            source_advertiser_id,
            window_key,
            period["period_start"],
            period["period_end"],
        ]
        org_rollup_filter = ""
        if organization_id:
            org_rollup_filter = "AND organization_id = ?"
            params.append(organization_id)
        row = conn.execute(
            f"""
            SELECT
              COUNT(*) AS matched_source_material_count,
              SUM(CASE WHEN material_type = 'video' THEN 1 ELSE 0 END) AS matched_video_count,
              ROUND(COALESCE(SUM(stat_cost), 0), 4) AS stat_cost,
              ROUND(COALESCE(SUM(convert_cnt), 0), 4) AS convert_cnt,
              COALESCE(MAX(account_count), 0) AS account_count_max
            FROM product_source_material_metric_rollups
            WHERE product = ?
              AND source_advertiser_id = ?
              AND window_key = ?
              AND period_start = ?
              AND period_end = ?
              {org_rollup_filter}
            """,
            tuple(params),
        ).fetchone()
        rollup_summary = {
            "window_key": window_key,
            "period_start": period["period_start"],
            "period_end": period["period_end"],
            "matched_source_material_count": int(row[0] or 0),
            "matched_video_count": int(row[1] or 0),
            "stat_cost": float(row[2] or 0),
            "convert_cnt": float(row[3] or 0),
            "account_count_max": int(row[4] or 0),
        }

    source_summary["active_source_without_spend_count"] = max(
        0,
        source_summary["active_source_material_count"] - rollup_summary["matched_source_material_count"],
    )
    source_summary["active_video_without_spend_count"] = max(
        0,
        source_summary["active_video_count"] - rollup_summary["matched_video_count"],
    )
    return {"source_summary": source_summary, "rollup_summary": rollup_summary}


def _candidate_policy(cfg: dict[str, Any]) -> dict[str, Any]:
    policy = cfg.get("candidate_policy") if isinstance(cfg.get("candidate_policy"), dict) else {}
    window_key = str(policy.get("window_key") or cfg.get("window_key") or "all_history").strip()
    if not window_key:
        raise ValueError("source_material_candidate_pool candidate_policy.window_key is required")
    material_type = str(policy.get("material_type") or "video").strip()
    if material_type != "video":
        raise ValueError("source_material_candidate_pool currently only supports material_type=video")
    return {
        "window_key": window_key,
        "material_type": material_type,
        "limit": int(policy.get("limit") or 300),
        "min_stat_cost": float(policy.get("min_stat_cost") or 0),
        "min_account_count": int(policy.get("min_account_count") or 1),
        "min_convert_cnt": float(policy.get("min_convert_cnt") or 0),
        "exclude_review_statuses": [str(item) for item in policy.get("exclude_review_statuses", [])],
    }


def _pool_key(
    *,
    cfg: dict[str, Any],
    product: str,
    source_advertiser_id: str,
    window_key: str,
) -> str:
    value = str(cfg.get("pool_key") or "").strip()
    if value:
        return value
    safe_product = product.replace(":", "_")
    return f"{safe_product}:{source_advertiser_id}:{window_key}"


def _select_candidates(
    *,
    conn: sqlite3.Connection,
    product: str,
    source_advertiser_id: str,
    organization_id: str,
    policy: dict[str, Any],
    period: dict[str, str] | None,
) -> list[dict[str, Any]]:
    if not period:
        return []
    params: list[Any] = [
        product,
        source_advertiser_id,
        policy["window_key"],
        period["period_start"],
        period["period_end"],
        policy["material_type"],
        policy["min_stat_cost"],
        policy["min_account_count"],
        policy["min_convert_cnt"],
    ]
    org_filter = ""
    if organization_id:
        org_filter = "AND organization_id = ?"
        params.append(organization_id)
    review_filter = ""
    excluded = list(policy["exclude_review_statuses"])
    if excluded:
        placeholders = ",".join("?" for _ in excluded)
        review_filter = f"AND review_status NOT IN ({placeholders})"
        params.extend(excluded)
    params.append(policy["limit"])

    rows = conn.execute(
        f"""
        SELECT
          material_id, material_type, source_video_id, name, review_status,
          signature, duration, file_size, create_time, tag_ids_json,
          account_count, project_count, promotion_count, stat_cost,
          show_cnt, click_cnt, convert_cnt, active_register,
          roi_1day_cost_weighted, roi_7days_cost_weighted
        FROM product_source_material_metric_rollups
        WHERE product = ?
          AND source_advertiser_id = ?
          AND window_key = ?
          AND period_start = ?
          AND period_end = ?
          AND material_type = ?
          AND stat_cost >= ?
          AND account_count >= ?
          AND convert_cnt >= ?
          {org_filter}
          {review_filter}
        ORDER BY stat_cost DESC, convert_cnt DESC, account_count DESC, material_id ASC
        LIMIT ?
        """,
        tuple(params),
    ).fetchall()
    candidates: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        stat_cost = float(row[13] or 0)
        candidates.append(
            {
                "rank": index,
                "material_id": str(row[0] or ""),
                "material_type": str(row[1] or ""),
                "source_video_id": str(row[2] or ""),
                "name": str(row[3] or ""),
                "review_status": str(row[4] or ""),
                "signature": str(row[5] or ""),
                "duration": float(row[6] or 0),
                "file_size": float(row[7] or 0),
                "create_time": str(row[8] or ""),
                "tag_ids_json": str(row[9] or "[]"),
                "account_count": int(row[10] or 0),
                "project_count": int(row[11] or 0),
                "promotion_count": int(row[12] or 0),
                "stat_cost": stat_cost,
                "show_cnt": float(row[14] or 0),
                "click_cnt": float(row[15] or 0),
                "convert_cnt": float(row[16] or 0),
                "active_register": float(row[17] or 0),
                "roi_1day_cost_weighted": float(row[18] or 0),
                "roi_7days_cost_weighted": float(row[19] or 0),
                "score": stat_cost,
            }
        )
    return candidates


def _write_candidates(
    *,
    conn: sqlite3.Connection,
    pool_key: str,
    product: str,
    source_advertiser_id: str,
    organization_id: str,
    policy: dict[str, Any],
    period: dict[str, str] | None,
    candidates: list[dict[str, Any]],
    synced_at: str,
) -> None:
    conn.execute("DELETE FROM product_source_material_candidates WHERE pool_key = ?", (pool_key,))
    if not period:
        return
    for item in candidates:
        reason_json = json.dumps(
            {
                "ranking": "stat_cost desc, convert_cnt desc, account_count desc",
                "policy": policy,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        conn.execute(
            """
            INSERT INTO product_source_material_candidates (
              pool_key, product, source_advertiser_id, organization_id, window_key,
              period_start, period_end, rank, material_id, material_type,
              source_video_id, name, review_status, signature, duration,
              file_size, create_time, tag_ids_json, account_count, project_count,
              promotion_count, stat_cost, show_cnt, click_cnt, convert_cnt,
              active_register, roi_1day_cost_weighted, roi_7days_cost_weighted,
              score, reason_json, source, synced_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                pool_key,
                product,
                source_advertiser_id,
                organization_id,
                policy["window_key"],
                period["period_start"],
                period["period_end"],
                int(item["rank"]),
                item["material_id"],
                item["material_type"],
                item["source_video_id"],
                item["name"],
                item["review_status"],
                item["signature"],
                float(item["duration"]),
                float(item["file_size"]),
                item["create_time"],
                item["tag_ids_json"],
                int(item["account_count"]),
                int(item["project_count"]),
                int(item["promotion_count"]),
                float(item["stat_cost"]),
                float(item["show_cnt"]),
                float(item["click_cnt"]),
                float(item["convert_cnt"]),
                float(item["active_register"]),
                float(item["roi_1day_cost_weighted"]),
                float(item["roi_7days_cost_weighted"]),
                float(item["score"]),
                reason_json,
                "source_material_candidate_pool",
                synced_at,
            ),
        )


def run_source_material_candidate_pool_request(
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
        raise ValueError("source_material_candidate_pool requires product")
    if not source_advertiser_id:
        raise ValueError("source_material_candidate_pool requires source_advertiser_id")

    policy = _candidate_policy(cfg)
    pool_key = _pool_key(
        cfg=cfg,
        product=product,
        source_advertiser_id=source_advertiser_id,
        window_key=policy["window_key"],
    )
    synced_at = _utc_now()

    with sqlite3.connect(db_path) as conn:
        period = _latest_period(
            conn=conn,
            product=product,
            source_advertiser_id=source_advertiser_id,
            organization_id=organization_id,
            window_key=policy["window_key"],
        )
        acceptance = _source_acceptance(
            conn=conn,
            product=product,
            source_advertiser_id=source_advertiser_id,
            organization_id=organization_id,
            window_key=policy["window_key"],
            period=period,
        )
        candidates = _select_candidates(
            conn=conn,
            product=product,
            source_advertiser_id=source_advertiser_id,
            organization_id=organization_id,
            policy=policy,
            period=period,
        )
        _write_candidates(
            conn=conn,
            pool_key=pool_key,
            product=product,
            source_advertiser_id=source_advertiser_id,
            organization_id=organization_id,
            policy=policy,
            period=period,
            candidates=candidates,
            synced_at=synced_at,
        )

    payload = {
        "ok": True,
        "workflow": "source_material_candidate_pool",
        "phase": "phase1",
        "execution_enabled": False,
        "external_api_calls": 0,
        "product": product,
        "source_advertiser_id": source_advertiser_id,
        "organization_id": organization_id,
        "pool_key": pool_key,
        "candidate_policy": policy,
        "acceptance": acceptance,
        "summary": {
            "candidate_count": len(candidates),
            "selected_window_key": policy["window_key"],
            "period_start": period["period_start"] if period else "",
            "period_end": period["period_end"] if period else "",
        },
        "top_candidates": candidates[:20],
        "guardrails": {
            "external_api_calls": 0,
            "business_actions": [],
            "writes": ["product_source_material_candidates", "run_artifact"],
            "spend_source": "product_source_material_metric_rollups",
        },
    }
    artifact_path = write_run_artifact(runs_dir, "source_material_candidate_pool", payload)
    payload["artifact_path"] = str(artifact_path)
    return payload
