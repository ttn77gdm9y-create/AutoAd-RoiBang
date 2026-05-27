from copy import deepcopy

from roibang_v2.ui.create_plan_preview import build_create_plan_preview
from roibang_v2.ui.create_plan_preview import build_create_plan_preview_from_review
from roibang_v2.ui.create_plan_preview import filter_preview_materials
from roibang_v2.ui.create_plan_preview import filter_preview_units
from tests.test_create_plan_review import _plan


def test_preview_uses_product_metrics_and_creative_counts():
    preview = build_create_plan_preview(_plan())

    assert preview["summary"]["product_key"] == "diandian-hero"
    assert preview["summary"]["unique_material_count"] == 1
    assert preview["summary"]["title_count"] == 1
    assert preview["summary"]["cta_count"] == 1
    assert preview["summary"]["selling_point_count"] == 1
    material = preview["materials"][0]
    assert material["material_id"] == "m-shared"
    assert material["video_id"] == "video-dd"
    assert material["product_stat_cost"] == 123.45
    assert material["product_convert_cnt"] == 6
    assert "global_stat_cost" not in material
    assert material["covered_accounts"] == ["acc-1"]
    assert material["missing_video_id"] is False


def test_preview_flags_missing_video_id_only_on_materials():
    plan = _plan()
    plan["create_strategy_plan"]["strategy"]["projects"][0]["units"][0]["materials"][0]["source_video_id"] = ""

    preview = build_create_plan_preview(plan)

    assert preview["summary"]["missing_video_id_material_count"] == 1
    assert preview["materials"][0]["missing_video_id"] is True
    assert preview["copywriting"][0]["title"] == "标题1"


def test_preview_filters_materials_by_missing_video_usage_account_and_query():
    plan = _plan()
    project = plan["create_strategy_plan"]["strategy"]["projects"][0]
    second_unit = deepcopy(project["units"][0])
    second_unit["unit_key"] = "acc-1-p001-u02"
    second_unit["materials"][0]["material_id"] = "m-missing"
    second_unit["materials"][0]["source_video_id"] = ""
    second_unit["materials"][0]["name"] = "缺视频素材"
    project["units"].append(second_unit)
    preview = build_create_plan_preview(plan)

    rows = filter_preview_materials(
        preview["materials"],
        missing_video_only=True,
        min_usage_count=1,
        account_id="acc-1",
        query="缺视频",
    )

    assert len(rows) == 1
    assert rows[0]["material_id"] == "m-missing"


def test_preview_filters_units_by_account_and_project_query():
    plan = _plan()
    preview = build_create_plan_preview(plan)

    rows = filter_preview_units(preview["units"], account_id="acc-1", project_query="项目1")

    assert len(rows) == 1
    assert rows[0]["promotion_name"] == "单元1"
    assert rows[0]["title_count"] == 1
    assert rows[0]["cta_count"] == 1
    assert rows[0]["selling_point_count"] == 1


def test_preview_from_operation_review_shape():
    base = build_create_plan_preview(_plan())
    preview = build_create_plan_preview_from_review(
        {
            "review": base["review"],
            "materials": base["materials"],
            "creative_usage": {
                "titles": base["copywriting"],
                "ctas": base["ctas"],
                "selling_points": base["selling_points"],
            },
            "unit_assignments": base["units"],
        }
    )

    assert preview["summary"]["material_assignment_count"] == 1
    assert preview["materials"][0]["material_id"] == "m-shared"


def test_preview_from_operation_review_merges_top_level_details_when_review_is_summary_only():
    base = build_create_plan_preview(_plan())
    preview = build_create_plan_preview_from_review(
        {
            "review": {
                "can_execute": True,
                "summary": {"material_assignment_count": 1, "unique_material_count": 1},
            },
            "materials": base["materials"],
            "creative_usage": {
                "titles": base["copywriting"],
                "ctas": base["ctas"],
                "selling_points": base["selling_points"],
            },
            "unit_assignments": base["units"],
        }
    )

    assert preview["materials"][0]["material_id"] == "m-shared"
    assert preview["copywriting"][0]["title"] == "标题1"
