from __future__ import annotations

import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from roibang_v2.runs import write_run_artifact


_KNOWN_KINDS = {"video", "title", "image", "trial_play", "instant_play"}


def _config(request: dict[str, Any]) -> dict[str, Any]:
    value = request.get("material_kind_reconcile")
    return dict(value) if isinstance(value, dict) else dict(request)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _date_filter(cfg: dict[str, Any]) -> tuple[str, list[Any], dict[str, str]]:
    value = cfg.get("date_range") if isinstance(cfg.get("date_range"), dict) else {}
    start = str(value.get("start") or "").strip()
    end = str(value.get("end") or "").strip()
    if not start and not end:
        return "", [], {}
    if not start or not end:
        raise ValueError("material_kind_reconcile.date_range requires both start and end")
    return " AND metric_date BETWEEN ? AND ? ", [start, end], {"start": start, "end": end}


def _normalize_kind(value: Any) -> str:
    text = str(value or "").strip().lower()
    aliases = {
        "素材视频": "video",
        "视频": "video",
        "video_material": "video",
        "title_material": "title",
        "text": "title",
        "文案": "title",
        "标题": "title",
        "image_material": "image",
        "图片": "image",
    }
    normalized = aliases.get(text, text)
    return normalized if normalized in _KNOWN_KINDS else ""


def _add_evidence(evidence: dict[str, Counter[str]], material_id: Any, material_kind: Any) -> None:
    material = str(material_id or "").strip()
    kind = _normalize_kind(material_kind)
    if material and kind:
        evidence[material][kind] += 1


def _dominant_kind(counter: Counter[str]) -> str:
    if not counter:
        return ""
    ordered = counter.most_common()
    if len(ordered) > 1 and ordered[0][1] == ordered[1][1]:
        return ""
    return ordered[0][0]


def _kind_evidence(conn: sqlite3.Connection) -> dict[str, str]:
    evidence: dict[str, Counter[str]] = defaultdict(Counter)
    for material_id, material_kind in conn.execute(
        """
        SELECT material_id, material_kind
        FROM material_bindings
        WHERE TRIM(material_id) != ''
          AND TRIM(material_kind) != ''
        """
    ):
        _add_evidence(evidence, material_id, material_kind)
    for material_id, material_kind in conn.execute(
        """
        SELECT material_id, material_kind
        FROM material_profiles
        WHERE TRIM(material_id) != ''
          AND TRIM(material_kind) != ''
        """
    ):
        _add_evidence(evidence, material_id, material_kind)
    for material_id, material_type in conn.execute(
        """
        SELECT material_id, material_type
        FROM account_materials
        WHERE TRIM(material_id) != ''
          AND TRIM(material_type) != ''
        """
    ):
        _add_evidence(evidence, material_id, material_type)
    for material_id, material_type in conn.execute(
        """
        SELECT material_id, material_type
        FROM product_source_materials
        WHERE TRIM(material_id) != ''
          AND TRIM(material_type) != ''
        """
    ):
        _add_evidence(evidence, material_id, material_type)
    for source_material_id, target_material_id in conn.execute(
        """
        SELECT source_material_id, target_material_id
        FROM material_source_mappings
        WHERE TRIM(source_material_id) != ''
           OR TRIM(target_material_id) != ''
        """
    ):
        _add_evidence(evidence, source_material_id, "video")
        _add_evidence(evidence, target_material_id, "video")
    return {material_id: kind for material_id, counter in evidence.items() if (kind := _dominant_kind(counter))}


def _video_evidence_material_ids(conn: sqlite3.Connection) -> set[str]:
    ids: set[str] = set()
    for material_id, video_id, material_kind in conn.execute(
        """
        SELECT material_id, video_id, material_kind
        FROM material_profiles
        WHERE TRIM(material_id) != ''
        """
    ):
        if _normalize_kind(material_kind) == "video" and str(video_id or "").strip():
            ids.add(str(material_id or "").strip())
    for material_id, video_id, material_type in conn.execute(
        """
        SELECT material_id, video_id, material_type
        FROM account_materials
        WHERE TRIM(material_id) != ''
        """
    ):
        if _normalize_kind(material_type) == "video" and str(video_id or "").strip():
            ids.add(str(material_id or "").strip())
    for material_id, video_id, material_type in conn.execute(
        """
        SELECT material_id, video_id, material_type
        FROM product_source_materials
        WHERE TRIM(material_id) != ''
        """
    ):
        if _normalize_kind(material_type) == "video" and str(video_id or "").strip():
            ids.add(str(material_id or "").strip())
    for material_id, video_id, material_kind in conn.execute(
        """
        SELECT material_id, video_id, material_kind
        FROM material_bindings
        WHERE TRIM(material_id) != ''
        """
    ):
        if _normalize_kind(material_kind) == "video" and str(video_id or "").strip():
            ids.add(str(material_id or "").strip())
    for source_material_id, target_material_id, source_video_id, target_video_id in conn.execute(
        """
        SELECT source_material_id, target_material_id, source_video_id, target_video_id
        FROM material_source_mappings
        """
    ):
        if str(source_material_id or "").strip() and str(source_video_id or "").strip():
            ids.add(str(source_material_id or "").strip())
        if str(target_material_id or "").strip() and str(target_video_id or "").strip():
            ids.add(str(target_material_id or "").strip())
    return ids


def run_material_kind_reconcile_request(
    request: dict[str, Any],
    *,
    db_path: str | Path,
    runs_dir: str | Path,
) -> dict[str, Any]:
    cfg = _config(request)
    date_sql, date_params, date_range = _date_filter(cfg)
    synced_at = _utc_now()
    updates_by_kind: Counter[str] = Counter()
    material_ids_updated: set[str] = set()
    rows_updated = 0
    evidence_count = 0
    unresolved_video_material_ids_updated = 0
    with sqlite3.connect(db_path) as conn:
        evidence = _kind_evidence(conn)
        video_evidence = _video_evidence_material_ids(conn)
        evidence_count = len(evidence)
        current_rows = conn.execute(
            f"""
            SELECT material_id, material_kind, COUNT(*) AS row_count
            FROM material_daily_metrics
            WHERE TRIM(material_id) != ''
              {date_sql}
            GROUP BY material_id, material_kind
            """,
            tuple(date_params),
        ).fetchall()
        for material_id, material_kind, row_count in current_rows:
            material_id_text = str(material_id or "").strip()
            resolved_kind = evidence.get(material_id_text, "")
            if not resolved_kind:
                continue
            if _normalize_kind(material_kind) == resolved_kind:
                continue
            cursor = conn.execute(
                f"""
                UPDATE material_daily_metrics
                SET material_kind = ?,
                    synced_at = ?
                WHERE material_id = ?
                  {date_sql}
                  AND COALESCE(material_kind, '') != ?
                """,
                (resolved_kind, synced_at, material_id_text, *date_params, resolved_kind),
            )
            changed = int(cursor.rowcount or 0)
            if changed:
                rows_updated += changed
                material_ids_updated.add(material_id_text)
                updates_by_kind[resolved_kind] += int(row_count or changed)
        if bool(cfg.get("mark_unresolved_video_as_unknown", False)):
            unresolved_video_rows = int(
                conn.execute(
                    f"""
                    WITH video_evidence AS (
                      SELECT material_id
                      FROM material_profiles
                      WHERE TRIM(material_id) != ''
                        AND material_kind = 'video'
                        AND TRIM(video_id) != ''
                      UNION
                      SELECT material_id
                      FROM account_materials
                      WHERE TRIM(material_id) != ''
                        AND material_type = 'video'
                        AND TRIM(video_id) != ''
                      UNION
                      SELECT material_id
                      FROM product_source_materials
                      WHERE TRIM(material_id) != ''
                        AND material_type = 'video'
                        AND TRIM(video_id) != ''
                      UNION
                      SELECT material_id
                      FROM material_bindings
                      WHERE TRIM(material_id) != ''
                        AND material_kind = 'video'
                        AND TRIM(video_id) != ''
                      UNION
                      SELECT source_material_id
                      FROM material_source_mappings
                      WHERE TRIM(source_material_id) != ''
                        AND TRIM(source_video_id) != ''
                      UNION
                      SELECT target_material_id
                      FROM material_source_mappings
                      WHERE TRIM(target_material_id) != ''
                        AND TRIM(target_video_id) != ''
                    )
                    SELECT COUNT(*)
                    FROM material_daily_metrics
                    WHERE COALESCE(material_kind, '') = 'video'
                      {date_sql}
                      AND material_id NOT IN (SELECT material_id FROM video_evidence)
                    """,
                    tuple(date_params),
                ).fetchone()[0]
                or 0
            )
            before_unknown = int(
                conn.execute(
                    f"""
                    SELECT COUNT(DISTINCT material_id)
                    FROM material_daily_metrics
                    WHERE material_kind = 'unknown'
                      {date_sql}
                    """,
                    tuple(date_params),
                ).fetchone()[0]
                or 0
            )
            params = [synced_at, *date_params]
            cursor = conn.execute(
                f"""
                WITH video_evidence AS (
                  SELECT material_id
                  FROM material_profiles
                  WHERE TRIM(material_id) != ''
                    AND material_kind = 'video'
                    AND TRIM(video_id) != ''
                  UNION
                  SELECT material_id
                  FROM account_materials
                  WHERE TRIM(material_id) != ''
                    AND material_type = 'video'
                    AND TRIM(video_id) != ''
                  UNION
                  SELECT material_id
                  FROM product_source_materials
                  WHERE TRIM(material_id) != ''
                    AND material_type = 'video'
                    AND TRIM(video_id) != ''
                  UNION
                  SELECT material_id
                  FROM material_bindings
                  WHERE TRIM(material_id) != ''
                    AND material_kind = 'video'
                    AND TRIM(video_id) != ''
                  UNION
                  SELECT source_material_id
                  FROM material_source_mappings
                  WHERE TRIM(source_material_id) != ''
                    AND TRIM(source_video_id) != ''
                  UNION
                  SELECT target_material_id
                  FROM material_source_mappings
                  WHERE TRIM(target_material_id) != ''
                    AND TRIM(target_video_id) != ''
                )
                UPDATE material_daily_metrics
                SET material_kind = 'unknown',
                    synced_at = ?
                WHERE COALESCE(material_kind, '') = 'video'
                  {date_sql}
                  AND material_id NOT IN (SELECT material_id FROM video_evidence)
                """,
                tuple(params),
            )
            changed = unresolved_video_rows
            after_unknown = int(
                conn.execute(
                    f"""
                    SELECT COUNT(DISTINCT material_id)
                    FROM material_daily_metrics
                    WHERE material_kind = 'unknown'
                      {date_sql}
                    """,
                    tuple(date_params),
                ).fetchone()[0]
                or 0
            )
            if changed or after_unknown > before_unknown:
                rows_updated += changed
                unresolved_video_material_ids_updated = max(after_unknown - before_unknown, 0)
                updates_by_kind["unknown"] += changed
    payload = {
        "ok": True,
        "workflow": "material_kind_reconcile",
        "phase": "phase1",
        "execution_enabled": False,
        "external_api_calls": 0,
        "date_range": date_range,
        "summary": {
            "evidence_material_count": evidence_count,
            "material_ids_updated": len(material_ids_updated) + unresolved_video_material_ids_updated,
            "unresolved_video_material_ids_updated": unresolved_video_material_ids_updated,
            "rows_updated": rows_updated,
            "updates_by_kind": dict(sorted(updates_by_kind.items())),
        },
        "guardrails": {
            "external_api_calls": 0,
            "business_actions": [],
            "writes": ["material_daily_metrics", "run_artifact"],
        },
    }
    artifact_path = write_run_artifact(runs_dir, "material_kind_reconcile", payload)
    return {**payload, "artifact_path": str(artifact_path)}
