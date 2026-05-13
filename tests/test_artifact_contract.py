import importlib.util
import json
from pathlib import Path

from roibang_v2.artifacts.contract import validate_artifact_contract
from roibang_v2.scheduler.jobs import load_job_registry


def _load_validate_script():
    script_path = Path("scripts/validate_run_artifact.py")
    spec = importlib.util.spec_from_file_location("validate_run_artifact", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _write_json(path: Path, payload: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_validate_artifact_contract_accepts_matching_result_json(tmp_path):
    registry = load_job_registry(Path("configs/scheduler/roibang-v2.jobs.example.json"))
    artifact = tmp_path / "material_sync.json"
    _write_json(
        artifact,
        {
            "ok": True,
            "workflow": "material_sync",
            "execution_enabled": False,
            "external_api_calls": 0,
            "plan": {"status": "sufficient"},
        },
    )

    result = validate_artifact_contract(registry, job_id="roibang-material-sync", artifact_path=artifact)

    assert result["ok"] is True
    assert result["job_id"] == "roibang-material-sync"
    assert result["workflow"] == "material_sync"
    assert result["missing_fields"] == []
    assert result["violations"] == []


def test_validate_artifact_contract_rejects_missing_required_fields(tmp_path):
    registry = load_job_registry(Path("configs/scheduler/roibang-v2.jobs.example.json"))
    artifact = tmp_path / "material_sync.json"
    _write_json(
        artifact,
        {
            "ok": True,
            "workflow": "material_sync",
            "execution_enabled": False,
            "external_api_calls": 0,
        },
    )

    result = validate_artifact_contract(registry, job_id="roibang-material-sync", artifact_path=artifact)

    assert result["ok"] is False
    assert result["missing_fields"] == ["plan"]
    assert "missing required fields: plan" in result["violations"]


def test_validate_artifact_contract_rejects_workflow_mismatch(tmp_path):
    registry = load_job_registry(Path("configs/scheduler/roibang-v2.jobs.example.json"))
    artifact = tmp_path / "wrong_workflow.json"
    _write_json(
        artifact,
        {
            "ok": True,
            "workflow": "daily_learning",
            "execution_enabled": False,
            "external_api_calls": 0,
            "plan": {},
        },
    )

    result = validate_artifact_contract(registry, job_id="roibang-material-sync", artifact_path=artifact)

    assert result["ok"] is False
    assert "workflow mismatch: expected material_sync, got daily_learning" in result["violations"]


def test_validate_artifact_contract_rejects_phase1_safety_value_violations(tmp_path):
    registry = {
        "jobs": [
            {
                "id": "create-execute",
                "name": "Create execute",
                "enabled": True,
                "schedule": {"type": "cron", "expr": "0 9 * * *", "tz": "Asia/Shanghai"},
                "script": {"path": "scripts/run_create_execute.py", "mode": "foreground"},
                "policy": {},
                "result_contract": {
                    "workflow": "create_execute",
                    "artifact_dir": "runs/create_execute",
                    "must_include": ["ok", "workflow", "execution_enabled", "external_api_calls", "actions"],
                    "must_equal": {
                        "execution_enabled": False,
                        "external_api_calls": 0
                    },
                    "must_be_empty": ["actions"],
                },
            }
        ]
    }
    artifact = tmp_path / "unsafe.json"
    _write_json(
        artifact,
        {
            "ok": True,
            "workflow": "create_execute",
            "execution_enabled": True,
            "external_api_calls": 1,
            "actions": [{"action": "create_project"}],
        },
    )

    result = validate_artifact_contract(registry, job_id="create-execute", artifact_path=artifact)

    assert result["ok"] is False
    assert "field execution_enabled must equal False, got True" in result["violations"]
    assert "field external_api_calls must equal 0, got 1" in result["violations"]
    assert "field actions must be empty" in result["violations"]


def test_validate_artifact_contract_can_find_latest_artifact(tmp_path):
    registry = {
        "jobs": [
            {
                "id": "daily",
                "name": "Daily",
                "enabled": True,
                "schedule": {"type": "cron", "expr": "0 9 * * *", "tz": "Asia/Shanghai"},
                "script": {"path": "scripts/run_daily_learning.py", "mode": "foreground"},
                "policy": {},
                "result_contract": {
                    "workflow": "daily_learning",
                    "artifact_dir": "runs/daily_learning",
                    "must_include": ["ok", "workflow", "summary"],
                },
            }
        ]
    }
    _write_json(tmp_path / "runs" / "daily_learning" / "20260101T000000Z.json", {"workflow": "old"})
    latest = tmp_path / "runs" / "daily_learning" / "20260102T000000Z.json"
    _write_json(latest, {"ok": True, "workflow": "daily_learning", "summary": {}})

    result = validate_artifact_contract(registry, job_id="daily", repo_root=tmp_path)

    assert result["ok"] is True
    assert result["artifact_path"] == str(latest)


def test_validate_artifact_contract_accepts_main_create_outputs(tmp_path):
    registry = load_job_registry(Path("configs/scheduler/roibang-v2.jobs.example.json"))
    plan_validate = tmp_path / "create_plan_validate.json"
    first_live = tmp_path / "create_first_live_local_chain.json"
    execute_once = tmp_path / "create_live_execute_once.json"
    execute_report = tmp_path / "create_live_execute_report.json"

    _write_json(
        plan_validate,
        {
            "ok": True,
            "workflow": "create_plan_validate",
            "phase": "phase2_preparation",
            "execution_enabled": False,
            "external_api_calls": 0,
            "status": "passed",
            "summary": {},
            "source_contract": {},
            "violations": [],
            "actions": [],
        },
    )
    _write_json(
        first_live,
        {
            "ok": True,
            "workflow": "create_first_live_local_chain",
            "phase": "phase2_preparation",
            "execution_enabled": False,
            "external_api_calls": 0,
            "status": "ready_for_execute_script",
            "summary": {"ready_for_execute_script": True, "ready_for_live_execute": False},
            "first_live_scope": {},
            "scope_guard": {},
            "chain_steps": [],
            "artifacts": {},
            "preparation_check": {},
            "dry_chain": {},
            "human_next_steps": [],
            "violations": [],
            "actions": [],
        },
    )
    _write_json(
        execute_once,
        {
            "ok": True,
            "workflow": "create_live_execute_once",
            "phase": "phase2_preparation",
            "execution_enabled": False,
            "live_execute_enabled": False,
            "external_api_calls": 0,
            "status": "blocked",
            "blocking_reasons": ["live execute disabled"],
            "transport_call_count": 0,
            "idempotency": {},
            "material_bind_records": [],
            "actions": [],
        },
    )
    _write_json(
        execute_report,
        {
            "ok": True,
            "workflow": "create_live_execute_report",
            "phase": "phase2_preparation",
            "execution_enabled": False,
            "external_api_calls": 0,
            "status": "reported",
            "message": "未执行真实创建",
            "summary": {},
            "create_plan_summary": {},
            "create_plan_contract": {},
            "db_ledger_summary": {},
            "source_artifact_path": "",
            "plan_artifact_path": "",
            "actions": [],
        },
    )

    assert validate_artifact_contract(registry, job_id="roibang-create-plan-validate", artifact_path=plan_validate)["ok"] is True
    assert validate_artifact_contract(registry, job_id="roibang-create-first-live-local-chain", artifact_path=first_live)["ok"] is True
    assert validate_artifact_contract(registry, job_id="roibang-create-live-execute-once", artifact_path=execute_once)["ok"] is True
    assert validate_artifact_contract(registry, job_id="roibang-create-live-execute-report", artifact_path=execute_report)["ok"] is True


def test_validate_run_artifact_cli_exits_nonzero_for_bad_contract(tmp_path, capsys):
    module = _load_validate_script()
    artifact = tmp_path / "bad.json"
    _write_json(artifact, {"ok": True, "workflow": "material_sync"})

    exit_code = module.validate_from_args(
        [
            "--registry",
            "configs/scheduler/roibang-v2.jobs.example.json",
            "--job-id",
            "roibang-material-sync",
            "--artifact",
            str(artifact),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert '"ok": false' in captured.out
    assert "missing required fields" in captured.out
