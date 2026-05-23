import importlib.util
import json
from pathlib import Path

from roibang_v2.workflows.project_status_update_config import build_project_status_update_config
from roibang_v2.workflows.project_status_update_config import run_project_status_update_config_request


def _load_script(name: str = "run_project_status_update_config.py"):
    script_path = Path("scripts") / name
    spec = importlib.util.spec_from_file_location(name.removesuffix(".py"), script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_project_status_update_config_expands_enabled_projects_from_accounts():
    calls: list[dict] = []

    def transport(request: dict) -> dict:
        calls.append(request)
        return {
            "code": 0,
            "data": {
                "list": [
                    {
                        "project_id": "p-1",
                        "name": "勇者突进-正常",
                        "status_first": "PROJECT_STATUS_ENABLE",
                        "delivery_type": "NORMAL",
                    },
                    {
                        "project_id": "p-duration",
                        "name": "勇者突进-周期稳投",
                        "status_first": "PROJECT_STATUS_ENABLE",
                        "delivery_type": "DURATION",
                    },
                ],
                "page_info": {"total_number": 2},
            },
        }

    result = build_project_status_update_config(
        {
            "project_update_id": "pause-six-accounts-001",
            "operator": "郭靖",
            "allowed_target_accounts_path": "configs/control-allowed-accounts.local.json",
            "advertiser_ids": ["adv-1"],
            "opt_status": "DISABLE",
            "reason": "重建前关停旧项目",
        },
        transport=transport,
    )

    assert result["external_api_calls"] == 1
    assert result["summary"]["action_count"] == 1
    assert result["summary"]["skipped_duration_project_count"] == 1
    assert result["project_update"]["actions"] == [
        {
            "action_type": "status_update",
            "advertiser_id": "adv-1",
            "entity_type": "project",
            "project_id": "p-1",
            "project_name": "勇者突进-正常",
            "opt_status": "DISABLE",
            "reason": "重建前关停旧项目",
        }
    ]
    assert calls[0]["operation"] == "lookup_project_list"
    assert calls[0]["payload"]["filtering"] == {"status_first": "PROJECT_STATUS_ENABLE"}


def test_project_status_update_config_filters_projects_by_name_contains():
    calls: list[dict] = []

    def transport(request: dict) -> dict:
        calls.append(request)
        return {
            "code": 0,
            "data": {
                "list": [
                    {"project_id": "p-0511", "name": "0511_郭靖_勇者突进_微小每付7R男"},
                    {"project_id": "p-0501", "name": "0501_郭靖_勇者突进_微小每付通投"},
                ]
            },
        }

    result = build_project_status_update_config(
        {
            "project_update_id": "enable-0511-001",
            "advertiser_ids": ["adv-1"],
            "opt_status": "ENABLE",
            "name_contains": ["0511"],
        },
        transport=transport,
    )

    assert result["summary"]["action_count"] == 1
    assert result["summary"]["name_contains"] == ["0511"]
    assert result["project_update"]["actions"][0]["project_id"] == "p-0511"
    assert calls[0]["payload"]["filtering"] == {
        "status_first": "PROJECT_STATUS_DISABLE",
        "status_second": "PROJECT_STATUS_STOP",
        "name": "0511",
    }


def test_project_management_update_config_builds_budget_actions_by_name():
    def transport(_request: dict) -> dict:
        return {
            "code": 0,
            "data": {
                "list": [
                    {"project_id": "p-1", "name": "0513_郭靖_勇者突进_放量"},
                    {"project_id": "p-2", "name": "0512_郭靖_勇者突进_放量"},
                ]
            },
        }

    result = build_project_status_update_config(
        {
            "project_update_id": "budget-0513-001",
            "advertiser_ids": ["adv-1"],
            "action_type": "budget_update",
            "budget_mode": "BUDGET_MODE_DAY",
            "budget": 88888,
            "name_contains": ["0513"],
        },
        transport=transport,
    )

    assert result["workflow"] == "project_management_update_config"
    assert result["summary"]["action_type"] == "budget_update"
    assert result["summary"]["action_count"] == 1
    assert result["project_update"]["actions"] == [
        {
            "action_type": "budget_update",
            "advertiser_id": "adv-1",
            "entity_type": "project",
            "project_id": "p-1",
            "project_name": "0513_郭靖_勇者突进_放量",
            "budget_mode": "BUDGET_MODE_DAY",
            "budget": 88888,
        }
    ]


def test_project_management_update_config_builds_delete_actions_by_name_without_hidden_status_filter():
    calls: list[dict] = []

    def transport(request: dict) -> dict:
        calls.append(request)
        return {"code": 0, "data": {"list": [{"project_id": "p-closed", "name": "0513_郭靖_旧项目"}]}}

    result = build_project_status_update_config(
        {
            "project_update_id": "delete-0513-001",
            "advertiser_ids": ["adv-1"],
            "action_type": "delete_project",
            "name_contains": ["0513"],
        },
        transport=transport,
    )

    assert result["summary"]["action_type"] == "delete_project"
    assert result["project_update"]["actions"][0] == {
        "action_type": "delete_project",
        "advertiser_id": "adv-1",
        "entity_type": "project",
        "project_id": "p-closed",
        "project_name": "0513_郭靖_旧项目",
    }
    assert calls[0]["payload"]["filtering"] == {"name": "0513"}


def test_project_management_update_config_filters_delete_actions_by_realtime_spend():
    calls: list[dict] = []

    def transport(request: dict) -> dict:
        calls.append(request)
        if request["operation"] == "lookup_project_list":
            return {
                "code": 0,
                "data": {
                    "list": [
                        {"project_id": "p-low", "name": "0513_郭靖_低消耗"},
                        {"project_id": "p-high", "name": "0513_郭靖_高消耗"},
                        {"project_id": "p-no-cost", "name": "0513_郭靖_无消耗"},
                    ]
                },
            }
        if request["operation"] == "lookup_project_report":
            return {
                "code": 0,
                "data": {
                    "rows": [
                        {
                            "dimensions": {"cdp_project_id": "p-low", "cdp_project_name": "0513_郭靖_低消耗"},
                            "metrics": {"stat_cost": "99.99"},
                        },
                        {
                            "dimensions": {"cdp_project_id": "p-high", "cdp_project_name": "0513_郭靖_高消耗"},
                            "metrics": {"stat_cost": "100.00"},
                        },
                    ]
                },
            }
        raise AssertionError(request)

    result = build_project_status_update_config(
        {
            "project_update_id": "delete-0513-low-spend-001",
            "advertiser_ids": ["adv-1"],
            "action_type": "delete_project",
            "name_contains": ["0513"],
            "spend_filter": {
                "window": "today",
                "end_date": "2026-05-14",
                "max_stat_cost_exclusive": 100,
            },
        },
        transport=transport,
    )

    assert result["summary"]["action_count"] == 2
    assert result["summary"]["spend_filter"] == {
        "window": "today",
        "start_date": "2026-05-14",
        "end_date": "2026-05-14",
        "max_stat_cost_exclusive": 100.0,
    }
    assert [
        (action["project_id"], action["stat_cost"])
        for action in result["project_update"]["actions"]
    ] == [("p-low", 99.99), ("p-no-cost", 0.0)]
    assert [(call["operation"], call["endpoint"]) for call in calls] == [
        ("lookup_project_list", "/open_api/v3.0/project/list/"),
        ("lookup_project_report", "/open_api/v3.0/report/custom/get/"),
    ]
    assert calls[1]["payload"]["start_time"] == "2026-05-14"
    assert calls[1]["payload"]["end_time"] == "2026-05-14"


def test_project_management_update_config_filters_by_yesterday_billing_convert_cnt():
    calls: list[dict] = []

    def transport(request: dict) -> dict:
        calls.append(request)
        if request["operation"] == "lookup_project_list":
            return {
                "code": 0,
                "data": {
                    "list": [
                        {"project_id": "p-zero", "name": "0515_郭靖_无计费转化"},
                        {"project_id": "p-one", "name": "0515_郭靖_有计费转化"},
                    ]
                },
            }
        if request["operation"] == "lookup_project_report":
            return {
                "code": 0,
                "data": {
                    "rows": [
                        {
                            "dimensions": {"cdp_project_id": "p-zero", "cdp_project_name": "0515_郭靖_无计费转化"},
                            "metrics": {
                                "stat_cost": "88",
                                "active_register": "2",
                                "attribution_convert_cnt": "0",
                                "attribution_billing_game_in_app_roi_1day": "0",
                            },
                        },
                        {
                            "dimensions": {"cdp_project_id": "p-one", "cdp_project_name": "0515_郭靖_有计费转化"},
                            "metrics": {
                                "stat_cost": "120",
                                "active_register": "3",
                                "attribution_convert_cnt": "1",
                                "attribution_billing_game_in_app_roi_1day": "0.12",
                            },
                        },
                    ]
                },
            }
        raise AssertionError(request)

    result = build_project_status_update_config(
        {
            "project_update_id": "disable-yesterday-zero-billing-001",
            "advertiser_ids": ["adv-1"],
            "action_type": "status_update",
            "opt_status": "DISABLE",
            "name_contains": ["0515"],
            "realtime_filter": {
                "window": "yesterday",
                "end_date": "2026-05-16",
                "metric_filters": [{"field": "billing_convert_cnt", "op": "eq", "value": 0}],
            },
        },
        transport=transport,
    )

    assert result["summary"]["action_count"] == 1
    assert result["summary"]["realtime_filter"]["window"] == "yesterday"
    assert result["summary"]["realtime_filter"]["start_date"] == "2026-05-15"
    assert result["project_update"]["actions"][0]["project_id"] == "p-zero"
    assert result["project_update"]["actions"][0]["metrics"] == {
        "stat_cost": 88.0,
        "show_cnt": 0.0,
        "click_cnt": 0.0,
        "ctr": None,
        "active_register": 2.0,
        "register_cost": 44.0,
        "billing_convert_cnt": 0.0,
        "billing_conversion_cost": None,
        "billing_1day_pay_roi": 0.0,
    }
    assert result["matched_projects"][0]["match_reasons"] == ["billing_convert_cnt eq 0.0"]
    assert result["skipped_projects"][0]["skip_reason"] == "metric_filter_not_matched"
    assert "attribution_convert_cnt" in calls[1]["payload"]["metrics"]


def test_project_management_update_config_can_match_zero_billing_roi():
    def transport(request: dict) -> dict:
        if request["operation"] == "lookup_project_list":
            return {
                "code": 0,
                "data": {
                    "list": [
                        {"project_id": "p-zero-roi", "name": "郭靖-勇者突进-零ROI"},
                        {"project_id": "p-good-roi", "name": "郭靖-勇者突进-有ROI"},
                    ]
                },
            }
        if request["operation"] == "lookup_project_report":
            return {
                "code": 0,
                "data": {
                    "rows": [
                        {
                            "dimensions": {"cdp_project_id": "p-zero-roi"},
                            "metrics": {"stat_cost": "100", "attribution_billing_game_in_app_roi_1day": "0"},
                        },
                        {
                            "dimensions": {"cdp_project_id": "p-good-roi"},
                            "metrics": {"stat_cost": "100", "attribution_billing_game_in_app_roi_1day": "0.03"},
                        },
                    ]
                },
            }
        raise AssertionError(request)

    result = build_project_status_update_config(
        {
            "project_update_id": "delete-zero-roi-001",
            "advertiser_ids": ["adv-1"],
            "action_type": "delete_project",
            "name_contains": ["郭靖", "勇者突进"],
            "realtime_filter": {
                "window": "today",
                "end_date": "2026-05-22",
                "metric_filters": [{"field": "billing_1day_pay_roi", "op": "eq", "value": 0}],
            },
        },
        transport=transport,
    )

    assert result["summary"]["action_count"] == 1
    assert result["project_update"]["actions"][0]["project_id"] == "p-zero-roi"
    assert result["project_update"]["actions"][0]["metrics"]["billing_1day_pay_roi"] == 0.0
    assert result["matched_projects"][0]["match_reasons"] == ["billing_1day_pay_roi eq 0.0"]


def test_project_management_update_config_filters_by_last_3_days_cost_and_register_cost():
    def transport(request: dict) -> dict:
        if request["operation"] == "lookup_project_list":
            return {
                "code": 0,
                "data": {
                    "list": [
                        {"project_id": "p-low", "name": "郭靖_低消耗"},
                        {"project_id": "p-high", "name": "郭靖_高消耗"},
                    ]
                },
            }
        if request["operation"] == "lookup_project_report":
            return {
                "code": 0,
                "data": {
                    "rows": [
                        {
                            "dimensions": {"cdp_project_id": "p-low"},
                            "metrics": {"stat_cost": "199.99", "active_register": "1", "attribution_convert_cnt": "0"},
                        },
                        {
                            "dimensions": {"cdp_project_id": "p-high"},
                            "metrics": {"stat_cost": "300", "active_register": "1", "attribution_convert_cnt": "0"},
                        },
                    ]
                },
            }
        raise AssertionError(request)

    result = build_project_status_update_config(
        {
            "project_update_id": "delete-last-3-low-cost-001",
            "advertiser_ids": ["adv-1"],
            "action_type": "delete_project",
            "realtime_filter": {
                "window": "last_3_days",
                "end_date": "2026-05-16",
                "metric_filters": [
                    {"field": "stat_cost", "op": "lt", "value": 200},
                    {"field": "register_cost", "op": "gte", "value": 100},
                ],
            },
        },
        transport=transport,
    )

    assert result["summary"]["action_count"] == 1
    assert result["summary"]["realtime_filter"]["start_date"] == "2026-05-14"
    assert result["summary"]["realtime_filter"]["end_date"] == "2026-05-16"
    assert result["project_update"]["actions"][0]["project_id"] == "p-low"
    assert result["matched_projects"][0]["match_reasons"] == ["stat_cost lt 200.0", "register_cost gte 100.0"]


def test_project_management_update_config_rejects_unsupported_realtime_window():
    def transport(_request: dict) -> dict:
        raise AssertionError("transport should not be called")

    try:
        build_project_status_update_config(
            {
                "project_update_id": "bad-window",
                "advertiser_ids": ["adv-1"],
                "action_type": "delete_project",
                "realtime_filter": {
                    "window": "last_7_days",
                    "end_date": "2026-05-16",
                    "metric_filters": [{"field": "stat_cost", "op": "lt", "value": 100}],
                },
            },
            transport=transport,
        )
    except ValueError as exc:
        assert "only supports today, yesterday, last_3_days" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_run_project_status_update_config_writes_project_update_json(tmp_path: Path):
    def transport(_request: dict) -> dict:
        return {"code": 0, "data": {"list": [{"project_id": "p-1", "name": "勇者突进"}]}}

    output_path = tmp_path / "pause.local.json"
    result = run_project_status_update_config_request(
        {
            "project_update_id": "pause-account-001",
            "advertiser_ids": ["adv-1"],
            "opt_status": "DISABLE",
            "output_path": str(output_path),
        },
        runs_dir=tmp_path / "runs",
        transport=transport,
    )

    saved = json.loads(output_path.read_text(encoding="utf-8"))
    assert result["ok"] is True
    assert result["workflow"] == "project_status_update_config"
    assert result["project_update_path"] == str(output_path)
    assert Path(result["artifact_path"]).exists()
    assert saved["actions"][0]["action_type"] == "status_update"


def test_project_status_update_config_cli_requires_config_for_live_lookup(tmp_path: Path, capsys):
    module = _load_script()

    exit_code = module.run_from_args(
        [
            "--project-update-id",
            "pause-account-001",
            "--advertiser-id",
            "adv-1",
            "--opt-status",
            "DISABLE",
            "--output",
            str(tmp_path / "pause.local.json"),
            "--runs-dir",
            str(tmp_path / "runs"),
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert output["workflow"] == "project_status_update_config"
    assert output["status"] == "blocked"
    assert output["blocking_reasons"] == ["project status update config requires --config for live project lookup"]


def test_project_status_update_config_cli_reads_nested_runner_transport_config():
    module = _load_script()

    config = module._transport_config(
        {
            "create_live_execute_once": {
                "create_http_transport": {
                    "enabled": True,
                    "allow_mutation": True,
                    "run_id": "run-001",
                }
            }
        }
    )

    assert config == {"enabled": True, "allow_mutation": True, "run_id": "run-001"}


def test_project_realtime_filter_cli_parses_metric_filter():
    module = _load_script("run_project_management_update_config.py")

    assert module._parse_metric_filter("billing_convert_cnt:eq:0") == {
        "field": "billing_convert_cnt",
        "op": "eq",
        "value": 0.0,
    }


def test_project_realtime_filter_cli_wrapper_defaults_to_delete_project(tmp_path: Path, capsys):
    module = _load_script("run_project_realtime_filter_config.py")

    exit_code = module.run_from_args(
        [
            "--project-update-id",
            "delete-low-cost",
            "--advertiser-id",
            "adv-1",
            "--spend-window",
            "today",
            "--metric-filter",
            "stat_cost:lt:100",
            "--output",
            str(tmp_path / "delete.local.json"),
            "--runs-dir",
            str(tmp_path / "runs"),
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert output["workflow"] == "project_management_update_config"
    assert output["blocking_reasons"] == ["project management update config requires --config for live project lookup"]
