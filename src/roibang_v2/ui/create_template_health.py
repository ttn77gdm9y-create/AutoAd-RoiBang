from __future__ import annotations

from typing import Any


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any) -> str:
    return str(value or "").strip()


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _template(mode: dict[str, Any], catalog: dict[str, Any]) -> dict[str, Any]:
    templates = _dict(catalog.get("templates"))
    return _dict(templates.get(_text(mode.get("template_key"))))


def _has_value(mapping: dict[str, Any], key: str) -> bool:
    return key in mapping and _text(mapping.get(key)) != ""


def _contains_yzt(value: Any) -> bool:
    return "勇者突进" in _text(value) or "yzt" in _text(value).lower()


def _is_7r_template(mode: dict[str, Any], template: dict[str, Any]) -> bool:
    mode_key = _text(mode.get("mode_key")).lower()
    template_key = _text(mode.get("template_key")).lower()
    return "7r" in mode_key or "7r" in template_key or bool(template.get("requires_roi_goal"))


def build_create_template_health(mode: dict[str, Any], catalog: dict[str, Any]) -> dict[str, Any]:
    defaults = _dict(mode.get("defaults"))
    selection = _dict(mode.get("material_selection"))
    creative = _dict(mode.get("unit_creative_selection"))
    template_key = _text(mode.get("template_key"))
    product_key = _text(mode.get("product_key"))
    template = _template(mode, catalog)
    title_pool = [item for item in _list(template.get("title_pool")) if _text(item)]
    cta_pool = [item for item in _list(template.get("cta_pool")) if _text(item)]
    selling_points = [item for item in _list(template.get("product_selling_points")) if _text(item)]
    aweme_ids = [item for item in _list(template.get("aweme_ids")) if _text(item)]
    selection_type = _text(selection.get("selection_type"))
    random_materials = selection_type == "random_materials"

    blocking_reasons: list[str] = []
    warnings: list[str] = []

    if not template:
        blocking_reasons.append(f"基础模板不存在：{template_key or '-'}")
    if _text(catalog.get("product_key")) and _text(catalog.get("product_key")) != product_key:
        blocking_reasons.append(f"模板文件产品不匹配：{_text(catalog.get('product_key'))} != {product_key}")
    if not title_pool:
        blocking_reasons.append("文案池为空")
    if not cta_pool:
        blocking_reasons.append("CTA（行动按钮）池为空")
    if not selling_points:
        blocking_reasons.append("卖点池为空")

    if random_materials:
        if _has_value(defaults, "cpa_bid"):
            blocking_reasons.append("随机素材模板不应写死 cpa_bid（项目出价）")
        if _has_value(defaults, "roi_coefficient"):
            blocking_reasons.append("随机素材模板不应写死 roi_coefficient（ROI 系数）")
        if _has_value(selection, "lookback_days"):
            blocking_reasons.append("随机素材模板不应要求 lookback_days（回看天数）")
        if _int(selection.get("min_stat_cost")) != 0:
            blocking_reasons.append("随机素材模板最低消耗应为 0")

    for key in ["product_name", "source_name", "copy_product_name", "copy_source_name"]:
        if _contains_yzt(template.get(key)):
            blocking_reasons.append(f"模板仍残留勇者突进字段：{key}")

    cta_max = _int(creative.get("cta_max_count"))
    selling_max = _int(creative.get("product_selling_point_max_count"))
    if cta_pool and cta_max > len(cta_pool):
        warnings.append(f"CTA（行动按钮）随机数量超过池大小：{cta_max} > {len(cta_pool)}")
    if selling_points and selling_max > len(selling_points):
        warnings.append(f"卖点随机数量超过池大小：{selling_max} > {len(selling_points)}")

    summary = {
        "product_key": product_key,
        "template_key": template_key,
        "selection_type": selection_type,
        "title_count": len(title_pool),
        "cta_count": len(cta_pool),
        "selling_point_count": len(selling_points),
        "aweme_count": len(aweme_ids),
        "hardcoded_cpa_bid": _has_value(defaults, "cpa_bid"),
        "hardcoded_roi_coefficient": _has_value(defaults, "roi_coefficient"),
        "requires_lookback_days": _has_value(selection, "lookback_days"),
        "product_specific_template": bool(product_key and _text(catalog.get("product_key")) == product_key),
    }
    return {
        "ok": not blocking_reasons,
        "status": "passed" if not blocking_reasons else "blocked",
        "summary": summary,
        "blocking_reasons": blocking_reasons,
        "warnings": warnings,
    }


def build_create_mode_health(mode: dict[str, Any], catalog: dict[str, Any]) -> dict[str, Any]:
    defaults = _dict(mode.get("defaults"))
    selection = _dict(mode.get("material_selection"))
    requirements = _dict(mode.get("material_requirements"))
    mode_key = _text(mode.get("mode_key"))
    product_key = _text(mode.get("product_key"))
    template_key = _text(mode.get("template_key"))
    template = _template(mode, catalog)
    selection_type = _text(selection.get("selection_type"))
    random_materials = selection_type == "random_materials"
    is_diandian = product_key == "diandian-hero"
    is_7r = _is_7r_template(mode, template)
    blocking_reasons: list[str] = []
    warnings: list[str] = []

    if not mode_key:
        blocking_reasons.append("mode_key（创建模式键）不能为空")
    if not product_key:
        blocking_reasons.append("product_key（产品键）不能为空")
    if not template_key:
        blocking_reasons.append("template_key（基础模板键）不能为空")
    if template_key and not template:
        blocking_reasons.append(f"基础模板不存在：{template_key}")
    if _text(catalog.get("product_key")) and _text(catalog.get("product_key")) != product_key:
        blocking_reasons.append(f"模板文件产品不匹配：{_text(catalog.get('product_key'))} != {product_key}")

    for key, label in [
        ("daily_budget", "daily_budget（日预算）"),
        ("project_count", "project_count（项目数）"),
        ("units_per_project", "units_per_project（单元数）"),
    ]:
        if _int(defaults.get(key)) <= 0:
            blocking_reasons.append(f"{label}必须大于 0")
    if _int(requirements.get("materials_per_unit")) <= 0:
        blocking_reasons.append("materials_per_unit（每单元素材数）必须大于 0")

    if random_materials:
        random_forbidden = [
            ("lookback_days", "lookback_days（回看天数）"),
            ("first_seen_days", "first_seen_days（有效创建日期回看）"),
            ("max_stat_cost", "max_stat_cost（最高消耗）"),
            ("min_convert_cnt", "min_convert_cnt（最低转化）"),
            ("max_convert_cnt", "max_convert_cnt（最高转化）"),
            ("candidate_pool_limit", "candidate_pool_limit（候选池上限）"),
        ]
        for key, label in random_forbidden:
            if _has_value(selection, key):
                blocking_reasons.append(f"随机素材不应设置 {label}")
        if _int(selection.get("min_stat_cost")) != 0:
            blocking_reasons.append("随机素材 min_stat_cost（最低消耗）必须为 0")
        if _text(selection.get("sort_by")) != "random_stable":
            blocking_reasons.append("随机素材 sort_by（排序方式）必须为 random_stable（稳定随机）")
        if not bool(selection.get("random_shuffle")):
            blocking_reasons.append("随机素材 random_shuffle（随机打乱）必须为 true")
        if is_diandian and _has_value(defaults, "cpa_bid"):
            blocking_reasons.append("点点英雄随机素材不应写死 cpa_bid（项目出价）")
        if is_diandian and _has_value(defaults, "roi_coefficient"):
            blocking_reasons.append("点点英雄随机素材不应写死 roi_coefficient（ROI 系数）")

    if _has_value(defaults, "roi_coefficient") and not is_7r:
        blocking_reasons.append("非 7R 模板不应写 roi_coefficient（ROI 系数）")
    if is_7r and not _has_value(defaults, "roi_coefficient"):
        warnings.append("7R 模板 ROI 系数建议在本次生成时填写，不建议写死到模板")

    summary = {
        "mode_key": mode_key,
        "product_key": product_key,
        "template_key": template_key,
        "selection_type": selection_type,
        "random_materials": random_materials,
        "is_7r_template": is_7r,
        "hardcoded_cpa_bid": _has_value(defaults, "cpa_bid"),
        "hardcoded_roi_coefficient": _has_value(defaults, "roi_coefficient"),
        "requires_lookback_days": _has_value(selection, "lookback_days"),
        "daily_budget": _int(defaults.get("daily_budget")),
        "project_count": _int(defaults.get("project_count")),
        "units_per_project": _int(defaults.get("units_per_project")),
        "materials_per_unit": _int(requirements.get("materials_per_unit")),
        "product_specific_template": bool(product_key and _text(catalog.get("product_key")) == product_key),
    }
    return {
        "ok": not blocking_reasons,
        "status": "passed" if not blocking_reasons else "blocked",
        "summary": summary,
        "blocking_reasons": blocking_reasons,
        "warnings": warnings,
    }
