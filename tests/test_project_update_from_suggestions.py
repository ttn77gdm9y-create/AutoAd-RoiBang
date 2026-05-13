import importlib.util
import json
from pathlib import Path

from roibang_v2.workflows.project_update_from_suggestions import build_project_update_from_suggestions
from roibang_v2.workflows.project_update_from_suggestions import run_project_update_from_suggestions_request


def _suggestions() -> dict:
    return {
        "ok": True,
        "workflow": "control_strategy_suggestions",
        "execution_enabled": False,
        "external_api_calls": 0,
        "summary": {
            "target_date": "2026-05-12",
            "suggestion_count": 2,
            "schedule_hollow_suggestion_count": 2,
            "allowed_account_count": 15,
        },
        "suggestions": [
            {
                "suggestion_type": "schedule_hollow",
                "rule_id": "schedule_hollow_low_realtime_hour_roi",
                "target_date": "2026-05-12",
                "advertiser_id": "1856647523922953",
                "entity_type": "project",
                "entity_id": "project-1",
                "hollow_hours": [5, 6, 7],
                "reason": "当天实时小时数据 ROI 低于阈值，建议临时拉空这些小时",
                "metrics": {"stat_cost": 100, "convert_cnt": 0, "roi_1day": 0},
                "restore": {
                    "required": True,
                    "restore_date": "2026-05-13",
                    "reason": "当天临时拉空时段，第二天必须恢复原始时段，避免长期影响投放节奏。",
                },
                "execution": {"enabled": False},
            },
            {
                "suggestion_type": "pause_project",
                "target_date": "2026-05-12",
                "advertiser_id": "1856647523922953",
                "entity_type": "project",
                "entity_id": "project-ignored",
            },
            {
                "suggestion_type": "schedule_hollow",
                "rule_id": "schedule_hollow_low_realtime_hour_roi",
                "target_date": "2026-05-12",
                "advertiser_id": "1856647539522568",
                "entity_type": "project",
                "entity_id": "project-2",
                "hollow_hours": [2, 9],
                "reason": "当天实时小时数据 ROI 低于阈值，建议临时拉空这些小时",
                "metrics": {"stat_cost": 80, "convert_cnt": 0, "roi_1day": 0},
                "restore": {
                    "required": True,
                    "restore_date": "2026-05-13",
                    "reason": "当天临时拉空时段，第二天必须恢复原始时段，避免长期影响投放节奏。",
                },
                "execution": {"enabled": False},
            },
        ],
    }


def _load_script():
    script_path = Path("scripts/run_project_update_from_suggestions.py")
    spec = importlib.util.spec_from_file_location("run_project_update_from_suggestions", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_build_project_update_from_schedule_hollow_suggestions_only():
    result = build_project_update_from_suggestions(
        _suggestions(),
        {
            "project_update_id": "project-update-20260512-001",
            "operator": "郭靖",
            "allowed_target_accounts_path": "configs/control-allowed-accounts.local.json",
        },
    )

    assert result["workflow"] == "project_update_from_suggestions"
    assert result["execution_enabled"] is False
    assert result["external_api_calls"] == 0
    assert result["summary"] == {
        "project_update_id": "project-update-20260512-001",
        "source_suggestion_count": 3,
        "schedule_hollow_action_count": 2,
        "restore_action_count": 2,
        "target_date": "2026-05-12",
        "restore_date": "2026-05-13",
    }
    update = result["project_update"]
    assert update["execution"] == {"enabled": False, "status": "planned_only"}
    assert update["allowed_target_accounts_path"] == "configs/control-allowed-accounts.local.json"
    assert update["actions"][0] == {
        "action_type": "schedule_hollow",
        "advertiser_id": "1856647523922953",
        "entity_type": "project",
        "project_id": "project-1",
        "target_date": "2026-05-12",
        "hollow_hours": [5, 6, 7],
        "preserve_original_schedule_required": True,
        "restore_required": True,
        "restore_date": "2026-05-13",
        "reason": "当天实时小时数据 ROI 低于阈值，建议临时拉空这些小时",
        "metrics": {"stat_cost": 100, "convert_cnt": 0, "roi_1day": 0},
    }
    assert update["restore_actions"][0]["action_type"] == "schedule_restore"
    assert update["restore_actions"][0]["restore_date"] == "2026-05-13"


def test_run_project_update_from_suggestions_writes_update_file_and_artifact(tmp_path: Path):
    output_path = tmp_path / "project_update.local.json"

    result = run_project_update_from_suggestions_request(
        {
            "suggestions_artifact": _suggestions(),
            "project_update_id": "project-update-20260512-001",
            "operator": "郭靖",
            "allowed_target_accounts_path": "configs/control-allowed-accounts.local.json",
            "output_path": str(output_path),
        },
        runs_dir=tmp_path / "runs",
    )

    saved = json.loads(output_path.read_text(encoding="utf-8"))
    assert result["ok"] is True
    assert result["project_update_path"] == str(output_path)
    assert Path(result["artifact_path"]).exists()
    assert saved["project_update_id"] == "project-update-20260512-001"
    assert len(saved["actions"]) == 2
    assert len(saved["restore_actions"]) == 2


def test_project_update_from_suggestions_cli_accepts_artifact_file(tmp_path: Path, capsys):
    suggestions_path = tmp_path / "suggestions.json"
    output_path = tmp_path / "project_update.local.json"
    suggestions_path.write_text(json.dumps(_suggestions(), ensure_ascii=False), encoding="utf-8")
    module = _load_script()

    exit_code = module.run_from_args(
        [
            "--suggestions-artifact",
            str(suggestions_path),
            "--project-update-id",
            "project-update-20260512-001",
            "--operator",
            "郭靖",
            "--allowed-target-accounts-path",
            "configs/control-allowed-accounts.local.json",
            "--output",
            str(output_path),
            "--runs-dir",
            str(tmp_path / "runs"),
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["workflow"] == "project_update_from_suggestions"
    assert output["execution_enabled"] is False
    assert output["external_api_calls"] == 0
    assert output["summary"]["schedule_hollow_action_count"] == 2
    assert output["project_update_path"] == str(output_path)
