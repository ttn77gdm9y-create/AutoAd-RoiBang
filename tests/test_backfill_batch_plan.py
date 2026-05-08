import importlib.util
from pathlib import Path

from roibang_v2.accounts.pool import build_backfill_batch_plan, import_accounts_csv
from roibang_v2.db.bootstrap import bootstrap_database


def _load_batch_plan_script():
    script_path = Path("scripts/plan_report_backfill_batches.py")
    spec = importlib.util.spec_from_file_location("plan_report_backfill_batches", script_path)
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
                "黑旗-勇者突进-字小-傲星-001,1850000000000002,100,勇者突进,BYTE_GAME",
                "黑旗-其他产品-微小-傲星-001,1850000000000003,12.5,其他产品,WECHAT_GAME",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def test_build_backfill_batch_plan_chunks_accounts_dates_and_requests(tmp_path):
    db_path = tmp_path / "roibang.sqlite3"
    csv_path = tmp_path / "accounts.csv"
    bootstrap_database(db_path)
    _write_accounts_csv(csv_path)
    import_accounts_csv(csv_path, db_path=db_path)

    plan = build_backfill_batch_plan(
        db_path=db_path,
        product="勇者突进",
        platforms=["WECHAT_GAME"],
        start_date="2026-02-10",
        end_date="2026-02-12",
        endpoints=["report_custom", "operation_log_search"],
        report_presets=["promotion_daily"],
        max_accounts_per_batch=1,
        max_dates_per_batch=2,
        runs_dir=tmp_path / "runs",
    )

    assert plan["ok"] is True
    assert plan["workflow"] == "report_backfill_batch_plan"
    assert plan["execution_enabled"] is False
    assert plan["external_api_calls"] == 0
    assert plan["summary"] == {
        "product": "勇者突进",
        "platforms": ["WECHAT_GAME"],
        "account_count": 2,
        "date_count": 3,
        "batch_count": 4,
        "planned_account_date_tasks": 6,
        "planned_request_count": 12,
        "requests_per_account_date": 2,
    }
    assert plan["batches"][0]["batch_id"] == "batch_0001"
    assert plan["batches"][0]["date_range"] == {"start": "2026-02-10", "end": "2026-02-11", "dates": ["2026-02-10", "2026-02-11"]}
    assert plan["batches"][0]["account_count"] == 1
    assert plan["batches"][0]["planned_request_count"] == 4
    assert plan["batches"][0]["report_fetch_request"]["report_fetch"]["source"] == "openapi_http_execute"
    assert plan["batches"][0]["report_fetch_request"]["report_fetch"]["execution"] == {
        "status": "planned_only",
        "external_api_enabled": False,
    }
    assert Path(plan["artifact_path"]).exists()


def test_build_backfill_batch_plan_respects_request_limit(tmp_path):
    db_path = tmp_path / "roibang.sqlite3"
    csv_path = tmp_path / "accounts.csv"
    bootstrap_database(db_path)
    _write_accounts_csv(csv_path)
    import_accounts_csv(csv_path, db_path=db_path)

    plan = build_backfill_batch_plan(
        db_path=db_path,
        product="勇者突进",
        platforms=["WECHAT_GAME"],
        start_date="2026-02-10",
        end_date="2026-02-12",
        endpoints=["report_custom", "operation_log_search"],
        report_presets=["promotion_daily"],
        max_accounts_per_batch=2,
        max_dates_per_batch=3,
        max_requests_per_batch=4,
        runs_dir=tmp_path / "runs",
    )

    assert plan["summary"]["batch_count"] == 3
    assert [batch["planned_request_count"] for batch in plan["batches"]] == [4, 4, 4]
    assert [batch["date_range"]["dates"] for batch in plan["batches"]] == [
        ["2026-02-10"],
        ["2026-02-11"],
        ["2026-02-12"],
    ]


def test_plan_report_backfill_batches_cli_prints_summary_only(tmp_path, capsys):
    db_path = tmp_path / "roibang.sqlite3"
    csv_path = tmp_path / "accounts.csv"
    bootstrap_database(db_path)
    _write_accounts_csv(csv_path)
    import_accounts_csv(csv_path, db_path=db_path)
    module = _load_batch_plan_script()

    exit_code = module.plan_from_args(
        [
            "--db",
            str(db_path),
            "--runs-dir",
            str(tmp_path / "runs"),
            "--product",
            "勇者突进",
            "--platform",
            "WECHAT_GAME",
            "--start-date",
            "2026-02-10",
            "--end-date",
            "2026-02-10",
            "--endpoint",
            "report_custom",
            "--endpoint",
            "operation_log_search",
            "--report-preset",
            "promotion_daily",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert '"workflow": "report_backfill_batch_plan"' in captured.out
    assert '"planned_request_count": 4' in captured.out
    assert '"batches":' not in captured.out
