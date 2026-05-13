import importlib.util
import json
from pathlib import Path

from roibang_v2.backfill.runner import run_backfill_batches_request
from roibang_v2.db.bootstrap import bootstrap_database
from roibang_v2.accounts.pool import import_accounts_csv
from roibang_v2.fetch.openapi_http import HttpResponse


def _load_runner_script():
    script_path = Path("scripts/run_backfill_batches.py")
    spec = importlib.util.spec_from_file_location("run_backfill_batches", script_path)
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


def _write_plan(path: Path):
    path.write_text(
        json.dumps(
            {
                "workflow": "report_backfill_batch_plan",
                "batches": [
                    {
                        "batch_id": "batch_0001",
                        "planned_request_count": 2,
                        "report_fetch_request": {
                            "report_fetch": {
                                "mode": "backfill",
                                "source": "openapi_http_execute",
                                "batch_id": "batch_0001",
                                "product": "勇者突进",
                                "platforms": ["WECHAT_GAME"],
                                "account_ids": ["1858371222574218"],
                                "date_range": {"start": "2026-02-10", "end": "2026-02-10"},
                                "openapi": {
                                    "endpoints": ["report_custom"],
                                    "report_presets": ["promotion_daily"],
                                    "page_size": 100,
                                },
                                "openapi_http": {"enabled": False, "token_env": "ROIBANG_TEST_ACCESS_TOKEN"},
                                "output": {"snapshot_dir": "data/snapshots/report/backfill/batch_0001"},
                                "execution": {"status": "planned_only", "external_api_enabled": False},
                            }
                        },
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _runner_request(plan_path: Path, *, execute: bool = False) -> dict:
    return {
        "backfill_runner": {
            "plan_file": str(plan_path),
            "batch_ids": ["batch_0001"],
            "execution": {
                "status": "execute" if execute else "planned_only",
                "external_api_enabled": execute,
            },
            "openapi_http": {
                "enabled": execute,
                "token_env": "ROIBANG_TEST_ACCESS_TOKEN",
                "response_audit_dir": "data/runs/openapi_http/backfill_runner_test",
                "max_retries": 0,
            },
            "stop_on_error": True,
        }
    }


def test_backfill_runner_dry_run_does_not_execute_batches(tmp_path):
    db_path = tmp_path / "roibang.sqlite3"
    plan_path = tmp_path / "plan.json"
    bootstrap_database(db_path)
    _write_plan(plan_path)

    result = run_backfill_batches_request(
        _runner_request(plan_path, execute=False),
        db_path=db_path,
        runs_dir=tmp_path / "runs",
    )

    assert result["ok"] is True
    assert result["workflow"] == "backfill_batch_runner"
    assert result["execution_enabled"] is False
    assert result["external_api_calls"] == 0
    assert result["summary"] == {
        "selected_batch_count": 1,
        "executed_batch_count": 0,
        "planned_request_count": 2,
        "external_api_calls": 0,
        "failed_batch_count": 0,
    }
    assert result["batches"][0]["status"] == "planned_only"


def test_backfill_runner_execute_uses_batch_account_ids(monkeypatch, tmp_path):
    db_path = tmp_path / "roibang.sqlite3"
    csv_path = tmp_path / "accounts.csv"
    plan_path = tmp_path / "plan.json"
    bootstrap_database(db_path)
    _write_accounts_csv(csv_path)
    import_accounts_csv(csv_path, db_path=db_path)
    _write_plan(plan_path)
    monkeypatch.setenv("ROIBANG_TEST_ACCESS_TOKEN", "secret-token")
    calls = []

    def fake_opener(_url, query_params, _headers, _timeout_seconds):
        calls.append(dict(query_params))
        return HttpResponse(
            200,
            {
                "code": 0,
                "data": {
                    "rows": [
                        {
                            "dimensions": {
                                "stat_time": "2026-02-10",
                                "promotion_id": "promotion_1",
                                "promotion_name": "单元1",
                            },
                            "metrics": {"stat_cost": "1", "convert_cnt": "1"},
                        }
                    ],
                    "page_info": {"page": 1, "total_page": 1},
                },
            },
        )

    result = run_backfill_batches_request(
        _runner_request(plan_path, execute=True),
        db_path=db_path,
        runs_dir=tmp_path / "runs",
        http_opener=fake_opener,
    )

    assert result["ok"] is True
    assert result["external_api_calls"] == 1
    assert result["summary"]["executed_batch_count"] == 1
    assert calls == [
        {
            "advertiser_id": "1858371222574218",
            "data_topic": "BASIC_DATA",
            "dimensions": "[\"stat_time_day\",\"cdp_project_id\",\"cdp_project_name\",\"cdp_promotion_id\",\"cdp_promotion_name\"]",
            "metrics": "[\"stat_cost\",\"show_cnt\",\"click_cnt\",\"convert_cnt\",\"attribution_convert_cnt\",\"attribution_convert_cost\",\"attribution_billing_game_in_app_ltv_1day\",\"attribution_billing_game_in_app_roi_1day\"]",
            "filters": "[]",
            "start_time": "2026-02-10",
            "end_time": "2026-02-10",
            "order_by": "[{\"field\":\"stat_cost\",\"type\":\"DESC\"}]",
            "page": "1",
            "page_size": "100",
        }
    ]


def test_run_backfill_batches_cli_prints_summary(tmp_path, capsys):
    db_path = tmp_path / "roibang.sqlite3"
    plan_path = tmp_path / "plan.json"
    request_path = tmp_path / "runner.json"
    bootstrap_database(db_path)
    _write_plan(plan_path)
    request_path.write_text(json.dumps(_runner_request(plan_path), ensure_ascii=False), encoding="utf-8")
    module = _load_runner_script()

    exit_code = module.run_from_args(
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
    assert '"workflow": "backfill_batch_runner"' in captured.out
    assert '"executed_batch_count": 0' in captured.out
    assert '"batches":' not in captured.out
