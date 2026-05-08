import importlib.util
import json
from pathlib import Path

from roibang_v2.workflows.strategy_dry_run import build_strategy_dry_run, run_strategy_dry_run_request


def _strategy_plan() -> dict:
    return {
        "workflow": "strategy_plan",
        "phase": "phase1",
        "execution_enabled": False,
        "external_api_calls": 0,
        "plan": {
            "plan_id": "plan_req_001",
            "target_date": "2026-05-06",
            "phase": "phase1",
            "execution_enabled": False,
            "external_api_calls": 0,
            "strategy": {
                "recommendations": [
                    {
                        "recommendation_type": "plan_material_provision",
                        "product": "勇者突进",
                        "source_advertiser_id": "1856647522964490",
                        "target_advertiser_id": "1850000000000001",
                        "missing_material_ids": ["m003", "m004"],
                        "allowed_phase1_output": "material_provision_plan_only",
                    }
                ]
            },
            "actions": [],
        },
    }


def _strategy_preflight(*, passed: bool = True) -> dict:
    return {
        "workflow": "strategy_preflight",
        "phase": "phase1",
        "execution_enabled": False,
        "external_api_calls": 0,
        "status": "passed" if passed else "failed",
        "summary": {
            "plan_id": "plan_req_001",
            "target_date": "2026-05-06",
            "violation_count": 0 if passed else 1,
        },
        "lineage": {
            "strategy_plan": {
                "workflow": "strategy_plan",
                "artifact_path": "",
                "plan_id": "plan_req_001",
                "target_date": "2026-05-06",
            }
        },
        "violations": [] if passed else ["bad plan"],
        "approved_for_execute": False,
    }


def _load_dry_run_script():
    script_path = Path("scripts/run_strategy_dry_run.py")
    spec = importlib.util.spec_from_file_location("run_strategy_dry_run", script_path)
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


def test_strategy_dry_run_builds_non_executable_material_provision_candidates():
    result = build_strategy_dry_run(
        strategy_plan_artifact=_strategy_plan(),
        strategy_preflight_artifact=_strategy_preflight(),
        policy={"max_materials_per_dry_run": 10, "max_target_accounts_per_dry_run": 5},
    )

    assert result["ok"] is True
    assert result["workflow"] == "strategy_dry_run"
    assert result["phase"] == "phase1"
    assert result["execution_enabled"] is False
    assert result["external_api_calls"] == 0
    assert result["status"] == "simulated"
    assert result["summary"] == {
        "plan_id": "plan_req_001",
        "target_date": "2026-05-06",
        "candidate_task_count": 1,
        "target_account_count": 1,
        "material_count": 2,
        "violation_count": 0,
    }
    assert result["lineage"]["strategy_plan"]["plan_id"] == "plan_req_001"
    assert result["lineage"]["strategy_preflight"]["plan_id"] == "plan_req_001"
    assert result["candidate_tasks"] == [
        {
            "task_type": "material_provision_candidate",
            "product": "勇者突进",
            "source_advertiser_id": "1856647522964490",
            "target_advertiser_id": "1850000000000001",
            "material_ids": ["m003", "m004"],
            "executable": False,
            "live_api_payloads": [],
            "allowed_phase1_output": "dry_run_only",
        }
    ]
    assert result["approved_for_execute"] is False
    assert result["actions"] == []


def test_strategy_dry_run_fails_closed_when_preflight_failed():
    result = build_strategy_dry_run(
        strategy_plan_artifact=_strategy_plan(),
        strategy_preflight_artifact=_strategy_preflight(passed=False),
        policy={},
    )

    assert result["ok"] is False
    assert result["status"] == "blocked"
    assert result["candidate_tasks"] == []
    assert "strategy preflight must pass before dry-run" in result["violations"]


def test_strategy_dry_run_blocks_mismatched_preflight_lineage():
    preflight = _strategy_preflight()
    preflight["lineage"]["strategy_plan"]["plan_id"] = "plan_req_old"

    result = build_strategy_dry_run(
        strategy_plan_artifact=_strategy_plan(),
        strategy_preflight_artifact=preflight,
        policy={},
    )

    assert result["ok"] is False
    assert result["status"] == "blocked"
    assert "strategy plan plan_id must match strategy preflight plan_id" in result["violations"]


def test_strategy_dry_run_blocks_mismatched_preflight_summary():
    preflight = _strategy_preflight()
    preflight["summary"]["target_date"] = "2026-05-05"

    result = build_strategy_dry_run(
        strategy_plan_artifact=_strategy_plan(),
        strategy_preflight_artifact=preflight,
        policy={},
    )

    assert result["ok"] is False
    assert result["status"] == "blocked"
    assert "strategy plan target_date must match strategy preflight target_date" in result["violations"]


def test_strategy_dry_run_enforces_policy_limits():
    result = build_strategy_dry_run(
        strategy_plan_artifact=_strategy_plan(),
        strategy_preflight_artifact=_strategy_preflight(),
        policy={"max_materials_per_dry_run": 1, "max_target_accounts_per_dry_run": 5},
    )

    assert result["ok"] is False
    assert result["status"] == "blocked"
    assert "dry-run material count exceeds policy limit" in result["violations"]


def test_run_strategy_dry_run_request_writes_artifact(tmp_path: Path):
    result = run_strategy_dry_run_request(
        {
            "strategy_dry_run": {
                "strategy_plan_artifact": _strategy_plan(),
                "strategy_preflight_artifact": _strategy_preflight(),
                "policy": {"max_materials_per_dry_run": 10},
            }
        },
        runs_dir=tmp_path / "runs",
    )

    artifact = Path(result["artifact_path"])
    assert artifact.exists()
    saved = json.loads(artifact.read_text(encoding="utf-8"))
    assert saved["workflow"] == "strategy_dry_run"
    assert saved["status"] == "simulated"
    assert saved["lineage"]["strategy_plan"]["plan_id"] == "plan_req_001"


def test_strategy_dry_run_cli_uses_latest_artifacts(tmp_path: Path, capsys):
    runs_dir = tmp_path / "runs"
    (runs_dir / "strategy_plan").mkdir(parents=True)
    (runs_dir / "strategy_preflight").mkdir(parents=True)
    (runs_dir / "strategy_plan" / "20260505T000000Z.json").write_text(
        json.dumps(_strategy_plan(), ensure_ascii=False),
        encoding="utf-8",
    )
    (runs_dir / "strategy_preflight" / "20260505T000000Z.json").write_text(
        json.dumps(_strategy_preflight(), ensure_ascii=False),
        encoding="utf-8",
    )
    module = _load_dry_run_script()

    exit_code = module.run_from_args(["--config", str(_runtime_config(tmp_path))])

    output = json.loads(capsys.readouterr().out)
    artifact = json.loads(Path(output["artifact_path"]).read_text(encoding="utf-8"))
    assert exit_code == 0
    assert output["status"] == "simulated"
    assert artifact["candidate_tasks"][0]["executable"] is False
