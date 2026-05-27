from roibang_v2.ui.create_template_health import build_create_template_health


def _mode(selection_type: str = "random_materials") -> dict:
    return {
        "mode_key": "wx_pay_male_random_materials",
        "product_key": "diandian-hero",
        "product": "点点英雄",
        "template_key": "wx_pay_male",
        "defaults": {"daily_budget": 88888, "project_count": 5, "units_per_project": 1},
        "material_selection": {
            "selection_type": selection_type,
            "source_scope": "source_material_account",
            "min_stat_cost": 0,
            "sort_by": "random_stable",
        },
        "unit_creative_selection": {
            "title_strategy": "deterministic_shuffle_per_unit",
            "cta_min_count": 2,
            "cta_max_count": 3,
            "product_selling_point_min_count": 2,
            "product_selling_point_max_count": 3,
        },
    }


def _catalog() -> dict:
    return {
        "product_key": "diandian-hero",
        "product": "点点英雄",
        "templates": {
            "wx_pay_male": {
                "product_name": "点点英雄",
                "source_name": "点点英雄",
                "copy_product_name": "点点英雄",
                "copy_source_name": "点点英雄",
                "title_pool": ["标题1", "标题2", "标题3"],
                "cta_pool": ["点击即玩", "不用下载", "全场免费"],
                "product_selling_points": ["爆率高", "福利多", "不肝不氪"],
                "aweme_ids": ["58845779326"],
            }
        },
    }


def test_template_health_passes_for_diandian_random_materials():
    result = build_create_template_health(_mode(), _catalog())

    assert result["ok"] is True
    assert result["status"] == "passed"
    assert result["blocking_reasons"] == []
    assert result["summary"] == {
        "product_key": "diandian-hero",
        "template_key": "wx_pay_male",
        "selection_type": "random_materials",
        "title_count": 3,
        "cta_count": 3,
        "selling_point_count": 3,
        "aweme_count": 1,
        "hardcoded_cpa_bid": False,
        "hardcoded_roi_coefficient": False,
        "requires_lookback_days": False,
        "product_specific_template": True,
    }


def test_template_health_blocks_missing_creative_pools_and_template():
    result = build_create_template_health(
        {**_mode(), "template_key": "missing"},
        {"product_key": "diandian-hero", "templates": {}},
    )

    assert result["ok"] is False
    assert "基础模板不存在：missing" in result["blocking_reasons"]
    assert "文案池为空" in result["blocking_reasons"]
    assert "CTA（行动按钮）池为空" in result["blocking_reasons"]
    assert "卖点池为空" in result["blocking_reasons"]


def test_template_health_warns_random_materials_hardcoded_constraints_and_yzt_residue():
    mode = _mode()
    mode["defaults"] = {"daily_budget": 88888, "cpa_bid": 103, "roi_coefficient": 0.41}
    mode["material_selection"] = {
        "selection_type": "random_materials",
        "lookback_days": 7,
        "min_stat_cost": 100,
    }
    catalog = _catalog()
    catalog["templates"]["wx_pay_male"]["copy_source_name"] = "勇者突进"

    result = build_create_template_health(mode, catalog)

    assert result["ok"] is False
    assert "随机素材模板不应写死 cpa_bid（项目出价）" in result["blocking_reasons"]
    assert "随机素材模板不应写死 roi_coefficient（ROI 系数）" in result["blocking_reasons"]
    assert "随机素材模板不应要求 lookback_days（回看天数）" in result["blocking_reasons"]
    assert "随机素材模板最低消耗应为 0" in result["blocking_reasons"]
    assert "模板仍残留勇者突进字段：copy_source_name" in result["blocking_reasons"]


def test_template_health_warns_when_random_count_exceeds_pool_size():
    mode = _mode()
    mode["unit_creative_selection"] = {
        "cta_min_count": 4,
        "cta_max_count": 5,
        "product_selling_point_min_count": 4,
        "product_selling_point_max_count": 5,
    }

    result = build_create_template_health(mode, _catalog())

    assert result["ok"] is True
    assert "CTA（行动按钮）随机数量超过池大小：5 > 3" in result["warnings"]
    assert "卖点随机数量超过池大小：5 > 3" in result["warnings"]
