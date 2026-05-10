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
                "source_artifact_path": "/runs/create_live_execute_once/a.json",
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
    assert result["db_ledger_summary"]["provider_id_counts"] == {"project": 1, "promotion": 1}
    assert result["db_ledger_summary"]["material_bind_count"] == 1
    assert "完成项目1个、单元1个、素材推送1组" in result["message"]
    assert artifact["actions"] == []


def test_create_live_execute_report_script_reads_latest_execute_once_artifact(tmp_path: Path, capsys):
    runtime_path = _runtime_config(tmp_path)
    source_path = tmp_path / "runs" / "create_live_execute_once" / "20260510T000000Z.json"
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text(json.dumps(_completed_execute_once_artifact(), ensure_ascii=False), encoding="utf-8")
    module = _load_script("run_create_live_execute_report")

    exit_code = module.run_from_args(["--config", str(runtime_path)])

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["workflow"] == "create_live_execute_report"
    assert output["status"] == "reported_completed"
    assert output["external_api_calls"] == 0
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
    assert artifact["actions"] == []
