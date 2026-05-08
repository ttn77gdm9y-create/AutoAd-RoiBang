import importlib.util
import json
from pathlib import Path

from roibang_v2.workflows.strategy_execute import build_strategy_execute, run_strategy_execute_request


def _strategy_approval() -> dict:
    return {
        "workflow": "strategy_approval",
        "phase": "phase1",
        "execution_enabled": False,
        "external_api_calls": 0,
        "status": "recorded",
        "approval_mode": "phase1_record_only",
        "policy_decision": "would_approve",
        "approved": False,
        "execute_allowed": False,
        "approved_for_execute": False,
        "summary": {
            "plan_id": "plan_req_001",
            "target_date": "2026-05-06",
            "candidate_task_count": 1,
            "target_account_count": 1,
            "material_count": 2,
            "violation_count": 0,
        },
        "violations": [],
        "lineage": {
            "strategy_dry_run": {
                "workflow": "strategy_dry_run",
                "artifact_path": "",
                "plan_id": "plan_req_001",
                "target_date": "2026-05-06",
            },
            "strategy_plan": {
                "workflow": "strategy_plan",
                "artifact_path": "",
                "plan_id": "plan_req_001",
                "target_date": "2026-05-06",
            },
        },
        "actions": [],
    }


def _load_execute_script():
    script_path = Path("scripts/run_strategy_execute.py")
    spec = importlib.util.spec_from_file_location("run_strategy_execute", script_path)
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
                "phase": "phase1",
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


def test_strategy_execute_is_hard_blocked_in_phase1_even_when_policy_would_approve():
    result = build_strategy_execute(strategy_approval_artifact=_strategy_approval(), policy={})

    assert result["ok"] is True
    assert result["workflow"] == "strategy_execute"
    assert result["phase"] == "phase1"
    assert result["execution_enabled"] is False
    assert result["external_api_calls"] == 0
    assert result["status"] == "blocked"
    assert result["reason"] == "phase1_execute_disabled"
    assert result["summary"] == {
        "plan_id": "plan_req_001",
        "target_date": "2026-05-06",
        "candidate_task_count": 1,
        "target_account_count": 1,
        "material_count": 2,
        "approval_status": "recorded",
        "policy_decision": "would_approve",
        "execute_allowed": False,
    }
    assert result["lineage"]["strategy_approval"]["plan_id"] == "plan_req_001"
    assert result["lineage"]["strategy_dry_run"]["plan_id"] == "plan_req_001"
    assert result["violations"] == []
    assert result["approved_for_execute"] is False
    assert result["executed_task_count"] == 0
    assert result["actions"] == []


def test_strategy_execute_records_upstream_approval_violations_but_still_blocks():
    approval = _strategy_approval()
    approval["status"] = "blocked"
    approval["violations"] = ["bad approval"]

    result = build_strategy_execute(strategy_approval_artifact=approval, policy={})

    assert result["ok"] is False
    assert result["status"] == "blocked"
    assert result["reason"] == "phase1_execute_disabled"
    assert "strategy approval must be recorded before execute" in result["violations"]
    assert "bad approval" in result["violations"]
    assert result["executed_task_count"] == 0


def test_strategy_execute_blocks_inconsistent_approval_lineage():
    approval = _strategy_approval()
    approval["lineage"]["strategy_plan"]["plan_id"] = "plan_req_old"

    result = build_strategy_execute(strategy_approval_artifact=approval, policy={})

    assert result["ok"] is False
    assert result["status"] == "blocked"
    assert "strategy approval plan_id must match strategy plan plan_id" in result["violations"]


def test_run_strategy_execute_request_writes_artifact(tmp_path: Path):
    result = run_strategy_execute_request(
        {"strategy_execute": {"strategy_approval_artifact": _strategy_approval()}},
        runs_dir=tmp_path / "runs",
    )

    artifact = Path(result["artifact_path"])
    assert artifact.exists()
    saved = json.loads(artifact.read_text(encoding="utf-8"))
    assert saved["workflow"] == "strategy_execute"
    assert saved["status"] == "blocked"
    assert saved["actions"] == []
    assert saved["lineage"]["strategy_approval"]["plan_id"] == "plan_req_001"


def test_strategy_execute_cli_uses_latest_approval_artifact(tmp_path: Path, capsys):
    runs_dir = tmp_path / "runs"
    (runs_dir / "strategy_approval").mkdir(parents=True)
    (runs_dir / "strategy_approval" / "20260505T000000Z.json").write_text(
        json.dumps(_strategy_approval(), ensure_ascii=False),
        encoding="utf-8",
    )
    module = _load_execute_script()

    exit_code = module.run_from_args(["--config", str(_runtime_config(tmp_path))])

    output = json.loads(capsys.readouterr().out)
    artifact = json.loads(Path(output["artifact_path"]).read_text(encoding="utf-8"))
    assert exit_code == 0
    assert output["workflow"] == "strategy_execute"
    assert output["status"] == "blocked"
    assert output["reason"] == "phase1_execute_disabled"
    assert artifact["executed_task_count"] == 0
