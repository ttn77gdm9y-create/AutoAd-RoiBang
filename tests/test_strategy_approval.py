import importlib.util
import json
from pathlib import Path

from roibang_v2.workflows.strategy_approval import build_strategy_approval, run_strategy_approval_request


def _strategy_dry_run(*, ok: bool = True) -> dict:
    return {
        "workflow": "strategy_dry_run",
        "phase": "phase1",
        "execution_enabled": False,
        "external_api_calls": 0,
        "status": "simulated" if ok else "blocked",
        "summary": {
            "plan_id": "plan_req_001",
            "target_date": "2026-05-06",
            "candidate_task_count": 1 if ok else 0,
            "target_account_count": 1 if ok else 0,
            "material_count": 2 if ok else 0,
            "violation_count": 0 if ok else 1,
        },
        "candidate_tasks": [
            {
                "task_type": "material_provision_candidate",
                "target_advertiser_id": "1850000000000001",
                "source_advertiser_id": "1856647522964490",
                "material_ids": ["m003", "m004"],
                "executable": False,
                "live_api_payloads": [],
            }
        ]
        if ok
        else [],
        "violations": [] if ok else ["bad dry run"],
        "lineage": {
            "strategy_plan": {
                "workflow": "strategy_plan",
                "artifact_path": "",
                "plan_id": "plan_req_001",
                "target_date": "2026-05-06",
            },
            "strategy_preflight": {
                "workflow": "strategy_preflight",
                "artifact_path": "",
                "plan_id": "plan_req_001",
                "target_date": "2026-05-06",
            },
        },
        "approved_for_execute": False,
        "actions": [],
    }


def _load_approval_script():
    script_path = Path("scripts/run_strategy_approval.py")
    spec = importlib.util.spec_from_file_location("run_strategy_approval", script_path)
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


def test_strategy_approval_records_policy_review_but_disallows_execute_in_phase1():
    result = build_strategy_approval(
        strategy_dry_run_artifact=_strategy_dry_run(),
        policy={"auto_approve_phase1": True, "max_materials_per_approval": 10, "max_target_accounts_per_approval": 5},
    )

    assert result["ok"] is True
    assert result["workflow"] == "strategy_approval"
    assert result["phase"] == "phase1"
    assert result["execution_enabled"] is False
    assert result["external_api_calls"] == 0
    assert result["status"] == "recorded"
    assert result["approval_mode"] == "phase1_record_only"
    assert result["policy_decision"] == "would_approve"
    assert result["approved"] is False
    assert result["execute_allowed"] is False
    assert result["approved_for_execute"] is False
    assert result["actions"] == []
    assert result["summary"] == {
        "plan_id": "plan_req_001",
        "target_date": "2026-05-06",
        "candidate_task_count": 1,
        "target_account_count": 1,
        "material_count": 2,
        "violation_count": 0,
    }
    assert result["lineage"]["strategy_dry_run"]["plan_id"] == "plan_req_001"
    assert result["lineage"]["strategy_plan"]["plan_id"] == "plan_req_001"


def test_strategy_approval_blocks_failed_dry_run():
    result = build_strategy_approval(strategy_dry_run_artifact=_strategy_dry_run(ok=False), policy={})

    assert result["ok"] is False
    assert result["status"] == "blocked"
    assert result["policy_decision"] == "reject"
    assert result["execute_allowed"] is False
    assert "strategy dry-run must be simulated before approval" in result["violations"]


def test_strategy_approval_blocks_inconsistent_dry_run_lineage():
    dry_run = _strategy_dry_run()
    dry_run["lineage"]["strategy_preflight"]["target_date"] = "2026-05-05"

    result = build_strategy_approval(strategy_dry_run_artifact=dry_run, policy={})

    assert result["ok"] is False
    assert result["status"] == "blocked"
    assert "strategy dry-run target_date must match strategy preflight target_date" in result["violations"]


def test_strategy_approval_enforces_policy_limits():
    result = build_strategy_approval(
        strategy_dry_run_artifact=_strategy_dry_run(),
        policy={"max_materials_per_approval": 1, "max_target_accounts_per_approval": 5},
    )

    assert result["ok"] is False
    assert result["status"] == "blocked"
    assert result["policy_decision"] == "reject"
    assert "approval material count exceeds policy limit" in result["violations"]


def test_run_strategy_approval_request_writes_artifact(tmp_path: Path):
    result = run_strategy_approval_request(
        {
            "strategy_approval": {
                "strategy_dry_run_artifact": _strategy_dry_run(),
                "policy": {"auto_approve_phase1": True},
            }
        },
        runs_dir=tmp_path / "runs",
    )

    artifact = Path(result["artifact_path"])
    assert artifact.exists()
    saved = json.loads(artifact.read_text(encoding="utf-8"))
    assert saved["workflow"] == "strategy_approval"
    assert saved["execute_allowed"] is False
    assert saved["lineage"]["strategy_dry_run"]["plan_id"] == "plan_req_001"


def test_strategy_approval_cli_uses_latest_dry_run_artifact(tmp_path: Path, capsys):
    runs_dir = tmp_path / "runs"
    (runs_dir / "strategy_dry_run").mkdir(parents=True)
    (runs_dir / "strategy_dry_run" / "20260505T000000Z.json").write_text(
        json.dumps(_strategy_dry_run(), ensure_ascii=False),
        encoding="utf-8",
    )
    module = _load_approval_script()

    exit_code = module.run_from_args(["--config", str(_runtime_config(tmp_path))])

    output = json.loads(capsys.readouterr().out)
    artifact = json.loads(Path(output["artifact_path"]).read_text(encoding="utf-8"))
    assert exit_code == 0
    assert output["workflow"] == "strategy_approval"
    assert output["execute_allowed"] is False
    assert artifact["policy_decision"] in {"would_approve", "record_only"}
