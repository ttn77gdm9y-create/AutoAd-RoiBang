import json
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.main import create_app


def _client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(project_root=tmp_path))


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _write_account_store(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "configs" / "accounts" / "product-accounts.local.json",
        {
            "accounts": [
                {
                    "product_key": "diandian-hero",
                    "product_name": "点点英雄",
                    "advertiser_id": "1001",
                    "advertiser_name": "黑旗游戏",
                    "channel": "微信",
                    "owner": "运营A",
                    "account_remark": "点点英雄-黑旗",
                    "status": "active",
                    "notes": "",
                },
                {
                    "product_key": "seat-game",
                    "product_name": "你行你先坐",
                    "advertiser_id": "1002",
                    "advertiser_name": "赚亿点点",
                    "channel": "微信",
                    "owner": "运营B",
                    "account_remark": "坐哪里-赚亿",
                    "status": "paused",
                    "notes": "",
                },
            ]
        },
    )


def _write_patrol_artifact(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "data" / "runs" / "delivery_patrol" / "20260527T100000Z.json",
        {
            "workflow": "delivery_patrol",
            "summary": {
                "target_date": "2026-05-27",
                "account_count": 2,
                "project_count": 3,
                "promotion_count": 8,
                "overall_metrics": {
                    "today": {
                        "stat_cost": 1234.56,
                        "billing_convert_cnt": 4,
                        "billing_conversion_cost": 308.64,
                        "billing_1day_pay_roi": 0.21,
                    }
                },
            },
            "accounts": [
                {
                    "advertiser_id": "1001",
                    "advertiser_name": "黑旗游戏",
                    "metrics": {
                        "today": {
                            "stat_cost": 1000,
                            "billing_convert_cnt": 3,
                            "billing_conversion_cost": 333.33,
                            "billing_1day_pay_roi": 0.25,
                        }
                    },
                },
                {
                    "advertiser_id": "1002",
                    "advertiser_name": "赚亿点点",
                    "metrics": {
                        "today": {
                            "stat_cost": 234.56,
                            "billing_convert_cnt": 1,
                            "billing_conversion_cost": 234.56,
                            "billing_1day_pay_roi": 0.04,
                        }
                    },
                },
            ],
            "projects": [
                {
                    "advertiser_id": "1001",
                    "project_id": "p1",
                    "project_name": "点点英雄-7R-1",
                    "business_status": "healthy",
                    "metrics": {"today": {"stat_cost": 600, "billing_convert_cnt": 2}},
                },
                {
                    "advertiser_id": "1001",
                    "project_id": "p2",
                    "project_name": "点点英雄-7R-2",
                    "business_status": "attention",
                    "metrics": {"today": {"stat_cost": 400, "billing_convert_cnt": 0}},
                },
                {
                    "advertiser_id": "1002",
                    "project_id": "p3",
                    "project_name": "坐哪里-通投",
                    "business_status": "paused",
                    "metrics": {"today": {"stat_cost": 234.56, "billing_convert_cnt": 1}},
                },
            ],
            "promotions": [
                {
                    "advertiser_id": "1001",
                    "project_id": "p1",
                    "promotion_id": "u1",
                    "promotion_name": "点点英雄-素材A",
                    "business_status": "healthy",
                    "metrics": {
                        "today": {
                            "stat_cost": 450,
                            "billing_convert_cnt": 2,
                            "billing_1day_pay_roi": 0.3,
                        }
                    },
                },
                {
                    "advertiser_id": "1001",
                    "project_id": "p2",
                    "promotion_id": "u2",
                    "promotion_name": "点点英雄-素材B",
                    "business_status": "attention",
                    "metrics": {
                        "today": {
                            "stat_cost": 120,
                            "billing_convert_cnt": 0,
                            "billing_1day_pay_roi": 0.0,
                        }
                    },
                },
            ],
        },
    )


def _write_suggestions_artifact(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "data" / "runs" / "delivery_patrol_suggestions" / "20260527T100001Z.json",
        {
            "workflow": "delivery_patrol_suggestions",
            "summary": {"suggestion_count": 2},
            "suggestions": [
                {
                    "advertiser_id": "1001",
                    "project_id": "p2",
                    "target_level": "project",
                    "action": "watch",
                    "reason": "今日消耗已有但转化不足",
                },
                {
                    "advertiser_id": "1002",
                    "project_id": "p3",
                    "target_level": "project",
                    "action": "lower_budget",
                    "reason": "ROI 偏低",
                },
            ],
        },
    )


def _write_dashboard_fixture(tmp_path: Path) -> None:
    _write_account_store(tmp_path)
    _write_patrol_artifact(tmp_path)
    _write_suggestions_artifact(tmp_path)


def _write_previous_day_patrol_artifact(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "data" / "runs" / "delivery_patrol" / "20260526T100000Z.json",
        {
            "workflow": "delivery_patrol",
            "summary": {
                "target_date": "2026-05-26",
                "account_count": 1,
                "project_count": 1,
                "promotion_count": 0,
                "overall_metrics": {
                    "today": {
                        "stat_cost": 88.0,
                        "billing_convert_cnt": 2,
                        "billing_conversion_cost": 44.0,
                        "billing_1day_pay_roi": 0.6,
                    }
                },
            },
            "accounts": [
                {
                    "advertiser_id": "1001",
                    "advertiser_name": "黑旗游戏",
                    "metrics": {
                        "today": {
                            "stat_cost": 88.0,
                            "billing_convert_cnt": 2,
                            "billing_conversion_cost": 44.0,
                            "billing_1day_pay_roi": 0.6,
                        }
                    },
                }
            ],
            "projects": [
                {
                    "advertiser_id": "1001",
                    "project_id": "old-p1",
                    "project_name": "点点英雄-昨日",
                    "business_status": "healthy",
                    "metrics": {"today": {"stat_cost": 88.0, "billing_convert_cnt": 2}},
                }
            ],
            "promotions": [],
        },
    )


def test_dashboard_overview_returns_chinese_metric_summary(tmp_path):
    _write_dashboard_fixture(tmp_path)
    client = _client(tmp_path)

    response = client.get("/api/dashboard/overview")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["title"] == "首页数据看板"
    assert {"label": "今日消耗", "value": 1234.56} in payload["summary"]["items"]
    assert {"label": "活跃账户", "value": 1} in payload["summary"]["items"]
    assert {"label": "异常项目", "value": 2} in payload["summary"]["items"]
    assert {"label": "建议事项", "value": 2} in payload["summary"]["items"]
    assert payload["table"]["columns"] == [
        "产品",
        "账户数",
        "消耗",
        "计费转化",
        "转化成本",
        "付费 ROI",
        "异常项目",
        "建议事项",
    ]
    assert payload["table"]["rows"][0]["产品"] == "点点英雄"


def test_dashboard_overview_uses_selected_date_range_artifact(tmp_path):
    _write_dashboard_fixture(tmp_path)
    _write_previous_day_patrol_artifact(tmp_path)
    client = _client(tmp_path)

    response = client.get(
        "/api/dashboard/overview",
        params={"start_date": "2026-05-26", "end_date": "2026-05-26"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert {"label": "数据日期", "value": "2026-05-26"} in payload["summary"]["items"]
    assert {"label": "今日消耗", "value": 88.0} in payload["summary"]["items"]
    assert payload["table"]["rows"] == [
        {
            "产品": "点点英雄",
            "账户数": 1,
            "消耗": 88.0,
            "计费转化": 2.0,
            "转化成本": 44.0,
            "付费 ROI": 0.6,
            "异常项目": 0,
            "建议事项": 0,
        }
    ]


def test_dashboard_filters_returns_chinese_filter_options(tmp_path):
    _write_dashboard_fixture(tmp_path)
    client = _client(tmp_path)

    response = client.get("/api/dashboard/filters")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["title"] == "看板筛选项"
    assert {"label": "产品数", "value": 2} in payload["summary"]["items"]
    assert payload["table"]["columns"] == ["类型", "显示名称", "值"]
    assert {"类型": "产品", "显示名称": "点点英雄", "值": "diandian-hero"} in payload["table"]["rows"]
    assert {"类型": "负责人", "显示名称": "运营A", "值": "运营A"} in payload["table"]["rows"]


def test_dashboard_overview_filters_by_product_key(tmp_path):
    _write_dashboard_fixture(tmp_path)
    client = _client(tmp_path)

    response = client.get("/api/dashboard/overview", params={"product_key": "diandian-hero"})

    assert response.status_code == 200
    payload = response.json()
    assert {"label": "今日消耗", "value": 1000.0} in payload["summary"]["items"]
    assert {"label": "活跃账户", "value": 1} in payload["summary"]["items"]
    assert {"label": "活跃项目", "value": 2} in payload["summary"]["items"]
    assert payload["table"]["rows"] == [
        {
            "产品": "点点英雄",
            "账户数": 1,
            "消耗": 1000.0,
            "计费转化": 3.0,
            "转化成本": 333.33,
            "付费 ROI": 0.25,
            "异常项目": 1,
            "建议事项": 1,
        }
    ]


def test_dashboard_product_detail_returns_chinese_drilldown(tmp_path):
    _write_dashboard_fixture(tmp_path)
    client = _client(tmp_path)

    response = client.get("/api/dashboard/products/diandian-hero")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["title"] == "产品详情"
    assert {"label": "产品", "value": "点点英雄"} in payload["summary"]["items"]
    assert {"label": "产品 Key", "value": "diandian-hero"} in payload["summary"]["items"]
    assert {"label": "账户数", "value": 1} in payload["summary"]["items"]
    assert {"label": "活跃账户", "value": 1} in payload["summary"]["items"]
    assert {"label": "项目数", "value": 2} in payload["summary"]["items"]
    assert {"label": "异常项目", "value": 1} in payload["summary"]["items"]
    assert {"label": "单元素材数", "value": 2} in payload["summary"]["items"]
    assert {"label": "建议事项", "value": 1} in payload["summary"]["items"]
    assert payload["table"]["columns"] == [
        "类型",
        "产品",
        "账户 ID",
        "关联 ID",
        "名称",
        "状态/动作",
        "消耗",
        "计费转化",
        "说明",
    ]
    assert {
        "类型": "账户",
        "产品": "点点英雄",
        "账户 ID": "1001",
        "关联 ID": "1001",
        "名称": "黑旗游戏",
        "状态/动作": "active",
        "消耗": 1000.0,
        "计费转化": 3.0,
        "说明": "负责人：运营A；渠道：微信",
    } in payload["table"]["rows"]
    assert {
        "类型": "项目",
        "产品": "点点英雄",
        "账户 ID": "1001",
        "关联 ID": "p2",
        "名称": "点点英雄-7R-2",
        "状态/动作": "attention",
        "消耗": 400.0,
        "计费转化": 0.0,
        "说明": "异常项目",
    } in payload["table"]["rows"]
    assert {
        "类型": "建议",
        "产品": "点点英雄",
        "账户 ID": "1001",
        "关联 ID": "p2",
        "名称": "project",
        "状态/动作": "watch",
        "消耗": None,
        "计费转化": None,
        "说明": "今日消耗已有但转化不足",
    } in payload["table"]["rows"]


def test_dashboard_projects_returns_project_table(tmp_path):
    _write_dashboard_fixture(tmp_path)
    client = _client(tmp_path)

    response = client.get("/api/dashboard/projects")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["title"] == "项目看板"
    assert {"label": "项目数", "value": 3} in payload["summary"]["items"]
    assert payload["table"]["columns"] == ["产品", "账户 ID", "项目 ID", "项目名", "状态", "消耗", "计费转化", "异常原因"]
    assert payload["table"]["rows"][1]["项目 ID"] == "p2"
    assert payload["table"]["rows"][1]["状态"] == "attention"
    assert payload["table"]["rows"][1]["异常原因"] == "今日消耗已有但转化不足"


def test_dashboard_project_detail_returns_chinese_drilldown(tmp_path):
    _write_dashboard_fixture(tmp_path)
    client = _client(tmp_path)

    response = client.get("/api/dashboard/projects/p2")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["title"] == "项目详情"
    assert {"label": "产品", "value": "点点英雄"} in payload["summary"]["items"]
    assert {"label": "账户 ID", "value": "1001"} in payload["summary"]["items"]
    assert {"label": "项目 ID", "value": "p2"} in payload["summary"]["items"]
    assert {"label": "状态", "value": "attention"} in payload["summary"]["items"]
    assert {"label": "消耗", "value": 400.0} in payload["summary"]["items"]
    assert {"label": "计费转化", "value": 0.0} in payload["summary"]["items"]
    assert {"label": "单元素材数", "value": 1} in payload["summary"]["items"]
    assert {"label": "建议事项", "value": 1} in payload["summary"]["items"]
    assert payload["table"]["columns"] == [
        "类型",
        "产品",
        "账户 ID",
        "关联 ID",
        "名称",
        "状态/动作",
        "消耗",
        "计费转化",
        "说明",
    ]
    assert {
        "类型": "项目",
        "产品": "点点英雄",
        "账户 ID": "1001",
        "关联 ID": "p2",
        "名称": "点点英雄-7R-2",
        "状态/动作": "attention",
        "消耗": 400.0,
        "计费转化": 0.0,
        "说明": "异常项目",
    } in payload["table"]["rows"]
    assert {
        "类型": "单元素材",
        "产品": "点点英雄",
        "账户 ID": "1001",
        "关联 ID": "u2",
        "名称": "点点英雄-素材B",
        "状态/动作": "attention",
        "消耗": 120.0,
        "计费转化": 0.0,
        "说明": "项目 ID：p2",
    } in payload["table"]["rows"]


def test_dashboard_accounts_returns_account_metric_table(tmp_path):
    _write_dashboard_fixture(tmp_path)
    client = _client(tmp_path)

    response = client.get("/api/dashboard/accounts")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["title"] == "账户看板"
    assert {"label": "账户数", "value": 2} in payload["summary"]["items"]
    assert payload["table"]["columns"] == [
        "产品",
        "账户 ID",
        "账户名",
        "渠道",
        "负责人",
        "状态",
        "消耗",
        "计费转化",
        "转化成本",
        "付费 ROI",
        "项目数",
        "异常项目",
        "建议事项",
    ]
    first_row = payload["table"]["rows"][0]
    assert first_row["账户 ID"] == "1001"
    assert first_row["消耗"] == 1000.0
    assert first_row["项目数"] == 2
    assert first_row["异常项目"] == 1


def test_dashboard_account_detail_returns_chinese_drilldown(tmp_path):
    _write_dashboard_fixture(tmp_path)
    client = _client(tmp_path)

    response = client.get("/api/dashboard/accounts/1001")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["title"] == "账户详情"
    assert {"label": "账户 ID", "value": "1001"} in payload["summary"]["items"]
    assert {"label": "产品", "value": "点点英雄"} in payload["summary"]["items"]
    assert {"label": "项目数", "value": 2} in payload["summary"]["items"]
    assert {"label": "异常项目", "value": 1} in payload["summary"]["items"]
    assert {"label": "单元素材数", "value": 2} in payload["summary"]["items"]
    assert {"label": "建议事项", "value": 1} in payload["summary"]["items"]
    assert payload["table"]["columns"] == [
        "类型",
        "产品",
        "账户 ID",
        "关联 ID",
        "名称",
        "状态/动作",
        "消耗",
        "计费转化",
        "说明",
    ]
    assert {
        "类型": "项目",
        "产品": "点点英雄",
        "账户 ID": "1001",
        "关联 ID": "p2",
        "名称": "点点英雄-7R-2",
        "状态/动作": "attention",
        "消耗": 400.0,
        "计费转化": 0.0,
        "说明": "异常项目",
    } in payload["table"]["rows"]
    assert {
        "类型": "单元素材",
        "产品": "点点英雄",
        "账户 ID": "1001",
        "关联 ID": "u2",
        "名称": "点点英雄-素材B",
        "状态/动作": "attention",
        "消耗": 120.0,
        "计费转化": 0.0,
        "说明": "项目 ID：p2",
    } in payload["table"]["rows"]
    assert {
        "类型": "建议",
        "产品": "点点英雄",
        "账户 ID": "1001",
        "关联 ID": "p2",
        "名称": "project",
        "状态/动作": "watch",
        "消耗": None,
        "计费转化": None,
        "说明": "今日消耗已有但转化不足",
    } in payload["table"]["rows"]


def test_dashboard_materials_returns_promotion_table(tmp_path):
    _write_dashboard_fixture(tmp_path)
    client = _client(tmp_path)

    response = client.get("/api/dashboard/materials")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["title"] == "单元素材看板"
    assert {"label": "单元素材数", "value": 2} in payload["summary"]["items"]
    assert payload["table"]["columns"] == [
        "产品",
        "账户 ID",
        "项目 ID",
        "单元 ID",
        "单元名",
        "状态",
        "消耗",
        "计费转化",
        "付费 ROI",
    ]
    assert payload["table"]["rows"][0]["单元 ID"] == "u1"
    assert payload["table"]["rows"][1]["状态"] == "attention"


def test_dashboard_material_detail_returns_chinese_drilldown(tmp_path):
    _write_dashboard_fixture(tmp_path)
    client = _client(tmp_path)

    response = client.get("/api/dashboard/materials/u2")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["title"] == "单元素材详情"
    assert {"label": "产品", "value": "点点英雄"} in payload["summary"]["items"]
    assert {"label": "账户 ID", "value": "1001"} in payload["summary"]["items"]
    assert {"label": "项目 ID", "value": "p2"} in payload["summary"]["items"]
    assert {"label": "单元 ID", "value": "u2"} in payload["summary"]["items"]
    assert {"label": "状态", "value": "attention"} in payload["summary"]["items"]
    assert {"label": "消耗", "value": 120.0} in payload["summary"]["items"]
    assert {"label": "计费转化", "value": 0.0} in payload["summary"]["items"]
    assert {"label": "付费 ROI", "value": 0.0} in payload["summary"]["items"]
    assert {"label": "关联建议", "value": 1} in payload["summary"]["items"]
    assert {
        "类型": "项目",
        "产品": "点点英雄",
        "账户 ID": "1001",
        "关联 ID": "p2",
        "名称": "点点英雄-7R-2",
        "状态/动作": "attention",
        "消耗": 400.0,
        "计费转化": 0.0,
        "说明": "异常项目",
    } in payload["table"]["rows"]
    assert {
        "类型": "单元素材",
        "产品": "点点英雄",
        "账户 ID": "1001",
        "关联 ID": "u2",
        "名称": "点点英雄-素材B",
        "状态/动作": "attention",
        "消耗": 120.0,
        "计费转化": 0.0,
        "说明": "项目 ID：p2",
    } in payload["table"]["rows"]


def test_dashboard_suggestions_handles_missing_artifact(tmp_path):
    _write_account_store(tmp_path)
    _write_patrol_artifact(tmp_path)
    client = _client(tmp_path)

    response = client.get("/api/dashboard/suggestions")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["title"] == "异常与建议中心"
    assert {"label": "建议事项", "value": 0} in payload["summary"]["items"]
    assert payload["table"]["rows"] == []


def test_dashboard_suggestions_returns_chinese_reason_and_config_hint(tmp_path):
    _write_dashboard_fixture(tmp_path)
    client = _client(tmp_path)

    response = client.get("/api/dashboard/suggestions")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["title"] == "异常与建议中心"
    assert {"label": "建议事项", "value": 2} in payload["summary"]["items"]
    assert {"label": "可生成配置", "value": 1} in payload["summary"]["items"]
    assert payload["table"]["columns"] == [
        "优先级",
        "产品",
        "账户 ID",
        "层级",
        "项目 ID",
        "建议动作",
        "中文解释",
        "可生成配置",
    ]
    assert {
        "优先级": "低",
        "产品": "点点英雄",
        "账户 ID": "1001",
        "层级": "project",
        "项目 ID": "p2",
        "建议动作": "watch",
        "中文解释": "今日消耗已有但转化不足",
        "可生成配置": "观察，无需生成执行配置",
    } in payload["table"]["rows"]
    assert {
        "优先级": "中",
        "产品": "你行你先坐",
        "账户 ID": "1002",
        "层级": "project",
        "项目 ID": "p3",
        "建议动作": "lower_budget",
        "中文解释": "ROI 偏低",
        "可生成配置": "可生成调预算配置",
    } in payload["table"]["rows"]


def test_dashboard_overview_keeps_patrol_data_when_account_store_missing(tmp_path):
    _write_patrol_artifact(tmp_path)
    _write_suggestions_artifact(tmp_path)
    client = _client(tmp_path)

    response = client.get("/api/dashboard/overview")

    assert response.status_code == 200
    payload = response.json()
    assert {"label": "今日消耗", "value": 1234.56} in payload["summary"]["items"]
    assert {"label": "活跃项目", "value": 3} in payload["summary"]["items"]
    assert payload["table"]["rows"][0]["产品"].startswith("未归档产品")
