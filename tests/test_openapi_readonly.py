import json

import pytest

from roibang_v2.fetch.openapi_readonly import (
    build_openapi_readonly_plan,
    build_readonly_request,
    validate_readonly_endpoint,
)


def test_build_readonly_request_uses_get_and_redacted_token():
    request = build_readonly_request(
        "report_custom",
        {
            "advertiser_id": "1858371222574218",
            "data_topic": "BASIC_DATA",
            "dimensions": ["stat_time", "promotion_id"],
            "metrics": ["stat_cost", "convert_cnt"],
            "filters": [{"field": "micro_promotion_type", "values": ["WECHAT_GAME"]}],
            "start_time": "2026-02-10",
            "end_time": "2026-02-10",
            "page": 1,
            "page_size": 100,
        },
    )

    assert request["method"] == "GET"
    assert request["endpoint_key"] == "report_custom"
    assert request["path"] == "/open_api/v3.0/report/custom/get/"
    assert request["headers"] == {"Access-Token": "<redacted>"}
    assert request["query_params"]["dimensions"] == '["stat_time","promotion_id"]'
    assert request["query_params"]["filters"] == '[{"field":"micro_promotion_type","values":["WECHAT_GAME"]}]'


def test_account_daily_plan_uses_supported_day_dimension():
    plan = build_openapi_readonly_plan(
        accounts=[
            {
                "advertiser_id": "1858371222574218",
                "account_name": "account",
                "product": "勇者突进",
                "platform": "WECHAT_GAME",
            }
        ],
        dates=["2026-05-06"],
        endpoints=["report_custom"],
        report_presets=["account_daily"],
        platforms=["WECHAT_GAME"],
    )

    request = plan["requests"][0]
    assert json.loads(request["query_params"]["dimensions"]) == ["stat_time_day"]
    assert json.loads(request["query_params"]["filters"]) == []
    metrics = json.loads(request["query_params"]["metrics"])
    assert "attribution_billing_game_in_app_roi_1day" in metrics


def test_promotion_daily_plan_requests_billing_roi_metrics():
    plan = build_openapi_readonly_plan(
        accounts=[
            {
                "advertiser_id": "1858371222574218",
                "account_name": "account",
                "product": "勇者突进",
                "platform": "WECHAT_GAME",
            }
        ],
        dates=["2026-05-06"],
        endpoints=["report_custom"],
        report_presets=["promotion_daily"],
        platforms=["WECHAT_GAME"],
    )

    metrics = json.loads(plan["requests"][0]["query_params"]["metrics"])
    assert "attribution_billing_game_in_app_roi_1day" in metrics
    assert "attribution_billing_game_in_app_ltv_1day" in metrics
    assert "attribution_convert_cnt" in metrics
    assert "attribution_convert_cost" in metrics


def test_material_daily_plan_uses_supported_material_dimensions():
    plan = build_openapi_readonly_plan(
        accounts=[
            {
                "advertiser_id": "1858371222574218",
                "account_name": "account",
                "product": "勇者突进",
                "platform": "WECHAT_GAME",
            }
        ],
        dates=["2026-05-06"],
        endpoints=["report_custom"],
        report_presets=["material_daily"],
        platforms=["WECHAT_GAME"],
    )

    request = plan["requests"][0]
    assert json.loads(request["query_params"]["dimensions"]) == [
        "stat_time_day",
        "cdp_project_id",
        "cdp_project_name",
        "cdp_promotion_id",
        "cdp_promotion_name",
        "material_id",
    ]
    metrics = json.loads(request["query_params"]["metrics"])
    assert "attribution_billing_game_in_app_roi_1day" in metrics
    assert "attribution_billing_game_in_app_ltv_1day" in metrics
    assert "attribution_convert_cnt" in metrics
    assert "attribution_convert_cost" in metrics
    assert request["query_params"]["page_size"] == "20"


def test_promotion_list_plan_caps_page_size_to_openapi_limit():
    plan = build_openapi_readonly_plan(
        accounts=[
            {
                "advertiser_id": "1858371222574218",
                "account_name": "account",
                "product": "勇者突进",
                "platform": "WECHAT_GAME",
            }
        ],
        dates=["2026-05-06"],
        endpoints=["promotion_list"],
        report_presets=["promotion_daily"],
        platforms=["WECHAT_GAME"],
        page_size=100,
    )

    request = plan["requests"][0]
    assert request["endpoint_key"] == "promotion_list"
    assert request["query_params"]["page_size"] == "20"


@pytest.mark.parametrize(
    "endpoint_key",
    [
        "project_create",
        "promotion_update",
        "ad_delete",
        "budget_update",
        "bid_adjust",
        "schedule_update",
        "material_upload",
        "material_bind",
        "/open_api/v3.0/project/create/",
    ],
)
def test_validate_readonly_endpoint_rejects_mutation_shapes(endpoint_key):
    with pytest.raises(ValueError):
        validate_readonly_endpoint(endpoint_key)


def test_build_openapi_readonly_plan_has_no_external_calls():
    plan = build_openapi_readonly_plan(
        accounts=[
            {
                "advertiser_id": "1858371222574218",
                "account_name": "黑旗-勇者突进-微小-傲星-306",
                "product": "勇者突进",
                "platform": "WECHAT_GAME",
            }
        ],
        dates=["2026-02-10"],
        endpoints=["report_custom_config", "report_custom", "project_list", "promotion_list"],
        report_presets=["promotion_daily"],
        platforms=["WECHAT_GAME"],
        page_size=100,
    )

    assert plan["external_api_calls"] == 0
    assert plan["execution_enabled"] is False
    assert plan["summary"] == {
        "account_count": 1,
        "date_count": 1,
        "endpoint_count": 4,
        "report_preset_count": 1,
        "planned_request_count": 4,
    }
    assert [item["endpoint_key"] for item in plan["requests"]] == [
        "report_custom_config",
        "report_custom",
        "project_list",
        "promotion_list",
    ]
    assert plan["requests"][1]["query_params"]["advertiser_id"] == "1858371222574218"
    assert plan["requests"][1]["query_params"]["start_time"] == "2026-02-10"
    assert plan["requests"][1]["query_params"]["page_size"] == "100"
