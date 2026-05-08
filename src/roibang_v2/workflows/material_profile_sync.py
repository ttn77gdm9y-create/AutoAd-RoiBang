from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from roibang_v2.config import load_json
from roibang_v2.fetch.openapi_executor import Transport
from roibang_v2.fetch.openapi_executor import execute_openapi_readonly_plan
from roibang_v2.fetch.openapi_readonly import build_readonly_request
from roibang_v2.fetch.workbench_material_center import WorkbenchMaterialCenterOpener
from roibang_v2.fetch.workbench_material_center import fetch_video_materials
from roibang_v2.materials.product_source import import_product_source_materials
from roibang_v2.runs import write_run_artifact


def _config(request: dict[str, Any]) -> dict[str, Any]:
    value = request.get("material_profile_sync")
    return dict(value) if isinstance(value, dict) else dict(request)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _first_text(row: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = str(row.get(key) or "").strip()
        if value:
            return value
    return ""


def _float_value(row: dict[str, Any], *keys: str) -> float:
    for key in keys:
        value = str(row.get(key) or "").replace(",", "").strip()
        if not value:
            continue
        try:
            return float(value)
        except ValueError:
            continue
    return 0.0


def _bool_int(row: dict[str, Any], key: str) -> int:
    value = row.get(key)
    if isinstance(value, bool):
        return 1 if value else 0
    if isinstance(value, int | float):
        return 1 if value else 0
    text = str(value or "").strip().lower()
    return 1 if text in {"1", "true", "yes", "y"} else 0


def _json_list(row: dict[str, Any], key: str) -> str:
    value = row.get(key)
    items = value if isinstance(value, list) else []
    return json.dumps(items, ensure_ascii=False, sort_keys=True)


def _rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    nested = data.get("data")
    if isinstance(nested, dict):
        nested_rows = _rows(nested)
        if nested_rows:
            return nested_rows
    for key in ("materials", "videos", "items", "list", "rows"):
        value = data.get(key)
        if isinstance(value, list):
            return [row for row in value if isinstance(row, dict)]
    return []


def _review_status(row: dict[str, Any]) -> str:
    explicit = _first_text(row, "review_status", "media_review_status", "media_status", "status")
    if explicit:
        return explicit
    audit_result = row.get("audit_result")
    if isinstance(audit_result, dict):
        return _first_text(audit_result, "status", "review_status")
    return ""


def _video_id(row: dict[str, Any], material_id: str) -> str:
    explicit = _first_text(row, "video_id", "vid")
    if explicit:
        return explicit
    fallback_id = _first_text(row, "id")
    if fallback_id and fallback_id != material_id:
        return fallback_id
    return ""


def _canonical_material_key(*, material_id: str) -> str:
    return f"material:{material_id}"


def _material_kind(row: dict[str, Any], *, image_id: str, video_id: str) -> str:
    explicit = _first_text(row, "material_kind", "file_type")
    if explicit:
        return explicit
    material_type = _first_text(row, "material_type")
    if material_type.lower() in {"video", "image"}:
        return material_type.lower()
    if image_id and not video_id and not _first_text(row, "video_url"):
        return "image"
    return "video"


def _date_filter_sql(cfg: dict[str, Any]) -> tuple[str, list[Any]]:
    value = cfg.get("date_range") if isinstance(cfg.get("date_range"), dict) else {}
    start = str(value.get("start") or "").strip()
    end = str(value.get("end") or "").strip()
    if not start and not end:
        return "", []
    if not start or not end:
        raise ValueError("material_profile_sync.date_range requires both start and end")
    return " AND metric_date BETWEEN ? AND ? ", [start, end]


def _limits(cfg: dict[str, Any]) -> dict[str, int]:
    value = cfg.get("limits") if isinstance(cfg.get("limits"), dict) else {}
    return {
        "max_accounts": int(value.get("max_accounts") or 0),
        "max_pages": int(value.get("max_pages") or cfg.get("max_pages") or 20),
    }


def _known_material_count(conn: sqlite3.Connection, cfg: dict[str, Any]) -> int:
    date_sql, params = _date_filter_sql(cfg)
    return int(
        conn.execute(
            f"""
            SELECT COUNT(DISTINCT material_id)
            FROM material_daily_metrics
            WHERE TRIM(material_id) != ''
            {date_sql}
            """,
            tuple(params),
        ).fetchone()[0]
        or 0
    )


def _missing_material_count(conn: sqlite3.Connection, cfg: dict[str, Any]) -> int:
    date_sql, params = _date_filter_sql(cfg)
    return int(
        conn.execute(
            f"""
            SELECT COUNT(DISTINCT mdm.material_id)
            FROM material_daily_metrics mdm
            LEFT JOIN material_profiles mp
              ON mp.material_id = mdm.material_id
            WHERE TRIM(mdm.material_id) != ''
              AND mp.material_id IS NULL
              {date_sql}
            """,
            tuple(params),
        ).fetchone()[0]
        or 0
    )


def _source_accounts_from_metrics(
    *,
    conn: sqlite3.Connection,
    cfg: dict[str, Any],
) -> list[dict[str, Any]]:
    date_sql, params = _date_filter_sql(cfg)
    skip_profiled = bool(cfg.get("skip_profiled_materials", True))
    profile_sql = ""
    if skip_profiled:
        profile_sql = """
              AND NOT EXISTS (
                SELECT 1
                FROM material_profiles mp
                WHERE mp.material_id = mdm.material_id
              )
        """
    rows = conn.execute(
        f"""
        SELECT
          advertiser_id,
          COUNT(DISTINCT material_id) AS material_count,
          ROUND(COALESCE(SUM(stat_cost), 0), 4) AS stat_cost
        FROM material_daily_metrics mdm
        WHERE TRIM(advertiser_id) != ''
          AND TRIM(material_id) != ''
          {date_sql}
          {profile_sql}
        GROUP BY advertiser_id
        ORDER BY stat_cost DESC, material_count DESC, advertiser_id
        """,
        tuple(params),
    ).fetchall()
    accounts = [
        {
            "advertiser_id": str(advertiser_id),
            "material_count": int(material_count or 0),
            "stat_cost": float(stat_cost or 0),
        }
        for advertiser_id, material_count, stat_cost in rows
    ]
    max_accounts = _limits(cfg)["max_accounts"]
    return accounts[:max_accounts] if max_accounts > 0 else accounts


def _material_id_chunk_size(cfg: dict[str, Any]) -> int:
    value = int(cfg.get("material_id_chunk_size") or 100)
    if value < 1:
        raise ValueError("material_profile_sync.material_id_chunk_size must be positive")
    return value


def _chunked(values: list[str], size: int) -> list[list[str]]:
    return [values[start : start + size] for start in range(0, len(values), size)]


def _openapi_material_ids(values: list[str]) -> list[int | str]:
    result: list[int | str] = []
    for value in values:
        text = str(value).strip()
        if text.isdigit():
            result.append(int(text))
        elif text:
            result.append(text)
    return result


def _endpoint_sequence(cfg: dict[str, Any]) -> list[str]:
    configured = cfg.get("endpoint_sequence")
    if isinstance(configured, list):
        sequence = [str(item).strip() for item in configured if str(item).strip()]
        if sequence:
            return sequence
    return [str(cfg.get("endpoint") or "video_material_get")]


def _material_lookup_params(
    *,
    endpoint_key: str,
    cfg: dict[str, Any],
    account: str,
    chunk: list[str],
    page_size: int,
) -> dict[str, Any]:
    material_ids = _openapi_material_ids(chunk)
    if endpoint_key == "ebp_video_material_get":
        return {
            "advertiser_id": account,
            "filtering": {"material_ids": material_ids},
            "page": 1,
            "page_size": min(page_size, max(1, len(chunk))),
        }
    if endpoint_key == "material_attributes_list":
        return {
            "account_id": account,
            "account_type": str(cfg.get("account_type") or "AD"),
            "filtering": {"material_ids": material_ids},
            "return_lowquality_suggestions": bool(cfg.get("return_lowquality_suggestions", True)),
            "page": 1,
            "page_size": min(page_size, max(1, len(chunk))),
        }
    return {
        "advertiser_id": account,
        "filtering": {"material_ids": material_ids},
        "page": 1,
        "page_size": min(page_size, max(1, len(chunk))),
    }


def _missing_material_lookup_requests(
    *,
    conn: sqlite3.Connection,
    cfg: dict[str, Any],
    endpoint_key: str | None = None,
) -> tuple[list[dict[str, Any]], int]:
    date_sql, params = _date_filter_sql(cfg)
    resolved_endpoint_key = str(endpoint_key or cfg.get("endpoint") or "video_material_get")
    lookup_accounts_from = str(cfg.get("lookup_accounts_from") or "material_daily_metrics").strip()
    if resolved_endpoint_key != "material_attributes_list" and lookup_accounts_from == "source_accounts":
        return _source_account_material_lookup_requests(conn=conn, cfg=cfg, endpoint_key=resolved_endpoint_key)
    if resolved_endpoint_key == "material_attributes_list":
        account_type = str(cfg.get("account_type") or "AD")
        rows = conn.execute(
            f"""
            SELECT
              mdm.advertiser_id,
              mdm.material_id,
              ROUND(COALESCE(SUM(mdm.stat_cost), 0), 4) AS stat_cost
            FROM material_daily_metrics mdm
            LEFT JOIN material_attribute_snapshots mas
              ON mas.material_id = mdm.material_id
             AND mas.account_id = mdm.advertiser_id
             AND mas.account_type = ?
            WHERE TRIM(mdm.advertiser_id) != ''
              AND TRIM(mdm.material_id) != ''
              AND mas.material_id IS NULL
              {date_sql}
            GROUP BY mdm.advertiser_id, mdm.material_id
            ORDER BY stat_cost DESC, mdm.advertiser_id, mdm.material_id
            """,
            (account_type, *params),
        ).fetchall()
    else:
        rows = conn.execute(
            f"""
            SELECT
              mdm.advertiser_id,
              mdm.material_id,
              ROUND(COALESCE(SUM(mdm.stat_cost), 0), 4) AS stat_cost
            FROM material_daily_metrics mdm
            LEFT JOIN material_profiles mp
              ON mp.material_id = mdm.material_id
            WHERE TRIM(mdm.advertiser_id) != ''
              AND TRIM(mdm.material_id) != ''
              AND mp.material_id IS NULL
              {date_sql}
            GROUP BY mdm.advertiser_id, mdm.material_id
            ORDER BY stat_cost DESC, mdm.advertiser_id, mdm.material_id
            """,
            tuple(params),
        ).fetchall()
    grouped: dict[str, list[tuple[str, float]]] = {}
    account_costs: dict[str, float] = {}
    for advertiser_id, material_id, stat_cost in rows:
        account = str(advertiser_id)
        cost = float(stat_cost or 0)
        grouped.setdefault(account, []).append((str(material_id), cost))
        account_costs[account] = account_costs.get(account, 0.0) + cost
    ordered_accounts = sorted(
        grouped,
        key=lambda account: (-account_costs[account], -len(grouped[account]), account),
    )
    max_accounts = _limits(cfg)["max_accounts"]
    if max_accounts > 0:
        ordered_accounts = ordered_accounts[:max_accounts]
    chunk_size = _material_id_chunk_size(cfg)
    page_size = int(cfg.get("page_size") or chunk_size)
    requests: list[dict[str, Any]] = []
    for account in ordered_accounts:
        material_ids = [material_id for material_id, _cost in grouped[account]]
        for chunk in _chunked(material_ids, chunk_size):
            requests.append(
                {
                    "account": {
                        "advertiser_id": account,
                        "material_count": len(chunk),
                        "stat_cost": round(account_costs[account], 4),
                    },
                    **build_readonly_request(
                        resolved_endpoint_key,
                        _material_lookup_params(
                            endpoint_key=resolved_endpoint_key,
                            cfg=cfg,
                            account=account,
                            chunk=chunk,
                            page_size=page_size,
                        ),
                    ),
                }
            )
    return requests, len(ordered_accounts)


def _source_account_material_lookup_requests(
    *,
    conn: sqlite3.Connection,
    cfg: dict[str, Any],
    endpoint_key: str,
) -> tuple[list[dict[str, Any]], int]:
    source_accounts = _configured_source_accounts(cfg)
    if not source_accounts:
        raise ValueError("material_profile_sync.lookup_accounts_from=source_accounts requires source_accounts")
    max_accounts = _limits(cfg)["max_accounts"]
    if max_accounts > 0:
        source_accounts = source_accounts[:max_accounts]
    date_sql, params = _date_filter_sql(cfg)
    rows = conn.execute(
        f"""
        SELECT
          mdm.material_id,
          ROUND(COALESCE(SUM(mdm.stat_cost), 0), 4) AS stat_cost
        FROM material_daily_metrics mdm
        LEFT JOIN material_profiles mp
          ON mp.material_id = mdm.material_id
        WHERE TRIM(mdm.material_id) != ''
          AND mp.material_id IS NULL
          {date_sql}
        GROUP BY mdm.material_id
        ORDER BY stat_cost DESC, mdm.material_id
        """,
        tuple(params),
    ).fetchall()
    material_ids = [str(material_id) for material_id, _stat_cost in rows]
    total_cost = round(sum(float(stat_cost or 0) for _material_id, stat_cost in rows), 4)
    chunk_size = _material_id_chunk_size(cfg)
    page_size = int(cfg.get("page_size") or chunk_size)
    requests: list[dict[str, Any]] = []
    for account in source_accounts:
        advertiser_id = str(account["advertiser_id"])
        for chunk in _chunked(material_ids, chunk_size):
            requests.append(
                {
                    "account": {
                        "advertiser_id": advertiser_id,
                        "lookup_account_role": "source_account",
                        "material_count": len(chunk),
                        "stat_cost": total_cost,
                    },
                    **build_readonly_request(
                        endpoint_key,
                        _material_lookup_params(
                            endpoint_key=endpoint_key,
                            cfg=cfg,
                            account=advertiser_id,
                            chunk=chunk,
                            page_size=page_size,
                        ),
                    ),
                }
            )
    return requests, len(source_accounts)


def _configured_source_accounts(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    rows = cfg.get("source_accounts")
    if not isinstance(rows, list):
        return []
    accounts: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        advertiser_id = _first_text(row, "advertiser_id", "source_advertiser_id")
        if advertiser_id:
            accounts.append({"advertiser_id": advertiser_id})
    return accounts


def _workbench_material_center_accounts(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    accounts = _configured_source_accounts(cfg)
    if not accounts:
        raise ValueError("workbench material center sync requires source_accounts")
    max_accounts = _limits(cfg)["max_accounts"]
    return accounts[:max_accounts] if max_accounts > 0 else accounts


def _workbench_material_center_plan(cfg: dict[str, Any]) -> dict[str, Any]:
    accounts = _workbench_material_center_accounts(cfg)
    max_pages = max(1, _limits(cfg)["max_pages"])
    limit = int(cfg.get("limit") or cfg.get("page_size") or 100)
    requests: list[dict[str, Any]] = []
    for account in accounts:
        advertiser_id = str(account["advertiser_id"])
        for page in range(1, max_pages + 1):
            requests.append({"advertiser_id": advertiser_id, "page": page, "limit": limit})
    return {
        "ok": True,
        "workflow": "material_profile_sync_workbench_material_center_plan",
        "phase": "phase1",
        "execution_enabled": False,
        "external_api_calls": 0,
        "summary": {
            "source_account_count": len(accounts),
            "planned_request_count": len(requests),
            "page_size": limit,
            "max_pages": max_pages,
        },
        "requests": requests,
    }


def _source_accounts(
    *,
    db_path: str | Path,
    cfg: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    configured = _configured_source_accounts(cfg)
    with sqlite3.connect(db_path) as conn:
        known_count = _known_material_count(conn, cfg)
        missing_count = _missing_material_count(conn, cfg)
        if configured:
            accounts = configured
        else:
            source = str(cfg.get("account_source") or "material_daily_metrics")
            if source != "material_daily_metrics":
                raise ValueError(f"unsupported material profile account_source: {source}")
            accounts = _source_accounts_from_metrics(conn=conn, cfg=cfg)
    return accounts, {"known_material_count": known_count, "missing_material_count": missing_count}


def _openapi_plan(
    *,
    db_path: str | Path,
    cfg: dict[str, Any],
) -> dict[str, Any]:
    accounts, counts = _source_accounts(db_path=db_path, cfg=cfg)
    endpoint_sequence = _endpoint_sequence(cfg)
    endpoint_key = endpoint_sequence[0]
    page_size = int(cfg.get("page_size") or 100)
    lookup_mode = str(cfg.get("lookup_mode") or "account_pages")
    if lookup_mode == "missing_material_ids":
        with sqlite3.connect(db_path) as conn:
            requests = []
            source_account_count = 0
            for stage_endpoint_key in endpoint_sequence:
                stage_requests, stage_source_account_count = _missing_material_lookup_requests(
                    conn=conn,
                    cfg=cfg,
                    endpoint_key=stage_endpoint_key,
                )
                requests.extend(stage_requests)
                source_account_count = max(source_account_count, stage_source_account_count)
    elif lookup_mode == "account_pages":
        source_account_count = len(accounts)
        requests = [
            {
                "account": account,
                **build_readonly_request(
                    endpoint_key,
                    {
                        "advertiser_id": str(account["advertiser_id"]),
                        "page": 1,
                        "page_size": page_size,
                    },
                ),
            }
            for account in accounts
        ]
    else:
        raise ValueError(f"unsupported material profile lookup_mode: {lookup_mode}")
    return {
        "ok": True,
        "workflow": "material_profile_sync_openapi_plan",
        "phase": "phase1",
        "execution_enabled": False,
        "external_api_calls": 0,
        "summary": {
            "source_account_count": source_account_count,
            "known_material_count": counts["known_material_count"],
            "missing_material_count": counts["missing_material_count"],
            "planned_request_count": len(requests),
            "page_size": page_size,
            "lookup_mode": lookup_mode,
            "endpoint_sequence": endpoint_sequence,
        },
        "requests": requests,
    }


def build_material_profile_sync_preflight(
    request: dict[str, Any],
    *,
    db_path: str | Path,
) -> dict[str, Any]:
    cfg = _config(request)
    kind = str(cfg.get("kind") or "local_profile_file")
    if kind == "workbench_material_center":
        plan = _workbench_material_center_plan(cfg)
        return {
            "ok": True,
            "workflow": "material_profile_sync_preflight",
            "phase": "phase1",
            "execution_enabled": False,
            "external_api_calls": 0,
            "summary": {
                "kind": kind,
                "enabled": bool(cfg.get("enabled", False)),
                **plan["summary"],
            },
            "plan": plan,
        }
    if kind != "openapi_video_materials":
        raise ValueError(f"unsupported material profile sync preflight kind: {kind}")
    plan = _openapi_plan(db_path=db_path, cfg=cfg)
    return {
        "ok": True,
        "workflow": "material_profile_sync_preflight",
        "phase": "phase1",
        "execution_enabled": False,
        "external_api_calls": 0,
        "summary": {
            "kind": kind,
            "enabled": bool(cfg.get("enabled", False)),
            **plan["summary"],
        },
        "plan": plan,
    }


def import_material_profiles(
    *,
    db_path: str | Path,
    materials: list[dict[str, Any]],
    source: str,
) -> dict[str, Any]:
    synced_at = _utc_now()
    profiles_imported = 0
    canonical_keys: set[str] = set()
    with sqlite3.connect(db_path) as conn:
        for row in materials:
            material_id = _first_text(row, "material_id", "mid", "id")
            if not material_id:
                continue
            video_id = _video_id(row, material_id)
            image_id = _first_text(row, "image_id", "image_material_id")
            canonical_key = _canonical_material_key(material_id=material_id)
            material_kind = _material_kind(row, image_id=image_id, video_id=video_id)
            name = _first_text(row, "name", "title", "filename", "material_name", "file_name", "video_name")
            review_status = _review_status(row)
            create_time = _first_text(row, "create_time", "created_at", "create_date")
            cover_url = _first_text(row, "cover_url", "head_image_uri", "poster_url", "image_url")
            duration = _float_value(row, "duration", "video_duration")
            source_advertiser_id = _first_text(row, "source_advertiser_id", "advertiser_id")
            payload_json = json.dumps(row, ensure_ascii=False, sort_keys=True)

            conn.execute(
                """
                INSERT INTO material_profiles (
                  material_id, canonical_material_key, material_kind, name, video_id,
                  review_status, create_time, duration, cover_url,
                  source_advertiser_id, payload_json, source, synced_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(material_id) DO UPDATE SET
                  canonical_material_key=excluded.canonical_material_key,
                  material_kind=COALESCE(NULLIF(excluded.material_kind, ''), material_profiles.material_kind),
                  name=COALESCE(NULLIF(excluded.name, ''), material_profiles.name),
                  video_id=COALESCE(NULLIF(excluded.video_id, ''), material_profiles.video_id),
                  review_status=COALESCE(NULLIF(excluded.review_status, ''), material_profiles.review_status),
                  create_time=COALESCE(NULLIF(excluded.create_time, ''), material_profiles.create_time),
                  duration=CASE WHEN excluded.duration > 0 THEN excluded.duration ELSE material_profiles.duration END,
                  cover_url=COALESCE(NULLIF(excluded.cover_url, ''), material_profiles.cover_url),
                  source_advertiser_id=COALESCE(NULLIF(excluded.source_advertiser_id, ''), material_profiles.source_advertiser_id),
                  payload_json=excluded.payload_json,
                  source=excluded.source,
                  synced_at=excluded.synced_at
                """,
                (
                    material_id,
                    canonical_key,
                    material_kind,
                    name,
                    video_id,
                    review_status,
                    create_time,
                    duration,
                    cover_url,
                    source_advertiser_id,
                    payload_json,
                    source,
                    synced_at,
                ),
            )
            conn.execute(
                """
                INSERT INTO materials (
                  material_id, name, material_type, video_id, review_status,
                  payload_json, source, synced_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(material_id) DO UPDATE SET
                  name=COALESCE(NULLIF(excluded.name, ''), materials.name),
                  material_type=COALESCE(NULLIF(excluded.material_type, ''), materials.material_type),
                  video_id=COALESCE(NULLIF(excluded.video_id, ''), materials.video_id),
                  review_status=COALESCE(NULLIF(excluded.review_status, ''), materials.review_status),
                  payload_json=excluded.payload_json,
                  source=excluded.source,
                  synced_at=excluded.synced_at
                """,
                (
                    material_id,
                    name,
                    material_kind,
                    video_id,
                    review_status,
                    payload_json,
                    source,
                    synced_at,
                ),
            )
            account_id = _first_text(row, "advertiser_id", "source_advertiser_id")
            if account_id:
                conn.execute(
                    """
                    INSERT INTO account_materials (
                      advertiser_id, material_id, video_id, material_type,
                      review_status, source, synced_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(advertiser_id, material_id) DO UPDATE SET
                      video_id=COALESCE(NULLIF(excluded.video_id, ''), account_materials.video_id),
                      material_type=COALESCE(NULLIF(excluded.material_type, ''), account_materials.material_type),
                      review_status=COALESCE(NULLIF(excluded.review_status, ''), account_materials.review_status),
                      source=excluded.source,
                      synced_at=excluded.synced_at
                    """,
                    (
                        account_id,
                        material_id,
                        video_id,
                        material_kind,
                        review_status,
                        source,
                        synced_at,
                    ),
                )
            canonical_keys.add(canonical_key)
            profiles_imported += 1
    return {
        "ok": True,
        "profiles_imported": profiles_imported,
        "canonical_material_count": len(canonical_keys),
        "duplicate_profile_count": max(profiles_imported - len(canonical_keys), 0),
        "external_api_calls": 0,
    }


ATTRIBUTE_FLAG_FIELDS = [
    "is_ad_high_quality_material",
    "is_ad_low_quality_material",
    "is_ecp_high_quality_material",
    "is_ecp_low_quality_material",
    "is_local_high_quality_material",
    "is_local_low_quality_material",
    "is_first_publish_material",
    "is_inefficient_material",
    "is_carry_material",
    "is_similar_material",
    "is_similar_queue_material",
    "is_similar_expected_queue_material",
]


def import_material_attribute_snapshots(
    *,
    db_path: str | Path,
    materials: list[dict[str, Any]],
    source: str,
) -> dict[str, Any]:
    synced_at = _utc_now()
    attributes_imported = 0
    with sqlite3.connect(db_path) as conn:
        for row in materials:
            material_id = _first_text(row, "material_id", "mid", "id")
            if not material_id:
                continue
            account_id = _first_text(row, "_request_account_id", "account_id", "advertiser_id")
            account_type = _first_text(row, "_request_account_type", "account_type") or "AD"
            payload_json = json.dumps(
                {key: value for key, value in row.items() if not str(key).startswith("_request_")},
                ensure_ascii=False,
                sort_keys=True,
            )
            conn.execute(
                """
                INSERT INTO material_attribute_snapshots (
                  material_id,
                  account_id,
                  account_type,
                  is_ad_high_quality_material,
                  is_ad_low_quality_material,
                  is_ecp_high_quality_material,
                  is_ecp_low_quality_material,
                  is_local_high_quality_material,
                  is_local_low_quality_material,
                  is_first_publish_material,
                  is_inefficient_material,
                  is_carry_material,
                  is_similar_material,
                  is_similar_queue_material,
                  is_similar_expected_queue_material,
                  ad_low_quality_suggestions_json,
                  ecp_low_quality_suggestions_json,
                  local_low_quality_suggestions_json,
                  attributes_modify_time,
                  payload_json,
                  source,
                  synced_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(material_id, account_id, account_type) DO UPDATE SET
                  is_ad_high_quality_material=excluded.is_ad_high_quality_material,
                  is_ad_low_quality_material=excluded.is_ad_low_quality_material,
                  is_ecp_high_quality_material=excluded.is_ecp_high_quality_material,
                  is_ecp_low_quality_material=excluded.is_ecp_low_quality_material,
                  is_local_high_quality_material=excluded.is_local_high_quality_material,
                  is_local_low_quality_material=excluded.is_local_low_quality_material,
                  is_first_publish_material=excluded.is_first_publish_material,
                  is_inefficient_material=excluded.is_inefficient_material,
                  is_carry_material=excluded.is_carry_material,
                  is_similar_material=excluded.is_similar_material,
                  is_similar_queue_material=excluded.is_similar_queue_material,
                  is_similar_expected_queue_material=excluded.is_similar_expected_queue_material,
                  ad_low_quality_suggestions_json=excluded.ad_low_quality_suggestions_json,
                  ecp_low_quality_suggestions_json=excluded.ecp_low_quality_suggestions_json,
                  local_low_quality_suggestions_json=excluded.local_low_quality_suggestions_json,
                  attributes_modify_time=excluded.attributes_modify_time,
                  payload_json=excluded.payload_json,
                  source=excluded.source,
                  synced_at=excluded.synced_at
                """,
                (
                    material_id,
                    account_id,
                    account_type,
                    *[_bool_int(row, field) for field in ATTRIBUTE_FLAG_FIELDS],
                    _json_list(row, "ad_low_quality_suggestions"),
                    _json_list(row, "ecp_low_quality_suggestions"),
                    _json_list(row, "local_low_quality_suggestions"),
                    _first_text(row, "attributes_modify_time"),
                    payload_json,
                    source,
                    synced_at,
                ),
            )
            attributes_imported += 1
    return {
        "ok": True,
        "attributes_imported": attributes_imported,
        "external_api_calls": 0,
    }


def _run_workbench_material_center(
    cfg: dict[str, Any],
    *,
    db_path: str | Path,
    opener: WorkbenchMaterialCenterOpener | None,
) -> dict[str, Any]:
    plan = _workbench_material_center_plan(cfg)
    if not bool(cfg.get("enabled", False)):
        return {
            "ok": True,
            "workflow": "material_profile_sync",
            "phase": "phase1",
            "execution_enabled": False,
            "external_api_calls": 0,
            "skipped": True,
            "reason": "workbench_material_center disabled",
            "summary": {
                "kind": "workbench_material_center",
                "enabled": False,
                **plan["summary"],
            },
            "preflight": {
                "ok": True,
                "workflow": "material_profile_sync_preflight",
                "phase": "phase1",
                "execution_enabled": False,
                "external_api_calls": 0,
                "summary": {
                    "kind": "workbench_material_center",
                    "enabled": False,
                    **plan["summary"],
                },
                "plan": plan,
            },
            "guardrails": {
                "external_api_calls": 0,
                "business_actions": [],
                "writes": ["run_artifact"],
            },
        }

    statistic_start_time = _first_text(cfg, "statistic_start_time")
    statistic_end_time = _first_text(cfg, "statistic_end_time")
    if not statistic_start_time or not statistic_end_time:
        raise ValueError("workbench material center sync requires statistic_start_time and statistic_end_time")

    total_transport_calls = 0
    total_rows_received = 0
    total_profiles_imported = 0
    total_canonical_material_count = 0
    total_duplicate_profile_count = 0
    total_product_source_materials_imported = 0
    account_results: list[dict[str, Any]] = []
    product = _first_text(cfg, "product")
    organization_id = _first_text(cfg, "organization_id", "ebp_id")
    for account in _workbench_material_center_accounts(cfg):
        advertiser_id = str(account["advertiser_id"])
        account_organization_id = str(account.get("organization_id") or organization_id)
        fetched = fetch_video_materials(
            cfg,
            advertiser_id=advertiser_id,
            statistic_start_time=statistic_start_time,
            statistic_end_time=statistic_end_time,
            opener=opener,
        )
        imported = import_material_profiles(
            db_path=db_path,
            materials=fetched["materials"],
            source="workbench_material_center",
        )
        source_imported: dict[str, Any] = {"product_source_materials_imported": 0}
        if product:
            source_imported = import_product_source_materials(
                db_path=db_path,
                product=product,
                source_advertiser_id=advertiser_id,
                organization_id=account_organization_id,
                materials=fetched["materials"],
                source="workbench_material_center",
                mark_absent_inactive=False,
            )
        transport_calls = int(fetched["summary"]["transport_calls"])
        rows_received = int(fetched["summary"]["rows_received"])
        profiles_imported = int(imported.get("profiles_imported") or 0)
        product_source_materials_imported = int(source_imported.get("product_source_materials_imported") or 0)
        total_transport_calls += transport_calls
        total_rows_received += rows_received
        total_profiles_imported += profiles_imported
        total_product_source_materials_imported += product_source_materials_imported
        total_canonical_material_count += int(imported.get("canonical_material_count") or 0)
        total_duplicate_profile_count += int(imported.get("duplicate_profile_count") or 0)
        account_results.append(
            {
                "advertiser_id": advertiser_id,
                "transport_calls": transport_calls,
                "rows_received": rows_received,
                "rows_importable": int(fetched["summary"].get("rows_importable") or profiles_imported),
                "total_count": int(fetched["summary"].get("total_count") or rows_received),
                "stopped_by_created_at_range": bool(fetched["summary"].get("stopped_by_created_at_range", False)),
                "profiles_imported": profiles_imported,
                "product_source_materials_imported": product_source_materials_imported,
            }
        )

    return {
        "ok": True,
        "workflow": "material_profile_sync",
        "phase": "phase1",
        "execution_enabled": False,
        "external_api_calls": total_transport_calls,
        "skipped": False,
        "summary": {
            "kind": "workbench_material_center",
            "enabled": True,
            **plan["summary"],
            "transport_calls": total_transport_calls,
            "rows_received": total_rows_received,
            "profiles_imported": total_profiles_imported,
            "product_source_materials_imported": total_product_source_materials_imported,
            "canonical_material_count": total_canonical_material_count,
            "duplicate_profile_count": total_duplicate_profile_count,
            "accounts": account_results,
        },
        "execution": {
            "summary": {
                "transport_calls": total_transport_calls,
                "rows_received": total_rows_received,
                "account_count": len(account_results),
            },
        },
        "guardrails": {
            "external_api_calls": total_transport_calls,
            "business_actions": [],
            "writes": ["material_profiles", "materials", "account_materials", "product_source_materials", "run_artifact"],
        },
    }


def run_material_profile_sync_request(
    request: dict[str, Any],
    *,
    db_path: str | Path,
    runs_dir: str | Path,
    transport: Transport | None = None,
    material_center_opener: WorkbenchMaterialCenterOpener | None = None,
) -> dict[str, Any]:
    cfg = _config(request)
    kind = str(cfg.get("kind") or "local_profile_file")
    if kind == "openapi_video_materials":
        payload = _run_openapi_video_materials(cfg, db_path=db_path, transport=transport)
        artifact_path = write_run_artifact(runs_dir, "material_profile_sync", payload)
        return {**payload, "artifact_path": str(artifact_path)}
    if kind == "workbench_material_center":
        payload = _run_workbench_material_center(cfg, db_path=db_path, opener=material_center_opener)
        artifact_path = write_run_artifact(runs_dir, "material_profile_sync", payload)
        return {**payload, "artifact_path": str(artifact_path)}
    if kind != "local_profile_file":
        raise ValueError(f"unsupported material profile sync kind in phase1: {kind}")
    profile_file = Path(str(cfg.get("profile_file") or ""))
    if not str(profile_file):
        raise ValueError("material_profile_sync requires profile_file")
    data = load_json(profile_file)
    imported = import_material_profiles(db_path=db_path, materials=_rows(data), source=str(profile_file))
    payload = {
        "ok": True,
        "workflow": "material_profile_sync",
        "phase": "phase1",
        "execution_enabled": False,
        "external_api_calls": 0,
        "summary": {
            "kind": kind,
            **imported,
        },
        "guardrails": {
            "external_api_calls": 0,
            "business_actions": [],
            "writes": ["material_profiles", "materials", "account_materials", "material_attribute_snapshots", "run_artifact"],
        },
    }
    artifact_path = write_run_artifact(runs_dir, "material_profile_sync", payload)
    return {**payload, "artifact_path": str(artifact_path)}


def _material_id_set_from_request(request: dict[str, Any]) -> set[str]:
    query_params = request.get("query_params") if isinstance(request.get("query_params"), dict) else {}
    raw_filter = query_params.get("filtering") or query_params.get("filter_param")
    if not raw_filter:
        return set()
    try:
        decoded = json.loads(str(raw_filter))
    except json.JSONDecodeError:
        return set()
    material_ids = decoded.get("material_ids") if isinstance(decoded, dict) else []
    if not isinstance(material_ids, list):
        return set()
    return {str(material_id).strip() for material_id in material_ids if str(material_id).strip()}


def _rows_from_execution(execution: dict[str, Any]) -> tuple[list[dict[str, Any]], int]:
    rows: list[dict[str, Any]] = []
    skipped_unrequested = 0
    for item in execution.get("responses") or []:
        if not isinstance(item, dict):
            continue
        requested_ids = _material_id_set_from_request(item.get("request") if isinstance(item.get("request"), dict) else {})
        for row in item.get("rows") or []:
            if not isinstance(row, dict):
                continue
            material_id = _first_text(row, "material_id", "mid", "id")
            if requested_ids and material_id not in requested_ids:
                skipped_unrequested += 1
                continue
            rows.append(row)
    return rows, skipped_unrequested


def _attribute_rows_from_execution(execution: dict[str, Any]) -> tuple[list[dict[str, Any]], int]:
    rows: list[dict[str, Any]] = []
    skipped_unrequested = 0
    for item in execution.get("responses") or []:
        if not isinstance(item, dict):
            continue
        request = item.get("request") if isinstance(item.get("request"), dict) else {}
        query_params = request.get("query_params") if isinstance(request.get("query_params"), dict) else {}
        account_id = str(query_params.get("account_id") or "")
        account_type = str(query_params.get("account_type") or "AD")
        requested_ids = _material_id_set_from_request(request)
        for row in item.get("rows") or []:
            if isinstance(row, dict):
                material_id = _first_text(row, "material_id", "mid", "id")
                if requested_ids and material_id not in requested_ids:
                    skipped_unrequested += 1
                    continue
                rows.append({**row, "_request_account_id": account_id, "_request_account_type": account_type})
    return rows, skipped_unrequested


def _single_endpoint_cfg(cfg: dict[str, Any], endpoint_key: str) -> dict[str, Any]:
    stage_cfg = dict(cfg)
    stage_cfg["endpoint"] = endpoint_key
    stage_cfg.pop("endpoint_sequence", None)
    return stage_cfg


def _run_openapi_video_materials(
    cfg: dict[str, Any],
    *,
    db_path: str | Path,
    transport: Transport | None,
) -> dict[str, Any]:
    if not bool(cfg.get("enabled", False)):
        preflight = build_material_profile_sync_preflight({"material_profile_sync": cfg}, db_path=db_path)
        return {
            "ok": True,
            "workflow": "material_profile_sync",
            "phase": "phase1",
            "execution_enabled": False,
            "external_api_calls": 0,
            "skipped": True,
            "reason": "openapi_video_materials disabled",
            "summary": preflight["summary"],
            "preflight": preflight,
            "guardrails": {
                "external_api_calls": 0,
                "business_actions": [],
                "writes": ["run_artifact"],
            },
        }
    if transport is None:
        raise RuntimeError("openapi_video_materials enabled requires an explicit readonly transport")

    retry_codes = cfg.get("retry_api_codes") if isinstance(cfg.get("retry_api_codes"), list) else []
    plan = _openapi_plan(db_path=db_path, cfg=cfg)
    stages: list[dict[str, Any]] = []
    total_transport_calls = 0
    total_rows_received = 0
    total_profiles_imported = 0
    total_attributes_imported = 0
    total_canonical_material_count = 0
    total_duplicate_profile_count = 0
    for endpoint_key in _endpoint_sequence(cfg):
        stage_cfg = _single_endpoint_cfg(cfg, endpoint_key)
        stage_plan = _openapi_plan(db_path=db_path, cfg=stage_cfg)
        if not stage_plan.get("requests"):
            continue
        execution = execute_openapi_readonly_plan(
            stage_plan,
            transport=transport,
            max_pages=max(1, _limits(cfg)["max_pages"]),
            retry_api_codes=retry_codes,
            max_api_retries=int(cfg.get("max_api_retries") or 0),
            retry_sleep_seconds=float(cfg.get("retry_sleep_seconds") or 1),
        )
        skipped_unrequested = 0
        if endpoint_key == "material_attributes_list":
            rows_to_import, skipped_unrequested = _attribute_rows_from_execution(execution)
            imported = import_material_attribute_snapshots(
                db_path=db_path,
                materials=rows_to_import,
                source=f"openapi_{endpoint_key}",
            )
        else:
            rows_to_import, skipped_unrequested = _rows_from_execution(execution)
            imported = import_material_profiles(
                db_path=db_path,
                materials=rows_to_import,
                source=f"openapi_{endpoint_key}",
            )
        transport_calls = int(execution["summary"]["transport_calls"])
        rows_received = int(execution["summary"]["rows_received"])
        profiles_imported = int(imported.get("profiles_imported") or 0)
        attributes_imported = int(imported.get("attributes_imported") or 0)
        total_transport_calls += transport_calls
        total_rows_received += rows_received
        total_profiles_imported += profiles_imported
        total_attributes_imported += attributes_imported
        total_canonical_material_count += int(imported.get("canonical_material_count") or 0)
        total_duplicate_profile_count += int(imported.get("duplicate_profile_count") or 0)
        stages.append(
            {
                "endpoint_key": endpoint_key,
                "planned_request_count": int(stage_plan["summary"]["planned_request_count"]),
                "transport_calls": transport_calls,
                "rows_received": rows_received,
                "rows_eligible_for_import": len(rows_to_import),
                "rows_skipped_unrequested": skipped_unrequested,
                "profiles_imported": profiles_imported,
                "attributes_imported": attributes_imported,
            }
        )
    return {
        "ok": True,
        "workflow": "material_profile_sync",
        "phase": "phase1",
        "execution_enabled": False,
        "external_api_calls": total_transport_calls,
        "skipped": False,
        "summary": {
            **plan["summary"],
            "transport_calls": total_transport_calls,
            "rows_received": total_rows_received,
            "profiles_imported": total_profiles_imported,
            "attributes_imported": total_attributes_imported,
            "canonical_material_count": total_canonical_material_count,
            "duplicate_profile_count": total_duplicate_profile_count,
            "stages": stages,
        },
        "execution": {
            "summary": {
                "transport_calls": total_transport_calls,
                "rows_received": total_rows_received,
                "stage_count": len(stages),
            },
        },
        "guardrails": {
            "external_api_calls": total_transport_calls,
            "business_actions": [],
            "writes": ["material_profiles", "materials", "account_materials", "material_attribute_snapshots", "run_artifact"],
        },
    }
