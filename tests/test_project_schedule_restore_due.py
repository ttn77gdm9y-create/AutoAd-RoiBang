import importlib.util
import json
from pathlib import Path

from roibang_v2.workflows.project_update_execute import FULL_SCHEDULE_TIME
from roibang_v2.workflows.project_schedule_restore_due import run_project_schedule_restore_due_request


def _write_queue_and_ledger(tmp_path: Path) -> tuple[Path, Path]:
    ledger_path = tmp_path / "runs" / "project_update_execute" / "project-update-001.schedule_ledger.json"
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_path.write_text(
        json.dumps(
            {
                "project_update_id": "project-update-001",
                "source": "project_update_execute",
                "entries": [
                    {
                        "action_type": "schedule_hollow",
                        "advertiser_id": "adv-1",
                        "project_id": "project-1",
                        "project_name": "勇者突进",
                        "target_date": "2026-05-12",
                        "restore_date": "2026-05-12",
                        "restore_at": "2026-05-12T13:00:00+08:00",
                        "schedule_scene": "REALTIME",
                        "original_schedule_time": FULL_SCHEDULE_TIME,
                        "new_schedule_time": FULL_SCHEDULE_TIME[:72] + "00" + FULL_SCHEDULE_TIME[74:],
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    queue_path = tmp_path / "runs" / "project_schedule_restore_queue.json"
    queue_path.write_text(
        json.dumps(
            {
                "version": 1,
                "source": "project_update_execute",
                "items": [
                    {
                        "restore_id": "project-update-001:adv-1:project-1",
                        "status": "pending",
                        "project_update_id": "project-update-001",
                        "advertiser_id": "adv-1",
                        "project_id": "project-1",
                        "project_name": "勇者突进",
                        "target_date": "2026-05-12",
                        "restore_date": "2026-05-12",
                        "restore_at": "2026-05-12T13:00:00+08:00",
                        "schedule_scene": "REALTIME",
                        "ledger_path": str(ledger_path),
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return queue_path, ledger_path


def _load_script():
    script_path = Path("scripts/run_project_schedule_restore_due.py")
    spec = importlib.util.spec_from_file_location("run_project_schedule_restore_due", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_restore_due_dry_run_reports_due_without_external_calls(tmp_path: Path):
    queue_path, _ = _write_queue_and_ledger(tmp_path)

    result = run_project_schedule_restore_due_request(
        {
            "restore_queue_path": str(queue_path),
            "now": "2026-05-12T13:01:00+08:00",
            "execute_enabled": False,
            "approved": False,
        },
        runs_dir=tmp_path / "runs",
    )

    assert result["ok"] is True
    assert result["status"] == "checked"
    assert result["external_api_calls"] == 0
    assert result["summary"]["due_item_count"] == 1
    assert result["summary"]["restored_item_count"] == 0
    assert result["summary"]["failed_item_count"] == 0


def test_restore_due_executes_and_marks_queue_completed(tmp_path: Path):
    queue_path, _ = _write_queue_and_ledger(tmp_path)
    calls: list[dict] = []

    def transport(request: dict) -> dict:
        calls.append(request)
        return {"code": 0, "message": "OK", "data": {"success": True}}

    result = run_project_schedule_restore_due_request(
        {
            "restore_queue_path": str(queue_path),
            "now": "2026-05-12T13:01:00+08:00",
            "execute_enabled": True,
            "approved": True,
            "schedule_scene": "REALTIME",
        },
        runs_dir=tmp_path / "runs",
        transport=transport,
    )

    assert result["ok"] is True
    assert result["status"] == "completed"
    assert result["external_api_calls"] == 1
    assert result["summary"]["restored_item_count"] == 1
    assert result["summary"]["failed_item_count"] == 0
    assert calls[0]["operation"] == "update_project_week_schedule"
    assert calls[0]["payload"]["data"][0]["schedule_time"] == FULL_SCHEDULE_TIME
    queue = json.loads(queue_path.read_text(encoding="utf-8"))
    assert queue["items"][0]["status"] == "completed"
    assert queue["items"][0]["restore_artifact_path"]
    assert result["restore_report"]["completed"][0]["project_id"] == "project-1"


def test_restore_due_keeps_failed_items_pending_with_error(tmp_path: Path):
    queue_path, _ = _write_queue_and_ledger(tmp_path)

    def transport(request: dict) -> dict:
        return {"code": 40001, "message": "temporary failure", "data": {}}

    result = run_project_schedule_restore_due_request(
        {
            "restore_queue_path": str(queue_path),
            "now": "2026-05-12T13:01:00+08:00",
            "execute_enabled": True,
            "approved": True,
            "schedule_scene": "REALTIME",
        },
        runs_dir=tmp_path / "runs",
        transport=transport,
    )

    assert result["ok"] is False
    assert result["status"] == "failed"
    assert result["summary"]["restored_item_count"] == 0
    assert result["summary"]["failed_item_count"] == 1
    assert "temporary failure" in result["blocking_reasons"][0]
    queue = json.loads(queue_path.read_text(encoding="utf-8"))
    assert queue["items"][0]["status"] == "pending"
    assert queue["items"][0]["attempt_count"] == 1
    assert "temporary failure" in queue["items"][0]["last_error"]
    assert result["restore_report"]["failed"][0]["project_id"] == "project-1"


def test_restore_due_cli_dry_run(tmp_path: Path, capsys):
    queue_path, _ = _write_queue_and_ledger(tmp_path)
    module = _load_script()

    exit_code = module.run_from_args(
        [
            "--restore-queue",
            str(queue_path),
            "--now",
            "2026-05-12T13:01:00+08:00",
            "--runs-dir",
            str(tmp_path / "runs"),
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["workflow"] == "project_schedule_restore_due"
    assert output["summary"]["due_item_count"] == 1
    assert output["restore_report"]["pending"][0]["project_id"] == "project-1"


def test_restore_due_cli_execute_without_due_does_not_load_transport_config(tmp_path: Path, capsys):
    queue_path, _ = _write_queue_and_ledger(tmp_path)
    module = _load_script()

    exit_code = module.run_from_args(
        [
            "--restore-queue",
            str(queue_path),
            "--config",
            str(tmp_path / "missing-config.json"),
            "--now",
            "2026-05-12T12:59:00+08:00",
            "--execute",
            "--yes",
            "--runs-dir",
            str(tmp_path / "runs"),
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["workflow"] == "project_schedule_restore_due"
    assert output["execution_enabled"] is True
    assert output["external_api_calls"] == 0
    assert output["summary"]["due_item_count"] == 0
    assert output["summary"]["failed_item_count"] == 0
    assert output["restore_report"]["completed"] == []
