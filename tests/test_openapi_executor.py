from roibang_v2.fetch.openapi_executor import (
    build_snapshots_from_execution,
    execute_openapi_readonly_plan,
)
from roibang_v2.fetch.openapi_readonly import build_openapi_readonly_plan


def _single_report_plan():
    return build_openapi_readonly_plan(
        accounts=[
            {
                "advertiser_id": "1858371222574218",
                "account_name": "黑旗-勇者突进-微小-傲星-306",
                "product": "勇者突进",
                "platform": "WECHAT_GAME",
            }
        ],
        dates=["2026-02-10"],
        endpoints=["report_custom"],
        report_presets=["promotion_daily"],
        platforms=["WECHAT_GAME"],
        page_size=1,
    )


def _operation_log_plan():
    return build_openapi_readonly_plan(
        accounts=[
            {
                "advertiser_id": "1858371222574218",
                "account_name": "黑旗-勇者突进-微小-傲星-306",
                "product": "勇者突进",
                "platform": "WECHAT_GAME",
            }
        ],
        dates=["2026-02-10"],
        endpoints=["operation_log_search"],
        platforms=["WECHAT_GAME"],
        page_size=20,
    )


def test_execute_openapi_readonly_plan_follows_report_pagination():
    seen_pages = []

    def fake_transport(request):
        page = int(request["query_params"]["page"])
        seen_pages.append(page)
        return {
            "code": 0,
            "data": {
                "rows": [
                    {
                        "dimensions": {
                            "stat_time": "2026-02-10",
                            "promotion_id": f"promotion_{page}",
                            "promotion_name": f"单元 {page}",
                        },
                        "metrics": {"stat_cost": str(page * 100), "convert_cnt": page},
                    }
                ],
                "page_info": {"page": page, "total_page": 2},
            },
        }

    result = execute_openapi_readonly_plan(_single_report_plan(), transport=fake_transport)

    assert result["ok"] is True
    assert result["execution_enabled"] is False
    assert result["external_api_calls"] == 0
    assert result["summary"]["transport_calls"] == 2
    assert result["summary"]["rows_received"] == 2
    assert seen_pages == [1, 2]


def test_execute_openapi_readonly_plan_calculates_pages_from_total_count():
    seen_pages = []

    def fake_transport(request):
        page = int(request["query_params"]["page"])
        seen_pages.append(page)
        return {
            "code": 0,
            "data": {
                "logs": [
                    {
                        "request_id": f"req_{page}",
                        "content_title": "修改预算",
                        "object_type": "广告计划",
                        "object_id": page,
                        "create_time": "2026-02-10 11:22:33",
                    }
                ],
                "page_info": {"page": page, "page_size": 20, "total_count": 21},
            },
        }

    result = execute_openapi_readonly_plan(_operation_log_plan(), transport=fake_transport)

    assert result["summary"]["transport_calls"] == 2
    assert seen_pages == [1, 2]


def test_execute_openapi_readonly_plan_rejects_nonzero_api_code():
    def fake_transport(_request):
        return {
            "code": 40000,
            "message": "维度「stat_time」不支持",
            "data": {"rows": []},
        }

    try:
        execute_openapi_readonly_plan(_single_report_plan(), transport=fake_transport)
    except RuntimeError as exc:
        assert "OpenAPI response code=40000" in str(exc)
        assert "stat_time" in str(exc)
    else:
        raise AssertionError("non-zero OpenAPI business code should fail the readonly execution")


def test_execute_openapi_readonly_plan_retries_temporary_api_code():
    calls = []
    sleeps = []

    def fake_transport(request):
        calls.append(int(request["query_params"]["page"]))
        if len(calls) == 1:
            return {
                "code": 50000,
                "message": "服务内部错误，请稍后重试",
                "data": {"rows": []},
            }
        return {
            "code": 0,
            "data": {
                "rows": [
                    {
                        "dimensions": {
                            "stat_time": "2026-02-10",
                            "promotion_id": "promotion_1",
                        },
                        "metrics": {"stat_cost": "100"},
                    }
                ],
                "page_info": {"page": 1, "total_page": 1},
            },
        }

    result = execute_openapi_readonly_plan(
        _single_report_plan(),
        transport=fake_transport,
        retry_api_codes=[50000],
        max_api_retries=2,
        retry_sleep_seconds=3,
        sleeper=sleeps.append,
    )

    assert result["ok"] is True
    assert calls == [1, 1]
    assert sleeps == [3]
    assert result["summary"]["transport_calls"] == 2
    assert result["summary"]["rows_received"] == 1


def test_build_snapshots_from_execution_normalizes_promotion_daily_rows():
    def fake_transport(request):
        return {
            "code": 0,
            "data": {
                "rows": [
                    {
                        "dimensions": {
                            "stat_time": "2026-02-10",
                            "project_id": "project_1",
                            "project_name": "0210_勇者突进_项目",
                            "promotion_id": "promotion_1",
                            "promotion_name": "0210_勇者突进_单元",
                        },
                        "metrics": {
                            "stat_cost": "123.45",
                            "convert_cnt": "7",
                            "show_cnt": 1000,
                            "click_cnt": 33,
                        },
                    }
                ],
                "page_info": {"page": 1, "total_page": 1},
            },
        }

    execution = execute_openapi_readonly_plan(_single_report_plan(), transport=fake_transport)
    snapshots = build_snapshots_from_execution(execution)

    assert len(snapshots) == 1
    assert snapshots[0]["period"] == {"start": "2026-02-10", "end": "2026-02-10"}
    account = snapshots[0]["accounts"][0]
    assert account["advertiser_id"] == "1858371222574218"
    assert account["promotions"] == [
        {
            "advertiser_id": "1858371222574218",
            "project_id": "project_1",
            "project_name": "0210_勇者突进_项目",
            "promotion_id": "promotion_1",
            "promotion_name": "0210_勇者突进_单元",
            "promotion_status_name": "",
        }
    ]
    assert account["promotion_metrics"] == [
        {
            "promotion_id": "promotion_1",
            "stat_cost": 123.45,
            "convert_cnt": 7,
            "show_cnt": 1000,
            "click_cnt": 33,
        }
    ]


def test_operation_log_search_plan_uses_legacy_log_endpoint_and_daily_window():
    plan = _operation_log_plan()
    request = plan["requests"][0]

    assert request["endpoint_key"] == "operation_log_search"
    assert request["host"] == "https://ad.oceanengine.com"
    assert request["path"] == "/open_api/2/tools/log_search/"
    assert request["query_params"]["start_time"] == "2026-02-10 00:00:00"
    assert request["query_params"]["end_time"] == "2026-02-10 23:59:59"
    assert request["query_params"]["page_size"] == "20"


def test_operation_log_search_rows_are_normalized_into_snapshot_logs():
    def fake_transport(request):
        return {
            "code": 0,
            "data": {
                "logs": [
                    {
                        "request_id": "req_1",
                        "content_title": "修改预算",
                        "object_type": "广告计划",
                        "object_id": 123456,
                        "object_name": "0210_勇者突进_单元",
                        "create_time": "2026-02-10 11:22:33",
                        "content_log": ["预算: 300.0 -> 420.0"],
                        "operator": "管理员",
                    },
                    {
                        "request_id": "req_2",
                        "content_title": "修改项目",
                        "object_type": "项目",
                        "object_id": 654321,
                        "object_name": "0210_勇者突进_项目",
                        "create_time": "2026-02-10 12:00:00",
                        "content_log": ["状态: 暂停 -> 开启"],
                        "operator": "管理员",
                    },
                ],
                "page_info": {"page": 1, "page_size": 20, "total_page": 1},
            },
        }

    execution = execute_openapi_readonly_plan(_operation_log_plan(), transport=fake_transport)
    snapshots = build_snapshots_from_execution(execution)

    logs = snapshots[0]["accounts"][0]["operation_logs"]
    assert logs == [
        {
            "operation_id": "req_1",
            "occurred_at": "2026-02-10 11:22:33",
            "operator": "管理员",
            "entity_type": "promotion",
            "entity_id": "123456",
            "action": "修改预算",
            "detail": "预算: 300.0 -> 420.0",
            "payload": {
                "object_name": "0210_勇者突进_单元",
                "object_type": "广告计划",
            },
        },
        {
            "operation_id": "req_2",
            "occurred_at": "2026-02-10 12:00:00",
            "operator": "管理员",
            "entity_type": "project",
            "entity_id": "654321",
            "action": "修改项目",
            "detail": "状态: 暂停 -> 开启",
            "payload": {
                "object_name": "0210_勇者突进_项目",
                "object_type": "项目",
            },
        },
    ]


def test_operation_log_search_rows_build_stable_id_when_log_id_is_zero():
    def fake_transport(request):
        return {
            "code": 0,
            "data": {
                "logs": [
                    {
                        "second_log_id": 0,
                        "content_title": "修改",
                        "object_type": "单元",
                        "object_id": 123456,
                        "object_name": "单元名称",
                        "create_time": "2026-05-06 16:16:47",
                        "content_log": ["修改 审核状态: 视频转码中 -> 新建审核中"],
                        "operator": "系统",
                    }
                ],
                "page_info": {"page": 1, "page_size": 20, "total_page": 1},
            },
        }

    execution = execute_openapi_readonly_plan(_operation_log_plan(), transport=fake_transport)
    snapshots = build_snapshots_from_execution(execution)

    logs = snapshots[0]["accounts"][0]["operation_logs"]
    assert logs[0]["operation_id"].startswith("op_")
    assert logs[0]["entity_type"] == "promotion"
    assert logs[0]["detail"] == "修改 审核状态: 视频转码中 -> 新建审核中"
