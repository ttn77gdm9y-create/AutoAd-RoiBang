from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from roibang_v2.config import load_json


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _first_text(row: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = str(row.get(key) or "").strip()
        if value:
            return value
    return ""


def _float_value(row: dict[str, Any], key: str) -> float:
    try:
        return float(str(row.get(key) or "0").replace(",", ""))
    except ValueError:
        return 0.0


def _first_float(row: dict[str, Any], *keys: str) -> float:
    for key in keys:
        value = _float_value(row, key)
        if value:
            return value
    return 0.0


def _json_list(value: Any) -> str:
    if value in (None, ""):
        return "[]"
    if isinstance(value, list):
        items = [str(item).strip() for item in value if str(item).strip()]
        return json.dumps(items, ensure_ascii=False)
    return json.dumps([str(value).strip()], ensure_ascii=False)


def _tag_ids(row: dict[str, Any]) -> str:
    if "tag_ids" in row:
        return _json_list(row.get("tag_ids"))
    if "material_properties" in row:
        return _json_list(row.get("material_properties"))
    tags = row.get("tags")
    if isinstance(tags, list):
        values: list[str] = []
        for tag in tags:
            if isinstance(tag, dict):
                value = _first_text(tag, "tag_id", "id")
            else:
                value = str(tag or "").strip()
            if value:
                values.append(value)
        return json.dumps(values, ensure_ascii=False)
    return "[]"


def _rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("videos", "materials", "items", "list"):
        value = data.get(key)
        if isinstance(value, list):
            return [row for row in value if isinstance(row, dict)]
    return []


def _review_status(row: dict[str, Any]) -> str:
    explicit = _first_text(row, "review_status", "media_review_status", "media_status")
    if explicit:
        return explicit
    audit_result = row.get("audit_result")
    if isinstance(audit_result, dict):
        status = str(audit_result.get("status") or "").strip()
        if status:
            return status
    return ""


def _material_type(row: dict[str, Any]) -> str:
    value = _first_text(row, "material_type", "file_type", "material_kind")
    if value in {"3", "VIDEO", "video"}:
        return "video"
    if value in {"2", "IMAGE", "image"}:
        return "image"
    return value or "video"


def _meta(data: dict[str, Any]) -> dict[str, Any]:
    value = data.get("meta")
    return value if isinstance(value, dict) else {}


def import_product_source_file(path: str | Path, *, db_path: str | Path) -> dict[str, Any]:
    source = Path(path)
    data = load_json(source)
    meta = _meta(data)
    product = str(meta.get("product") or data.get("product") or "").strip()
    source_advertiser_id = str(meta.get("source_advertiser_id") or data.get("source_advertiser_id") or "").strip()
    organization_id = str(meta.get("organization_id") or data.get("organization_id") or "").strip()
    if not product:
        raise ValueError("product source material file missing product")
    if not source_advertiser_id:
        raise ValueError("product source material file missing source_advertiser_id")

    return import_product_source_materials(
        db_path=db_path,
        product=product,
        source_advertiser_id=source_advertiser_id,
        organization_id=organization_id,
        materials=_rows(data),
        source=str(source),
    )


def import_product_source_materials(
    *,
    db_path: str | Path,
    product: str,
    source_advertiser_id: str,
    organization_id: str = "",
    materials: list[dict[str, Any]],
    source: str = "openapi_source_materials",
    mark_absent_inactive: bool = False,
) -> dict[str, Any]:
    product = str(product or "").strip()
    source_advertiser_id = str(source_advertiser_id or "").strip()
    organization_id = str(organization_id or "").strip()
    if not product:
        raise ValueError("product source material file missing product")
    if not source_advertiser_id:
        raise ValueError("product source material file missing source_advertiser_id")

    synced_at = _now_iso()
    materials_imported = 0
    account_imported = 0
    source_imported = 0
    active_material_ids: set[str] = set()
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        for row in materials:
            if not isinstance(row, dict):
                continue
            material_id = _first_text(row, "material_id", "mid", "id")
            if not material_id:
                continue
            video_id = _first_text(row, "video_id", "vid", "id")
            name = _first_text(row, "name", "title", "filename", "material_name", "file_name", "video_name")
            material_type = _material_type(row)
            review_status = _review_status(row)
            cost_lookback = _float_value(row, "cost_lookback") or _float_value(row, "stat_cost")
            score = _float_value(row, "score")
            signature = _first_text(row, "signature", "material_signature", "file_signature", "video_signature", "content_signature", "md5")
            duration = _first_float(row, "duration", "video_duration")
            file_size = _first_float(row, "file_size", "size", "video_size")
            create_time = _first_text(row, "create_time", "created_at", "ctime", "upload_time", "modify_time")
            tag_ids_json = _tag_ids(row)
            payload_json = json.dumps(row, ensure_ascii=False, sort_keys=True)
            active_material_ids.add(material_id)

            conn.execute(
                """
                INSERT INTO materials (
                  material_id, name, material_type, video_id, review_status,
                  cost_lookback, score, payload_json, source, synced_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(material_id) DO UPDATE SET
                  name = excluded.name,
                  material_type = excluded.material_type,
                  video_id = excluded.video_id,
                  review_status = excluded.review_status,
                  cost_lookback = excluded.cost_lookback,
                  score = excluded.score,
                  payload_json = excluded.payload_json,
                  source = excluded.source,
                  synced_at = excluded.synced_at
                """,
                (
                    material_id,
                    name,
                    material_type,
                    video_id,
                    review_status,
                    cost_lookback,
                    score,
                    payload_json,
                    str(source),
                    synced_at,
                ),
            )
            materials_imported += 1

            conn.execute(
                """
                INSERT INTO account_materials (
                  advertiser_id, material_id, video_id, material_type,
                  review_status, cost_lookback, score, source, synced_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(advertiser_id, material_id) DO UPDATE SET
                  video_id = excluded.video_id,
                  material_type = excluded.material_type,
                  review_status = excluded.review_status,
                  cost_lookback = excluded.cost_lookback,
                  score = excluded.score,
                  source = excluded.source,
                  synced_at = excluded.synced_at
                """,
                (
                    source_advertiser_id,
                    material_id,
                    video_id,
                    material_type,
                    review_status,
                    cost_lookback,
                    score,
                    str(source),
                    synced_at,
                ),
            )
            account_imported += 1

            conn.execute(
                """
                INSERT INTO product_source_materials (
                  product, source_advertiser_id, organization_id, material_id,
                  video_id, name, material_type, review_status, signature,
                  duration, file_size, create_time, tag_ids_json, is_active,
                  first_seen_at, last_seen_at, cost_lookback, score,
                  payload_json, source, synced_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(product, source_advertiser_id, material_id) DO UPDATE SET
                  organization_id = excluded.organization_id,
                  video_id = excluded.video_id,
                  name = excluded.name,
                  material_type = excluded.material_type,
                  review_status = excluded.review_status,
                  signature = COALESCE(NULLIF(excluded.signature, ''), product_source_materials.signature),
                  duration = CASE WHEN excluded.duration > 0 THEN excluded.duration ELSE product_source_materials.duration END,
                  file_size = CASE WHEN excluded.file_size > 0 THEN excluded.file_size ELSE product_source_materials.file_size END,
                  create_time = COALESCE(NULLIF(excluded.create_time, ''), product_source_materials.create_time),
                  tag_ids_json = excluded.tag_ids_json,
                  is_active = 1,
                  first_seen_at = COALESCE(NULLIF(product_source_materials.first_seen_at, ''), excluded.first_seen_at),
                  last_seen_at = excluded.last_seen_at,
                  cost_lookback = excluded.cost_lookback,
                  score = excluded.score,
                  payload_json = excluded.payload_json,
                  source = excluded.source,
                  synced_at = excluded.synced_at
                """,
                (
                    product,
                    source_advertiser_id,
                    organization_id,
                    material_id,
                    video_id,
                    name,
                    material_type,
                    review_status,
                    signature,
                    duration,
                    file_size,
                    create_time,
                    tag_ids_json,
                    synced_at,
                    synced_at,
                    cost_lookback,
                    score,
                    payload_json,
                    str(source),
                    synced_at,
                ),
            )
            source_imported += 1
        inactive_rows = 0
        if mark_absent_inactive:
            if active_material_ids:
                placeholders = ",".join("?" for _ in active_material_ids)
                inactive_rows = conn.execute(
                    f"""
                    UPDATE product_source_materials
                    SET is_active = 0, synced_at = ?
                    WHERE product = ?
                      AND source_advertiser_id = ?
                      AND material_id NOT IN ({placeholders})
                    """,
                    (synced_at, product, source_advertiser_id, *sorted(active_material_ids)),
                ).rowcount
            else:
                inactive_rows = conn.execute(
                    """
                    UPDATE product_source_materials
                    SET is_active = 0, synced_at = ?
                    WHERE product = ? AND source_advertiser_id = ?
                    """,
                    (synced_at, product, source_advertiser_id),
                ).rowcount

    return {
        "ok": True,
        "product": product,
        "source_advertiser_id": source_advertiser_id,
        "organization_id": organization_id,
        "materials_imported": materials_imported,
        "product_source_materials_imported": source_imported,
        "inactive_product_source_materials": inactive_rows,
        "external_api_calls": 0,
    }


def select_product_source_materials(
    *,
    db_path: str | Path,
    product: str,
    source_advertiser_id: str,
    material_type: str,
    review_statuses: list[str],
    limit: int,
) -> list[dict[str, Any]]:
    placeholders = ",".join("?" for _ in review_statuses)
    query = f"""
        SELECT
          product, source_advertiser_id, organization_id, material_id, video_id,
          name, material_type, review_status, signature, duration, file_size,
          create_time, tag_ids_json, cost_lookback, score
        FROM product_source_materials
        WHERE product = ?
          AND source_advertiser_id = ?
          AND is_active = 1
          AND material_type = ?
          AND review_status IN ({placeholders})
        ORDER BY cost_lookback DESC, score DESC, material_id ASC
        LIMIT ?
    """
    params = (product, source_advertiser_id, material_type, *review_statuses, limit)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(query, params).fetchall()
    return [
        {
            "product": str(row["product"] or ""),
            "source_advertiser_id": str(row["source_advertiser_id"] or ""),
            "organization_id": str(row["organization_id"] or ""),
            "material_id": str(row["material_id"] or ""),
            "video_id": str(row["video_id"] or ""),
            "name": str(row["name"] or ""),
            "material_type": str(row["material_type"] or ""),
            "review_status": str(row["review_status"] or ""),
            "signature": str(row["signature"] or ""),
            "duration": float(row["duration"] or 0),
            "file_size": float(row["file_size"] or 0),
            "create_time": str(row["create_time"] or ""),
            "tag_ids_json": str(row["tag_ids_json"] or "[]"),
            "cost_lookback": float(row["cost_lookback"] or 0),
            "score": float(row["score"] or 0),
        }
        for row in rows
    ]


def target_existing_material_ids(*, db_path: str | Path, target_advertiser_id: str, material_ids: list[str]) -> set[str]:
    if not material_ids:
        return set()
    placeholders = ",".join("?" for _ in material_ids)
    query = f"""
        SELECT material_id
        FROM account_materials
        WHERE advertiser_id = ?
          AND material_id IN ({placeholders})
    """
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(query, (target_advertiser_id, *material_ids)).fetchall()
    return {str(row[0]) for row in rows}
