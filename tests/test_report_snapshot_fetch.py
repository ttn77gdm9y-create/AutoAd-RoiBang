import importlib.util
import json
from pathlib import Path

from roibang_v2.db.bootstrap import bootstrap_database
from roibang_v2.fetch.openapi_http import HttpResponse
from roibang_v2.fetch.report_snapshot import run_report_fetch_request
from roibang_v2.reports.snapshot import import_report_snapshot_file
from roibang_v2.workflows.daily_learning import build_daily_learning_artifact


def _load_fetch_script():
    script_path = Path("scripts/fetch_report_snapshot.py")
    spec = importlib.util.spec_from_file_location("fetch_report_snapshot", script_path)
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
                "黑旗-其他产品-微小-傲星-001,1850000000000003,12.5,其他产品,WECHAT_GAME",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def _request(csv_path: Path, snapshot_dir: Path) -> dict:
    return {
        "report_fetch": {
            "mode": "backfill",
            "source": "mock_openapi",
            "account_pool_csv": str(csv_path),
            "product": "勇者突进",
            "platforms": ["WECHAT_GAME"],
            "date_range": {"start": "2026-02-10", "end": "2026-02-11"},
            "output": {"snapshot_dir": str(snapshot_dir)},
            "limits": {"max_accounts": 1, "max_dates": 2},
            "execution": {"status": "planned_only", "external_api_enabled": False},
        }
    }


def test_mock_report_fetch_writes_daily_snapshot_files(tmp_path):
    db_path = tmp_path / "roibang.sqlite3"
    csv_path = tmp_path / "accounts.csv"
    snapshot_dir = tmp_path / "snapshots"
    bootstrap_database(db_path)
    _write_accounts_csv(csv_path)

    result = run_report_fetch_request(
        _request(csv_path, snapshot_dir),
        db_path=db_path,
        runs_dir=tmp_path / "runs",
    )

    first_snapshot = snapshot_dir / "2026-02-10.json"
    second_snapshot = snapshot_dir / "2026-02-11.json"
    payload = json.loads(first_snapshot.read_text(encoding="utf-8"))
    assert result["ok"] is True
    assert result["workflow"] == "report_fetch"
    assert result["execution_enabled"] is False
    assert result["external_api_calls"] == 0
    assert result["summary"] == {
        "mode": "backfill",
        "source": "mock_openapi",
        "product": "勇者突进",
        "platforms": ["WECHAT_GAME"],
        "account_count": 1,
        "date_count": 2,
        "snapshots_written": 2,
    }
    assert first_snapshot.exists()
    assert second_snapshot.exists()
    assert payload["period"] == {"start": "2026-02-10", "end": "2026-02-10"}
    assert payload["accounts"][0]["advertiser_id"] == "1858371222574218"
    assert payload["accounts"][0]["projects"][0]["project_name"].startswith("0210_勇者突进")
    assert payload["accounts"][0]["promotion_metrics"][0]["stat_cost"] > 0
    assert payload["accounts"][0]["operation_logs"][0]["entity_type"] == "account"
    assert Path(result["artifact_path"]).exists()


def test_mock_report_snapshot_can_feed_data_sync_and_daily_learning(tmp_path):
    db_path = tmp_path / "roibang.sqlite3"
    csv_path = tmp_path / "accounts.csv"
    snapshot_dir = tmp_path / "snapshots"
    bootstrap_database(db_path)
    _write_accounts_csv(csv_path)
    result = run_report_fetch_request(
        _request(csv_path, snapshot_dir),
        db_path=db_path,
        runs_dir=tmp_path / "runs",
    )

    imported = import_report_snapshot_file(result["snapshots"][0]["path"], db_path=db_path)
    artifact = build_daily_learning_artifact(
        db_path=db_path,
        policy={
            "target_date": "2026-02-10",
            "min_cost_for_signal": 50,
            "min_conversions_for_signal": 3,
            "low_roi_threshold": 0.4,
            "top_material_limit": 5,
        },
    )

    assert imported["promotion_metrics_imported"] == 1
    assert imported["operation_logs_imported"] == 1
    assert artifact["summary"]["promotion_metric_count"] == 1
    assert artifact["summary"]["operation_log_count"] == 1
    assert artifact["operation_log_summary"]["by_entity_type"] == {"account": 1}


def test_fetch_report_snapshot_cli_prints_summary_without_full_snapshot(tmp_path, capsys):
    db_path = tmp_path / "roibang.sqlite3"
    csv_path = tmp_path / "accounts.csv"
    snapshot_dir = tmp_path / "snapshots"
    request_path = tmp_path / "request.json"
    bootstrap_database(db_path)
    _write_accounts_csv(csv_path)
    request_path.write_text(json.dumps(_request(csv_path, snapshot_dir), ensure_ascii=False), encoding="utf-8")
    module = _load_fetch_script()

    exit_code = module.fetch_from_args(
        [
            "--request",
            str(request_path),
            "--db",
            str(db_path),
            "--runs-dir",
            str(tmp_path / "runs"),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert '"snapshots_written": 2' in captured.out
    assert '"external_api_calls": 0' in captured.out
    assert '"accounts":' not in captured.out


def test_fetch_report_snapshot_cli_rejects_http_execute_without_runtime_external_gate(tmp_path):
    db_path = tmp_path / "roibang.sqlite3"
    csv_path = tmp_path / "accounts.csv"
    snapshot_dir = tmp_path / "snapshots"
    request_path = tmp_path / "request.json"
    bootstrap_database(db_path)
    _write_accounts_csv(csv_path)
    request_path.write_text(
        json.dumps(_http_execute_request(csv_path, snapshot_dir, tmp_path / "audit"), ensure_ascii=False),
        encoding="utf-8",
    )
    module = _load_fetch_script()

    try:
        module.fetch_from_args(
            [
                "--request",
                str(request_path),
                "--db",
                str(db_path),
                "--runs-dir",
                str(tmp_path / "runs"),
            ]
        )
    except RuntimeError as exc:
        assert "runtime external_api_enabled=true" in str(exc)
    else:
        raise AssertionError("CLI should reject real HTTP source unless runtime gate is enabled")


def test_openapi_readonly_fetch_writes_request_plan_only(tmp_path):
    db_path = tmp_path / "roibang.sqlite3"
    csv_path = tmp_path / "accounts.csv"
    snapshot_dir = tmp_path / "snapshots"
    bootstrap_database(db_path)
    _write_accounts_csv(csv_path)
    request = _request(csv_path, snapshot_dir)
    request["report_fetch"]["source"] = "openapi_readonly"
    request["report_fetch"]["openapi"] = {
        "endpoints": ["report_custom_config", "report_custom", "project_list"],
        "report_presets": ["promotion_daily"],
        "page_size": 100,
    }

    result = run_report_fetch_request(
        request,
        db_path=db_path,
        runs_dir=tmp_path / "runs",
    )

    assert result["ok"] is True
    assert result["source"] == "openapi_readonly"
    assert result["execution_enabled"] is False
    assert result["external_api_calls"] == 0
    assert result["summary"]["snapshots_written"] == 0
    assert result["summary"]["planned_request_count"] == 6
    assert result["snapshots"] == []
    assert result["request_plan"]["summary"]["planned_request_count"] == 6
    assert Path(result["artifact_path"]).exists()


def test_openapi_readonly_requires_planned_only_and_external_api_disabled(tmp_path):
    db_path = tmp_path / "roibang.sqlite3"
    csv_path = tmp_path / "accounts.csv"
    bootstrap_database(db_path)
    _write_accounts_csv(csv_path)
    request = _request(csv_path, tmp_path / "snapshots")
    request["report_fetch"]["source"] = "openapi_readonly"
    request["report_fetch"]["execution"] = {"status": "execute", "external_api_enabled": False}

    try:
        run_report_fetch_request(request, db_path=db_path, runs_dir=tmp_path / "runs")
    except RuntimeError as exc:
        assert "planned_only" in str(exc)
    else:
        raise AssertionError("openapi_readonly execute mode should be rejected")


def test_openapi_mock_execute_writes_snapshot_from_fixture_transport(tmp_path):
    db_path = tmp_path / "roibang.sqlite3"
    csv_path = tmp_path / "accounts.csv"
    snapshot_dir = tmp_path / "snapshots"
    fixture_path = tmp_path / "openapi-responses.json"
    bootstrap_database(db_path)
    _write_accounts_csv(csv_path)
    fixture_path.write_text(
        json.dumps(
            {
                "responses": [
                    {
                        "endpoint_key": "report_custom",
                        "report_preset": "promotion_daily",
                        "page": 1,
                        "response": {
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
                                        "metrics": {"stat_cost": "321.5", "convert_cnt": "9"},
                                    }
                                ],
                                "page_info": {"page": 1, "total_page": 1},
                            },
                        },
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    request = _request(csv_path, snapshot_dir)
    request["report_fetch"]["source"] = "openapi_mock_execute"
    request["report_fetch"]["date_range"] = {"start": "2026-02-10", "end": "2026-02-10"}
    request["report_fetch"]["openapi"] = {
        "endpoints": ["report_custom"],
        "report_presets": ["promotion_daily"],
        "fixture_responses": str(fixture_path),
        "page_size": 100,
    }

    result = run_report_fetch_request(
        request,
        db_path=db_path,
        runs_dir=tmp_path / "runs",
    )

    snapshot_path = snapshot_dir / "2026-02-10.json"
    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    assert result["ok"] is True
    assert result["source"] == "openapi_mock_execute"
    assert result["external_api_calls"] == 0
    assert result["summary"]["transport_calls"] == 1
    assert result["summary"]["snapshots_written"] == 1
    assert result["snapshots"] == [{"date": "2026-02-10", "path": str(snapshot_path), "account_count": 1}]
    assert payload["accounts"][0]["promotion_metrics"] == [
        {"promotion_id": "promotion_1", "stat_cost": 321.5, "convert_cnt": 9}
    ]


def test_openapi_mock_execute_imports_promotion_list_material_bindings(tmp_path):
    db_path = tmp_path / "roibang.sqlite3"
    csv_path = tmp_path / "accounts.csv"
    snapshot_dir = tmp_path / "snapshots"
    fixture_path = tmp_path / "openapi-responses.json"
    bootstrap_database(db_path)
    _write_accounts_csv(csv_path)
    fixture_path.write_text(
        json.dumps(
            {
                "responses": [
                    {
                        "endpoint_key": "promotion_list",
                        "page": 1,
                        "response": {
                            "code": 0,
                            "data": {
                                "list": [
                                    {
                                        "project_id": "project_1",
                                        "project_name": "0210_勇者突进_项目",
                                        "promotion_id": "promotion_1",
                                        "promotion_name": "0210_勇者突进_单元",
                                        "promotion_materials": {
                                            "video_material_list": [
                                                {
                                                    "material_id": "7446393925521424395",
                                                    "video_id": "v-source-1",
                                                    "title": "勇者视频 A",
                                                }
                                            ]
                                        },
                                    }
                                ],
                                "page_info": {"page": 1, "total_page": 1},
                            },
                        },
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    request = _request(csv_path, snapshot_dir)
    request["report_fetch"]["source"] = "openapi_mock_execute"
    request["report_fetch"]["date_range"] = {"start": "2026-02-10", "end": "2026-02-10"}
    request["report_fetch"]["openapi"] = {
        "endpoints": ["promotion_list"],
        "report_presets": ["promotion_daily"],
        "fixture_responses": str(fixture_path),
        "page_size": 20,
    }

    result = run_report_fetch_request(
        request,
        db_path=db_path,
        runs_dir=tmp_path / "runs",
    )
    imported = import_report_snapshot_file(result["snapshots"][0]["path"], db_path=db_path)

    assert result["ok"] is True
    assert imported["promotions_imported"] == 1
    assert imported["material_bindings_imported"] == 1
    assert imported["material_summary_count"] == 1


def _http_execute_request(csv_path: Path, snapshot_dir: Path, audit_dir: Path) -> dict:
    request = _request(csv_path, snapshot_dir)
    request["report_fetch"]["source"] = "openapi_http_execute"
    request["report_fetch"]["date_range"] = {"start": "2026-02-10", "end": "2026-02-10"}
    request["report_fetch"]["openapi"] = {
        "endpoints": ["report_custom"],
        "report_presets": ["promotion_daily"],
        "page_size": 100,
    }
    request["report_fetch"]["openapi_http"] = {
        "enabled": True,
        "token_env": "ROIBANG_TEST_ACCESS_TOKEN",
        "timeout_seconds": 9,
        "max_retries": 0,
        "response_audit_dir": str(audit_dir),
    }
    request["report_fetch"]["execution"] = {"status": "execute", "external_api_enabled": True}
    return request


def test_openapi_http_execute_requires_explicit_external_api_gate(tmp_path):
    db_path = tmp_path / "roibang.sqlite3"
    csv_path = tmp_path / "accounts.csv"
    bootstrap_database(db_path)
    _write_accounts_csv(csv_path)
    request = _http_execute_request(csv_path, tmp_path / "snapshots", tmp_path / "audit")
    request["report_fetch"]["execution"] = {"status": "execute", "external_api_enabled": False}

    try:
        run_report_fetch_request(request, db_path=db_path, runs_dir=tmp_path / "runs")
    except RuntimeError as exc:
        assert "external_api_enabled=true" in str(exc)
    else:
        raise AssertionError("openapi_http_execute should require external_api_enabled=true")


def test_openapi_http_execute_writes_snapshot_with_injected_opener(monkeypatch, tmp_path):
    db_path = tmp_path / "roibang.sqlite3"
    csv_path = tmp_path / "accounts.csv"
    snapshot_dir = tmp_path / "snapshots"
    audit_dir = tmp_path / "audit"
    bootstrap_database(db_path)
    _write_accounts_csv(csv_path)
    monkeypatch.setenv("ROIBANG_TEST_ACCESS_TOKEN", "secret-token")

    def fake_opener(_url, _query_params, _headers, _timeout_seconds):
        return HttpResponse(
            200,
            {
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
                            "metrics": {"stat_cost": "321.5", "convert_cnt": "9"},
                        }
                    ],
                    "page_info": {"page": 1, "total_page": 1},
                },
            },
        )

    result = run_report_fetch_request(
        _http_execute_request(csv_path, snapshot_dir, audit_dir),
        db_path=db_path,
        runs_dir=tmp_path / "runs",
        http_opener=fake_opener,
    )

    snapshot_path = snapshot_dir / "2026-02-10.json"
    audit_text = (audit_dir / "http_responses.jsonl").read_text(encoding="utf-8")
    assert result["ok"] is True
    assert result["source"] == "openapi_http_execute"
    assert result["external_api_calls"] == 1
    assert result["execution_enabled"] is False
    assert result["summary"]["transport_calls"] == 1
    assert result["summary"]["snapshots_written"] == 1
    assert snapshot_path.exists()
    assert "secret-token" not in audit_text


def test_openapi_http_execute_retries_configured_api_code(monkeypatch, tmp_path):
    db_path = tmp_path / "roibang.sqlite3"
    csv_path = tmp_path / "accounts.csv"
    snapshot_dir = tmp_path / "snapshots"
    audit_dir = tmp_path / "audit"
    bootstrap_database(db_path)
    _write_accounts_csv(csv_path)
    monkeypatch.setenv("ROIBANG_TEST_ACCESS_TOKEN", "secret-token")
    calls = {"count": 0}
    sleeps: list[float] = []

    def fake_opener(_url, _query_params, _headers, _timeout_seconds):
        calls["count"] += 1
        if calls["count"] == 1:
            return HttpResponse(200, {"code": 40100, "message": "系统请求频率超限，请稍后重试"})
        return HttpResponse(
            200,
            {
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
                            "metrics": {"stat_cost": "321.5", "convert_cnt": "9"},
                        }
                    ],
                    "page_info": {"page": 1, "total_page": 1},
                },
            },
        )

    request = _http_execute_request(csv_path, snapshot_dir, audit_dir)
    request["report_fetch"]["openapi_http"]["retry_api_codes"] = [40100]
    request["report_fetch"]["openapi_http"]["max_api_retries"] = 1
    request["report_fetch"]["openapi_http"]["retry_sleep_seconds"] = 7

    result = run_report_fetch_request(
        request,
        db_path=db_path,
        runs_dir=tmp_path / "runs",
        http_opener=fake_opener,
        http_sleeper=sleeps.append,
    )

    assert result["ok"] is True
    assert result["summary"]["transport_calls"] == 2
    assert result["external_api_calls"] == 2
    assert result["summary"]["rows_received"] == 1
    assert calls["count"] == 2
    assert sleeps == [7]
