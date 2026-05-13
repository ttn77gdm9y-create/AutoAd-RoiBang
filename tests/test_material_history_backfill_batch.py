import importlib.util
import json
import sqlite3
from pathlib import Path

from roibang_v2.accounts.pool import import_accounts_csv
from roibang_v2.db.bootstrap import bootstrap_database
from roibang_v2.fetch.openapi_http import HttpResponse
from roibang_v2.workflows.material_history_backfill_batch import build_material_history_backfill_batch_preflight
from roibang_v2.workflows.material_history_backfill_batch import run_material_history_backfill_batch_request


def _write_accounts_csv(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "account_name,advertiser_id,消耗,product,platform",
                "黑旗-勇者突进-微小-傲星-306,1858371222574218,\"570,011.13\",勇者突进,WECHAT_GAME",
                "黑旗-勇者突进-微小-傲星-322,1858371234830346,\"120,001.00\",勇者突进,WECHAT_GAME",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def _request(csv_path: Path) -> dict:
    return {
        "material_history_backfill_batch": {
            "batch": {"size": 2, "retry_failed": False},
            "material_history_backfill": {
                "account_pool_csv": str(csv_path),
                "product": "勇者突进",
                "platforms": ["WECHAT_GAME"],
                "date_range": {"start": "2026-02-10", "end": "2026-02-14"},
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
                    "openapi_http": {"enabled": False},
                    "execution": {"status": "planned_only", "external_api_enabled": False},
                },
            },
        }
    }


def _record_state(
    db_path: Path,
    *,
    sync_date: str,
    status: str,
    product: str = "勇者突进",
    platform: str = "WECHAT_GAME",
    workflow: str = "material_history_backfill",
) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO material_sync_state (
              workflow, sync_date, status, product, platform, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (workflow, sync_date, status, product, platform, "2026-05-07T00:00:00+00:00"),
        )


def test_material_history_backfill_batch_preflight_skips_completed_and_failed_by_default(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    csv_path = tmp_path / "accounts.csv"
    bootstrap_database(db_path)
    _write_accounts_csv(csv_path)
    import_accounts_csv(csv_path, db_path=db_path)
    _record_state(db_path, sync_date="2026-02-10", status="completed")
    _record_state(db_path, sync_date="2026-02-11", status="failed")

    result = build_material_history_backfill_batch_preflight(
        _request(csv_path),
        db_path=db_path,
        runs_dir=tmp_path / "runs",
    )

    assert result["ok"] is True
    assert result["workflow"] == "material_history_backfill_batch_preflight"
    assert result["execution_enabled"] is False
    assert result["external_api_calls"] == 0
    assert result["summary"] == {
        "product": "勇者突进",
        "platforms": ["WECHAT_GAME"],
        "date_count": 5,
        "completed_date_count": 1,
        "failed_date_count": 1,
        "pending_date_count": 3,
        "selected_date_count": 2,
        "candidate_account_count": 2,
        "estimated_discovery_request_count": 2,
        "estimated_material_detail_initial_request_count": 4,
        "estimated_total_initial_request_count": 6,
    }
    assert result["skipped_dates"]["completed"] == ["2026-02-10"]
    assert result["skipped_dates"]["failed"] == ["2026-02-11"]
    assert result["selected_dates"] == ["2026-02-12", "2026-02-13"]
    assert result["remaining_dates"] == ["2026-02-14"]
    assert Path(result["artifact_path"]).exists()


def test_material_history_backfill_batch_preflight_supports_yesterday_mode(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    csv_path = tmp_path / "accounts.csv"
    bootstrap_database(db_path)
    _write_accounts_csv(csv_path)
    import_accounts_csv(csv_path, db_path=db_path)
    request = _request(csv_path)
    request["material_history_backfill_batch"]["material_history_backfill"]["date_range"] = {
        "mode": "yesterday",
        "base_date": "2026-05-11",
    }

    result = build_material_history_backfill_batch_preflight(
        request,
        db_path=db_path,
        runs_dir=tmp_path / "runs",
    )

    assert result["ok"] is True
    assert result["selected_dates"] == ["2026-05-10"]
    assert result["remaining_dates"] == []
    assert result["summary"]["date_count"] == 1


def test_material_history_backfill_batch_preflight_can_retry_failed_dates(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    csv_path = tmp_path / "accounts.csv"
    bootstrap_database(db_path)
    _write_accounts_csv(csv_path)
    request = _request(csv_path)
    request["material_history_backfill_batch"]["batch"] = {"size": 2, "retry_failed": True}
    _record_state(db_path, sync_date="2026-02-10", status="completed")
    _record_state(db_path, sync_date="2026-02-11", status="failed")

    result = build_material_history_backfill_batch_preflight(
        request,
        db_path=db_path,
        runs_dir=tmp_path / "runs",
    )

    assert result["selected_dates"] == ["2026-02-11", "2026-02-12"]
    assert result["skipped_dates"]["failed"] == []
    assert result["retry_dates"] == ["2026-02-11"]


def test_material_history_backfill_batch_preflight_can_rerun_completed_dates(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    csv_path = tmp_path / "accounts.csv"
    bootstrap_database(db_path)
    _write_accounts_csv(csv_path)
    request = _request(csv_path)
    request["material_history_backfill_batch"]["batch"] = {
        "size": 2,
        "retry_failed": False,
        "rerun_completed": True,
    }
    _record_state(db_path, sync_date="2026-02-10", status="completed")
    _record_state(db_path, sync_date="2026-02-11", status="failed")

    result = build_material_history_backfill_batch_preflight(
        request,
        db_path=db_path,
        runs_dir=tmp_path / "runs",
    )

    assert result["selected_dates"] == ["2026-02-10", "2026-02-12"]
    assert result["skipped_dates"]["completed"] == []
    assert result["skipped_dates"]["failed"] == ["2026-02-11"]
    assert result["rerun_completed_dates"] == ["2026-02-10"]


def test_material_history_backfill_batch_preflight_skips_completed_dates_already_rerun_for_key(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    csv_path = tmp_path / "accounts.csv"
    bootstrap_database(db_path)
    _write_accounts_csv(csv_path)
    request = _request(csv_path)
    request["material_history_backfill_batch"]["batch"] = {
        "size": 2,
        "retry_failed": False,
        "rerun_completed": True,
        "rerun_key": "roi_1day_test",
    }
    _record_state(db_path, sync_date="2026-02-10", status="completed")
    _record_state(
        db_path,
        sync_date="2026-02-10",
        status="completed",
        workflow="material_history_backfill_rerun:roi_1day_test",
    )

    result = build_material_history_backfill_batch_preflight(
        request,
        db_path=db_path,
        runs_dir=tmp_path / "runs",
    )

    assert result["selected_dates"] == ["2026-02-11", "2026-02-12"]
    assert result["skipped_dates"]["completed"] == ["2026-02-10"]
    assert result["rerun_completed_dates"] == []


def test_material_history_backfill_batch_preflight_cli_writes_summary(tmp_path: Path, capsys):
    db_path = tmp_path / "roibang.sqlite3"
    csv_path = tmp_path / "accounts.csv"
    request_path = tmp_path / "batch-request.json"
    runtime_path = tmp_path / "runtime.json"
    bootstrap_database(db_path)
    _write_accounts_csv(csv_path)
    request_path.write_text(json.dumps(_request(csv_path), ensure_ascii=False), encoding="utf-8")
    runtime_path.write_text(
        json.dumps(
            {
                "environment": "test",
                "phase": "phase1",
                "database_path": str(db_path),
                "runs_dir": str(tmp_path / "runs"),
                "fixtures_dir": str(tmp_path / "fixtures"),
                "external_api_enabled": False,
                "execution_enabled": False,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    script_path = Path("scripts/run_material_history_backfill_batch.py")
    spec = importlib.util.spec_from_file_location("run_material_history_backfill_batch", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)

    exit_code = module.run_from_args(
        [
            "--config",
            str(runtime_path),
            "--request",
            str(request_path),
            "--preflight",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert '"workflow": "material_history_backfill_batch_preflight"' in captured.out
    assert '"external_api_calls": 0' in captured.out
    assert '"selected_dates": [' in captured.out


def test_material_history_backfill_batch_cli_max_dates_caps_selected_dates_without_editing_request(
    tmp_path: Path,
    capsys,
):
    db_path = tmp_path / "roibang.sqlite3"
    csv_path = tmp_path / "accounts.csv"
    request_path = tmp_path / "batch-request.json"
    runtime_path = tmp_path / "runtime.json"
    bootstrap_database(db_path)
    _write_accounts_csv(csv_path)
    request = _request(csv_path)
    request["material_history_backfill_batch"]["batch"] = {"size": 2, "retry_failed": False}
    request_path.write_text(json.dumps(request, ensure_ascii=False), encoding="utf-8")
    runtime_path.write_text(
        json.dumps(
            {
                "environment": "test",
                "phase": "phase1",
                "database_path": str(db_path),
                "runs_dir": str(tmp_path / "runs"),
                "fixtures_dir": str(tmp_path / "fixtures"),
                "external_api_enabled": False,
                "execution_enabled": False,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    script_path = Path("scripts/run_material_history_backfill_batch.py")
    spec = importlib.util.spec_from_file_location("run_material_history_backfill_batch", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)

    exit_code = module.run_from_args(
        [
            "--config",
            str(runtime_path),
            "--request",
            str(request_path),
            "--preflight",
            "--max-dates",
            "1",
        ]
    )

    captured = capsys.readouterr()
    original_request = json.loads(request_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert '"selected_date_count": 1' in captured.out
    assert '"selected_dates": [\n    "2026-02-10"\n  ]' in captured.out
    assert original_request["material_history_backfill_batch"]["batch"]["size"] == 2


def test_material_history_backfill_batch_cli_can_temporarily_retry_failed_dates(
    tmp_path: Path,
    capsys,
):
    db_path = tmp_path / "roibang.sqlite3"
    csv_path = tmp_path / "accounts.csv"
    request_path = tmp_path / "batch-request.json"
    runtime_path = tmp_path / "runtime.json"
    bootstrap_database(db_path)
    _write_accounts_csv(csv_path)
    _record_state(db_path, sync_date="2026-02-10", status="failed")
    request = _request(csv_path)
    request["material_history_backfill_batch"]["batch"] = {"size": 2, "retry_failed": False}
    request_path.write_text(json.dumps(request, ensure_ascii=False), encoding="utf-8")
    runtime_path.write_text(
        json.dumps(
            {
                "environment": "test",
                "phase": "phase1",
                "database_path": str(db_path),
                "runs_dir": str(tmp_path / "runs"),
                "fixtures_dir": str(tmp_path / "fixtures"),
                "external_api_enabled": False,
                "execution_enabled": False,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    script_path = Path("scripts/run_material_history_backfill_batch.py")
    spec = importlib.util.spec_from_file_location("run_material_history_backfill_batch", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)

    exit_code = module.run_from_args(
        [
            "--config",
            str(runtime_path),
            "--request",
            str(request_path),
            "--preflight",
            "--max-dates",
            "1",
            "--retry-failed",
        ]
    )

    captured = capsys.readouterr()
    original_request = json.loads(request_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert '"selected_dates": [\n    "2026-02-10"\n  ]' in captured.out
    assert original_request["material_history_backfill_batch"]["batch"]["retry_failed"] is False


def test_material_history_backfill_batch_cli_can_temporarily_enable_readonly(
    tmp_path: Path,
    capsys,
):
    db_path = tmp_path / "roibang.sqlite3"
    csv_path = tmp_path / "accounts.csv"
    session_path = tmp_path / "workbench-session.json"
    request_path = tmp_path / "batch-request.json"
    runtime_path = tmp_path / "runtime.json"
    bootstrap_database(db_path)
    _write_accounts_csv(csv_path)
    session_path.write_text(
        json.dumps({"cookie": "fake_cookie", "csrf_token": "fake_csrf", "ebpid": "fake_ebpid"}),
        encoding="utf-8",
    )
    request = _request(csv_path)
    request["material_history_backfill_batch"]["batch"] = {"size": 1, "retry_failed": False}
    cfg = request["material_history_backfill_batch"]["material_history_backfill"]
    cfg["date_range"] = {"start": "2026-02-10", "end": "2026-02-11"}
    cfg["active_account_discovery"]["workbench"] = {
        "enabled": False,
        "session_file": str(session_path),
        "limit": 100,
        "stop_when_sorted_cost_reaches_zero": True,
    }
    cfg["material_fetch"]["openapi_http"]["enabled"] = False
    cfg["material_fetch"]["execution"] = {"status": "planned_only", "external_api_enabled": False}
    request_path.write_text(json.dumps(request, ensure_ascii=False), encoding="utf-8")
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

    script_path = Path("scripts/run_material_history_backfill_batch.py")
    spec = importlib.util.spec_from_file_location("run_material_history_backfill_batch", script_path)
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

    def openapi_transport(api_request):
        return {
            "code": 0,
            "data": {
                "page_info": {"page": 1, "page_size": 20, "total_page": 1, "total_count": 1},
                "rows": [
                    {
                        "dimensions": {
                            "stat_time_day": api_request["date"],
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
            "--enable-readonly",
        ],
        workbench_opener=workbench_opener,
        workbench_sleeper=lambda seconds: None,
        openapi_transport=openapi_transport,
    )

    captured = capsys.readouterr()
    original_request = json.loads(request_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert '"workflow": "material_history_backfill_batch"' in captured.out
    assert '"completed_date_count": 1' in captured.out
    assert original_request["material_history_backfill_batch"]["material_history_backfill"]["material_fetch"]["openapi_http"]["enabled"] is False


def test_material_history_backfill_batch_execution_runs_selected_dates_and_records_failures(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    csv_path = tmp_path / "accounts.csv"
    session_path = tmp_path / "workbench-session.json"
    bootstrap_database(db_path)
    _write_accounts_csv(csv_path)
    session_path.write_text(
        json.dumps({"cookie": "fake_cookie", "csrf_token": "fake_csrf", "ebpid": "fake_ebpid"}),
        encoding="utf-8",
    )
    request = _request(csv_path)
    request["material_history_backfill_batch"]["batch"] = {"size": 2, "retry_failed": False}
    cfg = request["material_history_backfill_batch"]["material_history_backfill"]
    cfg["date_range"] = {"start": "2026-02-10", "end": "2026-02-12"}
    cfg["active_account_discovery"]["workbench"] = {
        "enabled": True,
        "session_file": str(session_path),
        "limit": 100,
        "stop_when_sorted_cost_reaches_zero": True,
    }
    cfg["material_fetch"]["openapi_http"]["enabled"] = True
    cfg["material_fetch"]["execution"] = {"status": "execute", "external_api_enabled": True}

    def workbench_opener(_url, body, _headers, _timeout_seconds):
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
                        }
                    ],
                    "pagination": {"page": 1, "limit": 100, "total": 1, "hasMore": False},
                },
            },
        )

    def openapi_transport(api_request):
        if api_request["date"] == "2026-02-11":
            raise RuntimeError("temporary openapi failure")
        return {
            "code": 0,
            "data": {
                "page_info": {"page": 1, "page_size": 20, "total_page": 1, "total_count": 1},
                "rows": [
                    {
                        "dimensions": {
                            "stat_time_day": api_request["date"],
                            "cdp_project_id": "project_1",
                            "cdp_promotion_id": "promotion_1",
                            "material_id": f"material_{api_request['date']}",
                        },
                        "metrics": {"stat_cost": "88.00"},
                    }
                ],
            },
        }

    result = run_material_history_backfill_batch_request(
        request,
        db_path=db_path,
        runs_dir=tmp_path / "runs",
        workbench_opener=workbench_opener,
        workbench_sleeper=lambda seconds: None,
        openapi_transport=openapi_transport,
    )

    assert result["ok"] is False
    assert result["workflow"] == "material_history_backfill_batch"
    assert result["selected_dates"] == ["2026-02-10", "2026-02-11"]
    assert result["summary"]["completed_date_count"] == 1
    assert result["summary"]["failed_date_count"] == 1
    assert result["summary"]["remaining_date_count"] == 1
    assert result["executions"][0]["date"] == "2026-02-10"
    assert result["executions"][0]["ok"] is True
    assert result["executions"][1]["date"] == "2026-02-11"
    assert result["executions"][1]["ok"] is False
    with sqlite3.connect(db_path) as conn:
        state_rows = conn.execute(
            """
            SELECT sync_date, status, material_row_count, error_message
            FROM material_sync_state
            ORDER BY sync_date
            """
        ).fetchall()
        metric_rows = conn.execute(
            "SELECT metric_date, material_id, stat_cost FROM material_daily_metrics"
        ).fetchall()
    assert state_rows[0][:3] == ("2026-02-10", "completed", 1)
    assert state_rows[1][0:2] == ("2026-02-11", "failed")
    assert "temporary openapi failure" in state_rows[1][3]
    assert metric_rows == [("2026-02-10", "material_2026-02-10", 88.0)]
