import json
import importlib.util
from pathlib import Path

from roibang_v2.workflows.strategy_preflight import (
    build_strategy_preflight,
    run_strategy_preflight_request,
)


def _load_preflight_script():
    script_path = Path("scripts/run_strategy_preflight.py")
    spec = importlib.util.spec_from_file_location("run_strategy_preflight", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


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
            "dry_run": {"status": "draft_only", "payloads": []},
            "approval": {"status": "disabled_in_phase1"},
            "execute": {"status": "disabled_in_phase1"},
            "actions": [],
        },
    }


def test_strategy_preflight_passes_phase1_plan_only_material_provision():
    result = build_strategy_preflight(_strategy_plan())

    assert result["ok"] is True
    assert result["workflow"] == "strategy_preflight"
    assert result["phase"] == "phase1"
    assert result["execution_enabled"] is False
    assert result["external_api_calls"] == 0
    assert result["status"] == "passed"
    assert result["summary"] == {
        "plan_id": "plan_req_001",
        "target_date": "2026-05-06",
        "recommendation_count": 1,
        "material_provision_recommendation_count": 1,
        "violation_count": 0,
    }
    assert result["lineage"]["strategy_plan"]["plan_id"] == "plan_req_001"
    assert result["lineage"]["strategy_plan"]["target_date"] == "2026-05-06"
    assert result["approved_for_execute"] is False
    assert result["actions"] == []


def test_strategy_preflight_rejects_live_payloads_and_missing_material_ids():
    plan = _strategy_plan()
    recommendation = plan["plan"]["strategy"]["recommendations"][0]
    recommendation["missing_material_ids"] = []
    plan["plan"]["dry_run"]["payloads"] = [{"endpoint": "/open_api/2/file/video/bind/"}]
    plan["plan"]["actions"] = [{"action": "bind_material"}]

    result = build_strategy_preflight(plan)

    assert result["ok"] is False
    assert result["status"] == "failed"
    assert "strategy plan actions must be empty in phase1" in result["violations"]
    assert "dry_run payloads must be empty in phase1" in result["violations"]
    assert "material provision recommendation missing material ids" in result["violations"]


def test_run_strategy_preflight_request_writes_artifact(tmp_path: Path):
    result = run_strategy_preflight_request(
        {"strategy_preflight": {"strategy_plan_artifact": _strategy_plan()}},
        runs_dir=tmp_path / "runs",
    )

    artifact = Path(result["artifact_path"])
    assert artifact.exists()
    saved = json.loads(artifact.read_text(encoding="utf-8"))
    assert saved["workflow"] == "strategy_preflight"
    assert saved["status"] == "passed"
    assert saved["lineage"]["strategy_plan"]["plan_id"] == "plan_req_001"


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


def test_strategy_preflight_cli_accepts_explicit_strategy_plan_artifact(tmp_path: Path, capsys):
    plan_path = tmp_path / "strategy-plan.json"
    plan_path.write_text(json.dumps(_strategy_plan(), ensure_ascii=False), encoding="utf-8")
    module = _load_preflight_script()

    exit_code = module.run_from_args(
        [
            "--config",
            str(_runtime_config(tmp_path)),
            "--strategy-plan-artifact",
            str(plan_path),
        ]
    )

    output = json.loads(capsys.readouterr().out)
    artifact = Path(output["artifact_path"])
    assert exit_code == 0
    assert output["status"] == "passed"
    assert output["summary"]["violation_count"] == 0
    assert artifact.exists()
    saved = json.loads(artifact.read_text(encoding="utf-8"))
    assert saved["lineage"]["strategy_plan"]["artifact_path"] == str(plan_path)


def test_strategy_preflight_cli_uses_latest_strategy_plan_artifact(tmp_path: Path, capsys):
    runs_dir = tmp_path / "runs"
    strategy_dir = runs_dir / "strategy_plan"
    strategy_dir.mkdir(parents=True)
    (strategy_dir / "20260505T000000Z.json").write_text(json.dumps(_strategy_plan(), ensure_ascii=False), encoding="utf-8")
    module = _load_preflight_script()

    exit_code = module.run_from_args(["--config", str(_runtime_config(tmp_path))])

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["workflow"] == "strategy_preflight"
    assert output["summary"]["plan_id"] == "plan_req_001"
