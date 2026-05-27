from roibang_v2.ui.create_template_health import build_create_mode_health


def _catalog() -> dict:
    return {
        "product_key": "diandian-hero",
        "templates": {
            "wx_pay_male": {
                "title_pool": ["标题1", "标题2", "标题3"],
                "cta_pool": ["点击即玩", "不用下载", "全场免费"],
                "product_selling_points": ["爆率高", "福利多", "不肝不氪"],
            },
            "wx_7r_male": {
                "requires_roi_goal": True,
                "title_pool": ["标题1"],
                "cta_pool": ["点击即玩"],
                "product_selling_points": ["爆率高"],
            },
        },
    }


def _mode() -> dict:
    return {
        "mode_key": "wx_pay_male_random_materials",
        "product_key": "diandian-hero",
        "template_key": "wx_pay_male",
        "defaults": {"daily_budget": 88888, "project_count": 5, "units_per_project": 1},
        "material_requirements": {"materials_per_unit": 5},
        "material_selection": {
            "selection_type": "random_materials",
            "source_scope": "source_material_account",
            "min_stat_cost": 0,
            "sort_by": "random_stable",
            "random_shuffle": True,
        },
    }


def test_create_mode_health_passes_for_diandian_random_materials():
    result = build_create_mode_health(_mode(), _catalog())

    assert result["ok"] is True
    assert result["status"] == "passed"
    assert result["blocking_reasons"] == []
    assert result["summary"]["mode_key"] == "wx_pay_male_random_materials"
    assert result["summary"]["selection_type"] == "random_materials"
    assert result["summary"]["hardcoded_cpa_bid"] is False
    assert result["summary"]["hardcoded_roi_coefficient"] is False
    assert result["summary"]["requires_lookback_days"] is False


def test_create_mode_health_blocks_random_material_filters_and_bid_roi():
    mode = _mode()
    mode["defaults"] = {
        "daily_budget": 88888,
        "project_count": 5,
        "units_per_project": 1,
        "cpa_bid": 103,
        "roi_coefficient": 0.41,
    }
    mode["material_selection"] = {
        "selection_type": "random_materials",
        "lookback_days": 7,
        "first_seen_days": 3,
        "max_stat_cost": 1000,
        "min_convert_cnt": 1,
        "max_convert_cnt": 10,
        "candidate_pool_limit": 50,
        "min_stat_cost": 100,
        "sort_by": "stat_cost_desc",
        "random_shuffle": False,
    }

    result = build_create_mode_health(mode, _catalog())

    assert result["ok"] is False
    assert "随机素材不应设置 lookback_days（回看天数）" in result["blocking_reasons"]
    assert "随机素材不应设置 first_seen_days（有效创建日期回看）" in result["blocking_reasons"]
    assert "随机素材不应设置 max_stat_cost（最高消耗）" in result["blocking_reasons"]
    assert "随机素材不应设置 min_convert_cnt（最低转化）" in result["blocking_reasons"]
    assert "随机素材不应设置 max_convert_cnt（最高转化）" in result["blocking_reasons"]
    assert "随机素材不应设置 candidate_pool_limit（候选池上限）" in result["blocking_reasons"]
    assert "随机素材 min_stat_cost（最低消耗）必须为 0" in result["blocking_reasons"]
    assert "随机素材 sort_by（排序方式）必须为 random_stable（稳定随机）" in result["blocking_reasons"]
    assert "随机素材 random_shuffle（随机打乱）必须为 true" in result["blocking_reasons"]
    assert "点点英雄随机素材不应写死 cpa_bid（项目出价）" in result["blocking_reasons"]
    assert "点点英雄随机素材不应写死 roi_coefficient（ROI 系数）" in result["blocking_reasons"]


def test_create_mode_health_blocks_non_7r_roi_and_warns_7r_roi_policy():
    non_7r = _mode()
    non_7r["defaults"] = {"daily_budget": 88888, "project_count": 5, "units_per_project": 1, "roi_coefficient": 0.41}

    non_7r_result = build_create_mode_health(non_7r, _catalog())

    assert "非 7R 模板不应写 roi_coefficient（ROI 系数）" in non_7r_result["blocking_reasons"]

    mode_7r = _mode()
    mode_7r["mode_key"] = "wx_7r_male_random_materials"
    mode_7r["template_key"] = "wx_7r_male"

    result_7r = build_create_mode_health(mode_7r, _catalog())

    assert result_7r["ok"] is True
    assert "7R 模板 ROI 系数建议在本次生成时填写，不建议写死到模板" in result_7r["warnings"]


def test_create_mode_health_blocks_missing_identity_and_non_positive_counts():
    mode = _mode()
    mode["mode_key"] = ""
    mode["product_key"] = ""
    mode["template_key"] = "missing"
    mode["defaults"] = {"daily_budget": 0, "project_count": 0, "units_per_project": 0}
    mode["material_requirements"] = {"materials_per_unit": 0}

    result = build_create_mode_health(mode, _catalog())

    assert "mode_key（创建模式键）不能为空" in result["blocking_reasons"]
    assert "product_key（产品键）不能为空" in result["blocking_reasons"]
    assert "基础模板不存在：missing" in result["blocking_reasons"]
    assert "daily_budget（日预算）必须大于 0" in result["blocking_reasons"]
    assert "project_count（项目数）必须大于 0" in result["blocking_reasons"]
    assert "units_per_project（单元数）必须大于 0" in result["blocking_reasons"]
    assert "materials_per_unit（每单元素材数）必须大于 0" in result["blocking_reasons"]
