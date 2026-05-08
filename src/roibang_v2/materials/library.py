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


def _cache_rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("videos", "materials", "items", "list"):
        rows = data.get(key)
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
    return []


def _advertiser_id(path: Path, data: dict[str, Any]) -> str:
    meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}
    value = str(meta.get("advertiser_id") or data.get("advertiser_id") or "").strip()
    if value:
        return value
    raise ValueError(f"material cache missing advertiser_id: {path}")


def import_material_cache_file(path: str | Path, *, db_path: str | Path) -> dict[str, Any]:
    source = Path(path)
    data = load_json(source)
    advertiser_id = _advertiser_id(source, data)
    rows = _cache_rows(data)
    synced_at = _now_iso()
    materials_imported = 0
    account_materials_imported = 0

    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        for row in rows:
            material_id = _first_text(row, "material_id", "mid", "id")
            if not material_id:
                continue
            video_id = _first_text(row, "video_id", "vid")
            name = _first_text(row, "name", "filename", "material_name", "file_name", "video_name")
            material_type = _first_text(row, "material_type", "file_type") or "video"
            review_status = _first_text(row, "review_status", "media_review_status")
            cost_lookback = _float_value(row, "cost_lookback")
            score = _float_value(row, "score")
            payload_json = json.dumps(row, ensure_ascii=False, sort_keys=True)

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
                    advertiser_id,
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
            account_materials_imported += 1

    return {
        "ok": True,
        "advertiser_id": advertiser_id,
        "materials_imported": materials_imported,
        "account_materials_imported": account_materials_imported,
        "external_api_calls": 0,
    }


def count_available_materials(
    *,
    db_path: str | Path,
    advertiser_id: str,
    material_type: str,
    review_statuses: list[str],
) -> int:
    placeholders = ",".join("?" for _ in review_statuses)
    query = f"""
        SELECT COUNT(*)
        FROM account_materials
        WHERE advertiser_id = ?
          AND material_type = ?
          AND review_status IN ({placeholders})
    """
    with sqlite3.connect(db_path) as conn:
        return int(conn.execute(query, (advertiser_id, material_type, *review_statuses)).fetchone()[0])
