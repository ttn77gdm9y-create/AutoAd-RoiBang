import json
import sys
from pathlib import Path

from roibang_v2.ui.artifact_reader import compact_summary
from roibang_v2.ui.artifact_reader import find_latest_artifact
from roibang_v2.ui.artifact_reader import load_latest_artifact
from roibang_v2.ui.script_runner import build_ai_template_drafts_command
from roibang_v2.ui.script_runner import build_create_plan_command
from roibang_v2.ui.script_runner import build_delivery_patrol_command
from roibang_v2.ui.script_runner import build_project_filter_command
from roibang_v2.ui.streamlit_shell import list_create_modes
from roibang_v2.ui.streamlit_shell import load_ui_config
from roibang_v2.ui.streamlit_shell import mode_label


def test_load_ui_config_merges_defaults(tmp_path):
    config_path = tmp_path / "ui.json"
    config_path.write_text(json.dumps({"title": "Test UI", "runs_dir": "runs"}), encoding="utf-8")

    config = load_ui_config(config_path)

    assert config["title"] == "Test UI"
    assert config["runs_dir"] == "runs"
    assert config["default_owner"] == "郭靖"


def test_list_create_modes_reads_display_name_and_mode_key(tmp_path):
    mode_dir = tmp_path / "create-modes"
    mode_dir.mkdir()
    (mode_dir / "wx_pay_general_recent_scale.example.json").write_text(
        json.dumps(
            {
                "mode_key": "wx_pay_general_recent_scale",
                "display_name": "每付通投近期放量",
                "template_key": "wx_pay_general",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    rows = list_create_modes(mode_dir)

    assert rows == [
        {
            "mode_key": "wx_pay_general_recent_scale",
            "display_name": "每付通投近期放量",
            "template_key": "wx_pay_general",
        }
    ]
    assert mode_label(rows[0]) == "每付通投近期放量 (wx_pay_general_recent_scale)"


def test_artifact_reader_prefers_latest_json(tmp_path):
    workflow_dir = tmp_path / "delivery_patrol"
    workflow_dir.mkdir()
    old_path = workflow_dir / "20260517T010000Z.json"
    new_path = workflow_dir / "20260518T010000Z.json"
    old_path.write_text(json.dumps({"ok": True, "summary": {"value": "old"}}), encoding="utf-8")
    new_path.write_text(json.dumps({"ok": True, "summary": {"value": "new"}}), encoding="utf-8")

    latest = find_latest_artifact(tmp_path, "delivery_patrol")
    payload = load_latest_artifact(tmp_path, "delivery_patrol")

    assert latest == new_path
    assert payload["summary"]["value"] == "new"
    assert payload["artifact_path"] == str(new_path)
    assert compact_summary(payload)["summary"]["value"] == "new"


def test_build_delivery_patrol_command_uses_readonly_entrypoint():
    command = build_delivery_patrol_command(readonly=True)

    assert command[0] == sys.executable
    assert command[1:4] == ["scripts/run_delivery_patrol.py", "--config", "configs/runtime.openapi-execute.local.example.json"]
    assert "--enable-readonly" in command


def test_build_create_plan_command_splits_accounts_and_never_executes():
    command = build_create_plan_command(
        mode="每付通投近期放量",
        accounts="1851, 1852\n1853",
        owner="郭靖",
        target_date="2026-05-18",
    )

    assert command[:2] == [sys.executable, "scripts/run_create_mode.py"]
    assert "--mode" in command
    assert "每付通投近期放量" in command
    assert command.count("--account") == 3
    assert "--execute" not in command
    assert "--yes" not in command


def test_build_project_filter_command_adds_action_specific_fields():
    command = build_project_filter_command(
        project_update_id="close-low-cost",
        advertiser_id="1851",
        action_type="status_update",
        name_contains="0518",
        spend_window="today",
        metric_field="stat_cost",
        metric_op="lt",
        metric_value="100",
        output_path="configs/project-updates/close-low-cost.local.json",
        opt_status="DISABLE",
    )

    assert command[:2] == [sys.executable, "scripts/run_project_realtime_filter_config.py"]
    assert "--metric-filter" in command
    assert "stat_cost:lt:100" in command
    assert "--opt-status" in command
    assert "DISABLE" in command
    assert "--execute" not in command
    assert "--yes" not in command


def test_build_ai_template_drafts_command_is_readonly():
    command = build_ai_template_drafts_command()

    assert command[:2] == [sys.executable, "scripts/run_ai_create_template_drafts.py"]
    assert "configs/runtime.example.json" in command
    assert "--execute" not in command
    assert "--yes" not in command

