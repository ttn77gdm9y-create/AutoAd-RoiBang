from __future__ import annotations

import json
import sqlite3
import time
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

from roibang_v2.fetch.openapi_executor import Transport, execute_openapi_readonly_plan
from roibang_v2.fetch.openapi_readonly import build_readonly_request
from roibang_v2.materials.product_source import import_product_source_materials
from roibang_v2.runs import write_run_artifact


MutationTransport = Callable[[dict[str, Any]], dict[str, Any]]
Sleeper = Callable[[float], None]

BIND_MATERIAL_ENDPOINT = "/open_api/2/file/material/bind/"


def _cfg(request: dict[str, Any]) -> dict[str, Any]:
    value = request.get("source_material_account_auto_push")
    return dict(value) if isinstance(value, dict) else dict(request)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _float(value: Any) -> float:
    try:
        return float(str(value or "0").replace(",", ""))
    except ValueError:
        return 0.0


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalize_material_name(value: Any) -> str:
    text = _text(value)
    for prefix in ("推送视频_", "推送视频-", "推送视频 "):
        if text.startswith(prefix):
            text = text[len(prefix) :]
    return "".join(text.lower().split())


def _date_range(cfg: dict[str, Any], *, today: date | None = None) -> tuple[str, str]:
    value = cfg.get("date_range") if isinstance(cfg.get("date_range"), dict) else {}
    mode = _text(value.get("mode") or "yesterday")
    tz = ZoneInfo(_text(cfg.get("timezone") or "Asia/Shanghai"))
    base = today or datetime.now(tz).date()
    if mode == "yesterday":
        target = _text(value.get("base_date"))
        if target:
            base = date.fromisoformat(target)
        day = base - timedelta(days=1)
        return day.isoformat(), day.isoformat()
    start = _text(value.get("start"))
    end = _text(value.get("end") or start)
    if not start or not end:
        raise ValueError("source_material_account_auto_push date_range requires start/end or mode=yesterday")
    return start, end


def _chunks(items: list[Any], size: int) -> list[list[Any]]:
    chunk_size = max(int(size), 1)
    return [items[index : index + chunk_size] for index in range(0, len(items), chunk_size)]


def _api_code(response: dict[str, Any]) -> str:
    code = response.get("code")
    return "" if code in (None, "", 0, "0") else str(code)


def _response_message(response: dict[str, Any]) -> str:
    return _text(response.get("message") or response.get("msg") or response.get("error"))


def _source_sync_plan(cfg: dict[str, Any]) -> dict[str, Any]:
    source_advertiser_id = _text(cfg.get("source_advertiser_id"))
    page_size = _int(cfg.get("source_account_sync", {}).get("page_size") if isinstance(cfg.get("source_account_sync"), dict) else 100, 100)
    return {
        "ok": True,
        "workflow": "source_material_account_sync_plan",
        "phase": "source_material_account",
        "execution_enabled": False,
        "external_api_calls": 0,
        "requests": [
            {
                "source_account": {"source_advertiser_id": source_advertiser_id},
                **build_readonly_request(
                    "video_material_get",
                    {
                        "advertiser_id": source_advertiser_id,
                        "page": 1,
                        "page_size": page_size,
                    },
                ),
            }
        ],
    }


def _sync_source_account(
    cfg: dict[str, Any],
    *,
    db_path: str | Path,
    transport: Transport,
) -> dict[str, Any]:
    sync_cfg = cfg.get("source_account_sync") if isinstance(cfg.get("source_account_sync"), dict) else {}
    plan = _source_sync_plan(cfg)
    execution = execute_openapi_readonly_plan(
        plan,
        transport=transport,
        max_pages=_int(sync_cfg.get("max_pages"), 50),
        retry_api_codes=sync_cfg.get("retry_api_codes") if isinstance(sync_cfg.get("retry_api_codes"), list) else [],
        max_api_retries=_int(sync_cfg.get("max_api_retries"), 0),
        retry_sleep_seconds=_float(sync_cfg.get("retry_sleep_seconds") or 1),
    )
    rows: list[dict[str, Any]] = []
    for item in execution.get("responses") or []:
        if isinstance(item, dict):
            rows.extend(row for row in item.get("rows") or [] if isinstance(row, dict))
    imported = import_product_source_materials(
        db_path=db_path,
        product=_text(cfg.get("product")),
        source_advertiser_id=_text(cfg.get("source_advertiser_id")),
        organization_id=_text(cfg.get("organization_id")),
        materials=rows,
        source="source_material_account_auto_push.sync_source_account",
        mark_absent_inactive=bool(sync_cfg.get("mark_absent_inactive", False)),
    )
    return {
        "ok": True,
        "external_api_calls": int(execution["summary"]["transport_calls"]),
        "rows_received": int(execution["summary"]["rows_received"]),
        "import": imported,
    }


def _material_name_expr() -> str:
    return "COALESCE(NULLIF(m.name, ''), NULLIF(mp.name, ''), NULLIF(mb.title, ''), mdm.material_id)"


def _select_spent_materials(
    *,
    db_path: str | Path,
    cfg: dict[str, Any],
    period_start: str,
    period_end: str,
) -> list[dict[str, Any]]:
    source_advertiser_id = _text(cfg.get("source_advertiser_id"))
    material_cfg = cfg.get("material_source") if isinstance(cfg.get("material_source"), dict) else {}
    material_source = _text(material_cfg.get("from"))
    if material_source != "material_daily_metrics":
        summary_rows = _select_spent_video_summary_materials(
            db_path=db_path,
            cfg=cfg,
            period_start=period_start,
            period_end=period_end,
        )
        if summary_rows:
            return summary_rows

    min_cost = _float(material_cfg.get("min_stat_cost"))
    limit = _int(material_cfg.get("max_materials"), 500)
    account_ids = [str(item) for item in material_cfg.get("account_ids", []) if str(item).strip()] if isinstance(material_cfg.get("account_ids"), list) else []
    account_name_keyword = _text(material_cfg.get("account_name_keyword"))
    account_filter = ""
    params: list[Any] = [period_start, period_end, source_advertiser_id]
    if account_ids:
        placeholders = ",".join("?" for _ in account_ids)
        account_filter = f"AND mdm.advertiser_id IN ({placeholders})"
        params.extend(account_ids)
    elif account_name_keyword:
        account_filter = """
          AND EXISTS (
            SELECT 1
            FROM account_pool ap
            WHERE ap.advertiser_id = mdm.advertiser_id
              AND ap.account_name LIKE ?
          )
        """
        params.append(f"%{account_name_keyword}%")
    params.extend([min_cost, limit])
    query = f"""
        SELECT
          mdm.advertiser_id,
          mdm.material_id,
          mdm.material_kind,
          COALESCE(NULLIF(am.video_id, ''), NULLIF(m.video_id, ''), NULLIF(mp.video_id, ''), NULLIF(mb.video_id, '')) AS video_id,
          {_material_name_expr()} AS name,
          COALESCE(NULLIF(am.review_status, ''), NULLIF(m.review_status, ''), NULLIF(mp.review_status, '')) AS review_status,
          SUM(mdm.stat_cost) AS stat_cost,
          SUM(mdm.show_cnt) AS show_cnt,
          SUM(mdm.click_cnt) AS click_cnt,
          SUM(mdm.convert_cnt) AS convert_cnt,
          SUM(mdm.active_register) AS active_register,
          MAX(mdm.project_name) AS sample_project_name,
          MAX(mdm.promotion_name) AS sample_promotion_name
        FROM material_daily_metrics mdm
        LEFT JOIN account_materials am
          ON am.advertiser_id = mdm.advertiser_id AND am.material_id = mdm.material_id
        LEFT JOIN materials m
          ON m.material_id = mdm.material_id
        LEFT JOIN material_profiles mp
          ON mp.material_id = mdm.material_id
        LEFT JOIN (
          SELECT advertiser_id, material_id, MAX(video_id) AS video_id, MAX(title) AS title
          FROM material_bindings
          WHERE material_kind = 'video'
          GROUP BY advertiser_id, material_id
        ) mb
          ON mb.advertiser_id = mdm.advertiser_id AND mb.material_id = mdm.material_id
        WHERE mdm.metric_date BETWEEN ? AND ?
          AND mdm.advertiser_id <> ?
          AND COALESCE(NULLIF(mdm.material_kind, ''), 'unknown') IN ('video', 'unknown')
          {account_filter}
        GROUP BY mdm.advertiser_id, mdm.material_id, mdm.material_kind
        HAVING SUM(mdm.stat_cost) >= ?
        ORDER BY SUM(mdm.stat_cost) DESC, mdm.advertiser_id ASC, mdm.material_id ASC
        LIMIT ?
    """
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(query, tuple(params)).fetchall()
    results: list[dict[str, Any]] = []
    for row in rows:
        material_kind = _text(row["material_kind"] or "video")
        video_id = _text(row["video_id"])
        if material_kind == "unknown" and video_id:
            material_kind = "video"
        results.append(
            {
                "advertiser_id": _text(row["advertiser_id"]),
                "material_id": _text(row["material_id"]),
                "material_kind": material_kind,
                "video_id": video_id,
                "name": _text(row["name"]),
                "normalized_name": normalize_material_name(row["name"]),
                "review_status": _text(row["review_status"]),
                "stat_cost": float(row["stat_cost"] or 0),
                "show_cnt": float(row["show_cnt"] or 0),
                "click_cnt": float(row["click_cnt"] or 0),
                "convert_cnt": float(row["convert_cnt"] or 0),
                "active_register": float(row["active_register"] or 0),
                "sample_project_name": _text(row["sample_project_name"]),
                "sample_promotion_name": _text(row["sample_promotion_name"]),
            }
        )
    return results


def _select_spent_video_summary_materials(
    *,
    db_path: str | Path,
    cfg: dict[str, Any],
    period_start: str,
    period_end: str,
) -> list[dict[str, Any]]:
    source_advertiser_id = _text(cfg.get("source_advertiser_id"))
    material_cfg = cfg.get("material_source") if isinstance(cfg.get("material_source"), dict) else {}
    min_cost = _float(material_cfg.get("min_stat_cost"))
    limit = _int(material_cfg.get("max_materials"), 500)
    account_ids = [str(item) for item in material_cfg.get("account_ids", []) if str(item).strip()] if isinstance(material_cfg.get("account_ids"), list) else []
    account_name_keyword = _text(material_cfg.get("account_name_keyword"))
    account_filter = ""
    params: list[Any] = [period_start, period_end, source_advertiser_id]
    if account_ids:
        placeholders = ",".join("?" for _ in account_ids)
        account_filter = f"AND mb.advertiser_id IN ({placeholders})"
        params.extend(account_ids)
    elif account_name_keyword:
        account_filter = """
          AND EXISTS (
            SELECT 1
            FROM account_pool ap
            WHERE ap.advertiser_id = mb.advertiser_id
              AND ap.account_name LIKE ?
          )
        """
        params.append(f"%{account_name_keyword}%")
    params.extend([min_cost, limit])
    query = f"""
        WITH video_bindings AS (
          SELECT
            material_id,
            MIN(advertiser_id) AS advertiser_id,
            MAX(video_id) AS video_id,
            MAX(title) AS title
          FROM material_bindings
          WHERE material_kind = 'video'
            AND COALESCE(video_id, '') <> ''
          GROUP BY material_id
        )
        SELECT
          mb.advertiser_id,
          mms.material_id,
          mms.material_kind,
          COALESCE(NULLIF(mms.video_id, ''), NULLIF(mb.video_id, ''), NULLIF(am.video_id, ''), NULLIF(m.video_id, ''), NULLIF(mp.video_id, '')) AS video_id,
          COALESCE(NULLIF(m.name, ''), NULLIF(mp.name, ''), NULLIF(mms.title, ''), NULLIF(mb.title, ''), mms.material_id) AS name,
          COALESCE(NULLIF(am.review_status, ''), NULLIF(m.review_status, ''), NULLIF(mp.review_status, '')) AS review_status,
          mms.stat_cost AS stat_cost,
          0 AS show_cnt,
          0 AS click_cnt,
          mms.attribution_convert_cnt AS convert_cnt,
          mms.active_register AS active_register,
          '' AS sample_project_name,
          '' AS sample_promotion_name
        FROM material_metric_summaries mms
        JOIN video_bindings mb
          ON mb.material_id = mms.material_id
        LEFT JOIN account_materials am
          ON am.advertiser_id = mb.advertiser_id AND am.material_id = mms.material_id
        LEFT JOIN materials m
          ON m.material_id = mms.material_id
        LEFT JOIN material_profiles mp
          ON mp.material_id = mms.material_id
        WHERE mms.period_start = ?
          AND mms.period_end = ?
          AND mms.material_kind = 'video'
          AND mb.advertiser_id <> ?
          {account_filter}
          AND mms.stat_cost >= ?
        ORDER BY mms.stat_cost DESC, mb.advertiser_id ASC, mms.material_id ASC
        LIMIT ?
    """
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(query, tuple(params)).fetchall()
    return [
        {
            "advertiser_id": _text(row["advertiser_id"]),
            "material_id": _text(row["material_id"]),
            "material_kind": _text(row["material_kind"] or "video"),
            "video_id": _text(row["video_id"]),
            "name": _text(row["name"]),
            "normalized_name": normalize_material_name(row["name"]),
            "review_status": _text(row["review_status"]),
            "stat_cost": float(row["stat_cost"] or 0),
            "show_cnt": float(row["show_cnt"] or 0),
            "click_cnt": float(row["click_cnt"] or 0),
            "convert_cnt": float(row["convert_cnt"] or 0),
            "active_register": float(row["active_register"] or 0),
            "sample_project_name": _text(row["sample_project_name"]),
            "sample_promotion_name": _text(row["sample_promotion_name"]),
        }
        for row in rows
    ]


def _source_existing_materials(*, db_path: str | Path, cfg: dict[str, Any]) -> dict[str, Any]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT material_id, name, video_id, synced_at
            FROM product_source_materials
            WHERE product = ?
              AND source_advertiser_id = ?
              AND is_active = 1
            """,
            (_text(cfg.get("product")), _text(cfg.get("source_advertiser_id"))),
        ).fetchall()
    names = {normalize_material_name(row["name"]) for row in rows if normalize_material_name(row["name"])}
    return {
        "material_ids": {_text(row["material_id"]) for row in rows if _text(row["material_id"])},
        "normalized_names": names,
        "count": len(rows),
        "latest_synced_at": max((_text(row["synced_at"]) for row in rows), default=""),
    }


def _filter_new_materials(rows: list[dict[str, Any]], existing: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    new_rows: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    existing_ids = existing["material_ids"]
    existing_names = existing["normalized_names"]
    seen_names: set[str] = set()
    for row in rows:
        normalized_name = _text(row.get("normalized_name"))
        if _text(row.get("material_id")) in existing_ids:
            skipped.append({**row, "skip_reason": "source_account_already_has_material_id"})
            continue
        if normalized_name and normalized_name in existing_names:
            skipped.append({**row, "skip_reason": "source_account_already_has_name"})
            continue
        if normalized_name and normalized_name in seen_names:
            skipped.append({**row, "skip_reason": "duplicate_name_in_daily_rows"})
            continue
        seen_names.add(normalized_name)
        new_rows.append(row)
    return new_rows, skipped


def _detail_lookup_plan(rows: list[dict[str, Any]], *, page_size: int) -> dict[str, Any]:
    grouped: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        advertiser_id = _text(row.get("advertiser_id"))
        material_id = _text(row.get("material_id"))
        if advertiser_id and material_id:
            grouped[advertiser_id].append(material_id)
    requests: list[dict[str, Any]] = []
    for advertiser_id, material_ids in sorted(grouped.items()):
        unique_ids = sorted(set(material_ids))
        for chunk in _chunks(unique_ids, page_size):
            requests.append(
                {
                    "detail_account": {"advertiser_id": advertiser_id},
                    **build_readonly_request(
                        "video_material_get",
                        {
                            "advertiser_id": advertiser_id,
                            "material_ids": [int(item) if item.isdigit() else item for item in chunk],
                            "page": 1,
                            "page_size": page_size,
                        },
                    ),
                }
            )
    return {
        "ok": True,
        "workflow": "source_material_account_detail_lookup_plan",
        "phase": "source_material_account",
        "execution_enabled": False,
        "external_api_calls": 0,
        "requests": requests,
    }


def _first_text(row: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = _text(row.get(key))
        if value:
            return value
    return ""


def _material_type(row: dict[str, Any]) -> str:
    value = _first_text(row, "material_type", "file_type", "material_kind")
    if value in {"3", "VIDEO", "video"}:
        return "video"
    if value in {"2", "IMAGE", "image"}:
        return "image"
    return value or "video"


def _review_status(row: dict[str, Any]) -> str:
    return _first_text(row, "review_status", "media_review_status", "media_status")


def _import_account_material_rows(
    *,
    db_path: str | Path,
    advertiser_id: str,
    rows: list[dict[str, Any]],
    source: str,
) -> dict[str, Any]:
    synced_at = _now_iso()
    materials_imported = 0
    account_materials_imported = 0
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        for row in rows:
            material_id = _first_text(row, "material_id", "mid", "id")
            if not material_id:
                continue
            video_id = _first_text(row, "video_id", "vid", "id")
            name = _first_text(row, "name", "title", "filename", "material_name", "file_name", "video_name")
            material_type = _material_type(row)
            review_status = _review_status(row)
            payload_json = json.dumps(row, ensure_ascii=False, sort_keys=True)
            conn.execute(
                """
                INSERT INTO materials (
                  material_id, name, material_type, video_id, review_status,
                  cost_lookback, score, payload_json, source, synced_at
                ) VALUES (?, ?, ?, ?, ?, 0, 0, ?, ?, ?)
                ON CONFLICT(material_id) DO UPDATE SET
                  name = COALESCE(NULLIF(excluded.name, ''), materials.name),
                  material_type = COALESCE(NULLIF(excluded.material_type, ''), materials.material_type),
                  video_id = COALESCE(NULLIF(excluded.video_id, ''), materials.video_id),
                  review_status = COALESCE(NULLIF(excluded.review_status, ''), materials.review_status),
                  payload_json = excluded.payload_json,
                  source = excluded.source,
                  synced_at = excluded.synced_at
                """,
                (material_id, name, material_type, video_id, review_status, payload_json, source, synced_at),
            )
            materials_imported += 1
            conn.execute(
                """
                INSERT INTO account_materials (
                  advertiser_id, material_id, video_id, material_type,
                  review_status, cost_lookback, score, source, synced_at
                ) VALUES (?, ?, ?, ?, ?, 0, 0, ?, ?)
                ON CONFLICT(advertiser_id, material_id) DO UPDATE SET
                  video_id = COALESCE(NULLIF(excluded.video_id, ''), account_materials.video_id),
                  material_type = COALESCE(NULLIF(excluded.material_type, ''), account_materials.material_type),
                  review_status = COALESCE(NULLIF(excluded.review_status, ''), account_materials.review_status),
                  source = excluded.source,
                  synced_at = excluded.synced_at
                """,
                (advertiser_id, material_id, video_id, material_type, review_status, source, synced_at),
            )
            account_materials_imported += 1
    return {
        "ok": True,
        "advertiser_id": advertiser_id,
        "materials_imported": materials_imported,
        "account_materials_imported": account_materials_imported,
    }


def _fetch_missing_details(
    rows: list[dict[str, Any]],
    *,
    cfg: dict[str, Any],
    db_path: str | Path,
    transport: Transport,
) -> dict[str, Any]:
    detail_cfg = cfg.get("material_detail_fetch") if isinstance(cfg.get("material_detail_fetch"), dict) else {}
    page_size = _int(detail_cfg.get("page_size"), 100)
    plan = _detail_lookup_plan(rows, page_size=page_size)
    execution = execute_openapi_readonly_plan(
        plan,
        transport=transport,
        max_pages=_int(detail_cfg.get("max_pages"), 1),
        retry_api_codes=detail_cfg.get("retry_api_codes") if isinstance(detail_cfg.get("retry_api_codes"), list) else [],
        max_api_retries=_int(detail_cfg.get("max_api_retries"), 0),
        retry_sleep_seconds=_float(detail_cfg.get("retry_sleep_seconds") or 1),
    )
    imports: list[dict[str, Any]] = []
    for item in execution.get("responses") or []:
        if not isinstance(item, dict):
            continue
        request = item.get("request") if isinstance(item.get("request"), dict) else {}
        detail_account = request.get("detail_account") if isinstance(request.get("detail_account"), dict) else {}
        advertiser_id = _text(detail_account.get("advertiser_id"))
        if advertiser_id:
            imports.append(
                _import_account_material_rows(
                    db_path=db_path,
                    advertiser_id=advertiser_id,
                    rows=[row for row in item.get("rows") or [] if isinstance(row, dict)],
                    source="source_material_account_auto_push.detail_fetch",
                )
            )
    return {
        "ok": True,
        "external_api_calls": int(execution["summary"]["transport_calls"]),
        "rows_received": int(execution["summary"]["rows_received"]),
        "imports": imports,
    }


def build_source_material_account_push_plan(
    *,
    db_path: str | Path,
    cfg: dict[str, Any],
    period_start: str,
    period_end: str,
) -> dict[str, Any]:
    spent_rows = _select_spent_materials(db_path=db_path, cfg=cfg, period_start=period_start, period_end=period_end)
    existing = _source_existing_materials(db_path=db_path, cfg=cfg)
    new_rows, duplicate_skips = _filter_new_materials(spent_rows, existing)
    rows_ready = [row for row in new_rows if _text(row.get("video_id"))]
    missing_details = [row for row in new_rows if not _text(row.get("video_id"))]
    batch_size = _int(
        (cfg.get("material_source") if isinstance(cfg.get("material_source"), dict) else {}).get("max_video_ids_per_call"),
        50,
    )
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows_ready:
        grouped[_text(row.get("advertiser_id"))].append(row)
    batches: list[dict[str, Any]] = []
    for advertiser_id, rows in sorted(grouped.items()):
        for index, chunk in enumerate(_chunks(rows, batch_size), start=1):
            batches.append(
                {
                    "batch_key": f"{period_start}_{period_end}_{advertiser_id}_{index}",
                    "source_advertiser_id": advertiser_id,
                    "target_source_advertiser_id": _text(cfg.get("source_advertiser_id")),
                    "video_ids": [_text(row.get("video_id")) for row in chunk],
                    "material_ids": [_text(row.get("material_id")) for row in chunk],
                    "material_count": len(chunk),
                    "stat_cost": round(sum(float(row.get("stat_cost") or 0) for row in chunk), 4),
                    "materials": chunk,
                }
            )
    return {
        "ok": True,
        "workflow": "source_material_account_auto_push_plan",
        "phase": "source_material_account",
        "execution_enabled": False,
        "external_api_calls": 0,
        "product": _text(cfg.get("product")),
        "source_advertiser_id": _text(cfg.get("source_advertiser_id")),
        "organization_id": _text(cfg.get("organization_id")),
        "period_start": period_start,
        "period_end": period_end,
        "summary": {
            "spent_account_count": len({row["advertiser_id"] for row in spent_rows}),
            "spent_material_count": len(spent_rows),
            "source_account_existing_material_count": int(existing["count"]),
            "new_material_count": len(new_rows),
            "ready_material_count": len(rows_ready),
            "missing_video_id_count": len(missing_details),
            "duplicate_skipped_count": len(duplicate_skips),
            "push_batch_count": len(batches),
        },
        "push_batches": batches,
        "missing_detail_materials": missing_details,
        "skipped_materials": duplicate_skips,
        "source_account": {
            "existing_material_count": int(existing["count"]),
            "latest_synced_at": _text(existing["latest_synced_at"]),
        },
    }


def _bind_request(batch: dict[str, Any]) -> dict[str, Any]:
    return {
        "operation": "bind_material",
        "endpoint": BIND_MATERIAL_ENDPOINT,
        "payload": {
            "advertiser_id": int(batch["source_advertiser_id"]) if str(batch["source_advertiser_id"]).isdigit() else batch["source_advertiser_id"],
            "target_advertiser_ids": [
                int(batch["target_source_advertiser_id"])
                if str(batch["target_source_advertiser_id"]).isdigit()
                else batch["target_source_advertiser_id"]
            ],
            "video_ids": list(batch.get("video_ids") or []),
        },
    }


def _execute_batches(
    batches: list[dict[str, Any]],
    *,
    transport: MutationTransport,
    execute_cfg: dict[str, Any],
    sleeper: Sleeper,
) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    external_api_calls = 0
    retry_codes = {str(item) for item in execute_cfg.get("retry_api_codes", [])} if isinstance(execute_cfg.get("retry_api_codes"), list) else set()
    max_retries = _int(execute_cfg.get("max_api_retries"), 0)
    retry_sleep = _float(execute_cfg.get("retry_sleep_seconds") or 1)
    for batch in batches:
        request = _bind_request(batch)
        response: dict[str, Any] = {}
        attempts = max_retries + 1
        for attempt in range(1, attempts + 1):
            response = transport(request)
            external_api_calls += 1
            code = _api_code(response)
            if not code or code not in retry_codes or attempt == attempts:
                break
            sleeper(retry_sleep)
        code = _api_code(response)
        results.append(
            {
                "batch_key": batch["batch_key"],
                "source_advertiser_id": batch["source_advertiser_id"],
                "target_source_advertiser_id": batch["target_source_advertiser_id"],
                "video_count": len(batch.get("video_ids") or []),
                "status": "completed" if not code else "failed",
                "api_code": code,
                "message": _response_message(response),
                "response": response,
            }
        )
    return {
        "external_api_calls": external_api_calls,
        "results": results,
    }


def _blocked_payload(
    cfg: dict[str, Any],
    *,
    runs_dir: str | Path,
    period_start: str,
    period_end: str,
    reasons: list[str],
    plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "ok": False,
        "workflow": "source_material_account_auto_push",
        "phase": "source_material_account",
        "status": "blocked",
        "execution_enabled": False,
        "external_api_calls": 0,
        "summary": {
            "period_start": period_start,
            "period_end": period_end,
            "source_advertiser_id": _text(cfg.get("source_advertiser_id")),
            "push_batch_count": 0,
            "pushed_batch_count": 0,
            "pushed_video_count": 0,
            **((plan or {}).get("summary") if isinstance((plan or {}).get("summary"), dict) else {}),
        },
        "blocking_reasons": reasons,
        "plan": plan or {},
        "results": [],
    }
    artifact = write_run_artifact(runs_dir, "source_material_account_auto_push", payload)
    return {**payload, "artifact_path": str(artifact)}


def run_source_material_account_auto_push_request(
    request: dict[str, Any],
    *,
    db_path: str | Path,
    runs_dir: str | Path,
    readonly_transport: Transport | None = None,
    mutation_transport: MutationTransport | None = None,
    today: date | None = None,
    sleeper: Sleeper | None = None,
) -> dict[str, Any]:
    cfg = _cfg(request)
    period_start, period_end = _date_range(cfg, today=today)
    reasons: list[str] = []
    if not _text(cfg.get("product")):
        reasons.append("missing product")
    if not _text(cfg.get("source_advertiser_id")):
        reasons.append("missing source_advertiser_id")
    if reasons:
        return _blocked_payload(cfg, runs_dir=runs_dir, period_start=period_start, period_end=period_end, reasons=reasons)

    external_api_calls = 0
    readonly_steps: list[dict[str, Any]] = []
    source_sync_cfg = cfg.get("source_account_sync") if isinstance(cfg.get("source_account_sync"), dict) else {}
    if bool(source_sync_cfg.get("enabled", False)):
        if readonly_transport is None:
            reasons.append("source_account_sync enabled requires readonly_transport")
        else:
            sync_result = _sync_source_account(cfg, db_path=db_path, transport=readonly_transport)
            external_api_calls += int(sync_result["external_api_calls"])
            readonly_steps.append({"step": "source_account_sync", **sync_result})

    plan = build_source_material_account_push_plan(
        db_path=db_path,
        cfg=cfg,
        period_start=period_start,
        period_end=period_end,
    )
    detail_cfg = cfg.get("material_detail_fetch") if isinstance(cfg.get("material_detail_fetch"), dict) else {}
    if plan["summary"]["missing_video_id_count"] and bool(detail_cfg.get("enabled", False)):
        if readonly_transport is None:
            reasons.append("material_detail_fetch enabled requires readonly_transport")
        else:
            detail_result = _fetch_missing_details(
                plan["missing_detail_materials"],
                cfg=cfg,
                db_path=db_path,
                transport=readonly_transport,
            )
            external_api_calls += int(detail_result["external_api_calls"])
            readonly_steps.append({"step": "material_detail_fetch", **detail_result})
            plan = build_source_material_account_push_plan(
                db_path=db_path,
                cfg=cfg,
                period_start=period_start,
                period_end=period_end,
            )

    execute_cfg = cfg.get("execute") if isinstance(cfg.get("execute"), dict) else {}
    execute_enabled = bool(execute_cfg.get("enabled", False))
    approved = bool(execute_cfg.get("approved", False))
    if not execute_enabled:
        payload = {
            "ok": not reasons,
            "workflow": "source_material_account_auto_push",
            "phase": "source_material_account",
            "status": "preflight",
            "execution_enabled": False,
            "external_api_calls": external_api_calls,
            "summary": {
                "period_start": period_start,
                "period_end": period_end,
                "source_advertiser_id": _text(cfg.get("source_advertiser_id")),
                **plan["summary"],
                "pushed_batch_count": 0,
                "pushed_video_count": 0,
                "failed_batch_count": 0,
            },
            "blocking_reasons": reasons,
            "readonly_steps": readonly_steps,
            "plan": plan,
            "results": [],
        }
        artifact = write_run_artifact(runs_dir, "source_material_account_auto_push", payload)
        return {**payload, "artifact_path": str(artifact)}

    if not approved:
        reasons.append("execute requires approved=true")
    if mutation_transport is None:
        reasons.append("execute requires mutation_transport")
    if not bool(execute_cfg.get("allow_mutation", False)):
        reasons.append("execute requires allow_mutation=true")
    if reasons:
        return _blocked_payload(cfg, runs_dir=runs_dir, period_start=period_start, period_end=period_end, reasons=reasons, plan=plan)

    execution = _execute_batches(
        plan["push_batches"],
        transport=mutation_transport,
        execute_cfg=execute_cfg,
        sleeper=sleeper or time.sleep,
    )
    external_api_calls += int(execution["external_api_calls"])
    results = execution["results"]
    failed = [item for item in results if item["status"] != "completed"]
    completed = [item for item in results if item["status"] == "completed"]

    verify_cfg = cfg.get("verify_after_execute") if isinstance(cfg.get("verify_after_execute"), dict) else {}
    if bool(verify_cfg.get("enabled", False)) and readonly_transport is not None:
        sync_result = _sync_source_account(cfg, db_path=db_path, transport=readonly_transport)
        external_api_calls += int(sync_result["external_api_calls"])
        readonly_steps.append({"step": "verify_source_account_sync", **sync_result})

    payload = {
        "ok": not failed,
        "workflow": "source_material_account_auto_push",
        "phase": "source_material_account",
        "status": "completed" if not failed else "completed_with_errors",
        "execution_enabled": True,
        "external_api_calls": external_api_calls,
        "summary": {
            "period_start": period_start,
            "period_end": period_end,
            "source_advertiser_id": _text(cfg.get("source_advertiser_id")),
            **plan["summary"],
            "pushed_batch_count": len(completed),
            "pushed_video_count": sum(int(item.get("video_count") or 0) for item in completed),
            "failed_batch_count": len(failed),
        },
        "blocking_reasons": [],
        "readonly_steps": readonly_steps,
        "plan": plan,
        "results": results,
    }
    artifact = write_run_artifact(runs_dir, "source_material_account_auto_push", payload)
    return {**payload, "artifact_path": str(artifact)}
