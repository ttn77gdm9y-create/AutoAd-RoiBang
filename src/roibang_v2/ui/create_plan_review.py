from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from roibang_v2.workflows.frontend_operation_log import create_operation_details_from_plan


def _text(value: Any) -> str:
    return str(value or "").strip()


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _float(value: Any) -> float:
    try:
        return round(float(value or 0), 2)
    except (TypeError, ValueError):
        return 0.0


def _summary(plan_payload: dict[str, Any]) -> dict[str, Any]:
    value = plan_payload.get("summary")
    return dict(value) if isinstance(value, dict) else {}


def _request(plan_payload: dict[str, Any]) -> dict[str, Any]:
    value = plan_payload.get("create_request")
    return dict(value) if isinstance(value, dict) else {}


def _selection_type(plan_payload: dict[str, Any]) -> str:
    request = _request(plan_payload)
    selection = request.get("material_selection") if isinstance(request.get("material_selection"), dict) else {}
    return _text(selection.get("selection_type"))


def _material_key(row: dict[str, Any]) -> str:
    return _text(row.get("material_id")) or _text(row.get("source_video_id")) or _text(row.get("name"))


def _material_rows(details: dict[str, Any]) -> list[dict[str, Any]]:
    product = _text(details.get("product"))
    product_key = _text(details.get("product_key"))
    source_advertiser_id = _text(details.get("source_advertiser_id"))
    rows_by_key: dict[str, dict[str, Any]] = {}
    accounts_by_key: dict[str, set[str]] = defaultdict(set)
    units_by_key: dict[str, set[str]] = defaultdict(set)
    for assignment in details.get("material_assignments") or []:
        if not isinstance(assignment, dict):
            continue
        key = _material_key(assignment)
        if not key:
            continue
        row = rows_by_key.setdefault(
            key,
            {
                "material_id": _text(assignment.get("material_id")),
                "video_id": _text(assignment.get("source_video_id")),
                "name": _text(assignment.get("name")),
                "product": product,
                "product_key": product_key,
                "source_advertiser_id": source_advertiser_id,
                "product_stat_cost": _float(
                    assignment.get("product_stat_cost")
                    if assignment.get("product_stat_cost") is not None
                    else assignment.get("stat_cost")
                ),
                "product_convert_cnt": _float(
                    assignment.get("product_convert_cnt")
                    if assignment.get("product_convert_cnt") is not None
                    else assignment.get("convert_cnt")
                ),
                "rank": _int(assignment.get("rank")),
                "effective_create_date": _text(assignment.get("effective_create_date")),
                "first_seen_metric_date": _text(assignment.get("first_seen_metric_date")),
                "usage_count": 0,
                "covered_account_count": 0,
                "covered_unit_count": 0,
            },
        )
        row["usage_count"] = int(row["usage_count"]) + 1
        account_id = _text(assignment.get("advertiser_id"))
        unit_key = _text(assignment.get("unit_key"))
        if account_id:
            accounts_by_key[key].add(account_id)
        if unit_key:
            units_by_key[key].add(unit_key)
    for key, row in rows_by_key.items():
        row["covered_account_count"] = len(accounts_by_key[key])
        row["covered_unit_count"] = len(units_by_key[key])
        row["covered_accounts"] = sorted(accounts_by_key[key])
        row["covered_units"] = sorted(units_by_key[key])
    return sorted(
        rows_by_key.values(),
        key=lambda row: (-int(row["usage_count"]), -float(row["product_stat_cost"]), _text(row.get("material_id"))),
    )


def _creative_usage(details: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    title_counter: Counter[str] = Counter()
    cta_counter: Counter[str] = Counter()
    selling_counter: Counter[str] = Counter()
    title_units: dict[str, set[str]] = defaultdict(set)
    cta_units: dict[str, set[str]] = defaultdict(set)
    selling_units: dict[str, set[str]] = defaultdict(set)
    for unit in details.get("unit_copywriting") or []:
        if not isinstance(unit, dict):
            continue
        unit_key = _text(unit.get("unit_key"))
        for item in unit.get("title_material_list") or []:
            title = _text(item.get("title") if isinstance(item, dict) else item)
            if title:
                title_counter[title] += 1
                title_units[title].add(unit_key)
        for item in unit.get("call_to_action_buttons") or []:
            cta = _text(item)
            if cta:
                cta_counter[cta] += 1
                cta_units[cta].add(unit_key)
        product_info = unit.get("product_info") if isinstance(unit.get("product_info"), dict) else {}
        for item in product_info.get("selling_points") or []:
            selling = _text(item)
            if selling:
                selling_counter[selling] += 1
                selling_units[selling].add(unit_key)

    def rows(counter: Counter[str], unit_sets: dict[str, set[str]], key: str) -> list[dict[str, Any]]:
        return [
            {key: text, "usage_count": count, "covered_unit_count": len(unit_sets[text])}
            for text, count in counter.most_common()
        ]

    return {
        "titles": rows(title_counter, title_units, "title"),
        "ctas": rows(cta_counter, cta_units, "cta"),
        "selling_points": rows(selling_counter, selling_units, "selling_point"),
    }


def _unit_assignment_rows(details: dict[str, Any]) -> list[dict[str, Any]]:
    copywriting_by_unit: dict[str, dict[str, Any]] = {}
    for unit in details.get("unit_copywriting") or []:
        if isinstance(unit, dict):
            copywriting_by_unit[_text(unit.get("unit_key"))] = unit
    materials_by_unit: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for assignment in details.get("material_assignments") or []:
        if not isinstance(assignment, dict):
            continue
        materials_by_unit[_text(assignment.get("unit_key"))].append(
            {
                "material_id": _text(assignment.get("material_id")),
                "video_id": _text(assignment.get("source_video_id")),
                "name": _text(assignment.get("name")),
            }
        )
    rows: list[dict[str, Any]] = []
    for unit_key, copywriting in copywriting_by_unit.items():
        product_info = copywriting.get("product_info") if isinstance(copywriting.get("product_info"), dict) else {}
        titles = [
            _text(item.get("title") if isinstance(item, dict) else item)
            for item in copywriting.get("title_material_list") or []
        ]
        rows.append(
            {
                "advertiser_id": _text(copywriting.get("advertiser_id")),
                "project_key": _text(copywriting.get("project_key")),
                "project_name": _text(copywriting.get("project_name")),
                "unit_key": unit_key,
                "promotion_name": _text(copywriting.get("promotion_name")),
                "materials": materials_by_unit.get(unit_key, []),
                "titles": [item for item in titles if item],
                "ctas": [_text(item) for item in copywriting.get("call_to_action_buttons") or [] if _text(item)],
                "selling_points": [
                    _text(item) for item in product_info.get("selling_points") or [] if _text(item)
                ],
            }
        )
    return rows


def _blocking_reasons(
    *,
    summary: dict[str, Any],
    materials: list[dict[str, Any]],
    unit_assignments: list[dict[str, Any]],
) -> list[str]:
    reasons: list[str] = []
    if _int(summary.get("target_account_count")) <= 0:
        reasons.append("账户数为 0")
    if _int(summary.get("planned_project_count")) <= 0:
        reasons.append("计划项目数为 0")
    if _int(summary.get("planned_unit_count")) <= 0:
        reasons.append("计划单元数为 0")
    if _int(summary.get("planned_material_count")) <= 0:
        reasons.append("计划素材数为 0")
    if _int(summary.get("source_material_count")) <= 0:
        reasons.append("候选素材数为 0")
    if _int(summary.get("violation_count")) > 0:
        reasons.append(f"规则异常数量：{_int(summary.get('violation_count'))}")
    if not materials:
        reasons.append("没有选中任何素材")
    missing_video = sum(1 for row in materials if not _text(row.get("video_id")))
    if missing_video:
        reasons.append(f"缺 video_id（视频 ID）素材数：{missing_video}")
    missing_titles = sum(1 for row in unit_assignments if not row.get("titles"))
    if missing_titles:
        reasons.append(f"单元缺文案数：{missing_titles}")
    missing_ctas = sum(1 for row in unit_assignments if not row.get("ctas"))
    if missing_ctas:
        reasons.append(f"单元缺 CTA（行动按钮）数：{missing_ctas}")
    missing_selling = sum(1 for row in unit_assignments if not row.get("selling_points"))
    if missing_selling:
        reasons.append(f"单元缺卖点数：{missing_selling}")
    return reasons


def _warnings(materials: list[dict[str, Any]], unit_assignments: list[dict[str, Any]]) -> list[str]:
    warnings: list[str] = []
    for row in materials:
        if int(row.get("usage_count") or 0) >= 10:
            warnings.append(
                f"素材 {row.get('material_id') or row.get('video_id')} 使用次数较高：{row.get('usage_count')}"
            )
    account_unique: dict[str, set[str]] = defaultdict(set)
    for unit in unit_assignments:
        account_id = _text(unit.get("advertiser_id"))
        for material in unit.get("materials") or []:
            key = _text(material.get("material_id")) or _text(material.get("video_id"))
            if account_id and key:
                account_unique[account_id].add(key)
    for account_id, keys in account_unique.items():
        if len(keys) <= 1:
            warnings.append(f"账户 {account_id} 唯一素材数较少：{len(keys)}")
    return warnings


def build_create_plan_review(plan_payload: dict[str, Any]) -> dict[str, Any]:
    details = create_operation_details_from_plan(plan_payload)
    plan_summary = _summary(plan_payload)
    account_count = len(details.get("accounts") or [])
    materials = _material_rows(details)
    creative_usage = _creative_usage(details)
    unit_assignments = _unit_assignment_rows(details)
    summary = {
        "product": _text(details.get("product")),
        "product_key": _text(details.get("product_key")),
        "source_advertiser_id": _text(details.get("source_advertiser_id")),
        "mode_key": _text(details.get("mode_key")),
        "plan_id": _text(details.get("plan_id")),
        "target_account_count": account_count,
        "planned_project_count": _int(plan_summary.get("planned_project_count")),
        "planned_unit_count": _int(plan_summary.get("planned_unit_count")),
        "planned_material_count": _int(plan_summary.get("planned_material_count")),
        "source_material_count": _int(plan_summary.get("source_material_count")),
        "material_source": _text(plan_summary.get("material_source")),
        "violation_count": _int(plan_summary.get("violation_count")),
        "material_assignment_count": _int(details.get("material_assignment_count")),
        "unique_material_count": len(materials),
        "missing_video_id_material_count": sum(1 for row in materials if not _text(row.get("video_id"))),
        "selection_type": _selection_type(plan_payload),
    }
    summary["requires_lookback_days"] = summary["selection_type"] != "random_materials"
    blocking_reasons = _blocking_reasons(summary=summary, materials=materials, unit_assignments=unit_assignments)
    warning_rows = _warnings(materials, unit_assignments)
    summary["blocking_reason_count"] = len(blocking_reasons)
    summary["warning_count"] = len(warning_rows)
    return {
        "ok": not blocking_reasons,
        "can_execute": not blocking_reasons,
        "summary": summary,
        "blocking_reasons": blocking_reasons,
        "warnings": warning_rows,
        "accounts": details.get("accounts") or [],
        "materials": materials,
        "creative_usage": creative_usage,
        "unit_assignments": unit_assignments,
        "details": details,
    }
