import importlib.util
import json
from pathlib import Path

from roibang_v2.db.bootstrap import bootstrap_database
from roibang_v2.workflows.create_live_execute_report import run_create_live_execute_report_request
from roibang_v2.workflows.create_material_bind_ledger import record_create_material_bind_result
from roibang_v2.workflows.create_provider_id_ledger import record_create_provider_id


def _load_script(name: str):
    script_path = Path(f"scripts/{name}.py")
    spec = importlib.util.spec_from_file_location(name, script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _runtime_config(tmp_path: Path) -> Path:
    path = tmp_path / "runtime.json"
    path.write_text(
        json.dumps(
            {
                "environment": "test",
                "phase": "phase2",
                "database_path": str(tmp_path / "roibang.sqlite3"),
                "runs_dir": str(tmp_path / "runs"),
                "fixtures_dir": "data/fixtures",
                "external_api_enabled": False,
                "execution_enabled": False,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path


def _completed_execute_once_artifact() -> dict:
    return {
        "ok": True,
        "workflow": "create_live_execute_once",
        "phase": "phase2_preparation",
        "execution_enabled": True,
        "live_execute_enabled": True,
        "external_api_calls": 4,
        "status": "create_http_completed",
        "create_execute_summary": {"plan_id": "plan-1", "request_id": "req-1"},
        "blocking_reasons": [],
        "ordered_steps": [
            {"operation": "create_project", "status": "completed"},
            {"operation": "bind_material", "status": "completed"},
            {"operation": "lookup_target_material", "status": "completed"},
            {"operation": "create_unit", "status": "completed"},
        ],
        "provider_id_records": [
            {"status": "recorded", "entity_type": "project", "local_key": "p1", "provider_id": "project-1"},
            {"status": "recorded", "entity_type": "target_video", "local_key": "v1", "provider_id": "video-1"},
            {
                "status": "recorded",
                "entity_type": "target_video_cover",
                "local_key": "c1",
                "provider_id": "cover-1",
            },
            {"status": "recorded", "entity_type": "promotion", "local_key": "u1", "provider_id": "unit-1"},
        ],
        "material_bind_records": [{"status": "recorded", "bind_key": "bind-1"}],
        "transport_call_count": 4,
        "idempotency": {
            "status": "checked",
            "skipped_existing_provider_id_count": 0,
            "skipped_provider_id_records": [],
            "skipped_existing_material_bind_count": 0,
            "skipped_material_bind_records": [],
        },
        "failure": None,
        "actions": [],
    }


def _failed_execute_once_artifact() -> dict:
    payload = _completed_execute_once_artifact()
    payload["ok"] = False
    payload["status"] = "create_http_failed"
    payload["external_api_calls"] = 3
    payload["transport_call_count"] = 3
    payload["ordered_steps"] = [
        {"operation": "create_project", "status": "completed"},
        {"operation": "bind_material", "status": "completed"},
    ]
    payload["provider_id_records"] = [
        {"status": "recorded", "entity_type": "project", "local_key": "p2", "provider_id": "project-2"},
    ]
    payload["material_bind_records"] = [{"status": "recorded", "bind_key": "bind-2"}]
    payload["failure"] = {
        "operation": "create_unit",
        "index": 0,
        "message": "网络异常",
        "code": 40000,
    }
    return payload


def _create_plan() -> dict:
    return {
        "plan_id": "plan-1",
        "product": "yzt",
        "platform": "wx-mini-game",
        "launch_mode": "create_only",
        "source_advertiser_id": "source-1",
        "target_accounts": [
            {
                "advertiser_id": "target-1",
                "project_count": 1,
                "unit_count_per_project": 1,
                "daily_budget": 1000,
            }
        ],
        "materials": [{"source_material_id": "material-1", "source_video_id": "video-1"}],
        "reason": "首单链路验证",
    }


def test_create_live_execute_report_summarizes_completed_execution_without_api_calls(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)
    record_create_provider_id(
        db_path=db_path,
        entity_type="project",
        local_key="p1",
        provider_id="project-1",
        plan_id="plan-1",
        source_workflow="create_live_execute_once",
    )
    record_create_provider_id(
        db_path=db_path,
        entity_type="promotion",
        local_key="u1",
        provider_id="unit-1",
        plan_id="plan-1",
        source_workflow="create_live_execute_once",
    )
    record_create_material_bind_result(
        db_path=db_path,
        source_advertiser_id="source-1",
        target_advertiser_ids=["target-1"],
        source_video_ids=["video-1"],
        plan_id="plan-1",
        source_workflow="create_live_execute_once",
    )

    result = run_create_live_execute_report_request(
        {
            "create_live_execute_report": {
                "create_live_execute_once_artifact": _completed_execute_once_artifact(),
                "create_plan_artifact": _create_plan(),
                "source_artifact_path": "/runs/create_live_execute_once/a.json",
                "plan_artifact_path": "/configs/create-plans/first-live.local.json",
            }
        },
        runs_dir=tmp_path / "runs",
        db_path=db_path,
    )

    artifact = json.loads(Path(result["artifact_path"]).read_text(encoding="utf-8"))
    assert result["workflow"] == "create_live_execute_report"
    assert result["status"] == "reported_completed"
    assert result["execution_enabled"] is False
    assert result["external_api_calls"] == 0
    assert result["summary"]["source_external_api_calls"] == 4
    assert result["summary"]["created_project_count"] == 1
    assert result["summary"]["created_unit_count"] == 1
    assert result["summary"]["material_bind_count"] == 1
    assert result["create_plan_summary"]["plan_id"] == "plan-1"
    assert result["create_plan_summary"]["launch_mode"] == "create_only"
    assert result["create_plan_summary"]["target_account_count"] == 1
    assert result["create_plan_summary"]["project_count"] == 1
    assert result["create_plan_summary"]["unit_count"] == 1
    assert result["create_plan_summary"]["material_count"] == 1
    assert result["create_plan_contract"]["plan_id_matches_source"] is True
    assert result["plan_artifact_path"] == "/configs/create-plans/first-live.local.json"
    assert result["db_ledger_summary"]["provider_id_counts"] == {"project": 1, "promotion": 1}
    assert result["db_ledger_summary"]["material_bind_count"] == 1
    assert "完成项目1个、单元1个、素材推送1组" in result["message"]
    assert artifact["actions"] == []


def test_create_live_execute_report_script_reads_latest_execute_once_artifact(tmp_path: Path, capsys):
    runtime_path = _runtime_config(tmp_path)
    plan_path = tmp_path / "first-live.local.json"
    plan_path.write_text(json.dumps(_create_plan(), ensure_ascii=False), encoding="utf-8")
    source_path = tmp_path / "runs" / "create_live_execute_once" / "20260510T000000Z.json"
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text(json.dumps(_completed_execute_once_artifact(), ensure_ascii=False), encoding="utf-8")
    module = _load_script("run_create_live_execute_report")

    exit_code = module.run_from_args(["--config", str(runtime_path), "--plan", str(plan_path)])

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["workflow"] == "create_live_execute_report"
    assert output["status"] == "reported_completed"
    assert output["external_api_calls"] == 0
    assert output["create_plan_summary"]["plan_id"] == "plan-1"
    assert output["create_plan_contract"]["plan_id_matches_source"] is True
    assert output["plan_artifact_path"] == str(plan_path)
    assert output["source_artifact_path"] == str(source_path)
    assert Path(output["artifact_path"]).exists()


def test_create_live_execute_report_script_reports_missing_execute_once_as_not_found(tmp_path: Path, capsys):
    runtime_path = _runtime_config(tmp_path)
    module = _load_script("run_create_live_execute_report")

    exit_code = module.run_from_args(["--config", str(runtime_path)])

    output = json.loads(capsys.readouterr().out)
    artifact = json.loads(Path(output["artifact_path"]).read_text(encoding="utf-8"))
    assert exit_code == 0
    assert output["workflow"] == "create_live_execute_report"
    assert output["status"] == "not_found"
    assert output["execution_enabled"] is False
    assert output["external_api_calls"] == 0
    assert output["summary"]["source_status"] == "not_found"
    assert output["create_plan_summary"] == {}
    assert output["plan_artifact_path"] == ""
    assert artifact["actions"] == []


def test_create_live_execute_report_summarizes_multiple_execute_once_artifacts(tmp_path: Path):
    result = run_create_live_execute_report_request(
        {
            "create_live_execute_report": {
                "create_live_execute_once_artifacts": [
                    _completed_execute_once_artifact(),
                    _failed_execute_once_artifact(),
                ],
                "source_artifact_paths": [
                    "/runs/create_live_execute_once/a.json",
                    "/runs/create_live_execute_once/b.json",
                ],
            }
        },
        runs_dir=tmp_path / "runs",
        db_path=tmp_path / "roibang.sqlite3",
    )

    assert result["workflow"] == "create_live_execute_report"
    assert result["status"] == "reported_manual_review_required"
    assert result["execution_enabled"] is False
    assert result["external_api_calls"] == 0
    assert result["batch_summary"]["artifact_count"] == 2
    assert result["batch_summary"]["completed_artifact_count"] == 1
    assert result["batch_summary"]["failed_artifact_count"] == 1
    assert result["batch_summary"]["manual_review_required"] is True
    assert result["batch_summary"]["created_project_count"] == 2
    assert result["batch_summary"]["created_unit_count"] == 1
    assert result["batch_summary"]["material_bind_count"] == 2
    assert result["batch_summary"]["failure_reasons"] == [
        {
            "source_artifact_path": "/runs/create_live_execute_once/b.json",
            "operation": "create_unit",
            "index": 0,
            "message": "网络异常",
            "code": 40000,
        }
    ]
    assert "成功项目2个、成功单元1个" in result["message"]
    assert "需要人工处理：是" in result["message"]


def test_create_live_execute_report_script_accepts_multiple_execute_once_artifacts(tmp_path: Path, capsys):
    runtime_path = _runtime_config(tmp_path)
    first_path = tmp_path / "a.json"
    second_path = tmp_path / "b.json"
    first_path.write_text(json.dumps(_completed_execute_once_artifact(), ensure_ascii=False), encoding="utf-8")
    second_path.write_text(json.dumps(_failed_execute_once_artifact(), ensure_ascii=False), encoding="utf-8")
    module = _load_script("run_create_live_execute_report")

    exit_code = module.run_from_args(
        [
            "--config",
            str(runtime_path),
            "--create-live-execute-once-artifact",
            str(first_path),
            "--create-live-execute-once-artifact",
            str(second_path),
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["status"] == "reported_manual_review_required"
    assert output["batch_summary"]["artifact_count"] == 2
    assert output["batch_summary"]["manual_review_required"] is True
