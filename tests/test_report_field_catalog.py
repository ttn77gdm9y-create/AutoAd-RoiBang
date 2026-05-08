import json
from pathlib import Path

from roibang_v2.db.bootstrap import bootstrap_database
from roibang_v2.workflows.report_field_catalog import (
    build_report_field_catalog_preflight,
    run_report_field_catalog_request,
)


def _write_accounts_csv(path: Path):
    path.write_text(
        "\n".join(
            [
                "account_name,advertiser_id,消耗,product,platform",
                "黑旗-勇者突进-微小-傲星-306,1858371222574218,\"570,011.13\",勇者突进,WECHAT_GAME",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def _request(csv_path: Path) -> dict:
    return {
        "report_field_catalog": {
            "account_pool_csv": str(csv_path),
            "product": "勇者突进",
            "platforms": ["WECHAT_GAME"],
            "data_topics": ["BASIC_DATA", "MATERIAL_DATA"],
            "validate_presets": True,
            "openapi_http": {"enabled": False},
        }
    }


def _config_response():
    return {
        "code": 0,
        "message": "OK",
        "data": {
            "list": [
                {
                    "data_topic": "BASIC_DATA",
                    "dimensions": [
                        {"field": "stat_time_day", "name": "时间-天"},
                        {"field": "cdp_project_id", "name": "项目ID"},
                        {"field": "cdp_project_name", "name": "项目名称"},
                        {"field": "cdp_promotion_id", "name": "单元ID"},
                        {"field": "cdp_promotion_name", "name": "单元名称"},
                    ],
                    "metrics": [
                        {"field": "stat_cost", "name": "消耗"},
                        {"field": "show_cnt", "name": "展示"},
                        {"field": "click_cnt", "name": "点击"},
                        {"field": "convert_cnt", "name": "转化"},
                    ],
                },
                {
                    "data_topic": "MATERIAL_DATA",
                    "dimensions": [
                        {"field": "stat_time_day", "name": "时间-天"},
                        {"field": "cdp_project_id", "name": "项目ID"},
                        {"field": "cdp_project_name", "name": "项目名称"},
                        {"field": "cdp_promotion_id", "name": "单元ID"},
                        {"field": "cdp_promotion_name", "name": "单元名称"},
                        {"field": "material_id", "name": "素材ID"},
                    ],
                    "metrics": [
                        {"field": "stat_cost", "name": "消耗"},
                        {"field": "show_cnt", "name": "展示"},
                        {"field": "click_cnt", "name": "点击"},
                        {"field": "convert_cnt", "name": "转化"},
                    ],
                },
            ]
        },
    }


def test_report_field_catalog_preflight_plans_one_field_list_request(tmp_path):
    db_path = tmp_path / "roibang.sqlite3"
    csv_path = tmp_path / "accounts.csv"
    bootstrap_database(db_path)
    _write_accounts_csv(csv_path)

    result = build_report_field_catalog_preflight(
        _request(csv_path),
        db_path=db_path,
        runs_dir=tmp_path / "runs",
    )

    assert result["workflow"] == "report_field_catalog_preflight"
    assert result["external_api_calls"] == 0
    assert result["summary"] == {
        "account_count": 1,
        "sample_advertiser_id": "1858371222574218",
        "data_topics": ["BASIC_DATA", "MATERIAL_DATA"],
        "planned_request_count": 1,
    }


def test_report_field_catalog_fetches_supported_fields_and_validates_presets(tmp_path):
    db_path = tmp_path / "roibang.sqlite3"
    csv_path = tmp_path / "accounts.csv"
    bootstrap_database(db_path)
    _write_accounts_csv(csv_path)
    calls = []

    def transport(request):
        calls.append(request)
        return _config_response()

    result = run_report_field_catalog_request(
        _request(csv_path),
        db_path=db_path,
        runs_dir=tmp_path / "runs",
        transport=transport,
    )

    artifact = json.loads(Path(result["artifact_path"]).read_text(encoding="utf-8"))
    assert result["workflow"] == "report_field_catalog"
    assert result["external_api_calls"] == 1
    assert calls[0]["endpoint_key"] == "report_custom_config"
    assert calls[0]["query_params"]["data_topics"] == '["BASIC_DATA","MATERIAL_DATA"]'
    assert result["summary"]["topic_count"] == 2
    assert result["summary"]["preset_validation_ok"] is True
    assert artifact["catalog"]["topics"]["MATERIAL_DATA"]["dimension_fields"] == [
        "stat_time_day",
        "cdp_project_id",
        "cdp_project_name",
        "cdp_promotion_id",
        "cdp_promotion_name",
        "material_id",
    ]


def test_report_field_catalog_reports_outdated_preset_fields(tmp_path):
    db_path = tmp_path / "roibang.sqlite3"
    csv_path = tmp_path / "accounts.csv"
    bootstrap_database(db_path)
    _write_accounts_csv(csv_path)
    response = _config_response()
    material = response["data"]["list"][1]
    material["dimensions"] = [item for item in material["dimensions"] if item["field"] != "material_id"]

    result = run_report_field_catalog_request(
        _request(csv_path),
        db_path=db_path,
        runs_dir=tmp_path / "runs",
        transport=lambda _request: response,
    )

    assert result["ok"] is False
    assert result["summary"]["preset_validation_ok"] is False
    material_daily = result["preset_validation"]["material_daily"]
    assert material_daily["missing_dimensions"] == ["material_id"]
