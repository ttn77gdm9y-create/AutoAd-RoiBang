from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _normalized_list(values: list[Any]) -> list[str]:
    return sorted(str(value) for value in values if str(value or "").strip())


def build_material_bind_key(
    *,
    source_advertiser_id: str,
    target_advertiser_ids: list[Any],
    source_video_ids: list[Any],
) -> str:
    canonical = {
        "source_advertiser_id": str(source_advertiser_id or ""),
        "target_advertiser_ids": _normalized_list(target_advertiser_ids),
        "source_video_ids": _normalized_list(source_video_ids),
    }
    payload = json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _payload_lists(payload: dict[str, Any]) -> tuple[str, list[Any], list[Any]]:
    target_ids = payload.get("target_advertiser_ids")
    video_ids = payload.get("source_video_ids")
    if not isinstance(video_ids, list):
        video_ids = payload.get("video_ids")
    return (
        str(payload.get("source_advertiser_id") or payload.get("advertiser_id") or ""),
        list(target_ids) if isinstance(target_ids, list) else [],
        list(video_ids) if isinstance(video_ids, list) else [],
    )


def material_bind_key_from_payload(payload: dict[str, Any]) -> str:
    source_advertiser_id, target_advertiser_ids, source_video_ids = _payload_lists(payload)
    return build_material_bind_key(
        source_advertiser_id=source_advertiser_id,
        target_advertiser_ids=target_advertiser_ids,
        source_video_ids=source_video_ids,
    )


def existing_material_bind_result(*, db_path: str | Path, payload: dict[str, Any]) -> dict[str, Any] | None:
    bind_key = material_bind_key_from_payload(payload)
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT bind_key, source_advertiser_id, target_advertiser_ids_json,
                   source_video_ids_json, provider_task_id, status
            FROM create_material_bind_ledger
            WHERE bind_key = ? AND status = 'active'
            LIMIT 1
            """,
            (bind_key,),
        ).fetchone()
    if not row:
        return None
    return {
        "bind_key": str(row[0]),
        "source_advertiser_id": str(row[1]),
        "target_advertiser_ids": json.loads(str(row[2] or "[]")),
        "source_video_ids": json.loads(str(row[3] or "[]")),
        "provider_task_id": str(row[4]),
        "status": str(row[5]),
    }


def record_create_material_bind_result(
    *,
    db_path: str | Path,
    source_advertiser_id: str,
    target_advertiser_ids: list[Any],
    source_video_ids: list[Any],
    provider_task_id: str = "",
    plan_id: str = "",
    request_id: str = "",
    source_workflow: str = "",
    response_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    now = _now_iso()
    normalized_target_ids = _normalized_list(target_advertiser_ids)
    normalized_video_ids = _normalized_list(source_video_ids)
    bind_key = build_material_bind_key(
        source_advertiser_id=source_advertiser_id,
        target_advertiser_ids=normalized_target_ids,
        source_video_ids=normalized_video_ids,
    )
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO create_material_bind_ledger (
              bind_key, source_advertiser_id, target_advertiser_ids_json,
              source_video_ids_json, provider_task_id, plan_id, request_id,
              status, source_workflow, execution_enabled, response_payload_json,
              first_seen_at, last_seen_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(bind_key) DO UPDATE SET
              source_advertiser_id = excluded.source_advertiser_id,
              target_advertiser_ids_json = excluded.target_advertiser_ids_json,
              source_video_ids_json = excluded.source_video_ids_json,
              provider_task_id = excluded.provider_task_id,
              plan_id = excluded.plan_id,
              request_id = excluded.request_id,
              status = excluded.status,
              source_workflow = excluded.source_workflow,
              execution_enabled = excluded.execution_enabled,
              response_payload_json = excluded.response_payload_json,
              last_seen_at = excluded.last_seen_at
            """,
            (
                bind_key,
                str(source_advertiser_id or ""),
                json.dumps(normalized_target_ids, ensure_ascii=False),
                json.dumps(normalized_video_ids, ensure_ascii=False),
                str(provider_task_id or ""),
                str(plan_id or ""),
                str(request_id or ""),
                "active",
                str(source_workflow or ""),
                0,
                json.dumps(response_payload or {}, ensure_ascii=False, sort_keys=True),
                now,
                now,
            ),
        )
    return {
        "status": "recorded",
        "bind_key": bind_key,
        "source_advertiser_id": str(source_advertiser_id or ""),
        "target_advertiser_ids": normalized_target_ids,
        "source_video_ids": normalized_video_ids,
        "provider_task_id": str(provider_task_id or ""),
        "execution_enabled": False,
        "external_api_calls": 0,
        "actions": [],
    }


def record_create_material_bind_from_payload(
    *,
    db_path: str | Path,
    payload: dict[str, Any],
    provider_task_id: str = "",
    plan_id: str = "",
    request_id: str = "",
    source_workflow: str = "",
    response_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    source_advertiser_id, target_advertiser_ids, source_video_ids = _payload_lists(payload)
    return record_create_material_bind_result(
        db_path=db_path,
        source_advertiser_id=source_advertiser_id,
        target_advertiser_ids=target_advertiser_ids,
        source_video_ids=source_video_ids,
        provider_task_id=provider_task_id,
        plan_id=plan_id,
        request_id=request_id,
        source_workflow=source_workflow,
        response_payload=response_payload,
    )
