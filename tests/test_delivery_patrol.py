import importlib.util
import json
from pathlib import Path

from roibang_v2.db.bootstrap import bootstrap_database
from roibang_v2.fetch.openapi_http import HttpResponse
from roibang_v2.workflows.delivery_patrol import build_delivery_patrol_plan
from roibang_v2.workflows.delivery_patrol import run_delivery_patrol_request


def _load_script():
    script_path = Path("scripts/run_delivery_patrol.py")
    spec = importlib.util.spec_from_file_location("run_delivery_patrol", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _write_allowed_accounts(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "allowed_target_accounts": [
                    {
                        "account_name": "黑旗-勇者突进-微小-傲星-153",
                        "advertiser_id": "1856647523922953",
                        "product": "勇者突进",
                        "advertiser_remark": "勇者突进-微小-郭靖",
                        "enable": True,
                        "channel": "wx",
                    },
                    {
                        "account_name": "黑旗-其他产品-微小-傲星-1",
                        "advertiser_id": "blocked-by-product",
                        "product": "其他产品",
                        "advertiser_remark": "勇者突进-微小-其他",
                        "enable": True,
                        "channel": "wx",
                    },
                    {
                        "account_name": "黑旗-勇者突进-微小-其他-1",
                        "advertiser_id": "blocked-by-remark",
                        "product": "勇者突进",
                        "advertiser_remark": "勇者突进-微小-其他",
                        "enable": True,
                        "channel": "wx",
                    },
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _request(allowlist_path: Path) -> dict:
    return {
        "delivery_patrol": {
            "target_date": "2026-05-15",
            "yesterday_date": "2026-05-14",
            "product_keyword": "勇者突进",
            "allowed_target_accounts_path": str(allowlist_path),
            "account_scope": {
                "account_remark_equals": "勇者突进-微小-郭靖",
                "min_spend": 0,
            },
            "page_size": 100,
            "execution": {"status": "execute", "external_api_enabled": True},
            "openapi_http": {"enabled": True},
        }
    }


def _report_rows(request: dict) -> list[dict]:
    preset = request.get("report_preset")
    date = request.get("date")
    if preset == "account_daily":
        metrics = {
            "stat_cost": "100" if date == "2026-05-15" else "200",
            "show_cnt": "1000",
            "click_cnt": "50",
            "active_register": "2",
            "attribution_convert_cnt": "1",
            "attribution_billing_game_in_app_roi_1day": "0.12" if date == "2026-05-15" else "0.2",
        }
        return [{"dimensions": {"stat_time_day": date}, "metrics": metrics}]
    if preset == "project_daily":
        return [
            {
                "dimensions": {
                    "stat_time_day": date,
                    "cdp_project_id": "project-1",
                    "cdp_project_name": "0515_勇者突进_项目",
                },
                "metrics": {
                    "stat_cost": "80" if date == "2026-05-15" else "150",
                    "show_cnt": "800",
                    "click_cnt": "40",
                    "active_register": "2",
                    "attribution_convert_cnt": "1",
                    "attribution_billing_game_in_app_roi_1day": "0.1",
                },
            }
        ]
    if preset == "promotion_daily":
        return [
            {
                "dimensions": {
                    "stat_time_day": date,
                    "cdp_project_id": "project-1",
                    "cdp_project_name": "0515_勇者突进_项目",
                    "cdp_promotion_id": "promotion-1",
                    "cdp_promotion_name": "0515_勇者突进_单元",
                },
                "metrics": {
                    "stat_cost": "80" if date == "2026-05-15" else "150",
                    "show_cnt": "800",
                    "click_cnt": "40",
                    "active_register": "2",
                    "attribution_convert_cnt": "1",
                    "attribution_billing_game_in_app_roi_1day": "0.1",
                },
            }
        ]
    return []


def test_delivery_patrol_plan_reads_account_project_and_promotion_daily(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    allowlist_path = tmp_path / "allowed.json"
    bootstrap_database(db_path)
    _write_allowed_accounts(allowlist_path)

    plan = build_delivery_patrol_plan(db_path, _request(allowlist_path)["delivery_patrol"])

    assert plan["summary"]["allowed_account_count"] == 1
    assert plan["summary"]["date_count"] == 2
    assert plan["summary"]["planned_request_count"] == 8
    presets = [request["report_preset"] for request in plan["plan"]["requests"] if request["endpoint_key"] == "report_custom"]
    assert presets == [
        "account_daily",
        "project_daily",
        "promotion_daily",
        "account_daily",
        "project_daily",
        "promotion_daily",
    ]
    endpoints = [request["endpoint_key"] for request in plan["plan"]["requests"]]
    assert endpoints[-2:] == ["project_list", "promotion_list"]


def test_delivery_patrol_filters_accounts_by_account_remark(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    allowlist_path = tmp_path / "allowed.json"
    bootstrap_database(db_path)
    _write_allowed_accounts(allowlist_path)

    plan = build_delivery_patrol_plan(db_path, _request(allowlist_path)["delivery_patrol"])

    assert plan["accounts"] == [
        {
            "advertiser_id": "1856647523922953",
            "account_name": "黑旗-勇者突进-微小-傲星-153",
            "account_remark": "勇者突进-微小-郭靖",
            "product": "勇者突进",
            "platform": "WECHAT_GAME",
        }
    ]
    assert plan["summary"]["account_scope"] == {
        "source": "allowed_target_accounts",
        "account_remark_equals": "勇者突进-微小-郭靖",
        "min_spend": 0.0,
    }


def test_delivery_patrol_aggregates_today_and_yesterday_metrics(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    allowlist_path = tmp_path / "allowed.json"
    bootstrap_database(db_path)
    _write_allowed_accounts(allowlist_path)
    calls = []

    def transport(request: dict) -> dict:
        calls.append(request)
        if request["endpoint_key"] == "project_list":
            return {
                "code": 0,
                "data": {
                    "list": [
                        {
                            "project_id": "project-1",
                            "name": "0515_勇者突进_项目",
                            "project_status": "PROJECT_STATUS_ENABLE",
                        }
                    ],
                    "page_info": {"page": 1, "total_page": 1},
                },
            }
        if request["endpoint_key"] == "promotion_list":
            return {
                "code": 0,
                "data": {
                    "list": [
                        {
                            "promotion_id": "promotion-1",
                            "project_id": "project-1",
                            "name": "0515_勇者突进_单元",
                            "promotion_status": "PROMOTION_STATUS_ENABLE",
                        }
                    ],
                    "page_info": {"page": 1, "total_page": 1},
                },
            }
        return {
            "code": 0,
            "data": {
                "rows": _report_rows(request),
                "page_info": {"page": 1, "total_page": 1},
            },
        }

    result = run_delivery_patrol_request(
        _request(allowlist_path),
        db_path=db_path,
        runs_dir=tmp_path / "runs",
        transport=transport,
    )

    assert result["ok"] is True
    assert result["workflow"] == "delivery_patrol"
    assert result["execution_enabled"] is False
    assert result["external_api_calls"] == 8
    assert len(calls) == 8
    assert result["summary"]["account_count"] == 1
    assert result["summary"]["project_count"] == 1
    assert result["summary"]["promotion_count"] == 1
    assert result["summary"]["overall_metrics"]["today"]["stat_cost"] == 100
    assert result["summary"]["overall_metrics"]["yesterday"]["billing_1day_pay_roi"] == 0.2
    assert result["message"].startswith("RoiBang-V2 投放账户巡检 2026-05-15")
    assert "整体表现：今日消耗 100.0，注册成本 50.0，计费转化 1.0，计费转化成本 100.0，计费当日ROI 0.12；昨日消耗 200.0，注册成本 100.0，计费转化 1.0，计费转化成本 200.0，计费当日ROI 0.2" in result["message"]
    assert "账户：黑旗-勇者突进-微小-傲星-153" in result["message"]
    assert "重点项目" in result["message"]
    assert "项目ID project-1，状态 启用，" in result["message"]
    assert "重点单元" in result["message"]

    account = result["accounts"][0]
    assert account["account_remark"] == "勇者突进-微小-郭靖"
    assert account["metrics"]["today"]["stat_cost"] == 100
    assert account["metrics"]["today"]["ctr"] == 0.05
    assert account["metrics"]["today"]["register_cost"] == 50
    assert account["metrics"]["today"]["billing_convert_cnt"] == 1
    assert account["metrics"]["today"]["billing_conversion_cost"] == 100
    assert account["metrics"]["today"]["billing_1day_pay_roi"] == 0.12
    assert account["metrics"]["yesterday"]["stat_cost"] == 200
    assert account["summary"]["today_spent_project_count"] == 1
    assert account["summary"]["today_spent_promotion_count"] == 1
    assert "raw" in account["metrics"]["today"]
    assert account["metrics"]["today"]["raw"] == {"show_cnt": 1000, "click_cnt": 50}

    project = result["projects"][0]
    assert project["project_id"] == "project-1"
    assert project["status"] == "PROJECT_STATUS_ENABLE"
    assert project["metrics"]["today"]["stat_cost"] == 80
    promotion = result["promotions"][0]
    assert promotion["promotion_id"] == "promotion-1"
    assert promotion["status"] == "PROMOTION_STATUS_ENABLE"
    assert promotion["metrics"]["yesterday"]["stat_cost"] == 150
    assert Path(result["artifact_path"]).exists()
    assert (tmp_path / "runs/delivery_patrol/latest.md").read_text(encoding="utf-8").startswith(
        "RoiBang-V2 投放账户巡检"
    )
    assert json.loads((tmp_path / "runs/delivery_patrol/latest.json").read_text(encoding="utf-8"))["workflow"] == "delivery_patrol"


def test_delivery_patrol_adds_business_status_and_attention_items(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    allowlist_path = tmp_path / "allowed.json"
    bootstrap_database(db_path)
    _write_allowed_accounts(allowlist_path)
    request = _request(allowlist_path)
    request["delivery_patrol"]["business_rules"] = {
        "account_rules": {
            "zero_billing_convert": {"enabled": True, "min_stat_cost": 1000},
            "low_roi": {"enabled": True, "min_stat_cost": 1500, "roi_lt": 0.05},
        },
        "project_rules": {
            "high_cost_zero_convert": {"enabled": True, "min_stat_cost": 500},
            "low_roi": {"enabled": True, "min_stat_cost": 800, "billing_1day_pay_roi_lt": 0.05},
            "running_good": {"enabled": True, "min_stat_cost": 500, "billing_convert_cnt_gte": 1},
        },
        "promotion_rules": {
            "high_cost_zero_convert": {"enabled": True, "min_stat_cost": 300},
            "low_roi": {"enabled": True, "min_stat_cost": 500, "billing_1day_pay_roi_lt": 0.05},
        },
    }

    def transport(request: dict) -> dict:
        if request["endpoint_key"] == "project_list":
            return {
                "code": 0,
                "data": {
                    "list": [
                        {
                            "project_id": "project-zero",
                            "name": "0516_勇者突进_高消耗无转化",
                            "project_status": "PROJECT_STATUS_ENABLE",
                        },
                        {
                            "project_id": "project-good",
                            "name": "0516_勇者突进_有效跑量",
                            "project_status": "PROJECT_STATUS_ENABLE",
                        },
                    ],
                    "page_info": {"page": 1, "total_page": 1},
                },
            }
        if request["endpoint_key"] == "promotion_list":
            return {
                "code": 0,
                "data": {
                    "list": [
                        {
                            "promotion_id": "promotion-zero",
                            "project_id": "project-zero",
                            "name": "0516_勇者突进_无转化单元",
                            "promotion_status": "PROMOTION_STATUS_ENABLE",
                        }
                    ],
                    "page_info": {"page": 1, "total_page": 1},
                },
            }
        if request["report_preset"] == "account_daily":
            metrics = {
                "stat_cost": "1800" if request["date"] == "2026-05-15" else "900",
                "show_cnt": "10000",
                "click_cnt": "200",
                "active_register": "10",
                "attribution_convert_cnt": "0" if request["date"] == "2026-05-15" else "2",
                "attribution_billing_game_in_app_roi_1day": "0",
            }
            return {"code": 0, "data": {"rows": [{"dimensions": {"stat_time_day": request["date"]}, "metrics": metrics}]}}
        if request["report_preset"] == "project_daily":
            rows = []
            if request["date"] == "2026-05-15":
                rows = [
                    {
                        "dimensions": {
                            "stat_time_day": request["date"],
                            "cdp_project_id": "project-zero",
                            "cdp_project_name": "0516_勇者突进_高消耗无转化",
                        },
                        "metrics": {
                            "stat_cost": "620",
                            "show_cnt": "5000",
                            "click_cnt": "100",
                            "active_register": "3",
                            "attribution_convert_cnt": "0",
                            "attribution_billing_game_in_app_roi_1day": "0",
                        },
                    },
                    {
                        "dimensions": {
                            "stat_time_day": request["date"],
                            "cdp_project_id": "project-good",
                            "cdp_project_name": "0516_勇者突进_有效跑量",
                        },
                        "metrics": {
                            "stat_cost": "900",
                            "show_cnt": "7000",
                            "click_cnt": "140",
                            "active_register": "6",
                            "attribution_convert_cnt": "2",
                            "attribution_billing_game_in_app_roi_1day": "0.1",
                        },
                    },
                ]
            return {"code": 0, "data": {"rows": rows, "page_info": {"page": 1, "total_page": 1}}}
        if request["report_preset"] == "promotion_daily":
            rows = []
            if request["date"] == "2026-05-15":
                rows = [
                    {
                        "dimensions": {
                            "stat_time_day": request["date"],
                            "cdp_project_id": "project-zero",
                            "cdp_project_name": "0516_勇者突进_高消耗无转化",
                            "cdp_promotion_id": "promotion-zero",
                            "cdp_promotion_name": "0516_勇者突进_无转化单元",
                        },
                        "metrics": {
                            "stat_cost": "350",
                            "show_cnt": "3000",
                            "click_cnt": "60",
                            "active_register": "1",
                            "attribution_convert_cnt": "0",
                            "attribution_billing_game_in_app_roi_1day": "0",
                        },
                    }
                ]
            return {"code": 0, "data": {"rows": rows, "page_info": {"page": 1, "total_page": 1}}}
        raise AssertionError(request)

    result = run_delivery_patrol_request(
        request,
        db_path=db_path,
        runs_dir=tmp_path / "runs",
        transport=transport,
    )

    account = result["accounts"][0]
    assert account["business_status"] == "zero_billing_convert"
    assert account["severity"] == "high"
    assert account["status_reasons"] == ["今天消耗>=1000 且计费时间转化数为0"]
    projects = {project["project_id"]: project for project in result["projects"]}
    assert projects["project-zero"]["business_status"] == "high_cost_zero_convert"
    assert projects["project-zero"]["severity"] == "high"
    assert projects["project-good"]["business_status"] == "running_good"
    promotions = {promotion["promotion_id"]: promotion for promotion in result["promotions"]}
    assert promotions["promotion-zero"]["business_status"] == "unit_high_cost_zero_convert"
    assert result["summary"]["business_status_counts"]["accounts"] == {"zero_billing_convert": 1}
    assert result["summary"]["business_status_counts"]["projects"] == {
        "high_cost_zero_convert": 1,
        "running_good": 1,
    }
    assert result["summary"]["attention_count"] == 3
    assert [(item["entity_type"], item["entity_id"], item["business_status"]) for item in result["attention_items"]] == [
        ("account", "1856647523922953", "zero_billing_convert"),
        ("project", "project-zero", "high_cost_zero_convert"),
        ("promotion", "promotion-zero", "unit_high_cost_zero_convert"),
    ]
    assert result["top_accounts"][0]["advertiser_id"] == "1856647523922953"
    assert result["top_projects"][0]["project_id"] == "project-good"
    assert "状态分布" in result["message"]
    assert "重点账户" in result["message"]
    assert "有消耗无计费时间转化 1" in result["message"]
    assert "项目高消耗无计费时间转化 1" in result["message"]
    assert "项目跑量有效 1" in result["message"]
    assert "单元高消耗无计费时间转化" in result["message"]
    assert "zero_billing_convert" not in result["message"]
    assert "high_cost_zero_convert" not in result["message"]
    assert "unit_high_cost_zero_convert" not in result["message"]
    assert "完整 JSON" in result["message"]


def test_delivery_patrol_can_send_feishu_summary(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    allowlist_path = tmp_path / "allowed.json"
    bootstrap_database(db_path)
    _write_allowed_accounts(allowlist_path)
    sent: list[str] = []
    request = _request(allowlist_path)
    request["delivery_patrol"]["delivery"] = {
        "feishu": {"enabled": True, "chat_id": "oc_test", "runtime_file": "data/secrets/feishu.runtime.local.json"}
    }

    def transport(request: dict) -> dict:
        if request["endpoint_key"] in {"project_list", "promotion_list"}:
            return {"code": 0, "data": {"list": [], "page_info": {"page": 1, "total_page": 1}}}
        return {"code": 0, "data": {"rows": _report_rows(request), "page_info": {"page": 1, "total_page": 1}}}

    result = run_delivery_patrol_request(
        request,
        db_path=db_path,
        runs_dir=tmp_path / "runs",
        transport=transport,
        feishu_sender=lambda config, text: sent.append(f"{config['chat_id']}|{text}") or {"ok": True},
    )

    assert result["delivery"]["feishu"]["attempted"] is True
    assert sent and sent[0].startswith("oc_test|RoiBang-V2 投放账户巡检")


def test_delivery_patrol_can_include_suggestions_in_same_message(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    allowlist_path = tmp_path / "allowed.json"
    suggestions_request_path = tmp_path / "suggestions.json"
    bootstrap_database(db_path)
    _write_allowed_accounts(allowlist_path)
    suggestions_request_path.write_text(
        json.dumps(
            {
                "delivery_patrol_suggestions": {
                    "rules": {
                        "project": {
                            "close_low_roi": {
                                "enabled": True,
                                "min_stat_cost": 800,
                                "roi_lt": 0.05,
                                "max_billing_convert_cnt": 0,
                            }
                        }
                    }
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    request = _request(allowlist_path)
    request["delivery_patrol"]["suggestions"] = {
        "enabled": True,
        "request_path": str(suggestions_request_path),
        "db_path": str(db_path),
    }

    def transport(request: dict) -> dict:
        if request["endpoint_key"] == "project_list":
            return {
                "code": 0,
                "data": {
                    "list": [
                        {
                            "project_id": "project-close",
                            "name": "0518_郭靖勇者突进_建议关闭",
                            "project_status": "PROJECT_STATUS_ENABLE",
                        }
                    ],
                    "page_info": {"page": 1, "total_page": 1},
                },
            }
        if request["endpoint_key"] == "promotion_list":
            return {"code": 0, "data": {"list": [], "page_info": {"page": 1, "total_page": 1}}}
        if request["report_preset"] == "account_daily":
            return {
                "code": 0,
                "data": {
                    "rows": [
                        {
                            "dimensions": {"stat_time_day": request["date"]},
                            "metrics": {
                                "stat_cost": "900",
                                "show_cnt": "1000",
                                "click_cnt": "20",
                                "active_register": "3",
                                "attribution_convert_cnt": "0",
                                "attribution_billing_game_in_app_roi_1day": "0",
                            },
                        }
                    ],
                    "page_info": {"page": 1, "total_page": 1},
                },
            }
        if request["report_preset"] == "project_daily":
            rows = []
            if request["date"] == "2026-05-15":
                rows = [
                    {
                        "dimensions": {
                            "stat_time_day": request["date"],
                            "cdp_project_id": "project-close",
                            "cdp_project_name": "0518_郭靖勇者突进_建议关闭",
                        },
                        "metrics": {
                            "stat_cost": "900",
                            "show_cnt": "1000",
                            "click_cnt": "20",
                            "active_register": "3",
                            "attribution_convert_cnt": "0",
                            "attribution_billing_game_in_app_roi_1day": "0",
                        },
                    }
                ]
            return {"code": 0, "data": {"rows": rows, "page_info": {"page": 1, "total_page": 1}}}
        if request["report_preset"] == "promotion_daily":
            return {"code": 0, "data": {"rows": [], "page_info": {"page": 1, "total_page": 1}}}
        raise AssertionError(request)

    result = run_delivery_patrol_request(
        request,
        db_path=db_path,
        runs_dir=tmp_path / "runs",
        transport=transport,
    )

    assert result["delivery_patrol_suggestions"]["summary"]["suggest_close_project_count"] == 1
    assert result["delivery_patrol_suggestions"]["external_api_calls"] == 0
    assert result["delivery_patrol_suggestions"]["artifact_path"]
    assert "今日建议" in result["message"]
    assert "建议关闭项目 1" in result["message"]


def test_delivery_patrol_can_discover_today_spending_accounts_by_workbench_remark(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    session_path = tmp_path / "workbench-session.json"
    bootstrap_database(db_path)
    session_path.write_text(
        json.dumps({"cookie": "cookie-value", "csrf_token": "csrf-value", "ebpid": "ebp-1"}),
        encoding="utf-8",
    )
    request = {
        "delivery_patrol": {
            "target_date": "2026-05-15",
            "yesterday_date": "2026-05-14",
            "product_keyword": "勇者突进",
            "account_scope": {
                "source": "workbench_account_list",
                "account_remark_equals": "勇者突进-微小-郭靖",
                "min_spend": 0,
            },
            "active_account_discovery": {
                "enabled": True,
                "source": "workbench_account_list",
                "min_spend": 0,
                "workbench": {
                    "enabled": True,
                    "session_file": str(session_path),
                    "keyword": "勇者突进-微小",
                    "limit": 100,
                    "response_audit_dir": str(tmp_path / "audit"),
                },
            },
            "page_size": 100,
            "execution": {"status": "execute", "external_api_enabled": True},
            "openapi_http": {"enabled": True},
        }
    }
    workbench_calls = []
    openapi_calls = []

    def workbench_opener(url, body, headers, timeout_seconds):
        workbench_calls.append({"url": url, "body": body, "headers": headers, "timeout_seconds": timeout_seconds})
        return HttpResponse(
            200,
            {
                "code": 0,
                "data": {
                    "list": [
                        {
                            "advertiser_id": "1856647523922953",
                            "advertiser_name": "黑旗-勇者突进-微小-郭靖-153",
                            "advertiser_remark": "勇者突进-微小-郭靖",
                            "metrics": {"stat_cost": "88"},
                        },
                        {
                            "advertiser_id": "blocked-by-remark",
                            "advertiser_name": "黑旗-勇者突进-微小-其他-1",
                            "advertiser_remark": "勇者突进-微小-其他",
                            "metrics": {"stat_cost": "99"},
                        },
                    ],
                    "pagination": {"page": 1, "hasMore": False, "total": 2},
                },
            },
        )

    def transport(request):
        openapi_calls.append(request)
        if request["endpoint_key"] in {"project_list", "promotion_list"}:
            return {"code": 0, "data": {"list": [], "page_info": {"page": 1, "total_page": 1}}}
        return {"code": 0, "data": {"rows": _report_rows(request), "page_info": {"page": 1, "total_page": 1}}}

    result = run_delivery_patrol_request(
        request,
        db_path=db_path,
        runs_dir=tmp_path / "runs",
        transport=transport,
        workbench_opener=workbench_opener,
    )

    assert len(workbench_calls) == 1
    assert {call["account"]["advertiser_id"] for call in openapi_calls} == {"1856647523922953"}
    assert result["summary"]["account_count"] == 1
    assert result["summary"]["account_discovery"]["source"] == "workbench_account_list"
    assert result["summary"]["account_scope"]["account_remark_equals"] == "勇者突进-微小-郭靖"
    assert result["summary"]["account_discovery"]["total_spend"] == 88


def test_delivery_patrol_cli_requires_enable_readonly(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    allowlist_path = tmp_path / "allowed.json"
    request_path = tmp_path / "request.json"
    bootstrap_database(db_path)
    _write_allowed_accounts(allowlist_path)
    request_path.write_text(json.dumps(_request(allowlist_path), ensure_ascii=False), encoding="utf-8")
    module = _load_script()

    try:
        module.run_from_args(
            [
                "--config",
                "configs/runtime.example.json",
                "--request",
                str(request_path),
                "--db",
                str(db_path),
                "--runs-dir",
                str(tmp_path / "runs"),
            ]
        )
    except RuntimeError as exc:
        assert "requires --enable-readonly" in str(exc)
    else:
        raise AssertionError("CLI should fail closed without --enable-readonly")
