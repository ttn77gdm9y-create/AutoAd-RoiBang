from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _lookup_key(value: str) -> str:
    if value.startswith("<lookup:") and value.endswith(">"):
        return value[len("<lookup:") : -1]
    return ""


def _entity_type_for_field(field: str) -> str:
    if field == "project_id":
        return "project"
    if field == "promotion_id":
        return "promotion"
    if field == "video_id":
        return "target_video"
    if field == "video_cover_id":
        return "target_video_cover"
    if field == "target_video_id":
        return "target_video"
    if field == "target_video_cover_id":
        return "target_video_cover"
    return ""


def is_mock_provider_id(value: Any) -> bool:
    return str(value or "").strip().startswith("mock_")


PLAN_SCOPED_ENTITY_TYPES = {"project", "promotion"}
ASSET_SCOPED_ENTITY_TYPES = {"target_video", "target_video_cover"}


def _scope_for_record(entity_type: str, plan_id: str, request_id: str) -> tuple[str, str]:
    if entity_type in PLAN_SCOPED_ENTITY_TYPES:
        return str(plan_id), str(request_id)
    if entity_type in ASSET_SCOPED_ENTITY_TYPES:
        return "", ""
    return str(plan_id), str(request_id)


def record_create_provider_id(
    *,
    db_path: str | Path,
    entity_type: str,
    local_key: str,
    provider_id: str,
    plan_id: str = "",
    request_id: str = "",
    advertiser_id: str = "",
    parent_local_key: str = "",
    source_workflow: str = "",
    response_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    now = _now_iso()
    normalized_entity_type = str(entity_type).strip()
    normalized_local_key = str(local_key).strip()
    normalized_provider_id = str(provider_id).strip()
    scoped_plan_id, scoped_request_id = _scope_for_record(normalized_entity_type, str(plan_id), str(request_id))
    if not normalized_entity_type or not normalized_local_key or not normalized_provider_id:
        raise ValueError("entity_type, local_key and provider_id are required")
    with sqlite3.connect(db_path) as conn:
        existing = conn.execute(
            """
            SELECT provider_id, source_workflow, status
            FROM create_provider_id_ledger
            WHERE entity_type = ? AND local_key = ? AND plan_id = ? AND request_id = ?
            """,
            (normalized_entity_type, normalized_local_key, scoped_plan_id, scoped_request_id),
        ).fetchone()
        existing_provider_id = str(existing[0]) if existing else ""
        existing_source_workflow = str(existing[1]) if existing else ""
        existing_status = str(existing[2]) if existing else ""
        existing_is_reusable = (
            existing_status == "active"
            and not is_mock_provider_id(existing_provider_id)
            and existing_source_workflow != "create_mock_execute"
        )
        if existing and str(existing[0]) != normalized_provider_id and existing_is_reusable:
            return {
                "status": "conflict",
                "entity_type": normalized_entity_type,
                "local_key": normalized_local_key,
                "existing_provider_id": str(existing[0]),
                "provider_id": normalized_provider_id,
                "execution_enabled": False,
                "external_api_calls": 0,
                "actions": [],
            }
        conn.execute(
            """
            INSERT INTO create_provider_id_ledger (
              entity_type, local_key, provider_id, plan_id, request_id, advertiser_id,
              parent_local_key, status, source_workflow, execution_enabled,
              response_payload_json, first_seen_at, last_seen_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(entity_type, local_key, plan_id, request_id) DO UPDATE SET
              provider_id = excluded.provider_id,
              advertiser_id = excluded.advertiser_id,
              parent_local_key = excluded.parent_local_key,
              status = excluded.status,
              source_workflow = excluded.source_workflow,
              execution_enabled = excluded.execution_enabled,
              response_payload_json = excluded.response_payload_json,
              last_seen_at = excluded.last_seen_at
            """,
            (
                normalized_entity_type,
                normalized_local_key,
                normalized_provider_id,
                scoped_plan_id,
                scoped_request_id,
                str(advertiser_id),
                str(parent_local_key),
                "active",
                str(source_workflow),
                0,
                json.dumps(response_payload or {}, ensure_ascii=False, sort_keys=True),
                now,
                now,
            ),
        )
    return {
        "status": "recorded",
        "entity_type": normalized_entity_type,
        "local_key": normalized_local_key,
        "provider_id": normalized_provider_id,
        "execution_enabled": False,
        "external_api_calls": 0,
        "actions": [],
    }


def archive_create_provider_ids(
    *,
    db_path: str | Path,
    plan_id: str = "",
    request_id: str = "",
    entity_types: tuple[str, ...] = ("project", "promotion"),
    local_keys: tuple[str, ...] = (),
    match_any_local_key: bool = False,
    exclude_plan_id: str = "",
    exclude_request_id: str = "",
) -> dict[str, Any]:
    normalized_plan_id = str(plan_id or "").strip()
    normalized_request_id = str(request_id or "").strip()
    normalized_exclude_plan_id = str(exclude_plan_id or "").strip()
    normalized_exclude_request_id = str(exclude_request_id or "").strip()
    normalized_entity_types = tuple(str(item).strip() for item in entity_types if str(item).strip())
    normalized_local_keys = tuple(str(item).strip() for item in local_keys if str(item).strip())
    if not normalized_entity_types or (
        not normalized_plan_id and not normalized_request_id and not normalized_local_keys
    ):
        return {
            "status": "skipped",
            "archived_count": 0,
            "plan_id": normalized_plan_id,
            "request_id": normalized_request_id,
            "entity_types": list(normalized_entity_types),
            "local_key_count": len(normalized_local_keys),
            "execution_enabled": False,
            "external_api_calls": 0,
            "actions": [],
        }
    where = ["status = 'active'"]
    params: list[str] = []
    if normalized_local_keys:
        placeholders = ",".join("?" for _ in normalized_local_keys)
        where.append(f"local_key IN ({placeholders})")
        params.extend(normalized_local_keys)
    if normalized_exclude_plan_id:
        where.append("plan_id != ?")
        params.append(normalized_exclude_plan_id)
    if normalized_exclude_request_id:
        where.append("request_id != ?")
        params.append(normalized_exclude_request_id)
    if normalized_plan_id and not (match_any_local_key and normalized_local_keys):
        where.append("plan_id = ?")
        params.append(normalized_plan_id)
    elif normalized_request_id and not (match_any_local_key and normalized_local_keys):
        where.append("request_id = ?")
        params.append(normalized_request_id)
    placeholders = ",".join("?" for _ in normalized_entity_types)
    where.append(f"entity_type IN ({placeholders})")
    params.extend(normalized_entity_types)
    now = _now_iso()
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            f"""
            UPDATE create_provider_id_ledger
            SET status = 'archived',
                last_seen_at = ?
            WHERE {" AND ".join(where)}
            """,
            [now, *params],
        )
        archived_count = int(conn.execute("SELECT changes()").fetchone()[0] or 0)
    return {
        "status": "archived" if archived_count else "no_active_records",
        "archived_count": archived_count,
        "plan_id": normalized_plan_id,
        "request_id": normalized_request_id,
        "entity_types": list(normalized_entity_types),
        "local_key_count": len(normalized_local_keys),
        "execution_enabled": False,
        "external_api_calls": 0,
        "actions": [],
    }


def resolve_create_lookup_placeholders(
    *,
    db_path: str | Path,
    payload: dict[str, Any],
    plan_id: str = "",
    request_id: str = "",
) -> dict[str, Any]:
    unresolved: list[dict[str, str]] = []
    lookup_count = 0
    resolved_count = 0

    def resolve_value(conn: sqlite3.Connection, value: Any, *, field: str) -> Any:
        nonlocal lookup_count, resolved_count
        if isinstance(value, dict):
            return {key: resolve_value(conn, item, field=str(key)) for key, item in value.items()}
        if isinstance(value, list):
            return [resolve_value(conn, item, field=field) for item in value]
        text = str(value) if isinstance(value, str) else ""
        local_key = _lookup_key(text)
        if not local_key:
            return value
        lookup_count += 1
        entity_type = _entity_type_for_field(str(field))
        params: tuple[str, ...]
        where = "local_key = ? AND status = 'active'"
        params_list: list[str] = [local_key]
        if entity_type:
            where += " AND entity_type = ?"
            params_list.append(entity_type)
            scoped_plan_id, scoped_request_id = _scope_for_record(entity_type, str(plan_id), str(request_id))
            if entity_type in PLAN_SCOPED_ENTITY_TYPES:
                where += " AND plan_id = ? AND request_id = ?"
                params_list.extend([scoped_plan_id, scoped_request_id])
        params = tuple(params_list)
        row = conn.execute(
            f"""
            SELECT provider_id
            FROM create_provider_id_ledger
            WHERE {where}
              AND provider_id NOT LIKE 'mock_%'
              AND source_workflow != 'create_mock_execute'
            ORDER BY entity_type
            LIMIT 1
            """,
            params,
        ).fetchone()
        if row:
            resolved_count += 1
            return str(row[0])
        unresolved.append({"field": str(field), "placeholder": text, "local_key": local_key})
        return value

    with sqlite3.connect(db_path) as conn:
        resolved_payload = {field: resolve_value(conn, value, field=str(field)) for field, value in payload.items()}
    return {
        "status": "resolved" if not unresolved else "blocked",
        "lookup_count": lookup_count,
        "resolved_count": resolved_count,
        "unresolved_count": len(unresolved),
        "unresolved_placeholders": unresolved,
        "resolved_payload": resolved_payload,
        "execution_enabled": False,
        "external_api_calls": 0,
        "actions": [],
    }


def resolve_provider_payload_drafts(
    *,
    db_path: str | Path,
    provider_payload_drafts: list[dict[str, Any]],
    plan_id: str = "",
    request_id: str = "",
) -> dict[str, Any]:
    resolved_drafts: list[dict[str, Any]] = []
    unresolved_placeholders: list[dict[str, str]] = []
    lookup_count = 0
    resolved_count = 0
    for draft in provider_payload_drafts:
        if not isinstance(draft, dict):
            continue
        payload = draft.get("payload") if isinstance(draft.get("payload"), dict) else {}
        resolution = resolve_create_lookup_placeholders(
            db_path=db_path,
            payload=payload,
            plan_id=plan_id,
            request_id=request_id,
        )
        lookup_count += int(resolution.get("lookup_count") or 0)
        resolved_count += int(resolution.get("resolved_count") or 0)
        for item in resolution.get("unresolved_placeholders") or []:
            if not isinstance(item, dict):
                continue
            unresolved_placeholders.append(
                {
                    "operation": str(draft.get("operation") or ""),
                    "field": str(item.get("field") or ""),
                    "placeholder": str(item.get("placeholder") or ""),
                    "local_key": str(item.get("local_key") or ""),
                }
            )
        resolved_drafts.append(
            {
                **draft,
                "payload": resolution["resolved_payload"],
                "executable": False,
                "live_api_payload": False,
                "lookup_resolution_status": str(resolution.get("status") or ""),
            }
        )
    return {
        "status": "resolved" if not unresolved_placeholders else "blocked",
        "draft_count": len(resolved_drafts),
        "lookup_count": lookup_count,
        "resolved_count": resolved_count,
        "unresolved_count": len(unresolved_placeholders),
        "unresolved_placeholders": unresolved_placeholders,
        "resolved_provider_payload_drafts": resolved_drafts,
        "execution_enabled": False,
        "external_api_calls": 0,
        "actions": [],
    }
