from __future__ import annotations

from typing import Any

from roibang_v2.ui.create_plan_review import build_create_plan_review


def _text(value: Any) -> str:
    return str(value or "").strip()


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _bool_missing_video(row: dict[str, Any]) -> bool:
    return not _text(row.get("video_id"))


def _review_from_container(value: dict[str, Any]) -> dict[str, Any]:
    review = value.get("review") if isinstance(value.get("review"), dict) else {}
    if review:
        merged = dict(review)
        for key in ("accounts", "materials", "creative_usage", "unit_assignments"):
            if key not in merged and key in value:
                merged[key] = value[key]
        return merged
    if any(key in value for key in ("summary", "materials", "creative_usage", "unit_assignments")):
        return value
    return {}


def _copy_rows(rows: Any) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        return []
    return [dict(row) for row in rows if isinstance(row, dict)]


def _summary_value(review: dict[str, Any], key: str, default: Any = 0) -> Any:
    summary = review.get("summary") if isinstance(review.get("summary"), dict) else {}
    return summary.get(key, default)


def _material_rows(review: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in _copy_rows(review.get("materials")):
        material_id = _text(row.get("material_id"))
        video_id = _text(row.get("video_id"))
        accounts = row.get("covered_accounts") if isinstance(row.get("covered_accounts"), list) else []
        units = row.get("covered_units") if isinstance(row.get("covered_units"), list) else []
        rows.append(
            {
                "material_id": material_id,
                "video_id": video_id,
                "name": _text(row.get("name")),
                "product": _text(row.get("product")),
                "product_key": _text(row.get("product_key")),
                "source_advertiser_id": _text(row.get("source_advertiser_id")),
                "product_stat_cost": row.get("product_stat_cost", 0),
                "product_convert_cnt": row.get("product_convert_cnt", 0),
                "rank": row.get("rank"),
                "effective_create_date": _text(row.get("effective_create_date")),
                "first_seen_metric_date": _text(row.get("first_seen_metric_date")),
                "usage_count": _int(row.get("usage_count")),
                "covered_account_count": _int(row.get("covered_account_count")),
                "covered_unit_count": _int(row.get("covered_unit_count")),
                "covered_accounts": [_text(item) for item in accounts if _text(item)],
                "covered_units": [_text(item) for item in units if _text(item)],
                "missing_video_id": not video_id,
            }
        )
    return sorted(
        rows,
        key=lambda row: (
            bool(row["missing_video_id"]) is False,
            -_int(row.get("usage_count")),
            -float(row.get("product_stat_cost") or 0),
            _text(row.get("material_id")) or _text(row.get("video_id")),
        ),
    )


def _creative_rows(review: dict[str, Any], group_key: str) -> list[dict[str, Any]]:
    creative_usage = review.get("creative_usage") if isinstance(review.get("creative_usage"), dict) else {}
    return _copy_rows(creative_usage.get(group_key))


def _unit_rows(review: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in _copy_rows(review.get("unit_assignments")):
        materials = _copy_rows(row.get("materials"))
        rows.append(
            {
                "advertiser_id": _text(row.get("advertiser_id")),
                "project_key": _text(row.get("project_key")),
                "project_name": _text(row.get("project_name")),
                "unit_key": _text(row.get("unit_key")),
                "promotion_name": _text(row.get("promotion_name")),
                "materials": materials,
                "material_count": len(materials),
                "titles": [_text(item) for item in row.get("titles") or [] if _text(item)],
                "title_count": len([item for item in row.get("titles") or [] if _text(item)]),
                "ctas": [_text(item) for item in row.get("ctas") or [] if _text(item)],
                "cta_count": len([item for item in row.get("ctas") or [] if _text(item)]),
                "selling_points": [_text(item) for item in row.get("selling_points") or [] if _text(item)],
                "selling_point_count": len([item for item in row.get("selling_points") or [] if _text(item)]),
            }
        )
    return rows


def build_create_plan_preview_from_review(value: dict[str, Any]) -> dict[str, Any]:
    review = _review_from_container(value)
    if not review:
        return {}
    materials = _material_rows(review)
    titles = _creative_rows(review, "titles")
    ctas = _creative_rows(review, "ctas")
    selling_points = _creative_rows(review, "selling_points")
    units = _unit_rows(review)
    blocking_reasons = list(review.get("blocking_reasons") or [])
    warnings = list(review.get("warnings") or [])
    summary = {
        "product": _summary_value(review, "product", ""),
        "product_key": _summary_value(review, "product_key", ""),
        "source_advertiser_id": _summary_value(review, "source_advertiser_id", ""),
        "mode_key": _summary_value(review, "mode_key", ""),
        "plan_id": _summary_value(review, "plan_id", ""),
        "target_account_count": _summary_value(review, "target_account_count", len(review.get("accounts") or [])),
        "planned_project_count": _summary_value(review, "planned_project_count", 0),
        "planned_unit_count": _summary_value(review, "planned_unit_count", len(units)),
        "planned_material_count": _summary_value(review, "planned_material_count", 0),
        "source_material_count": _summary_value(review, "source_material_count", 0),
        "material_source": _summary_value(review, "material_source", ""),
        "material_assignment_count": _summary_value(
            review,
            "material_assignment_count",
            sum(_int(row.get("usage_count")) for row in materials),
        ),
        "unique_material_count": _summary_value(review, "unique_material_count", len(materials)),
        "missing_video_id_material_count": sum(1 for row in materials if _bool_missing_video(row)),
        "title_count": len(titles),
        "cta_count": len(ctas),
        "selling_point_count": len(selling_points),
        "warning_count": _summary_value(review, "warning_count", len(warnings)),
        "blocking_reason_count": _summary_value(review, "blocking_reason_count", len(blocking_reasons)),
        "selection_type": _summary_value(review, "selection_type", ""),
        "requires_lookback_days": bool(_summary_value(review, "requires_lookback_days", False)),
        "can_execute": bool(review.get("can_execute")),
    }
    return {
        "review": review,
        "summary": summary,
        "blocking_reasons": blocking_reasons,
        "warnings": warnings,
        "accounts": _copy_rows(review.get("accounts")),
        "materials": materials,
        "copywriting": titles,
        "ctas": ctas,
        "selling_points": selling_points,
        "units": units,
    }


def build_create_plan_preview(plan_payload: dict[str, Any]) -> dict[str, Any]:
    return build_create_plan_preview_from_review(build_create_plan_review(plan_payload))


def filter_preview_materials(
    rows: list[dict[str, Any]],
    *,
    missing_video_only: bool = False,
    min_usage_count: int = 0,
    account_id: str = "",
    query: str = "",
) -> list[dict[str, Any]]:
    account = _text(account_id)
    query_text = _text(query).lower()
    result: list[dict[str, Any]] = []
    for row in rows:
        if missing_video_only and not _bool_missing_video(row):
            continue
        if _int(row.get("usage_count")) < int(min_usage_count or 0):
            continue
        if account:
            accounts = row.get("covered_accounts") if isinstance(row.get("covered_accounts"), list) else []
            if account not in [_text(item) for item in accounts]:
                continue
        if query_text:
            haystack = " ".join(
                [
                    _text(row.get("material_id")),
                    _text(row.get("video_id")),
                    _text(row.get("name")),
                ]
            ).lower()
            if query_text not in haystack:
                continue
        result.append(row)
    return result


def filter_preview_units(
    rows: list[dict[str, Any]],
    *,
    account_id: str = "",
    project_query: str = "",
) -> list[dict[str, Any]]:
    account = _text(account_id)
    query = _text(project_query).lower()
    result: list[dict[str, Any]] = []
    for row in rows:
        if account and _text(row.get("advertiser_id")) != account:
            continue
        if query:
            haystack = " ".join(
                [
                    _text(row.get("project_key")),
                    _text(row.get("project_name")),
                    _text(row.get("unit_key")),
                    _text(row.get("promotion_name")),
                ]
            ).lower()
            if query not in haystack:
                continue
        result.append(row)
    return result
