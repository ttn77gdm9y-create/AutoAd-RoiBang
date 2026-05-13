import importlib.util
import json
import sqlite3
from datetime import date
from pathlib import Path

from roibang_v2.accounts.pool import import_accounts_csv
from roibang_v2.db.bootstrap import bootstrap_database
from roibang_v2.fetch.openapi_http import HttpResponse
from roibang_v2.workflows.material_history_backfill import build_material_history_backfill_preflight
from roibang_v2.workflows.material_history_backfill import import_material_daily_execution
from roibang_v2.workflows.material_history_backfill import run_material_history_backfill_request


def _write_accounts_csv(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "account_name,advertiser_id,消耗,product,platform",
                "黑旗-勇者突进-微小-傲星-306,1858371222574218,\"570,011.13\",勇者突进,WECHAT_GAME",
                "黑旗-勇者突进-微小-傲星-322,1858371234830346,\"120,001.00\",勇者突进,WECHAT_GAME",
                "黑旗-其他产品-微小-傲星-001,1850000000000003,12.5,其他产品,WECHAT_GAME",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def test_bootstrap_creates_material_history_tables(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"

    bootstrap_database(db_path)

    with sqlite3.connect(db_path) as conn:
        daily_columns = {
            row[1]
            for row in conn.execute("PRAGMA table_info(material_daily_metrics)").fetchall()
        }
        profile_columns = {
            row[1]
            for row in conn.execute("PRAGMA table_info(material_profiles)").fetchall()
        }
        state_columns = {
            row[1]
            for row in conn.execute("PRAGMA table_info(material_sync_state)").fetchall()
        }
        rollup_columns = {
            row[1]
            for row in conn.execute("PRAGMA table_info(material_metric_rollups)").fetchall()
        }

    assert {
        "metric_date",
        "advertiser_id",
        "project_id",
        "promotion_id",
        "material_id",
        "stat_cost",
        "metric_payload_json",
    }.issubset(daily_columns)
    assert {"material_id", "canonical_material_key", "name", "video_id", "review_status", "payload_json"}.issubset(
        profile_columns
    )
    assert {"workflow", "sync_date", "status", "artifact_path"}.issubset(state_columns)
    assert {
        "window_key",
        "window_days",
        "period_start",
        "period_end",
        "canonical_material_key",
        "material_id",
        "stat_cost",
    }.issubset(rollup_columns)


def test_material_history_backfill_preflight_plans_daily_discovery_and_material_fetch(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    csv_path = tmp_path / "accounts.csv"
    bootstrap_database(db_path)
    _write_accounts_csv(csv_path)
    import_accounts_csv(csv_path, db_path=db_path)

    result = build_material_history_backfill_preflight(
        {
            "material_history_backfill": {
                "product": "勇者突进",
                "platforms": ["WECHAT_GAME"],
                "date_range": {"start": "2026-02-10", "end": "2026-02-12"},
                "active_account_discovery": {
                    "source": "workbench_account_list",
                    "enabled": True,
                    "workbench": {"limit": 100},
                },
                "material_fetch": {
                    "source": "openapi_http_execute",
                    "openapi": {
                        "endpoints": ["report_custom"],
                        "report_presets": ["material_daily"],
                        "page_size": 20,
                    },
                },
            }
        },
        db_path=db_path,
        runs_dir=tmp_path / "runs",
    )

    assert result["ok"] is True
    assert result["workflow"] == "material_history_backfill_preflight"
    assert result["execution_enabled"] is False
    assert result["external_api_calls"] == 0
    assert result["summary"] == {
        "product": "勇者突进",
        "platforms": ["WECHAT_GAME"],
        "date_count": 3,
        "candidate_account_count": 2,
        "discovery_source": "workbench_account_list",
        "discovery_planned_request_count": 3,
        "material_detail_worst_case_account_count": 2,
        "material_detail_initial_request_count": 6,
        "estimated_total_initial_request_count": 9,
    }
    assert result["date_range"]["dates"] == ["2026-02-10", "2026-02-11", "2026-02-12"]
    assert result["detail_plan"]["report_presets"] == ["material_daily"]
    assert Path(result["artifact_path"]).exists()
    artifact = json.loads(Path(result["artifact_path"]).read_text(encoding="utf-8"))
    assert artifact["summary"]["estimated_total_initial_request_count"] == 9


def test_material_history_backfill_supports_yesterday_date_range_mode(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    csv_path = tmp_path / "accounts.csv"
    bootstrap_database(db_path)
    _write_accounts_csv(csv_path)
    import_accounts_csv(csv_path, db_path=db_path)

    result = build_material_history_backfill_preflight(
        {
            "material_history_backfill": {
                "account_pool_csv": str(csv_path),
                "product": "勇者突进",
                "platforms": ["WECHAT_GAME"],
                "date_range": {"mode": "yesterday", "base_date": "2026-05-11"},
                "active_account_discovery": {
                    "source": "workbench_account_list",
                    "enabled": True,
                    "workbench": {"limit": 100},
                },
                "material_fetch": {
                    "source": "openapi_http_execute",
                    "openapi": {
                        "endpoints": ["report_custom"],
                        "report_presets": ["material_daily"],
                        "page_size": 20,
                    },
                },
            }
        },
        db_path=db_path,
        runs_dir=tmp_path / "runs",
    )

    assert result["ok"] is True
    assert result["date_range"] == {
        "start": "2026-05-10",
        "end": "2026-05-10",
        "dates": ["2026-05-10"],
    }


def test_material_history_backfill_preflight_cli_writes_summary(tmp_path: Path, capsys):
    db_path = tmp_path / "roibang.sqlite3"
    csv_path = tmp_path / "accounts.csv"
    request_path = tmp_path / "request.json"
    bootstrap_database(db_path)
    _write_accounts_csv(csv_path)
    request_path.write_text(
        json.dumps(
            {
                "material_history_backfill": {
                    "account_pool_csv": str(csv_path),
                    "product": "勇者突进",
                    "platforms": ["WECHAT_GAME"],
                    "date_range": {"start": "2026-02-10", "end": "2026-02-10"},
                    "active_account_discovery": {
                        "source": "workbench_account_list",
                        "enabled": True,
                        "workbench": {"limit": 100},
                    },
                    "material_fetch": {
                        "source": "openapi_http_execute",
                        "openapi": {
                            "endpoints": ["report_custom"],
                            "report_presets": ["material_daily"],
                            "page_size": 20,
                        },
                    },
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    script_path = Path("scripts/run_material_history_backfill.py")
    spec = importlib.util.spec_from_file_location("run_material_history_backfill", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)

    exit_code = module.run_from_args(
        [
            "--config",
            "configs/runtime.example.json",
            "--request",
            str(request_path),
            "--db",
            str(db_path),
            "--runs-dir",
            str(tmp_path / "runs"),
            "--preflight",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert '"workflow": "material_history_backfill_preflight"' in captured.out
    assert '"external_api_calls": 0' in captured.out
    assert '"estimated_total_initial_request_count": 3' in captured.out


def test_material_daily_execution_imports_only_spending_rows(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)

    result = import_material_daily_execution(
        {
            "responses": [
                {
                    "request": {
                        "date": "2026-02-10",
                        "endpoint_key": "report_custom",
                        "report_preset": "material_daily",
                        "account": {"advertiser_id": "1858371222574218"},
                    },
                    "rows": [
                        {
                            "dimensions": {
                                "stat_time_day": "2026-02-10",
                                "cdp_project_id": "project_1",
                                "cdp_project_name": "项目 1",
                                "cdp_promotion_id": "promotion_1",
                                "cdp_promotion_name": "单元 1",
                                "material_id": "material_1",
                            },
                            "metrics": {
                                "stat_cost": "1,234.50",
                                "show_cnt": "1000",
                                "click_cnt": "25",
                                "convert_cnt": "3",
                                "active_register": "6",
                                "attribution_billing_game_in_app_roi_1day": "0.12",
                                "attribution_billing_game_in_app_roi_7days": "0.30",
                            },
                        },
                        {
                            "dimensions": {
                                "stat_time_day": "2026-02-10",
                                "cdp_project_id": "project_1",
                                "cdp_promotion_id": "promotion_1",
                                "material_id": "material_zero",
                            },
                            "metrics": {"stat_cost": "0.00"},
                        },
                    ],
                }
            ]
        },
        db_path=db_path,
        source="unit_test",
    )

    assert result == {
        "rows_seen": 2,
        "rows_imported": 1,
        "rows_skipped_zero_cost": 1,
        "rows_skipped_invalid": 0,
    }
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT
              metric_date, advertiser_id, project_id, promotion_id, material_id,
              stat_cost, show_cnt, roi_1day, roi_7days
            FROM material_daily_metrics
            """
        ).fetchall()
    assert rows == [
        ("2026-02-10", "1858371222574218", "project_1", "promotion_1", "material_1", 1234.5, 1000.0, 0.12, 0.3)
    ]


def test_material_history_backfill_default_disabled_writes_skipped_artifact(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    csv_path = tmp_path / "accounts.csv"
    bootstrap_database(db_path)
    _write_accounts_csv(csv_path)

    result = run_material_history_backfill_request(
        {
            "material_history_backfill": {
                "account_pool_csv": str(csv_path),
                "product": "勇者突进",
                "platforms": ["WECHAT_GAME"],
                "date_range": {"start": "2026-02-10", "end": "2026-02-10"},
                "active_account_discovery": {
                    "source": "workbench_account_list",
                    "enabled": True,
                    "workbench": {"limit": 100},
                },
                "material_fetch": {
                    "source": "openapi_http_execute",
                    "openapi": {"endpoints": ["report_custom"], "report_presets": ["material_daily"]},
                    "openapi_http": {"enabled": False},
                    "execution": {"status": "planned_only", "external_api_enabled": False},
                },
            }
        },
        db_path=db_path,
        runs_dir=tmp_path / "runs",
    )

    assert result["ok"] is True
    assert result["workflow"] == "material_history_backfill"
    assert result["skipped"] is True
    assert result["external_api_calls"] == 0
    assert result["preflight"]["summary"]["estimated_total_initial_request_count"] == 3
    assert Path(result["artifact_path"]).exists()


def test_material_history_backfill_uses_discovered_spending_accounts_for_material_fetch(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    csv_path = tmp_path / "accounts.csv"
    session_path = tmp_path / "workbench-session.json"
    bootstrap_database(db_path)
    _write_accounts_csv(csv_path)
    session_path.write_text(
        json.dumps({"cookie": "fake_cookie", "csrf_token": "fake_csrf", "ebpid": "fake_ebpid"}),
        encoding="utf-8",
    )

    def workbench_opener(url, body, headers, timeout_seconds):
        assert body["offset"] == 1
        return HttpResponse(
            200,
            {
                "code": 0,
                "data": {
                    "list": [
                        {
                            "advertiser_id": "1858371222574218",
                            "advertiser_name": "黑旗-勇者突进-微小-傲星-306",
                            "metrics": {"stat_cost": "88.00"},
                        },
                        {
                            "advertiser_id": "1858371234830346",
                            "advertiser_name": "黑旗-勇者突进-微小-傲星-322",
                            "metrics": {"stat_cost": "0.00"},
                        },
                    ],
                    "pagination": {"page": 1, "limit": 100, "total": 2, "hasMore": False},
                },
            },
        )

    def openapi_transport(request):
        assert request["account"]["advertiser_id"] == "1858371222574218"
        return {
            "code": 0,
            "data": {
                "page_info": {"page": 1, "page_size": 20, "total_page": 1, "total_count": 1},
                "rows": [
                    {
                        "dimensions": {
                            "stat_time_day": "2026-02-10",
                            "cdp_project_id": "project_1",
                            "cdp_promotion_id": "promotion_1",
                            "material_id": "material_1",
                        },
                        "metrics": {"stat_cost": "88.00", "show_cnt": "100"},
                    }
                ],
            },
        }

    result = run_material_history_backfill_request(
        {
            "material_history_backfill": {
                "account_pool_csv": str(csv_path),
                "product": "勇者突进",
                "platforms": ["WECHAT_GAME"],
                "date_range": {"start": "2026-02-10", "end": "2026-02-10"},
                "active_account_discovery": {
                    "source": "workbench_account_list",
                    "enabled": True,
                    "workbench": {
                        "enabled": True,
                        "session_file": str(session_path),
                        "limit": 100,
                        "stop_when_sorted_cost_reaches_zero": True,
                    },
                    "min_spend": 0,
                },
                "material_fetch": {
                    "source": "openapi_mock_execute",
                    "openapi": {
                        "endpoints": ["report_custom"],
                        "report_presets": ["material_daily"],
                        "page_size": 20,
                    },
                },
            }
        },
        db_path=db_path,
        runs_dir=tmp_path / "runs",
        workbench_opener=workbench_opener,
        workbench_sleeper=lambda seconds: None,
        openapi_transport=openapi_transport,
    )

    assert result["ok"] is True
    assert result["skipped"] is False
    assert result["summary"]["active_account_count"] == 1
    assert result["summary"]["material_rows_imported"] == 1
    assert result["summary"]["material_rows_unique_in_db"] == 1
    assert result["summary"]["material_fetch_transport_calls"] == 1
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT advertiser_id, material_id, stat_cost FROM material_daily_metrics"
        ).fetchall()
    assert rows == [("1858371222574218", "material_1", 88.0)]


def test_material_history_backfill_retries_temporary_openapi_business_code(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    csv_path = tmp_path / "accounts.csv"
    session_path = tmp_path / "workbench-session.json"
    bootstrap_database(db_path)
    _write_accounts_csv(csv_path)
    session_path.write_text(
        json.dumps({"cookie": "fake_cookie", "csrf_token": "fake_csrf", "ebpid": "fake_ebpid"}),
        encoding="utf-8",
    )

    def workbench_opener(_url, _body, _headers, _timeout_seconds):
        return HttpResponse(
            200,
            {
                "code": 0,
                "data": {
                    "list": [
                        {
                            "advertiser_id": "1858371222574218",
                            "advertiser_name": "黑旗-勇者突进-微小-傲星-306",
                            "metrics": {"stat_cost": "88.00"},
                        }
                    ],
                    "pagination": {"page": 1, "limit": 100, "total": 1, "hasMore": False},
                },
            },
        )

    openapi_calls = []

    def openapi_transport(request):
        openapi_calls.append(request["query_params"]["page"])
        if len(openapi_calls) == 1:
            return {
                "code": 50000,
                "message": "服务内部错误，请稍后重试",
                "data": {"rows": []},
            }
        return {
            "code": 0,
            "data": {
                "page_info": {"page": 1, "page_size": 20, "total_page": 1, "total_count": 1},
                "rows": [
                    {
                        "dimensions": {
                            "stat_time_day": "2026-02-10",
                            "cdp_project_id": "project_1",
                            "cdp_promotion_id": "promotion_1",
                            "material_id": "material_1",
                        },
                        "metrics": {"stat_cost": "88.00"},
                    }
                ],
            },
        }

    result = run_material_history_backfill_request(
        {
            "material_history_backfill": {
                "account_pool_csv": str(csv_path),
                "product": "勇者突进",
                "platforms": ["WECHAT_GAME"],
                "date_range": {"start": "2026-02-10", "end": "2026-02-10"},
                "active_account_discovery": {
                    "source": "workbench_account_list",
                    "enabled": True,
                    "workbench": {
                        "enabled": True,
                        "session_file": str(session_path),
                        "limit": 100,
                        "stop_when_sorted_cost_reaches_zero": True,
                    },
                    "min_spend": 0,
                },
                "material_fetch": {
                    "source": "openapi_mock_execute",
                    "openapi": {
                        "endpoints": ["report_custom"],
                        "report_presets": ["material_daily"],
                        "page_size": 20,
                    },
                    "openapi_http": {
                        "retry_api_codes": [50000],
                        "max_api_retries": 2,
                        "retry_sleep_seconds": 0,
                    },
                },
            }
        },
        db_path=db_path,
        runs_dir=tmp_path / "runs",
        workbench_opener=workbench_opener,
        workbench_sleeper=lambda seconds: None,
        openapi_transport=openapi_transport,
    )

    assert result["ok"] is True
    assert openapi_calls == ["1", "1"]
    assert result["summary"]["material_fetch_transport_calls"] == 2
    assert result["summary"]["material_rows_imported"] == 1


def test_material_history_backfill_cli_can_temporarily_enable_single_day_readonly(
    tmp_path: Path,
    capsys,
):
    db_path = tmp_path / "roibang.sqlite3"
    csv_path = tmp_path / "accounts.csv"
    session_path = tmp_path / "workbench-session.json"
    request_path = tmp_path / "request.json"
    runtime_path = tmp_path / "runtime.json"
    bootstrap_database(db_path)
    _write_accounts_csv(csv_path)
    session_path.write_text(
        json.dumps({"cookie": "fake_cookie", "csrf_token": "fake_csrf", "ebpid": "fake_ebpid"}),
        encoding="utf-8",
    )
    request_payload = {
        "material_history_backfill": {
            "account_pool_csv": str(csv_path),
            "product": "勇者突进",
            "platforms": ["WECHAT_GAME"],
            "date_range": {"start": "2026-02-10", "end": "2026-02-12"},
            "active_account_discovery": {
                "source": "workbench_account_list",
                "enabled": True,
                "workbench": {
                    "enabled": False,
                    "session_file": str(session_path),
                    "limit": 100,
                    "stop_when_sorted_cost_reaches_zero": True,
                },
                "min_spend": 0,
            },
            "material_fetch": {
                "source": "openapi_http_execute",
                "openapi": {"endpoints": ["report_custom"], "report_presets": ["material_daily"], "page_size": 20},
                "openapi_http": {"enabled": False, "token_file": str(tmp_path / "token.txt")},
                "execution": {"status": "planned_only", "external_api_enabled": False},
            },
        }
    }
    request_path.write_text(json.dumps(request_payload, ensure_ascii=False), encoding="utf-8")
    runtime_path.write_text(
        json.dumps(
            {
                "environment": "test",
                "phase": "phase1",
                "database_path": str(db_path),
                "runs_dir": str(tmp_path / "runs"),
                "fixtures_dir": str(tmp_path / "fixtures"),
                "external_api_enabled": True,
                "execution_enabled": False,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    script_path = Path("scripts/run_material_history_backfill.py")
    spec = importlib.util.spec_from_file_location("run_material_history_backfill", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)

    def workbench_opener(_url, _body, _headers, _timeout_seconds):
        return HttpResponse(
            200,
            {
                "code": 0,
                "data": {
                    "list": [
                        {
                            "advertiser_id": "1858371222574218",
                            "advertiser_name": "黑旗-勇者突进-微小-傲星-306",
                            "metrics": {"stat_cost": "88.00"},
                        }
                    ],
                    "pagination": {"page": 1, "limit": 100, "total": 1, "hasMore": False},
                },
            },
        )

    def openapi_transport(_request):
        return {
            "code": 0,
            "data": {
                "page_info": {"page": 1, "page_size": 20, "total_page": 1, "total_count": 1},
                "rows": [
                    {
                        "dimensions": {
                            "stat_time_day": "2026-05-06",
                            "cdp_project_id": "project_1",
                            "cdp_promotion_id": "promotion_1",
                            "material_id": "material_1",
                        },
                        "metrics": {"stat_cost": "88.00"},
                    }
                ],
            },
        }

    exit_code = module.run_from_args(
        [
            "--config",
            str(runtime_path),
            "--request",
            str(request_path),
            "--target-date",
            "2026-05-06",
            "--enable-readonly",
        ],
        workbench_opener=workbench_opener,
        workbench_sleeper=lambda seconds: None,
        openapi_transport=openapi_transport,
        today=date(2026, 5, 7),
    )

    captured = capsys.readouterr()
    original_request = json.loads(request_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert '"workflow": "material_history_backfill"' in captured.out
    assert '"material_rows_imported": 1' in captured.out
    assert original_request["material_history_backfill"]["date_range"] == {
        "start": "2026-02-10",
        "end": "2026-02-12",
    }
    assert original_request["material_history_backfill"]["material_fetch"]["openapi_http"]["enabled"] is False
