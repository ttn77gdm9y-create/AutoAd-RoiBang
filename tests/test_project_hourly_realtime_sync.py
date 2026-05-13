import json
import importlib.util
import sqlite3
from pathlib import Path

from roibang_v2.db.bootstrap import bootstrap_database
from roibang_v2.workflows.project_hourly_realtime_sync import build_project_hourly_realtime_plan
from roibang_v2.workflows.project_hourly_realtime_sync import run_project_hourly_realtime_sync_request


def _load_script():
    script_path = Path("scripts/run_project_hourly_realtime_sync.py")
    spec = importlib.util.spec_from_file_location("run_project_hourly_realtime_sync", script_path)
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
                        "enable": True,
                        "channel": "wx",
                    },
                    {
                        "account_name": "黑旗-其他产品-微小-傲星-1",
                        "advertiser_id": "blocked-by-product",
                        "product": "其他产品",
                        "enable": True,
                        "channel": "wx",
                    },
                    {
                        "account_name": "黑旗-勇者突进-微小-傲星-disabled",
                        "advertiser_id": "disabled-account",
                        "product": "勇者突进",
                        "enable": False,
                        "channel": "wx",
                    },
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_project_hourly_realtime_plan_uses_only_enabled_allowed_accounts(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    allowlist_path = tmp_path / "allowed.json"
    bootstrap_database(db_path)
    _write_allowed_accounts(allowlist_path)

    plan = build_project_hourly_realtime_plan(
        db_path,
        {
            "target_date": "2026-05-12",
            "product_keyword": "勇者突进",
            "allowed_target_accounts_path": str(allowlist_path),
            "page_size": 100,
        },
    )

    assert plan["summary"]["allowed_account_count"] == 1
    assert plan["summary"]["planned_request_count"] == 1
    request = plan["plan"]["requests"][0]
    assert request["endpoint_key"] == "report_custom"
    assert request["report_preset"] == "project_hourly"
    assert request["account"]["advertiser_id"] == "1856647523922953"
    assert "stat_time_hour" in json.loads(request["query_params"]["dimensions"])


def test_project_hourly_realtime_sync_imports_project_hour_rows(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    allowlist_path = tmp_path / "allowed.json"
    bootstrap_database(db_path)
    _write_allowed_accounts(allowlist_path)
    calls = []

    def transport(request: dict) -> dict:
        calls.append(request)
        return {
            "code": 0,
            "data": {
                "rows": [
                    {
                        "dimensions": {
                            "stat_time_hour": "2026-05-12 13:00:00",
                            "cdp_project_id": "project-1",
                            "cdp_project_name": "0512_勇者突进_项目",
                        },
                        "metrics": {
                            "stat_cost": "260.5",
                            "show_cnt": "1000",
                            "click_cnt": "30",
                            "convert_cnt": "1",
                            "attribution_billing_game_in_app_roi_1day": "0.12",
                        },
                    }
                ],
                "page_info": {"page": 1, "total_page": 1},
            },
        }

    result = run_project_hourly_realtime_sync_request(
        {
            "target_date": "2026-05-12",
            "product_keyword": "勇者突进",
            "allowed_target_accounts_path": str(allowlist_path),
            "execution": {"status": "execute", "external_api_enabled": True},
            "openapi_http": {"enabled": True},
        },
        db_path=db_path,
        runs_dir=tmp_path / "runs",
        transport=transport,
    )

    assert result["ok"] is True
    assert result["execution_enabled"] is False
    assert result["summary"]["allowed_account_count"] == 1
    assert result["summary"]["transport_calls"] == 1
    assert result["summary"]["rows_imported"] == 1
    assert calls[0]["report_preset"] == "project_hourly"
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT metric_date, metric_hour, advertiser_id, project_id, stat_cost, convert_cnt, roi_1day
            FROM project_hourly_metrics
            """
        ).fetchone()
    assert row == ("2026-05-12", 13, "1856647523922953", "project-1", 260.5, 1, 0.12)


def test_project_hourly_realtime_sync_fails_closed_without_readonly_gate(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    allowlist_path = tmp_path / "allowed.json"
    bootstrap_database(db_path)
    _write_allowed_accounts(allowlist_path)

    try:
        run_project_hourly_realtime_sync_request(
            {
                "target_date": "2026-05-12",
                "product_keyword": "勇者突进",
                "allowed_target_accounts_path": str(allowlist_path),
                "execution": {"status": "planned_only", "external_api_enabled": False},
                "openapi_http": {"enabled": False},
            },
            db_path=db_path,
            runs_dir=tmp_path / "runs",
        )
    except RuntimeError as exc:
        assert "requires execution.status=execute" in str(exc)
    else:
        raise AssertionError("real hourly realtime sync should fail closed without readonly approval")


def test_project_hourly_realtime_sync_cli_requires_enable_readonly(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    allowlist_path = tmp_path / "allowed.json"
    request_path = tmp_path / "request.json"
    bootstrap_database(db_path)
    _write_allowed_accounts(allowlist_path)
    request_path.write_text(
        json.dumps(
            {
                "project_hourly_realtime_sync": {
                    "target_date": "2026-05-12",
                    "product_keyword": "勇者突进",
                    "allowed_target_accounts_path": str(allowlist_path),
                    "execution": {"status": "planned_only", "external_api_enabled": False},
                    "openapi_http": {"enabled": False},
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
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


def test_project_hourly_realtime_sync_cli_preflight_prints_plan_without_external_calls(tmp_path: Path, capsys):
    db_path = tmp_path / "roibang.sqlite3"
    allowlist_path = tmp_path / "allowed.json"
    request_path = tmp_path / "request.json"
    bootstrap_database(db_path)
    _write_allowed_accounts(allowlist_path)
    request_path.write_text(
        json.dumps(
            {
                "project_hourly_realtime_sync": {
                    "target_date": "2026-05-12",
                    "product_keyword": "勇者突进",
                    "allowed_target_accounts_path": str(allowlist_path),
                    "page_size": 100,
                    "execution": {"status": "planned_only", "external_api_enabled": False},
                    "openapi_http": {"enabled": False},
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    module = _load_script()

    exit_code = module.run_from_args(
        [
            "--preflight",
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

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["workflow"] == "project_hourly_realtime_sync_plan"
    assert output["execution_enabled"] is False
    assert output["external_api_calls"] == 0
    assert output["summary"]["allowed_account_count"] == 1
    assert output["summary"]["planned_request_count"] == 1
    assert Path(output["artifact_path"]).exists()
