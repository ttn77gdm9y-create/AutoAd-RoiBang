import importlib.util
import json
import sqlite3
from pathlib import Path

from roibang_v2.accounts.pool import import_accounts_csv, import_allowed_accounts_json, select_accounts, build_backfill_plan
from roibang_v2.db.bootstrap import bootstrap_database


def _load_import_script():
    script_path = Path("scripts/import_accounts_csv.py")
    spec = importlib.util.spec_from_file_location("import_accounts_csv", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _load_allowed_import_script():
    script_path = Path("scripts/import_allowed_create_accounts.py")
    spec = importlib.util.spec_from_file_location("import_allowed_create_accounts", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _load_plan_script():
    script_path = Path("scripts/plan_report_backfill.py")
    spec = importlib.util.spec_from_file_location("plan_report_backfill", script_path)
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
                "黑旗-勇者突进-字小-傲星-001,1850000000000002,0,勇者突进,BYTE_GAME",
                "黑旗-其他产品-微小-傲星-001,1850000000000003,12.5,其他产品,WECHAT_GAME",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def test_import_accounts_csv_normalizes_and_upserts_rows(tmp_path):
    db_path = tmp_path / "roibang.sqlite3"
    csv_path = tmp_path / "accounts.csv"
    bootstrap_database(db_path)
    _write_accounts_csv(csv_path)

    result = import_accounts_csv(csv_path, db_path=db_path)
    result_again = import_accounts_csv(csv_path, db_path=db_path)

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT advertiser_id, account_name, product, platform, historical_spend
            FROM account_pool
            ORDER BY advertiser_id
            """
        ).fetchall()

    assert result["ok"] is True
    assert result["rows_seen"] == 3
    assert result["accounts_imported"] == 3
    assert result["products"] == {"其他产品": 1, "勇者突进": 2}
    assert result["platforms"] == {"BYTE_GAME": 1, "WECHAT_GAME": 2}
    assert result_again["accounts_imported"] == 3
    assert rows == [
        ("1850000000000002", "黑旗-勇者突进-字小-傲星-001", "勇者突进", "BYTE_GAME", 0.0),
        ("1850000000000003", "黑旗-其他产品-微小-傲星-001", "其他产品", "WECHAT_GAME", 12.5),
        ("1858371222574218", "黑旗-勇者突进-微小-傲星-306", "勇者突进", "WECHAT_GAME", 570011.13),
    ]


def test_import_allowed_accounts_json_syncs_enabled_rows_to_account_pool(tmp_path):
    db_path = tmp_path / "roibang.sqlite3"
    allowlist_path = tmp_path / "allowed.json"
    bootstrap_database(db_path)
    allowlist_path.write_text(
        json.dumps(
            {
                "product": "点点英雄",
                "channel": "wx",
                "allowed_target_accounts": [
                    {"advertiser_id": "acc-1", "account_name": "点点英雄-微小-001", "enable": True},
                    {"advertiser_id": "acc-2", "account_name": "点点英雄-微小-002", "enable": False},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = import_allowed_accounts_json(allowlist_path, db_path=db_path)

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT advertiser_id, account_name, product, platform, source
            FROM account_pool
            ORDER BY advertiser_id
            """
        ).fetchall()
    assert result["ok"] is True
    assert result["rows_seen"] == 2
    assert result["accounts_imported"] == 1
    assert result["skipped_disabled"] == 1
    assert result["products"] == {"点点英雄": 1}
    assert result["platforms"] == {"WECHAT_GAME": 1}
    assert rows == [("acc-1", "点点英雄-微小-001", "点点英雄", "WECHAT_GAME", str(allowlist_path))]


def test_select_accounts_filters_by_product_and_platform(tmp_path):
    db_path = tmp_path / "roibang.sqlite3"
    csv_path = tmp_path / "accounts.csv"
    bootstrap_database(db_path)
    _write_accounts_csv(csv_path)
    import_accounts_csv(csv_path, db_path=db_path)

    accounts = select_accounts(db_path=db_path, product="勇者突进", platforms=["WECHAT_GAME"])

    assert accounts == [
        {
            "advertiser_id": "1858371222574218",
            "account_name": "黑旗-勇者突进-微小-傲星-306",
            "product": "勇者突进",
            "platform": "WECHAT_GAME",
            "historical_spend": 570011.13,
        }
    ]


def test_build_backfill_plan_is_dry_run_and_chunks_by_day(tmp_path):
    db_path = tmp_path / "roibang.sqlite3"
    csv_path = tmp_path / "accounts.csv"
    bootstrap_database(db_path)
    _write_accounts_csv(csv_path)
    import_accounts_csv(csv_path, db_path=db_path)

    plan = build_backfill_plan(
        db_path=db_path,
        product="勇者突进",
        platforms=["WECHAT_GAME", "BYTE_GAME"],
        start_date="2026-02-10",
        end_date="2026-02-12",
        runs_dir=tmp_path / "runs",
    )

    assert plan["ok"] is True
    assert plan["workflow"] == "report_backfill_plan"
    assert plan["execution_enabled"] is False
    assert plan["external_api_calls"] == 0
    assert plan["summary"] == {
        "product": "勇者突进",
        "platforms": ["WECHAT_GAME", "BYTE_GAME"],
        "account_count": 2,
        "date_count": 3,
        "planned_fetch_tasks": 6,
    }
    assert plan["tasks"][0] == {
        "date": "2026-02-10",
        "advertiser_id": "1850000000000002",
        "account_name": "黑旗-勇者突进-字小-傲星-001",
        "product": "勇者突进",
        "platform": "BYTE_GAME",
        "status": "planned_only",
    }
    assert Path(plan["artifact_path"]).exists()


def test_import_accounts_csv_cli_writes_summary(tmp_path, capsys):
    db_path = tmp_path / "roibang.sqlite3"
    csv_path = tmp_path / "accounts.csv"
    bootstrap_database(db_path)
    _write_accounts_csv(csv_path)
    module = _load_import_script()

    exit_code = module.import_from_args(["--csv", str(csv_path), "--db", str(db_path)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert '"accounts_imported": 3' in captured.out


def test_import_allowed_create_accounts_cli_can_read_product_config(tmp_path, capsys):
    db_path = tmp_path / "roibang.sqlite3"
    allowlist_path = tmp_path / "allowed.json"
    product_path = tmp_path / "product.json"
    bootstrap_database(db_path)
    allowlist_path.write_text(
        json.dumps(
            {
                "product": "点点英雄",
                "channel": "wx",
                "allowed_target_accounts": [
                    {"advertiser_id": "acc-1", "account_name": "点点英雄-微小-001", "enable": True}
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    product_path.write_text(
        json.dumps({"allowed_target_accounts_path": str(allowlist_path)}, ensure_ascii=False),
        encoding="utf-8",
    )
    module = _load_allowed_import_script()

    exit_code = module.import_from_args(["--product-config", str(product_path), "--db", str(db_path)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert '"workflow": "allowed_create_accounts_import"' in captured.out
    assert '"accounts_imported": 1' in captured.out


def test_plan_report_backfill_cli_writes_plan(tmp_path, capsys):
    db_path = tmp_path / "roibang.sqlite3"
    csv_path = tmp_path / "accounts.csv"
    bootstrap_database(db_path)
    _write_accounts_csv(csv_path)
    import_accounts_csv(csv_path, db_path=db_path)
    module = _load_plan_script()

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
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert '"planned_fetch_tasks": 1' in captured.out
    assert '"external_api_calls": 0' in captured.out
    assert '"artifact_path":' in captured.out
    assert '"tasks":' not in captured.out
