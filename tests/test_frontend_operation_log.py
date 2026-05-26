import json
from pathlib import Path

from roibang_v2.workflows.frontend_operation_log import create_operation_details_from_plan
from roibang_v2.workflows.frontend_operation_log import record_frontend_operation


def _plan() -> dict:
    return {
        "mode_key": "wx_pay_male_random_materials",
        "summary": {"plan_id": "plan-1"},
        "create_request": {
            "product": "点点英雄",
            "product_key": "diandian-hero",
            "target_date": "2026-05-26",
            "source_advertiser_id": "source-1",
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
                                        "material_id": "m-1",
                                        "source_video_id": "v28033gi0000d8a07rnog65j98kl131g",
                                        "name": "素材1",
                                        "stat_cost": 100,
                                        "rank": 1,
                                    }
                                ],
                            }
                        ],
                    }
                ]
            }
        },
    }


def test_create_operation_details_from_plan_records_accounts_materials_and_copywriting():
    details = create_operation_details_from_plan(_plan())

    assert details["product"] == "点点英雄"
    assert details["accounts"][0]["advertiser_id"] == "acc-1"
    assert details["material_assignment_count"] == 1
    assert details["unique_materials"][0]["material_id"] == "m-1"
    assert details["copywriting"]["title_pool"] == ["标题1", "标题2"]
    assert details["copywriting"]["cta_pool"] == ["立即下载"]
    assert details["copywriting"]["selling_points"] == ["爆率高"]
    assert details["unit_copywriting"][0]["title_material_list"]
    assert details["unit_copywriting"][0]["call_to_action_buttons"] == ["立即下载"]
    assert details["unit_copywriting"][0]["product_info"]["selling_points"] == ["爆率高"]


def test_record_frontend_operation_writes_artifact_and_jsonl(tmp_path: Path):
    details = create_operation_details_from_plan(_plan())
    result = record_frontend_operation(
        runs_dir=tmp_path,
        operation_type="create_plan_generate",
        status="completed",
        actor="郭靖",
        request={"plan_path": "data/runs/create_mode/example.json"},
        result={"ok": True},
        details=details,
    )

    artifact_path = Path(result["artifact_path"])
    event_log_path = Path(result["event_log_path"])
    assert artifact_path.exists()
    assert event_log_path.exists()
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert artifact["summary"]["product"] == "点点英雄"
    assert artifact["summary"]["material_assignment_count"] == 1
    event = json.loads(event_log_path.read_text(encoding="utf-8").strip())
    assert event["operation_type"] == "create_plan_generate"
    assert event["artifact_path"] == str(artifact_path)
