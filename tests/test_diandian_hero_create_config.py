import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load(path: str) -> dict:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def test_diandian_hero_random_material_modes_do_not_hardcode_bid_roi_or_lookback():
    for name in [
        "configs/create-modes/diandian-hero/wx_pay_male_random_materials.local.json",
        "configs/create-modes/diandian-hero/wx_pay_general_random_materials.local.json",
    ]:
        payload = _load(name)
        defaults = payload.get("defaults") or {}
        selection = payload.get("material_selection") or {}

        assert payload["product_key"] == "diandian-hero"
        assert "cpa_bid" not in defaults
        assert "roi_coefficient" not in defaults
        assert selection["selection_type"] == "random_materials"
        assert "lookback_days" not in selection


def test_diandian_hero_template_is_product_specific_and_has_creative_pools():
    payload = _load("configs/create-templates/diandian-hero.local.json")

    assert payload["product_key"] == "diandian-hero"
    assert payload["source"] == "diandian_hero_product_template"
    for template in payload["templates"].values():
        assert template["product_name"] == "点点英雄"
        assert template["source_name"] == "点点英雄"
        assert template["copy_product_name"] == "点点英雄"
        assert template["copy_source_name"] == "点点英雄"
        assert len(template["title_pool"]) >= 3
        assert len(template["cta_pool"]) >= 3
        assert len(template["product_selling_points"]) >= 3
