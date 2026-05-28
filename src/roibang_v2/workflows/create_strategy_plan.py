from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from roibang_v2.runs import write_run_artifact
from roibang_v2.workflows.create_lineage import create_ref, create_request_payload

_INVALID_PROJECT_NAME_CHARS = re.compile(r'[\\/:*?"<>|\r\n\t]+')
_VALID_SOURCE_VIDEO_ID = re.compile(r"^v[0-9A-Za-z]{12,}$")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _int_value(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _policy_limit(policy: dict[str, Any], key: str, default: int) -> int:
    return max(_int_value(policy.get(key), default), 0)


def _request_config(request: dict[str, Any]) -> dict[str, Any]:
    value = request.get("create_request")
    if isinstance(value, dict):
        return dict(value)
    return create_request_payload(request)


def _target_accounts(request: dict[str, Any]) -> list[dict[str, Any]]:
    rows = request.get("target_accounts") if isinstance(request.get("target_accounts"), list) else []
    return [row for row in rows if isinstance(row, dict)]


def _material_requirements(request: dict[str, Any]) -> dict[str, Any]:
    value = request.get("material_requirements")
    return dict(value) if isinstance(value, dict) else {}


def _candidate_filters(policy: dict[str, Any]) -> dict[str, Any]:
    value = policy.get("candidate_filters")
    return dict(value) if isinstance(value, dict) else {}


def _float_value(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _allowed_review_statuses(filters: dict[str, Any]) -> set[str]:
    value = filters.get("allowed_review_statuses")
    if not isinstance(value, list) or not value:
        return set()
    return {str(item).strip() for item in value if str(item).strip()}


def _normalized_review_status(value: Any) -> str:
    raw = str(value or "").strip()
    return {"3": "APPROVED"}.get(raw, raw)


def _source_video_id(row: dict[str, Any]) -> str:
    return str(row.get("source_video_id") or row.get("video_id") or "").strip()


def _looks_like_real_source_video_id(value: Any) -> bool:
    return bool(_VALID_SOURCE_VIDEO_ID.fullmatch(str(value or "").strip()))


def _is_fixture_source(value: Any) -> bool:
    normalized = str(value or "").strip().lower().replace("\\", "/")
    return "fixtures" in normalized


def _filter_candidate_rows(rows: list[dict[str, Any]], *, policy: dict[str, Any]) -> list[dict[str, Any]]:
    filters = _candidate_filters(policy)
    allowed_statuses = _allowed_review_statuses(filters)
    min_score = _float_value(filters.get("min_candidate_score"), 0)
    min_stat_cost = _float_value(filters.get("min_candidate_stat_cost"), 0)
    filtered: list[dict[str, Any]] = []
    for row in rows:
        if _is_fixture_source(row.get("source")):
            continue
        if not _looks_like_real_source_video_id(_source_video_id(row)):
            continue
        review_status = _normalized_review_status(row.get("review_status"))
        if allowed_statuses and review_status and review_status not in allowed_statuses:
            continue
        if float(row.get("score") or 0) < min_score:
            continue
        if float(row.get("stat_cost") or 0) < min_stat_cost:
            continue
        filtered.append(row)
    return filtered


def _selection_policy(request: dict[str, Any]) -> dict[str, Any]:
    value = request.get("material_selection")
    return dict(value) if isinstance(value, dict) else {}


def _candidate_min_stat_cost(request: dict[str, Any], policy: dict[str, Any]) -> float:
    selection = _selection_policy(request)
    return max(_float_value(policy.get("min_candidate_stat_cost"), 0), _float_value(selection.get("min_stat_cost"), 0))


def _candidate_max_stat_cost(request: dict[str, Any]) -> float | None:
    selection = _selection_policy(request)
    value = _float_value(selection.get("max_stat_cost"), 0)
    return value if value > 0 else None


def _candidate_min_convert_cnt(request: dict[str, Any]) -> float | None:
    selection = _selection_policy(request)
    if selection.get("min_convert_cnt") is None:
        return None
    return _float_value(selection.get("min_convert_cnt"), 0)


def _candidate_max_convert_cnt(request: dict[str, Any]) -> float | None:
    selection = _selection_policy(request)
    if selection.get("max_convert_cnt") is None:
        return None
    return _float_value(selection.get("max_convert_cnt"), 0)


def _parse_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        try:
            return datetime.fromisoformat(normalized[:10])
        except ValueError:
            return None


def _target_date_datetime(request: dict[str, Any]) -> datetime:
    parsed = _parse_datetime(request.get("target_date"))
    if parsed is not None:
        return parsed
    return datetime.now(timezone.utc)


def _candidate_min_create_age_days(request: dict[str, Any]) -> int:
    selection = _selection_policy(request)
    return max(_int_value(selection.get("min_create_age_days"), 0), 0)


def _candidate_first_seen_days(request: dict[str, Any]) -> int:
    selection = _selection_policy(request)
    return max(_int_value(selection.get("first_seen_days"), 0), 0)


def _candidate_effective_create_datetime(row: dict[str, Any]) -> datetime | None:
    return _parse_datetime(
        row.get("effective_create_date")
        or row.get("first_seen_metric_date")
        or row.get("create_time")
        or row.get("first_seen_at")
    )


def _filter_candidate_rows_for_request(rows: list[dict[str, Any]], *, request: dict[str, Any], policy: dict[str, Any]) -> list[dict[str, Any]]:
    filtered = _filter_candidate_rows(rows, policy=policy)
    requirements = _material_requirements(request)
    material_type = str(requirements.get("material_type") or "video").strip()
    min_stat_cost = _candidate_min_stat_cost(request, _candidate_filters(policy))
    max_stat_cost = _candidate_max_stat_cost(request)
    min_convert_cnt = _candidate_min_convert_cnt(request)
    max_convert_cnt = _candidate_max_convert_cnt(request)
    min_create_age_days = _candidate_min_create_age_days(request)
    target_date = _target_date_datetime(request)
    create_before = (target_date - timedelta(days=min_create_age_days)).date()
    first_seen_days = _candidate_first_seen_days(request)
    first_seen_since = (target_date - timedelta(days=max(first_seen_days - 1, 0))).date()
    result = [
        row
        for row in filtered
        if (not material_type or str(row.get("material_type") or material_type).strip() == material_type)
        and float(row.get("stat_cost") or 0) >= min_stat_cost
    ]
    if max_stat_cost is not None:
        result = [row for row in result if float(row.get("stat_cost") or 0) <= max_stat_cost]
    if min_convert_cnt is not None:
        result = [row for row in result if float(row.get("convert_cnt") or 0) >= min_convert_cnt]
    if max_convert_cnt is not None:
        result = [row for row in result if float(row.get("convert_cnt") or 0) <= max_convert_cnt]
    if min_create_age_days > 0:
        result = [
            row
            for row in result
            if (created_at := _candidate_effective_create_datetime(row)) is not None
            and created_at.date() <= create_before
        ]
    if first_seen_days > 0:
        result = [
            row
            for row in result
            if (created_at := _candidate_effective_create_datetime(row)) is not None
            and created_at.date() >= first_seen_since
        ]
    return result


def _candidate_sort_key(row: dict[str, Any], *, selection: dict[str, Any]) -> tuple[Any, ...]:
    sort_by = str(selection.get("sort_by") or "")
    selection_type = str(selection.get("selection_type") or "")
    if sort_by in {"create_time_desc", "effective_create_date_desc"} or selection_type == "test_new":
        created_at = str(
            row.get("effective_create_date")
            or row.get("first_seen_metric_date")
            or row.get("create_time")
            or row.get("first_seen_at")
            or ""
        )
        return (created_at, -float(row.get("stat_cost") or 0), str(row.get("material_id") or ""))
    return (float(row.get("stat_cost") or 0), float(row.get("score") or 0), str(row.get("material_id") or ""))


def _sort_candidate_rows(rows: list[dict[str, Any]], *, request: dict[str, Any]) -> list[dict[str, Any]]:
    selection = _selection_policy(request)
    reverse = True
    if _int_value(selection.get("candidate_pool_limit"), 0) > 0:
        limit = _int_value(selection.get("candidate_pool_limit"), 0)
        rows = sorted(rows, key=lambda row: _candidate_sort_key(row, selection=selection), reverse=reverse)[:limit]
    if _scale_top_material_reuse_enabled(request):
        seed = str(request.get("request_id") or request.get("plan_id") or "")
        return sorted(
            rows,
            key=lambda row: (
                -float(row.get("stat_cost") or 0),
                hashlib.sha256(f"{seed}:{row.get('material_id')}".encode("utf-8")).hexdigest(),
            ),
        )
    if bool(selection.get("random_shuffle", False)):
        seed = str(request.get("request_id") or request.get("plan_id") or "")
        return sorted(
            rows,
            key=lambda row: hashlib.sha256(f"{seed}:{row.get('material_id')}".encode("utf-8")).hexdigest(),
        )
    return sorted(rows, key=lambda row: _candidate_sort_key(row, selection=selection), reverse=reverse)


def _target_existing_material_ids_by_account(
    *,
    db_path: str | Path,
    request: dict[str, Any],
    policy: dict[str, Any],
) -> dict[str, set[str]]:
    filters = _candidate_filters(policy)
    advertiser_ids = [str(account.get("advertiser_id") or "") for account in _target_accounts(request)]
    advertiser_ids = [advertiser_id for advertiser_id in advertiser_ids if advertiser_id]
    if not advertiser_ids or not bool(filters.get("exclude_target_account_existing_materials", False)):
        return {advertiser_id: set() for advertiser_id in advertiser_ids}
    placeholders = ",".join("?" for _ in advertiser_ids)
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            f"""
            SELECT advertiser_id, material_id
            FROM account_materials
            WHERE advertiser_id IN ({placeholders})
            """,
            advertiser_ids,
        ).fetchall()
    existing = {advertiser_id: set() for advertiser_id in advertiser_ids}
    for advertiser_id, material_id in rows:
        existing.setdefault(str(advertiser_id), set()).add(str(material_id))
    return existing


def _candidate_rows(*, db_path: str | Path, request: dict[str, Any], policy: dict[str, Any]) -> list[dict[str, Any]]:
    selected_materials = request.get("selected_materials")
    if isinstance(selected_materials, list) and selected_materials:
        rows = [dict(row) for row in selected_materials if isinstance(row, dict)]
        return _sort_candidate_rows(_filter_candidate_rows_for_request(rows, request=request, policy=policy), request=request)
    requirements = _material_requirements(request)
    selection = _selection_policy(request)
    lookback_days = _int_value(selection.get("lookback_days"), 0)
    material_type = str(requirements.get("material_type") or "video")
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT
              psm.material_id,
              psm.material_type,
              psm.video_id AS source_video_id,
              psm.name,
              psm.review_status,
              psm.source,
              COALESCE(MAX(CASE WHEN psmr.window_days = ? THEN psmr.stat_cost END), MAX(psmr.stat_cost), psm.cost_lookback, 0) AS stat_cost,
              COALESCE(MAX(CASE WHEN psmr.window_days = ? THEN psmr.convert_cnt END), MAX(psmr.convert_cnt), 0) AS convert_cnt,
              psm.score,
              psm.create_time,
              psm.first_seen_at,
              COALESCE(MAX(CASE WHEN psmr.window_days = ? THEN psmr.first_seen_metric_date END), MAX(psmr.first_seen_metric_date), '') AS first_seen_metric_date,
              COALESCE(
                MAX(CASE WHEN (psmr.window_key = 'all_history' OR psmr.window_days = 0) AND psmr.effective_create_date != '' THEN psmr.effective_create_date END),
                MIN(CASE WHEN psmr.effective_create_date != '' THEN psmr.effective_create_date END),
                psm.create_time,
                psm.first_seen_at,
                ''
              ) AS effective_create_date,
              COALESCE(
                MAX(CASE WHEN (psmr.window_key = 'all_history' OR psmr.window_days = 0) AND psmr.effective_create_date_source != '' THEN psmr.effective_create_date_source END),
                MAX(CASE WHEN psmr.effective_create_date_source != '' THEN psmr.effective_create_date_source END),
                ''
              ) AS effective_create_date_source
            FROM product_source_materials psm
            LEFT JOIN product_source_material_metric_rollups psmr
              ON psmr.product = psm.product
             AND psmr.source_advertiser_id = psm.source_advertiser_id
             AND psmr.material_id = psm.material_id
            WHERE psm.product = ?
              AND psm.source_advertiser_id = ?
              AND psm.material_type = ?
              AND psm.is_active = 1
              AND NOT EXISTS (
                SELECT 1
                FROM source_material_bad_videos bad
                WHERE bad.product = psm.product
                  AND bad.source_advertiser_id = psm.source_advertiser_id
                  AND bad.source_video_id = psm.video_id
                  AND bad.status = 'active'
              )
            GROUP BY
              psm.material_id, psm.material_type, psm.video_id, psm.name,
              psm.review_status, psm.source, psm.cost_lookback, psm.score, psm.create_time, psm.first_seen_at
            """,
            (
                lookback_days,
                lookback_days,
                lookback_days,
                str(request.get("product") or ""),
                str(request.get("source_advertiser_id") or ""),
                material_type,
            ),
        ).fetchall()
    normalized = []
    for index, row in enumerate(rows, start=1):
        normalized.append({"rank": index, **dict(row)})
    return _sort_candidate_rows(_filter_candidate_rows_for_request(normalized, request=request, policy=policy), request=request)


def _project_naming_policy(policy: dict[str, Any]) -> dict[str, Any]:
    value = policy.get("project_naming")
    return dict(value) if isinstance(value, dict) else {}


def _project_name_template(request: dict[str, Any], policy: dict[str, Any]) -> tuple[str, str]:
    naming = _project_naming_policy(policy)
    if str(naming.get("template") or "").strip():
        return str(naming.get("template") or "").strip(), "policy"
    if str(request.get("project_name_template") or "").strip():
        return str(request.get("project_name_template") or "").strip(), "request"
    return "{product}-{project_type}-{advertiser_id}-{index}", "default"


def _target_date_compact(request: dict[str, Any]) -> str:
    return re.sub(r"\D+", "", str(request.get("target_date") or ""))


def _target_date_mmdd(request: dict[str, Any]) -> str:
    compact = _target_date_compact(request)
    return compact[4:8] if len(compact) >= 8 else compact


def _batch_generated_at(request: dict[str, Any]) -> str:
    value = str(request.get("batch_generated_at") or "").strip()
    if value:
        return value
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _batch_code_source(request: dict[str, Any], *, generated_at: str) -> dict[str, Any]:
    return {
        "request_id": str(request.get("request_id") or ""),
        "target_date": str(request.get("target_date") or ""),
        "product": str(request.get("product") or ""),
        "project_type": str(request.get("project_type") or ""),
        "advertiser_ids": [
            str(account.get("advertiser_id") or "")
            for account in _target_accounts(request)
            if str(account.get("advertiser_id") or "")
        ],
        "generated_at": generated_at,
    }


def _batch_code(source_fields: dict[str, Any]) -> str:
    canonical = json.dumps(source_fields, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "B" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:8].upper()


def _normalize_project_name(name: str, *, replacement: str) -> str:
    normalized = _INVALID_PROJECT_NAME_CHARS.sub(replacement, name)
    normalized = re.sub(r"\s+", replacement, normalized)
    if replacement:
        normalized = re.sub(f"{re.escape(replacement)}+", replacement, normalized)
        normalized = normalized.strip(replacement)
    return normalized.strip()


def _project_name_entry(
    request: dict[str, Any],
    policy: dict[str, Any],
    *,
    advertiser_id: str,
    index: int,
) -> dict[str, Any]:
    naming = _project_naming_policy(policy)
    template, source = _project_name_template(request, policy)
    index_width = max(_int_value(naming.get("index_width"), 2), 1)
    replacement = str(naming.get("invalid_char_replacement") or "-")
    generated_at = _batch_generated_at(request)
    batch_source = _batch_code_source(request, generated_at=generated_at)
    batch_code = str(request.get("batch_code") or "").strip() or _batch_code(batch_source)
    values = {
        "owner": str(request.get("owner") or request.get("belonging") or request.get("name_owner") or ""),
        "product": str(request.get("product") or ""),
        "platform": str(request.get("platform") or ""),
        "project_type": str(request.get("project_type") or ""),
        "project_template_name": str(request.get("project_template_name") or request.get("project_type") or ""),
        "advertiser_id": advertiser_id,
        "index": f"{index:0{index_width}d}",
        "target_date": str(request.get("target_date") or ""),
        "target_date_compact": _target_date_compact(request),
        "target_date_mmdd": _target_date_mmdd(request),
        "batch_code": batch_code,
    }
    try:
        raw_name = template.format(**values)
    except KeyError:
        fallback = "{product}-{project_type}-{advertiser_id}-{index}"
        raw_name = fallback.format(**values)
        template = fallback
        source = "fallback"
    project_name = _normalize_project_name(raw_name, replacement=replacement)
    return {
        "project_name": project_name,
        "naming": {
            "source": source,
            "template": template,
            "index_width": index_width,
            "invalid_char_replacement": replacement,
            "batch_code": batch_code,
            "batch_code_source": {
                "algorithm": "sha256_first_8_uppercase",
                "generated_at": generated_at,
                "source_fields": batch_source,
                "freeze_rule": "generate once in plan, then reuse through preflight, dry-run, and execute",
            },
        },
    }


def _material_entry(row: dict[str, Any]) -> dict[str, Any]:
    entry = {
        "material_id": str(row.get("material_id") or ""),
        "material_type": str(row.get("material_type") or "video"),
        "source_video_id": _source_video_id(row),
        "name": str(row.get("name") or ""),
        "rank": int(row.get("rank") or 0),
        "score": float(row.get("score") or 0),
        "stat_cost": float(row.get("stat_cost") or 0),
        "convert_cnt": float(row.get("convert_cnt") or 0),
    }
    if str(row.get("create_time") or "").strip():
        entry["create_time"] = str(row.get("create_time") or "").strip()
    if str(row.get("first_seen_metric_date") or "").strip():
        entry["first_seen_metric_date"] = str(row.get("first_seen_metric_date") or "").strip()
    if str(row.get("effective_create_date") or "").strip():
        entry["effective_create_date"] = str(row.get("effective_create_date") or "").strip()
    if str(row.get("effective_create_date_source") or "").strip():
        entry["effective_create_date_source"] = str(row.get("effective_create_date_source") or "").strip()
    if str(row.get("source") or "").strip():
        entry["source"] = str(row.get("source") or "").strip()
    return entry


def _usable_source_material_count(
    *,
    request: dict[str, Any],
    candidates: list[dict[str, Any]],
    existing_by_account: dict[str, set[str]],
) -> int:
    advertiser_ids = [str(account.get("advertiser_id") or "") for account in _target_accounts(request)]
    advertiser_ids = [advertiser_id for advertiser_id in advertiser_ids if advertiser_id]
    if not advertiser_ids:
        return len(candidates)
    count = 0
    for row in candidates:
        material_id = str(row.get("material_id") or "")
        if any(material_id not in existing_by_account.get(advertiser_id, set()) for advertiser_id in advertiser_ids):
            count += 1
    return count


def _next_candidate(
    *,
    advertiser_id: str,
    candidates: list[dict[str, Any]],
    used_request_material_ids: set[str],
    used_unit_material_ids: set[str],
    material_accounts_used: dict[str, set[str]],
    material_account_use_counts: dict[str, dict[str, int]],
    existing_by_account: dict[str, set[str]],
    dedupe_scope: str,
    max_accounts_per_material: int,
    allow_reuse_on_shortage: bool,
) -> dict[str, Any] | None:
    existing_material_ids = existing_by_account.get(advertiser_id, set())
    for enforce_overlap in ([True, False] if allow_reuse_on_shortage else [True]):
        best_reuse_row: dict[str, Any] | None = None
        best_reuse_key: tuple[int, int] | None = None
        for order, row in enumerate(candidates):
            material_id = str(row.get("material_id") or "")
            if material_id in used_unit_material_ids:
                continue
            if material_id in existing_material_ids:
                continue
            if dedupe_scope == "request" and material_id in used_request_material_ids and enforce_overlap:
                continue
            if dedupe_scope == "max_account_overlap" and enforce_overlap:
                accounts = material_accounts_used.get(material_id, set())
                if advertiser_id in accounts:
                    continue
                if max_accounts_per_material > 0 and len(accounts) >= max_accounts_per_material:
                    continue
            if not enforce_overlap:
                account_use_count = int(material_account_use_counts.get(material_id, {}).get(advertiser_id, 0))
                reuse_key = (account_use_count, order)
                if best_reuse_key is None or reuse_key < best_reuse_key:
                    best_reuse_key = reuse_key
                    best_reuse_row = row
                continue
            return row
        if best_reuse_row is not None:
            return best_reuse_row
    return None


def _max_accounts_per_material(request: dict[str, Any], dedupe_scope: str) -> int:
    if dedupe_scope != "max_account_overlap":
        return 0
    requirements = _material_requirements(request)
    ratio = _float_value(requirements.get("max_cross_account_overlap_ratio"), 0.3)
    account_count = len(_target_accounts(request))
    return max(1, math.ceil(account_count * ratio))


def _allow_reuse_on_shortage(request: dict[str, Any]) -> bool:
    requirements = _material_requirements(request)
    return bool(requirements.get("allow_reuse_across_accounts", False)) or str(requirements.get("on_insufficient") or "") == "allow_reuse"


def _scale_top_material_reuse_enabled(request: dict[str, Any]) -> bool:
    requirements = _material_requirements(request)
    selection = _selection_policy(request)
    return (
        str(requirements.get("cross_account_reuse_mode") or "") == "scale_top_materials"
        and str(selection.get("selection_type") or "") == "high_spend"
        and bool(requirements.get("allow_reuse_across_accounts", False))
    )


def _initial_operation(request: dict[str, Any], key: str) -> str:
    value = request.get("initial_status") if isinstance(request.get("initial_status"), dict) else {}
    default = "DISABLE"
    return str(value.get(f"{key}_operation") or value.get("operation") or default)


def _build_projects(
    *,
    request: dict[str, Any],
    policy: dict[str, Any],
    candidates: list[dict[str, Any]],
    existing_by_account: dict[str, set[str]],
) -> list[dict[str, Any]]:
    requirements = _material_requirements(request)
    materials_per_unit = max(_int_value(requirements.get("materials_per_unit"), 1), 0)
    dedupe_scope = str(requirements.get("dedupe_scope") or "request")
    used_request_material_ids: set[str] = set()
    material_accounts_used: dict[str, set[str]] = {}
    material_account_use_counts: dict[str, dict[str, int]] = {}
    max_accounts_per_material = _max_accounts_per_material(request, dedupe_scope)
    allow_reuse_on_shortage = _allow_reuse_on_shortage(request)
    projects: list[dict[str, Any]] = []
    global_project_index = 0
    local_key_namespace = str(request.get("local_key_namespace") or "").strip()
    for account in _target_accounts(request):
        advertiser_id = str(account.get("advertiser_id") or "")
        project_count = max(_int_value(account.get("project_count"), 1), 0)
        units_per_project = max(_int_value(account.get("units_per_project"), 1), 0)
        for account_project_index in range(1, project_count + 1):
            global_project_index += 1
            project_key = (
                f"{advertiser_id}-{local_key_namespace}-p{account_project_index:03d}"
                if local_key_namespace
                else f"{advertiser_id}-p{account_project_index:03d}"
            )
            name_entry = _project_name_entry(request, policy, advertiser_id=advertiser_id, index=global_project_index)
            project_name = name_entry["project_name"]
            units: list[dict[str, Any]] = []
            for unit_index in range(1, units_per_project + 1):
                unit_key = f"{project_key}-u{unit_index:02d}"
                promotion_name = f"{project_name}_U{unit_index:02d}"
                materials: list[dict[str, Any]] = []
                used_unit_material_ids: set[str] = set()
                for _ in range(materials_per_unit):
                    row = _next_candidate(
                        advertiser_id=advertiser_id,
                        candidates=candidates,
                        used_request_material_ids=used_request_material_ids,
                        used_unit_material_ids=used_unit_material_ids,
                        material_accounts_used=material_accounts_used,
                        material_account_use_counts=material_account_use_counts,
                        existing_by_account=existing_by_account,
                        dedupe_scope=dedupe_scope,
                        max_accounts_per_material=max_accounts_per_material,
                        allow_reuse_on_shortage=allow_reuse_on_shortage,
                    )
                    if row is None:
                        break
                    material_id = str(row.get("material_id") or "")
                    if dedupe_scope == "request":
                        used_request_material_ids.add(material_id)
                    if dedupe_scope == "max_account_overlap":
                        material_accounts_used.setdefault(material_id, set()).add(advertiser_id)
                    material_account_use_counts.setdefault(material_id, {})
                    material_account_use_counts[material_id][advertiser_id] = (
                        int(material_account_use_counts[material_id].get(advertiser_id, 0)) + 1
                    )
                    used_unit_material_ids.add(material_id)
                    materials.append(_material_entry(row))
                units.append(
                    {
                        "unit_key": unit_key,
                        "unit_index": unit_index,
                        "promotion_name": promotion_name,
                        "operation": _initial_operation(request, "unit"),
                        "materials": materials,
                    }
                )
            projects.append(
                {
                    "project_key": project_key,
                    "advertiser_id": advertiser_id,
                    "project_index": global_project_index,
                    "project_name": project_name,
                    "naming": name_entry["naming"],
                    "project_type": str(request.get("project_type") or ""),
                    "daily_budget": float(account.get("daily_budget") or 0),
                    "operation": _initial_operation(request, "project"),
                    "field_defaults": request.get("field_defaults") if isinstance(request.get("field_defaults"), dict) else {},
                    "units": units,
                }
            )
    return projects


def _required_material_slots(request: dict[str, Any]) -> int:
    requirements = _material_requirements(request)
    materials_per_unit = max(_int_value(requirements.get("materials_per_unit"), 1), 0)
    total = 0
    for account in _target_accounts(request):
        project_count = max(_int_value(account.get("project_count"), 1), 0)
        units_per_project = max(_int_value(account.get("units_per_project"), 1), 0)
        total += project_count * units_per_project * materials_per_unit
    return total


def _violations(request: dict[str, Any], policy: dict[str, Any], *, candidate_count: int) -> list[str]:
    violations: list[str] = []
    accounts = _target_accounts(request)
    max_accounts = _policy_limit(policy, "max_target_accounts", 20)
    max_projects = _policy_limit(policy, "max_projects_per_account", 20)
    max_units = _policy_limit(policy, "max_units_per_project", 50)
    requirements = _material_requirements(request)
    dedupe_scope = str(requirements.get("dedupe_scope") or "request")
    required_materials = _required_material_slots(request)
    if required_materials > 0 and candidate_count <= 0:
        violations.append("source material account has no usable materials")
    if dedupe_scope == "request" and candidate_count < required_materials:
        violations.append(
            f"source material account has {candidate_count} usable materials, expected {required_materials} for dedupe_scope=request"
        )
    if len(accounts) > max_accounts:
        violations.append("target account count exceeds policy limit")
    for account in accounts:
        advertiser_id = str(account.get("advertiser_id") or "")
        if _int_value(account.get("project_count"), 1) > max_projects:
            violations.append(f"project count for {advertiser_id} exceeds policy limit")
        if _int_value(account.get("units_per_project"), 1) > max_units:
            violations.append(f"unit count for {advertiser_id} exceeds policy limit")
    return violations


def _summary(
    *,
    request: dict[str, Any],
    plan_id: str,
    projects: list[dict[str, Any]],
    source_material_count: int,
    violations: list[str],
) -> dict[str, Any]:
    units = [unit for project in projects for unit in project.get("units", [])]
    material_ids = {
        str(material.get("material_id") or "")
        for unit in units
        for material in unit.get("materials", [])
        if str(material.get("material_id") or "")
    }
    return {
        "plan_id": plan_id,
        "request_id": str(request.get("request_id") or ""),
        "target_date": str(request.get("target_date") or ""),
        "planned_project_count": len(projects),
        "planned_unit_count": len(units),
        "planned_material_count": len(material_ids),
        "source_material_count": source_material_count,
        "violation_count": len(violations),
    }


def build_create_strategy_plan(
    *,
    request: dict[str, Any],
    db_path: str | Path,
    policy: dict[str, Any],
) -> dict[str, Any]:
    cfg = _request_config(request)
    request_id = str(cfg.get("request_id") or "").strip()
    if not request_id:
        raise ValueError("create strategy plan requires request_id")
    candidates = _candidate_rows(db_path=db_path, request=cfg, policy=policy)
    existing_by_account = _target_existing_material_ids_by_account(db_path=db_path, request=cfg, policy=policy)
    source_material_count = _usable_source_material_count(
        request=cfg,
        candidates=candidates,
        existing_by_account=existing_by_account,
    )
    projects = _build_projects(request=cfg, policy=policy, candidates=candidates, existing_by_account=existing_by_account)
    violations = _violations(cfg, policy, candidate_count=source_material_count)
    plan_id = str(cfg.get("plan_id") or "").strip() or f"create_plan_{request_id}"
    return {
        "ok": not violations,
        "workflow": "create_strategy_plan",
        "plan_id": plan_id,
        "request_id": request_id,
        "phase": "phase1",
        "target_date": str(cfg.get("target_date") or ""),
        "execution_enabled": False,
        "external_api_calls": 0,
        "summary": _summary(
            request=cfg,
            plan_id=plan_id,
            projects=projects,
            source_material_count=source_material_count,
            violations=violations,
        ),
        "request": cfg,
        "strategy": {
            "source": "product_source_materials",
            "source_advertiser_id": str(cfg.get("source_advertiser_id") or ""),
            "projects": projects,
        },
        "preflight": {"required": True, "status": "draft_only"},
        "dry_run": {"required": True, "status": "draft_only"},
        "violations": violations,
        "actions": [],
        "live_api_payloads": [],
        "execute": {"status": "not_implemented_in_phase1"},
    }


def _store_plan(*, db_path: str | Path, request: dict[str, Any], plan: dict[str, Any]) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO create_strategy_plans (
              plan_id, request_id, phase, execution_enabled,
              request_json, plan_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(plan_id) DO UPDATE SET
              request_id = excluded.request_id,
              phase = excluded.phase,
              execution_enabled = excluded.execution_enabled,
              request_json = excluded.request_json,
              plan_json = excluded.plan_json,
              created_at = excluded.created_at
            """,
            (
                plan["plan_id"],
                plan["request_id"],
                plan["phase"],
                1 if plan.get("execution_enabled") else 0,
                json.dumps(request, ensure_ascii=False, sort_keys=True),
                json.dumps(plan, ensure_ascii=False, sort_keys=True),
                _now_iso(),
            ),
        )


def run_create_strategy_plan_request(
    request: dict[str, Any],
    *,
    db_path: str | Path,
    runs_dir: str | Path,
    policy: dict[str, Any],
    create_request_artifact_path: str | Path | None = None,
) -> dict[str, Any]:
    cfg = _request_config(request)
    plan = build_create_strategy_plan(request=cfg, db_path=db_path, policy=policy)
    _store_plan(db_path=db_path, request=cfg, plan=plan)
    payload = {
        "ok": plan["ok"],
        "workflow": "create_strategy_plan",
        "phase": "phase1",
        "execution_enabled": False,
        "external_api_calls": 0,
        "summary": plan["summary"],
        "lineage": {
            "create_request": create_ref(
                workflow="create_request",
                artifact={"request": cfg},
                artifact_path=create_request_artifact_path,
            ),
        },
        "plan": plan,
    }
    artifact = write_run_artifact(runs_dir, "create_strategy_plan", payload)
    return {**payload, "artifact_path": str(artifact)}
