from __future__ import annotations

from typing import Any


RANDOM_MATERIALS_IGNORED_SELECTION_KEYS = {
    "lookback_days",
    "first_seen_days",
    "min_create_age_days",
    "max_stat_cost",
    "min_convert_cnt",
    "max_convert_cnt",
    "candidate_pool_limit",
}


def normalize_material_selection(selection: dict[str, Any]) -> dict[str, Any]:
    result = dict(selection)
    selection_type = str(result.get("selection_type") or "").strip()
    if selection_type == "random_materials":
        for key in RANDOM_MATERIALS_IGNORED_SELECTION_KEYS:
            result.pop(key, None)
        result["source_scope"] = str(result.get("source_scope") or "source_material_account")
        result["min_stat_cost"] = 0
        result["sort_by"] = "random_stable"
        result["random_shuffle"] = True
    return result


def normalize_create_mode_config(mode_config: dict[str, Any]) -> dict[str, Any]:
    result = dict(mode_config)
    selection = result.get("material_selection") if isinstance(result.get("material_selection"), dict) else {}
    normalized_selection = normalize_material_selection(selection)
    if normalized_selection:
        result["material_selection"] = normalized_selection
    if normalized_selection.get("selection_type") == "random_materials":
        defaults = dict(result.get("defaults") if isinstance(result.get("defaults"), dict) else {})
        defaults.pop("cpa_bid", None)
        defaults.pop("roi_coefficient", None)
        result["defaults"] = defaults
    return result
