import importlib.util
import json
import sqlite3
from datetime import date
from pathlib import Path

from roibang_v2.db.bootstrap import bootstrap_database
from roibang_v2.fetch.openapi_http import HttpResponse
from roibang_v2.workflows.daily_report_pipeline import (
    build_daily_report_pipeline_preflight,
    run_daily_report_pipeline_request,
)


def _load_pipeline_script():
    script_path = Path("scripts/run_daily_report_pipeline.py")
    spec = importlib.util.spec_from_file_location("run_daily_report_pipeline", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _write_accounts_csv(path: Path):
    path.write_text(
        "\n".join(
            [
                "account_name,advertiser_id,消耗,product,platform",
                "黑旗-勇者突进-微小-傲星-306,1858371222574218,\"570,011.13\",勇者突进,WECHAT_GAME",
                "黑旗-勇者突进-微小-傲星-153,1856647523922953,\"549,533.67\",勇者突进,WECHAT_GAME",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def _pipeline_request(csv_path: Path, snapshot_dir: Path) -> dict:
    return {
        "daily_report_pipeline": {
            "target_date": {"mode": "yesterday"},
            "report_fetch": {
                "source": "mock_openapi",
                "account_pool_csv": str(csv_path),
                "product": "勇者突进",
                "platforms": ["WECHAT_GAME"],
                "output": {"snapshot_dir": str(snapshot_dir)},
                "limits": {"max_accounts": 1},
                "execution": {"status": "planned_only", "external_api_enabled": False},
            },
            "daily_learning": {
                "min_cost_for_signal": 50,
                "min_conversions_for_signal": 3,
                "low_roi_threshold": 0.4,
                "top_material_limit": 10,
                "operation_log_limit": 20,
            },
        }
    }


def _pipeline_request_with_material_source(csv_path: Path, snapshot_dir: Path) -> dict:
    payload = _pipeline_request(csv_path, snapshot_dir)
    payload["daily_report_pipeline"]["material_source"] = {
        "kind": "local_product_source",
        "source_file": "data/fixtures/product-source-materials.sample.json",
        "product": "勇者突进",
        "source_advertiser_id": "1856647522964490",
        "organization_id": "1851650746645060",
        "target_advertiser_id": "1850000000000001",
        "required_material_count": 4,
        "material_type": "video",
        "available_statuses": ["APPROVED"],
    }
    return payload


def _pipeline_request_with_openapi_material_source_preflight(csv_path: Path, snapshot_dir: Path) -> dict:
    payload = _pipeline_request(csv_path, snapshot_dir)
    payload["daily_report_pipeline"]["material_source"] = {
        "kind": "openapi_source_materials",
        "enabled": False,
        "product": "勇者突进",
        "source_accounts": [{"source_advertiser_id": "1856647522964490"}],
        "target_advertiser_id": "1850000000000001",
        "required_material_count": 4,
    }
    return payload


def _discovery_pipeline_request(csv_path: Path, snapshot_dir: Path, fixture_path: Path) -> dict:
    return {
        "daily_report_pipeline": {
            "target_date": {"mode": "yesterday"},
            "active_account_discovery": {
                "enabled": True,
                "min_spend": 0,
                "openapi": {
                    "fixture_responses": str(fixture_path),
                    "page_size": 100,
                },
            },
            "report_fetch": {
                "source": "openapi_mock_execute",
                "account_pool_csv": str(csv_path),
                "product": "勇者突进",
                "platforms": ["WECHAT_GAME"],
                "openapi": {
                    "endpoints": ["report_custom", "operation_log_search"],
                    "report_presets": ["promotion_daily"],
                    "fixture_responses": str(fixture_path),
                    "page_size": 100,
                },
                "output": {"snapshot_dir": str(snapshot_dir)},
                "execution": {"status": "planned_only", "external_api_enabled": False},
            },
            "daily_learning": {
                "min_cost_for_signal": 50,
                "min_conversions_for_signal": 3,
                "low_roi_threshold": 0.4,
                "top_material_limit": 10,
                "operation_log_limit": 20,
            },
        }
    }


def _workbench_discovery_pipeline_request(
    csv_path: Path,
    snapshot_dir: Path,
    fixture_path: Path,
    session_path: Path,
) -> dict:
    payload = _discovery_pipeline_request(csv_path, snapshot_dir, fixture_path)
    payload["daily_report_pipeline"]["active_account_discovery"] = {
        "enabled": True,
        "source": "workbench_account_list",
        "min_spend": 0,
        "workbench": {
            "enabled": True,
            "session_file": str(session_path),
            "keyword": "勇者突进-微小",
            "limit": 100,
            "stop_when_sorted_cost_reaches_zero": True,
            "response_audit_dir": str(session_path.parent / "workbench-audit"),
        },
    }
    return payload


def _write_discovery_fixture(path: Path):
    path.write_text(
        json.dumps(
            {
                "responses": [
                    {
                        "endpoint_key": "report_custom",
                        "report_preset": "account_daily",
                        "advertiser_id": "1858371222574218",
                        "page": 1,
                        "response": {
                            "code": 0,
                            "data": {
                                "rows": [
                                    {
                                        "dimensions": {
                                            "stat_time": "2026-05-06",
                                            "advertiser_id": "1858371222574218",
                                        },
                                        "metrics": {"stat_cost": "86.5", "convert_cnt": "3"},
                                    }
                                ],
                                "page_info": {"page": 1, "total_page": 1},
                            },
                        },
                    },
                    {
                        "endpoint_key": "report_custom",
                        "report_preset": "account_daily",
                        "advertiser_id": "1856647523922953",
                        "page": 1,
                        "response": {
                            "code": 0,
                            "data": {
                                "rows": [
                                    {
                                        "dimensions": {
                                            "stat_time": "2026-05-06",
                                            "advertiser_id": "1856647523922953",
                                        },
                                        "metrics": {"stat_cost": "0", "convert_cnt": "0"},
                                    }
                                ],
                                "page_info": {"page": 1, "total_page": 1},
                            },
                        },
                    },
                    {
                        "endpoint_key": "report_custom",
                        "report_preset": "promotion_daily",
                        "advertiser_id": "1858371222574218",
                        "page": 1,
                        "response": {
                            "code": 0,
                            "data": {
                                "rows": [
                                    {
                                        "dimensions": {
                                            "stat_time": "2026-05-06",
                                            "project_id": "project_active",
                                            "project_name": "0506_勇者突进_项目",
                                            "promotion_id": "promotion_active",
                                            "promotion_name": "0506_勇者突进_单元",
                                        },
                                        "metrics": {"stat_cost": "86.5", "convert_cnt": "3"},
                                    }
                                ],
                                "page_info": {"page": 1, "total_page": 1},
                            },
                        },
                    },
                    {
                        "endpoint_key": "operation_log_search",
                        "advertiser_id": "1858371222574218",
                        "page": 1,
                        "response": {
                            "code": 0,
                            "data": {
                                "logs": [
                                    {
                                        "request_id": "req_active",
                                        "content_title": "修改预算",
                                        "object_type": "广告计划",
                                        "object_id": "promotion_active",
                                        "create_time": "2026-05-06 10:00:00",
                                    }
                                ],
                                "page_info": {"page": 1, "total_page": 1},
                            },
                        },
                    },
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _write_workbench_session(path: Path):
    path.write_text(
        json.dumps(
            {
                "cookie": "sessionid=secret-session",
                "csrf_token": "secret-csrf-token",
                "ebpid": "1851650746645060",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_daily_report_pipeline_fetches_syncs_and_learns_for_yesterday(tmp_path):
    db_path = tmp_path / "roibang.sqlite3"
    csv_path = tmp_path / "accounts.csv"
    snapshot_dir = tmp_path / "snapshots"
    bootstrap_database(db_path)
    _write_accounts_csv(csv_path)

    result = run_daily_report_pipeline_request(
        _pipeline_request(csv_path, snapshot_dir),
        db_path=db_path,
        runs_dir=tmp_path / "runs",
        today=date(2026, 5, 7),
    )

    assert result["ok"] is True
    assert result["workflow"] == "daily_report_pipeline"
    assert result["execution_enabled"] is False
    assert result["external_api_calls"] == 0
    assert result["summary"] == {
        "target_date": "2026-05-06",
        "snapshots_written": 1,
        "snapshots_imported": 1,
        "daily_learning_built": True,
        "external_api_calls": 0,
    }
    assert (snapshot_dir / "2026-05-06.json").exists()
    assert result["steps"]["report_fetch"]["summary"]["date_count"] == 1
    assert result["steps"]["daily_learning"]["summary"]["target_date"] == "2026-05-06"
    assert Path(result["artifact_path"]).exists()


def test_daily_report_pipeline_catches_up_missing_metric_snapshot_dates(tmp_path):
    db_path = tmp_path / "roibang.sqlite3"
    csv_path = tmp_path / "accounts.csv"
    snapshot_dir = tmp_path / "snapshots"
    bootstrap_database(db_path)
    _write_accounts_csv(csv_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO metric_snapshots (
              entity_type, entity_id, metric_date, cost, conversions, roi, payload_json, synced_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("promotion", "old_promotion", "2026-05-03", 10, 1, 0.5, "{}", "2026-05-03T00:00:00+08:00"),
        )

    request = _pipeline_request(csv_path, snapshot_dir)
    request["daily_report_pipeline"]["catch_up"] = {"enabled": True, "max_days": 7}

    result = run_daily_report_pipeline_request(
        request,
        db_path=db_path,
        runs_dir=tmp_path / "runs",
        today=date(2026, 5, 7),
    )

    assert result["ok"] is True
    assert result["summary"]["target_dates"] == ["2026-05-04", "2026-05-05", "2026-05-06"]
    assert result["summary"]["snapshots_written"] == 3
    assert result["summary"]["snapshots_imported"] == 3
    assert (snapshot_dir / "2026-05-04.json").exists()
    assert (snapshot_dir / "2026-05-05.json").exists()
    assert (snapshot_dir / "2026-05-06.json").exists()
    with sqlite3.connect(db_path) as conn:
        latest = conn.execute("SELECT MAX(metric_date) FROM metric_snapshots").fetchone()[0]
    assert latest == "2026-05-06"


def test_daily_report_pipeline_runs_local_material_source_before_learning(tmp_path):
    db_path = tmp_path / "roibang.sqlite3"
    csv_path = tmp_path / "accounts.csv"
    snapshot_dir = tmp_path / "snapshots"
    bootstrap_database(db_path)
    _write_accounts_csv(csv_path)

    result = run_daily_report_pipeline_request(
        _pipeline_request_with_material_source(csv_path, snapshot_dir),
        db_path=db_path,
        runs_dir=tmp_path / "runs",
        today=date(2026, 5, 7),
    )

    assert result["ok"] is True
    assert result["summary"]["material_source_built"] is True
    assert result["steps"]["material_source"]["workflow"] == "material_source"
    assert result["steps"]["material_source"]["plan"]["provision_needed"] == 4
    assert result["steps"]["daily_learning"]["summary"]["target_date"] == "2026-05-06"


def test_daily_report_pipeline_material_source_openapi_disabled_preflights_only(tmp_path):
    db_path = tmp_path / "roibang.sqlite3"
    csv_path = tmp_path / "accounts.csv"
    snapshot_dir = tmp_path / "snapshots"
    bootstrap_database(db_path)
    _write_accounts_csv(csv_path)

    result = run_daily_report_pipeline_request(
        _pipeline_request_with_openapi_material_source_preflight(csv_path, snapshot_dir),
        db_path=db_path,
        runs_dir=tmp_path / "runs",
        today=date(2026, 5, 7),
    )

    assert result["ok"] is True
    assert result["summary"]["material_source_built"] is True
    assert result["external_api_calls"] == 0
    assert result["steps"]["material_source"]["skipped"] is True
    assert result["steps"]["material_source"]["preflight"]["summary"]["planned_request_count"] == 1


def test_daily_report_pipeline_preflight_includes_material_source_plan(tmp_path):
    db_path = tmp_path / "roibang.sqlite3"
    csv_path = tmp_path / "accounts.csv"
    snapshot_dir = tmp_path / "snapshots"
    bootstrap_database(db_path)
    _write_accounts_csv(csv_path)

    result = build_daily_report_pipeline_preflight(
        _pipeline_request_with_openapi_material_source_preflight(csv_path, snapshot_dir),
        db_path=db_path,
        runs_dir=tmp_path / "runs",
        today=date(2026, 5, 7),
    )

    assert result["external_api_calls"] == 0
    assert result["summary"]["material_source_planned_request_count"] == 1
    assert result["material_source_plan"]["summary"]["planned_request_count"] == 1


def test_daily_report_pipeline_discovers_spending_accounts_before_detail_fetch(tmp_path):
    db_path = tmp_path / "roibang.sqlite3"
    csv_path = tmp_path / "accounts.csv"
    snapshot_dir = tmp_path / "snapshots"
    fixture_path = tmp_path / "openapi-responses.json"
    bootstrap_database(db_path)
    _write_accounts_csv(csv_path)
    _write_discovery_fixture(fixture_path)

    result = run_daily_report_pipeline_request(
        _discovery_pipeline_request(csv_path, snapshot_dir, fixture_path),
        db_path=db_path,
        runs_dir=tmp_path / "runs",
        today=date(2026, 5, 7),
    )

    snapshot_payload = json.loads((snapshot_dir / "2026-05-06.json").read_text(encoding="utf-8"))
    assert result["ok"] is True
    assert result["summary"]["active_accounts_discovered"] == 1
    assert result["summary"]["detail_fetch_account_count"] == 1
    assert result["steps"]["active_account_discovery"]["summary"] == {
        "enabled": True,
        "source": "openapi_account_daily",
        "target_date": "2026-05-06",
        "candidate_account_count": 2,
        "active_account_count": 1,
        "min_spend": 0.0,
        "planned_request_count": 2,
        "transport_calls": 2,
        "rows_received": 2,
    }
    assert result["steps"]["report_fetch"]["summary"]["account_count"] == 1
    assert result["steps"]["report_fetch"]["summary"]["transport_calls"] == 2
    assert snapshot_payload["accounts"][0]["advertiser_id"] == "1858371222574218"
    assert result["steps"]["daily_learning"]["summary"]["operation_log_count"] == 1


def test_daily_report_pipeline_can_use_workbench_spend_discovery_before_detail_fetch(tmp_path):
    db_path = tmp_path / "roibang.sqlite3"
    csv_path = tmp_path / "accounts.csv"
    snapshot_dir = tmp_path / "snapshots"
    fixture_path = tmp_path / "openapi-responses.json"
    session_path = tmp_path / "session.json"
    bootstrap_database(db_path)
    _write_accounts_csv(csv_path)
    _write_discovery_fixture(fixture_path)
    _write_workbench_session(session_path)
    workbench_calls = []

    def workbench_opener(_url, body, _headers, _timeout_seconds):
        workbench_calls.append(body)
        return HttpResponse(
            200,
            {
                "code": 0,
                "data": {
                    "list": [
                        {
                            "advertiser_id": "1858371222574218",
                            "advertiser_name": "黑旗-勇者突进-微小-傲星-306",
                            "metrics": {"stat_cost": "1,252.22"},
                        },
                        {
                            "advertiser_id": "1856647523922953",
                            "advertiser_name": "黑旗-勇者突进-微小-傲星-153",
                            "metrics": {"stat_cost": "0.00"},
                        },
                    ],
                    "pagination": {"page": 1, "limit": 100, "total": 2, "hasMore": True},
                },
                "msg": "",
            },
        )

    result = run_daily_report_pipeline_request(
        _workbench_discovery_pipeline_request(csv_path, snapshot_dir, fixture_path, session_path),
        db_path=db_path,
        runs_dir=tmp_path / "runs",
        today=date(2026, 5, 7),
        workbench_opener=workbench_opener,
    )

    assert len(workbench_calls) == 1
    assert result["summary"]["active_accounts_discovered"] == 1
    assert result["summary"]["detail_fetch_account_count"] == 1
    assert result["steps"]["active_account_discovery"]["source"] == "workbench_account_list"
    assert result["steps"]["active_account_discovery"]["summary"]["transport_calls"] == 1
    assert result["steps"]["active_account_discovery"]["summary"]["rows_received"] == 2
    assert result["steps"]["report_fetch"]["summary"]["account_count"] == 1
    assert result["steps"]["report_fetch"]["summary"]["transport_calls"] == 2


def test_daily_report_pipeline_falls_back_to_openapi_discovery_when_workbench_fails(tmp_path):
    db_path = tmp_path / "roibang.sqlite3"
    csv_path = tmp_path / "accounts.csv"
    snapshot_dir = tmp_path / "snapshots"
    fixture_path = tmp_path / "openapi-responses.json"
    session_path = tmp_path / "session.json"
    bootstrap_database(db_path)
    _write_accounts_csv(csv_path)
    _write_discovery_fixture(fixture_path)
    _write_workbench_session(session_path)

    def failing_workbench_opener(_url, _body, _headers, _timeout_seconds):
        return HttpResponse(500, {"code": 50000, "msg": "server error"})

    result = run_daily_report_pipeline_request(
        _workbench_discovery_pipeline_request(csv_path, snapshot_dir, fixture_path, session_path),
        db_path=db_path,
        runs_dir=tmp_path / "runs",
        today=date(2026, 5, 7),
        workbench_opener=failing_workbench_opener,
    )

    discovery = result["steps"]["active_account_discovery"]
    assert result["summary"]["active_accounts_discovered"] == 1
    assert discovery["source"] == "openapi_account_daily"
    assert discovery["summary"]["fallback_used"] is True
    assert "HTTP 500" in discovery["summary"]["fallback_reason"]
    assert discovery["summary"]["transport_calls"] == 2
    assert result["steps"]["report_fetch"]["summary"]["account_count"] == 1


def test_daily_report_pipeline_skips_detail_fetch_when_no_accounts_spent(tmp_path):
    db_path = tmp_path / "roibang.sqlite3"
    csv_path = tmp_path / "accounts.csv"
    snapshot_dir = tmp_path / "snapshots"
    fixture_path = tmp_path / "openapi-responses.json"
    bootstrap_database(db_path)
    _write_accounts_csv(csv_path)
    _write_discovery_fixture(fixture_path)
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    for item in payload["responses"]:
        if item["endpoint_key"] == "report_custom" and item.get("report_preset") == "account_daily":
            item["response"]["data"]["rows"][0]["metrics"]["stat_cost"] = "0"
    fixture_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    result = run_daily_report_pipeline_request(
        _discovery_pipeline_request(csv_path, snapshot_dir, fixture_path),
        db_path=db_path,
        runs_dir=tmp_path / "runs",
        today=date(2026, 5, 7),
    )

    assert result["ok"] is True
    assert result["summary"]["active_accounts_discovered"] == 0
    assert result["summary"]["detail_fetch_account_count"] == 0
    assert result["summary"]["snapshots_written"] == 0
    assert result["summary"]["daily_learning_built"] is False
    assert result["steps"]["report_fetch"]["skipped"] is True
    assert not (snapshot_dir / "2026-05-06.json").exists()


def test_daily_report_pipeline_cli_rejects_http_source_without_runtime_gate(tmp_path):
    db_path = tmp_path / "roibang.sqlite3"
    request_path = tmp_path / "pipeline.json"
    bootstrap_database(db_path)
    payload = _pipeline_request(tmp_path / "accounts.csv", tmp_path / "snapshots")
    payload["daily_report_pipeline"]["report_fetch"]["source"] = "openapi_http_execute"
    payload["daily_report_pipeline"]["report_fetch"]["execution"] = {"status": "execute", "external_api_enabled": True}
    payload["daily_report_pipeline"]["report_fetch"]["openapi_http"] = {"enabled": True, "token_env": "ROIBANG_TEST_ACCESS_TOKEN"}
    request_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    module = _load_pipeline_script()

    try:
        module.run_from_args(["--request", str(request_path), "--db", str(db_path), "--runs-dir", str(tmp_path / "runs")])
    except RuntimeError as exc:
        assert "runtime external_api_enabled=true" in str(exc)
    else:
        raise AssertionError("HTTP pipeline should require runtime external API gate")


def test_daily_report_pipeline_cli_rejects_disabled_http_template_without_preflight(tmp_path):
    db_path = tmp_path / "roibang.sqlite3"
    module = _load_pipeline_script()
    bootstrap_database(db_path)

    try:
        module.run_from_args(
            [
                "--config",
                "configs/runtime.example.json",
                "--request",
                "configs/daily-report-pipeline.openapi-http.single-account.disabled.example.json",
                "--db",
                str(db_path),
                "--runs-dir",
                str(tmp_path / "runs"),
            ]
        )
    except RuntimeError as exc:
        assert "runtime external_api_enabled=true" in str(exc)
    else:
        raise AssertionError("disabled HTTP template should fail closed without --preflight")


def test_daily_report_pipeline_cli_preflight_writes_plan_without_external_api_calls(tmp_path, capsys):
    db_path = tmp_path / "roibang.sqlite3"
    runs_dir = tmp_path / "runs"
    module = _load_pipeline_script()
    bootstrap_database(db_path)

    exit_code = module.run_from_args(
        [
            "--preflight",
            "--config",
            "configs/runtime.example.json",
            "--request",
            "configs/daily-report-pipeline.openapi-http.single-account.disabled.example.json",
            "--db",
            str(db_path),
            "--runs-dir",
            str(runs_dir),
        ]
    )

    captured = capsys.readouterr()
    output = json.loads(captured.out)
    artifact = json.loads(Path(output["artifact_path"]).read_text(encoding="utf-8"))
    assert exit_code == 0
    assert output["workflow"] == "daily_report_pipeline_preflight"
    assert output["execution_enabled"] is False
    assert output["external_api_calls"] == 0
    assert output["summary"]["candidate_account_count"] == 1
    assert output["summary"]["discovery_planned_request_count"] == 1
    assert output["summary"]["detail_worst_case_account_count"] == 1
    assert output["summary"]["detail_worst_case_initial_request_count"] == 2
    assert output["summary"]["estimated_total_initial_request_count"] == 3
    assert artifact["detail_plan"]["endpoints"] == ["report_custom", "operation_log_search"]
    assert artifact["detail_plan"]["report_presets"] == ["promotion_daily"]
