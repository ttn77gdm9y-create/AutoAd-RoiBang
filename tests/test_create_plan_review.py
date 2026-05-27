from copy import deepcopy

from roibang_v2.ui.create_plan_review import build_create_plan_review


def _plan() -> dict:
    return {
        "mode_key": "wx_pay_male_random_materials",
        "summary": {
            "plan_id": "plan-1",
            "planned_project_count": 1,
            "planned_unit_count": 1,
            "planned_material_count": 1,
            "source_material_count": 3,
            "violation_count": 0,
        },
        "create_request": {
            "product": "点点英雄",
            "product_key": "diandian-hero",
            "target_date": "2026-05-26",
            "source_advertiser_id": "source-dd",
            "material_selection": {"selection_type": "random_materials"},
            "template_parameters": {
                "title_pool": ["标题1", "标题2"],
                "cta_pool": ["立即下载"],
                "product_selling_points": ["爆率高"],
                "unit_creative_selection": {
                    "title_strategy": "deterministic_shuffle_per_unit",
                    "cta_min_count": 1,
                    "cta_max_count": 1,
                    "product_selling_point_min_count": 1,
                    "product_selling_point_max_count": 1,
                },
            },
        },
        "create_strategy_plan": {
            "request": {
                "product": "点点英雄",
                "product_key": "diandian-hero",
                "source_advertiser_id": "source-dd",
                "template_parameters": {
                    "title_pool": ["标题1", "标题2"],
                    "cta_pool": ["立即下载"],
                    "product_selling_points": ["爆率高"],
                    "unit_creative_selection": {
                        "title_strategy": "deterministic_shuffle_per_unit",
                        "cta_min_count": 1,
                        "cta_max_count": 1,
                        "product_selling_point_min_count": 1,
                        "product_selling_point_max_count": 1,
                    },
                },
            },
            "strategy": {
                "projects": [
                    {
                        "project_key": "acc-1-p001",
                        "advertiser_id": "acc-1",
                        "project_name": "项目1",
                        "units": [
                            {
                                "unit_key": "acc-1-p001-u01",
                                "promotion_name": "单元1",
                                "materials": [
                                    {
                                        "material_id": "m-shared",
                                        "source_video_id": "video-dd",
                                        "name": "跨产品素材",
                                        "stat_cost": 123.45,
                                        "convert_cnt": 6,
                                        "cost_lookback": 99999,
                                        "global_stat_cost": 99999,
                                        "rank": 1,
                                        "effective_create_date": "2026-05-25",
                                    }
                                ],
                            }
                        ],
                    }
                ]
            },
        },
    }


def test_review_allows_valid_plan_and_uses_product_specific_material_metrics():
    review = build_create_plan_review(_plan())

    assert review["can_execute"] is True
    assert review["blocking_reasons"] == []
    material = review["materials"][0]
    assert material["material_id"] == "m-shared"
    assert material["video_id"] == "video-dd"
    assert material["product_key"] == "diandian-hero"
    assert material["product"] == "点点英雄"
    assert material["source_advertiser_id"] == "source-dd"
    assert material["product_stat_cost"] == 123.45
    assert material["product_convert_cnt"] == 6
    assert "cost_lookback" not in material
    assert "global_stat_cost" not in material
    assert review["summary"]["selection_type"] == "random_materials"
    assert review["summary"]["requires_lookback_days"] is False


def test_review_blocks_missing_video_id_only_for_material_rows_not_copywriting():
    plan = _plan()
    plan["create_strategy_plan"]["strategy"]["projects"][0]["units"][0]["materials"][0]["source_video_id"] = ""

    review = build_create_plan_review(plan)

    assert review["can_execute"] is False
    assert review["summary"]["missing_video_id_material_count"] == 1
    assert any("缺 video_id（视频 ID）素材数：1" in reason for reason in review["blocking_reasons"])
    assert all("标题" not in reason for reason in review["blocking_reasons"])


def test_review_blocks_empty_materials_and_zero_plan_counts():
    plan = _plan()
    plan["summary"]["planned_material_count"] = 0
    plan["summary"]["source_material_count"] = 0
    plan["create_strategy_plan"]["strategy"]["projects"][0]["units"][0]["materials"] = []

    review = build_create_plan_review(plan)

    assert review["can_execute"] is False
    assert "计划素材数为 0" in review["blocking_reasons"]
    assert "候选素材数为 0" in review["blocking_reasons"]
    assert "没有选中任何素材" in review["blocking_reasons"]


def test_review_blocks_units_missing_copy_cta_or_selling_points():
    plan = _plan()
    params = plan["create_strategy_plan"]["request"]["template_parameters"]
    params["title_pool"] = []
    params["cta_pool"] = []
    params["product_selling_points"] = []
    plan["create_request"]["template_parameters"] = deepcopy(params)

    review = build_create_plan_review(plan)

    assert review["can_execute"] is False
    assert "单元缺文案数：1" in review["blocking_reasons"]
    assert "单元缺 CTA（行动按钮）数：1" in review["blocking_reasons"]
    assert "单元缺卖点数：1" in review["blocking_reasons"]


def test_review_counts_usage_for_materials_and_creatives():
    plan = _plan()
    project = plan["create_strategy_plan"]["strategy"]["projects"][0]
    second_unit = deepcopy(project["units"][0])
    second_unit["unit_key"] = "acc-1-p001-u02"
    second_unit["promotion_name"] = "单元2"
    project["units"].append(second_unit)
    plan["summary"]["planned_unit_count"] = 2
    plan["summary"]["planned_material_count"] = 2

    review = build_create_plan_review(plan)

    assert review["materials"][0]["usage_count"] == 2
    assert review["materials"][0]["covered_account_count"] == 1
    assert review["materials"][0]["covered_unit_count"] == 2
    assert sum(row["usage_count"] for row in review["creative_usage"]["titles"]) == 2
    assert sum(row["usage_count"] for row in review["creative_usage"]["ctas"]) == 2
    assert sum(row["usage_count"] for row in review["creative_usage"]["selling_points"]) == 2
