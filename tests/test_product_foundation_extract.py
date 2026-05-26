import json
from pathlib import Path

from roibang_v2.workflows.product_foundation_extract import extract_product_foundation
from roibang_v2.workflows.product_foundation_extract import run_product_foundation_extract_request


def test_extract_product_foundation_reads_project_and_promotion_fields():
    project_rows = [
        {
            "project_id": "p1",
            "micro_app_instance_id": "micro-1",
            "micro_promotion_type": "WECHAT_GAME",
            "open_url": "https://landing.example.com",
        }
    ]
    promotion_rows = [
        {
            "promotion_id": "u1",
            "promotion_materials": {
                "mini_program_info": {"app_id": "micro-from-unit", "url": "https://touch.example.com"},
                "external_url_material_list": ["https://landing-from-unit.example.com"],
                "product_info": {"image_ids": ["product-image-1"]},
                "video_material_list": [{"video_id": "video-1", "video_cover_id": "cover-1"}],
                "anchor_material_list": [{"anchor_id": "anchor-1", "anchor_type": "MICRO_GAME"}],
            },
            "native_setting": {"anchor_related_type": "SELECT"},
        }
    ]

    result = extract_product_foundation(project_rows=project_rows, promotion_rows=promotion_rows)

    assert result["foundation"] == {
        "effective_touch_url": "https://touch.example.com",
        "anchor_id": "anchor-1",
        "anchor_type": "MICRO_GAME",
        "anchor_related_type": "SELECT",
        "landing_url": "https://landing.example.com",
        "product_image_id": "product-image-1",
        "fixed_video_cover_id": "cover-1",
        "micro_app_instance_id": "micro-1",
        "micro_promotion_type": "WECHAT_GAME",
    }
    assert result["missing_fields"] == []
    assert result["field_evidence"]["fixed_video_cover_id"]["source_path"]


def test_run_product_foundation_extract_request_uses_readonly_plan_and_writes_artifact(tmp_path: Path):
    calls = []

    def fake_transport(request):
        calls.append(request)
        if request["endpoint_key"] == "project_list":
            return {
                "code": 0,
                "data": {
                    "rows": [
                        {
                            "project_id": "764",
                            "micro_app_instance_id": "micro-1",
                            "micro_promotion_type": "WECHAT_GAME",
                        }
                    ],
                    "page_info": {"page": 1, "page_size": 20, "total_page": 1, "total_count": 1},
                },
            }
        return {
            "code": 0,
            "data": {
                "rows": [
                    {
                        "promotion_id": "unit-1",
                        "promotion_materials": {
                            "mini_program_info": {"url": "https://touch.example.com"},
                            "external_url_material_list": ["https://landing.example.com"],
                            "product_info": {"image_ids": ["product-image-1"]},
                            "video_material_list": [{"video_cover_id": "cover-1"}],
                            "anchor_material_list": [{"anchor_id": "anchor-1", "anchor_type": "MICRO_GAME"}],
                        },
                        "native_setting": {"anchor_related_type": "SELECT"},
                    }
                ],
                "page_info": {"page": 1, "page_size": 20, "total_page": 1, "total_count": 1},
            },
        }

    result = run_product_foundation_extract_request(
        {
            "product_foundation_extract": {
                "product": "点点英雄",
                "product_key": "diandian-hero",
                "advertiser_id": "1866125087858183",
                "project_id": "7643724755983777818",
            }
        },
        config={"openapi_http": {"enabled": True, "token_file": str(tmp_path / "token.txt")}},
        runs_dir=tmp_path / "runs",
        transport=fake_transport,
    )

    assert result["ok"] is True
    assert result["execution_enabled"] is False
    assert result["external_api_calls"] == 2
    assert result["summary"]["project_count"] == 1
    assert result["summary"]["promotion_count"] == 1
    assert result["draft"]["foundation"]["product_image_id"] == "product-image-1"
    assert [call["endpoint_key"] for call in calls] == ["project_list", "promotion_list"]
    assert json.loads(Path(result["artifact_path"]).read_text(encoding="utf-8"))["workflow"] == "product_foundation_extract"


def test_run_product_foundation_extract_blocks_missing_project_id(tmp_path: Path):
    result = run_product_foundation_extract_request(
        {"product_foundation_extract": {"advertiser_id": "186"}},
        config={},
        runs_dir=tmp_path / "runs",
    )

    assert result["ok"] is False
    assert result["status"] == "blocked"
    assert "missing project_id" in result["blocking_reasons"]
