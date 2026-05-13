import importlib.util
import json
from pathlib import Path

from roibang_v2.workflows.project_update_execute import FULL_SCHEDULE_TIME
from roibang_v2.workflows.project_update_execute import build_hollow_schedule_time
from roibang_v2.workflows.project_update_execute import run_project_update_execute_request


def _project_update() -> dict:
    return {
        "project_update_id": "project-update-20260512-001",
        "operator": "郭靖",
        "execution": {"enabled": False, "status": "planned_only"},
        "actions": [
            {
                "action_type": "schedule_hollow",
                "advertiser_id": "adv-1",
                "entity_type": "project",
                "project_id": "project-1",
                "target_date": "2026-05-12",
                "hollow_hours": [5, 6],
                "restore_date": "2026-05-13",
                "restore_at": "2026-05-13T00:05:00+08:00",
            },
            {
                "action_type": "schedule_hollow",
                "advertiser_id": "adv-1",
                "entity_type": "project",
                "project_id": "project-2",
                "target_date": "2026-05-12",
                "hollow_hours": [9],
                "restore_date": "2026-05-13",
                "restore_at": "2026-05-13T00:05:00+08:00",
            },
        ],
        "restore_actions": [
            {
                "action_type": "schedule_restore",
                "advertiser_id": "adv-1",
                "entity_type": "project",
                "project_id": "project-1",
                "restore_date": "2026-05-13",
                "restore_source": "preserved_original_schedule",
            },
            {
                "action_type": "schedule_restore",
                "advertiser_id": "adv-1",
                "entity_type": "project",
                "project_id": "project-2",
                "restore_date": "2026-05-13",
                "restore_source": "preserved_original_schedule",
            },
        ],
    }


def _preflight(ok: bool = True) -> dict:
    return {
        "ok": ok,
        "workflow": "project_update_preflight",
        "status": "passed" if ok else "failed",
        "execution_enabled": False,
        "external_api_calls": 0,
        "summary": {
            "project_update_id": "project-update-20260512-001",
            "action_count": 2,
            "restore_action_count": 2,
        },
        "violations": [] if ok else ["bad preflight"],
    }


def _load_script():
    script_path = Path("scripts/run_project_update_execute.py")
    spec = importlib.util.spec_from_file_location("run_project_update_execute", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_build_hollow_schedule_time_zeros_selected_hours_for_target_date_only():
    schedule = build_hollow_schedule_time(FULL_SCHEDULE_TIME, [5], target_date="2026-05-12")

    assert len(schedule) == 336
    target_day = 1
    assert schedule[target_day * 48 + 10] == "0"
    assert schedule[target_day * 48 + 11] == "0"
    assert schedule[0 * 48 + 10] == "1"
    assert schedule[2 * 48 + 10] == "1"
    assert schedule.count("0") == 2


def test_project_update_execute_requires_explicit_execute_flag(tmp_path: Path):
    result = run_project_update_execute_request(
        {
            "project_update": _project_update(),
            "preflight_artifact": _preflight(),
            "execute_enabled": False,
            "approved": False,
        },
        runs_dir=tmp_path / "runs",
    )

    assert result["ok"] is False
    assert result["status"] == "blocked"
    assert result["execution_enabled"] is False
    assert result["external_api_calls"] == 0
    assert result["blocking_reasons"] == ["project update execute requires execute_enabled=true and approved=true"]
    assert Path(result["artifact_path"]).exists()


def test_project_update_execute_saves_schedule_ledger_before_update_calls(tmp_path: Path):
    calls: list[dict] = []

    def transport(request: dict) -> dict:
        calls.append(request)
        if request["operation"] == "lookup_project_schedule":
            return {
                "code": 0,
                "data": {
                    "list": [
                        {
                            "project_id": "project-1",
                            "name": "勇者突进-1",
                            "delivery_type": "NORMAL",
                            "schedule_time": "",
                        },
                        {
                            "project_id": "project-2",
                            "name": "勇者突进-2",
                            "delivery_type": "NORMAL",
                            "schedule_time": FULL_SCHEDULE_TIME,
                        },
                    ]
                },
            }
        return {"code": 0, "message": "OK", "data": {"success": True}}

    result = run_project_update_execute_request(
        {
            "project_update": _project_update(),
            "preflight_artifact": _preflight(),
            "execute_enabled": True,
            "approved": True,
            "schedule_scene": "REALTIME",
        },
        runs_dir=tmp_path / "runs",
        transport=transport,
    )

    assert result["ok"] is True
    assert result["status"] == "completed"
    assert result["external_api_calls"] == 2
    assert [call["operation"] for call in calls] == ["lookup_project_schedule", "update_project_week_schedule"]
    update_payload = calls[1]["payload"]
    assert update_payload["advertiser_id"] == "adv-1"
    assert len(update_payload["data"]) == 2
    assert update_payload["data"][0]["schedule_scene"] == "REALTIME"
    assert update_payload["data"][0]["schedule_time"].count("0") == 4
    ledger = json.loads(Path(result["schedule_ledger_path"]).read_text(encoding="utf-8"))
    assert ledger["project_update_id"] == "project-update-20260512-001"
    assert ledger["entries"][0]["original_schedule_time"] == FULL_SCHEDULE_TIME
    assert ledger["entries"][0]["restore_date"] == "2026-05-13"
    queue = json.loads(Path(result["restore_queue_path"]).read_text(encoding="utf-8"))
    assert len(queue["items"]) == 2
    assert queue["items"][0]["status"] == "pending"
    assert queue["items"][0]["restore_at"] == "2026-05-13T00:05:00+08:00"


def test_project_update_execute_restores_schedule_from_action_without_lookup(tmp_path: Path):
    calls: list[dict] = []

    def transport(request: dict) -> dict:
        calls.append(request)
        return {"code": 0, "message": "OK", "data": {"success": True}}

    project_update = {
        "project_update_id": "project-update-20260512-001",
        "operator": "郭靖",
        "actions": [
            {
                "action_type": "schedule_restore",
                "advertiser_id": "adv-1",
                "entity_type": "project",
                "project_id": "project-1",
                "target_date": "2026-05-12",
                "restore_date": "2026-05-12",
                "original_schedule_time": FULL_SCHEDULE_TIME,
            }
        ],
    }

    result = run_project_update_execute_request(
        {
            "project_update": project_update,
            "preflight_artifact": _preflight(),
            "execute_enabled": True,
            "approved": True,
            "schedule_scene": "REALTIME",
        },
        runs_dir=tmp_path / "runs",
        transport=transport,
    )

    assert result["ok"] is True
    assert result["external_api_calls"] == 1
    assert [call["operation"] for call in calls] == ["update_project_week_schedule"]
    assert calls[0]["payload"]["data"] == [
        {
            "project_id": "project-1",
            "schedule_time": FULL_SCHEDULE_TIME,
            "schedule_scene": "REALTIME",
        }
    ]


def test_project_update_execute_stops_before_update_when_project_is_duration(tmp_path: Path):
    calls: list[dict] = []

    def transport(request: dict) -> dict:
        calls.append(request)
        return {
            "code": 0,
            "data": {
                "list": [
                    {
                        "project_id": "project-1",
                        "delivery_type": "DURATION",
                        "schedule_time": FULL_SCHEDULE_TIME,
                    },
                    {
                        "project_id": "project-2",
                        "delivery_type": "NORMAL",
                        "schedule_time": FULL_SCHEDULE_TIME,
                    },
                ]
            },
        }

    result = run_project_update_execute_request(
        {
            "project_update": _project_update(),
            "preflight_artifact": _preflight(),
            "execute_enabled": True,
            "approved": True,
        },
        runs_dir=tmp_path / "runs",
        transport=transport,
    )

    assert result["ok"] is False
    assert result["status"] == "failed_before_update"
    assert "DURATION project schedule cannot be updated: adv-1/project-1" in result["blocking_reasons"]
    assert [call["operation"] for call in calls] == ["lookup_project_schedule"]


def test_project_update_execute_cli_dry_run_blocks_without_transport(tmp_path: Path, capsys):
    update_path = tmp_path / "project_update.local.json"
    preflight_path = tmp_path / "preflight.json"
    update_path.write_text(json.dumps(_project_update(), ensure_ascii=False), encoding="utf-8")
    preflight_path.write_text(json.dumps(_preflight(), ensure_ascii=False), encoding="utf-8")
    module = _load_script()

    exit_code = module.run_from_args(
        [
            "--project-update",
            str(update_path),
            "--preflight-artifact",
            str(preflight_path),
            "--runs-dir",
            str(tmp_path / "runs"),
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert output["workflow"] == "project_update_execute"
    assert output["status"] == "blocked"
    assert output["external_api_calls"] == 0
