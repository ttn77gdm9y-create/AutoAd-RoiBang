import importlib.util
import json
from pathlib import Path

from roibang_v2.workflows.project_update_config import build_project_update_config
from roibang_v2.workflows.project_update_config import run_project_update_config_request


def _request(output_path: Path | None = None) -> dict:
    request = {
        "project_update_id": "project-update-20260512-1200-test",
        "operator": "郭靖",
        "allowed_target_accounts_path": "configs/control-allowed-accounts.local.json",
        "target_date": "2026-05-12",
        "block_start": "12:00",
        "block_end": "13:00",
        "restore_time": "13:00",
        "projects": [
            {"advertiser_id": "1856647523922953", "project_id": "7638601935722250250"},
            {"advertiser_id": "1856647539522568", "project_id": "7638602100376780846"},
        ],
    }
    if output_path is not None:
        request["output_path"] = str(output_path)
    return request


def _load_script():
    script_path = Path("scripts/run_project_update_config.py")
    spec = importlib.util.spec_from_file_location("run_project_update_config", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_build_project_update_config_from_two_projects():
    update = build_project_update_config(_request())

    assert update["project_update_id"] == "project-update-20260512-1200-test"
    assert update["execution"] == {"enabled": False, "status": "planned_only"}
    assert len(update["actions"]) == 2
    assert update["actions"][0]["action_type"] == "schedule_hollow"
    assert update["actions"][0]["target_date"] == "2026-05-12"
    assert update["actions"][0]["hollow_hours"] == [12]
    assert update["actions"][0]["restore_at"] == "2026-05-12T13:00:00+08:00"
    assert update["restore_actions"][0]["action_type"] == "schedule_restore"
    assert update["restore_actions"][0]["restore_at"] == "2026-05-12T13:00:00+08:00"


def test_build_project_update_config_supports_next_day_restore_date():
    request = _request()
    request["restore_date"] = "2026-05-13"
    request["restore_time"] = "00:10"

    update = build_project_update_config(request)

    assert update["actions"][0]["restore_date"] == "2026-05-13"
    assert update["actions"][0]["restore_at"] == "2026-05-13T00:10:00+08:00"
    assert update["restore_actions"][0]["restore_at"] == "2026-05-13T00:10:00+08:00"


def test_run_project_update_config_writes_file_and_artifact(tmp_path: Path):
    output_path = tmp_path / "project_update.local.json"

    result = run_project_update_config_request(_request(output_path), runs_dir=tmp_path / "runs")

    saved = json.loads(output_path.read_text(encoding="utf-8"))
    assert result["ok"] is True
    assert result["external_api_calls"] == 0
    assert result["project_update_path"] == str(output_path)
    assert Path(result["artifact_path"]).exists()
    assert saved["actions"][0]["hollow_hours"] == [12]


def test_project_update_config_cli_accepts_projects(tmp_path: Path, capsys):
    output_path = tmp_path / "project_update.local.json"
    module = _load_script()

    exit_code = module.run_from_args(
        [
            "--project-update-id",
            "project-update-20260512-1200-test",
            "--operator",
            "郭靖",
            "--target-date",
            "2026-05-12",
            "--block-start",
            "12:00",
            "--block-end",
            "13:00",
            "--restore-time",
            "13:00",
            "--project",
            "1856647523922953:7638601935722250250",
            "--project",
            "1856647539522568:7638602100376780846",
            "--output",
            str(output_path),
            "--runs-dir",
            str(tmp_path / "runs"),
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["workflow"] == "project_update_config"
    assert output["summary"]["action_count"] == 2
    assert output["project_update_path"] == str(output_path)
