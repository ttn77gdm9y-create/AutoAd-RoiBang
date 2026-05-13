import importlib.util
import json
import sqlite3
from pathlib import Path

from roibang_v2.workflows.project_update_preflight import build_project_update_preflight
from roibang_v2.workflows.project_update_preflight import run_project_update_preflight_request


def _write_allowed_accounts(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "allowed_target_accounts": [
                    {
                        "advertiser_id": "adv-1",
                        "account_name": "黑旗-勇者突进-微小-傲星-153",
                        "product": "勇者突进",
                        "enable": True,
                        "channel": "wx",
                    },
                    {
                        "advertiser_id": "adv-disabled",
                        "account_name": "黑旗-勇者突进-微小-傲星-999",
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


def _seed_project_hourly_metric(db_path: Path, *, advertiser_id: str = "adv-1", project_id: str = "project-1") -> None:
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE project_hourly_metrics (
          metric_date TEXT NOT NULL,
          metric_hour INTEGER NOT NULL,
          advertiser_id TEXT NOT NULL,
          project_id TEXT NOT NULL,
          project_name TEXT NOT NULL DEFAULT '',
          stat_cost REAL NOT NULL DEFAULT 0,
          show_cnt REAL NOT NULL DEFAULT 0,
          click_cnt REAL NOT NULL DEFAULT 0,
          convert_cnt REAL NOT NULL DEFAULT 0,
          roi_1day REAL NOT NULL DEFAULT 0,
          synced_at TEXT NOT NULL DEFAULT '',
          PRIMARY KEY (metric_date, metric_hour, advertiser_id, project_id)
        )
        """
    )
    conn.execute(
        """
        INSERT INTO project_hourly_metrics (
          metric_date, metric_hour, advertiser_id, project_id, project_name, stat_cost, synced_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        ("2026-05-12", 5, advertiser_id, project_id, "勇者突进-7R男", 100, "2026-05-12T11:00:00"),
    )
    conn.commit()
    conn.close()


def _project_update(allowlist_path: Path) -> dict:
    return {
        "project_update_id": "project-update-20260512-001",
        "operator": "郭靖",
        "allowed_target_accounts_path": str(allowlist_path),
        "execution": {"enabled": False, "status": "planned_only"},
        "actions": [
            {
                "action_type": "schedule_hollow",
                "advertiser_id": "adv-1",
                "entity_type": "project",
                "project_id": "project-1",
                "target_date": "2026-05-12",
                "hollow_hours": [5, 6],
                "preserve_original_schedule_required": True,
                "restore_required": True,
                "restore_date": "2026-05-13",
            }
        ],
        "restore_actions": [
            {
                "action_type": "schedule_restore",
                "advertiser_id": "adv-1",
                "entity_type": "project",
                "project_id": "project-1",
                "restore_date": "2026-05-13",
                "restore_source": "preserved_original_schedule",
                "preserve_original_schedule_required": True,
            }
        ],
    }


def _load_script():
    script_path = Path("scripts/run_project_update_preflight.py")
    spec = importlib.util.spec_from_file_location("run_project_update_preflight", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_project_update_preflight_passes_for_allowed_project_with_restore(tmp_path: Path):
    allowlist_path = tmp_path / "allowed.json"
    db_path = tmp_path / "roibang.sqlite3"
    _write_allowed_accounts(allowlist_path)
    _seed_project_hourly_metric(db_path)

    result = build_project_update_preflight(_project_update(allowlist_path), db_path=db_path)

    assert result["workflow"] == "project_update_preflight"
    assert result["ok"] is True
    assert result["status"] == "passed"
    assert result["execution_enabled"] is False
    assert result["external_api_calls"] == 0
    assert result["summary"] == {
        "project_update_id": "project-update-20260512-001",
        "action_count": 1,
        "restore_action_count": 1,
        "target_account_count": 1,
        "project_count": 1,
        "management_action_count": 0,
        "missing_allowed_account_count": 0,
        "disabled_allowed_account_count": 0,
        "missing_restore_count": 0,
        "invalid_action_count": 0,
        "missing_project_count": 0,
    }
    assert result["violations"] == []
    assert result["checks"]["allowed_account_contract"]["checked"] is True
    assert result["planned_changes"][0]["hollow_hours"] == [5, 6]


def test_project_update_preflight_fails_closed_for_unallowed_or_missing_restore(tmp_path: Path):
    allowlist_path = tmp_path / "allowed.json"
    db_path = tmp_path / "roibang.sqlite3"
    _write_allowed_accounts(allowlist_path)
    _seed_project_hourly_metric(db_path)
    update = _project_update(allowlist_path)
    update["actions"][0]["advertiser_id"] = "adv-outside"
    update["actions"][0]["project_id"] = "project-missing"
    update["actions"][0]["hollow_hours"] = [25, 25]
    update["restore_actions"] = []

    result = build_project_update_preflight(update, db_path=db_path)

    assert result["ok"] is False
    assert result["status"] == "failed"
    assert "target account is not in allowlist: adv-outside" in result["violations"]
    assert "schedule_hollow action requires a matching restore action: adv-outside/project-missing" in result["violations"]
    assert "hollow_hours must be unique hours from 0 to 23: adv-outside/project-missing" in result["violations"]
    assert "project is not present in local metrics or project table: adv-outside/project-missing" in result["violations"]


def test_run_project_update_preflight_writes_artifact(tmp_path: Path):
    allowlist_path = tmp_path / "allowed.json"
    db_path = tmp_path / "roibang.sqlite3"
    update_path = tmp_path / "project_update.local.json"
    _write_allowed_accounts(allowlist_path)
    _seed_project_hourly_metric(db_path)
    update_path.write_text(json.dumps(_project_update(allowlist_path), ensure_ascii=False), encoding="utf-8")

    result = run_project_update_preflight_request(
        {"project_update_path": str(update_path), "db_path": str(db_path)},
        runs_dir=tmp_path / "runs",
    )

    assert result["ok"] is True
    assert Path(result["artifact_path"]).exists()
    assert result["project_update_path"] == str(update_path)


def test_project_update_preflight_cli_accepts_update_file(tmp_path: Path, capsys):
    allowlist_path = tmp_path / "allowed.json"
    db_path = tmp_path / "roibang.sqlite3"
    update_path = tmp_path / "project_update.local.json"
    _write_allowed_accounts(allowlist_path)
    _seed_project_hourly_metric(db_path)
    update_path.write_text(json.dumps(_project_update(allowlist_path), ensure_ascii=False), encoding="utf-8")
    module = _load_script()

    exit_code = module.run_from_args(
        [
            "--project-update",
            str(update_path),
            "--db",
            str(db_path),
            "--runs-dir",
            str(tmp_path / "runs"),
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["workflow"] == "project_update_preflight"
    assert output["execution_enabled"] is False
    assert output["external_api_calls"] == 0
    assert output["summary"]["action_count"] == 1
