import json
import importlib.util
import sqlite3
from pathlib import Path

from roibang_v2.db.bootstrap import bootstrap_database
from roibang_v2.reports.snapshot import import_report_snapshot_file
from roibang_v2.workflows.daily_learning import build_daily_learning_artifact
from roibang_v2.workflows.strategy_plan import build_strategy_plan, run_strategy_plan_request


def _load_strategy_script():
    script_path = Path("scripts/run_strategy_plan.py")
    spec = importlib.util.spec_from_file_location("run_strategy_plan", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _seed_daily_learning(db_path: Path) -> dict:
    import_report_snapshot_file("data/fixtures/report-snapshot.sample.json", db_path=db_path)
    return build_daily_learning_artifact(
        db_path=db_path,
        policy={
            "target_date": "2026-05-05",
            "min_cost_for_signal": 50,
            "min_conversions_for_signal": 3,
            "low_roi_threshold": 0.4,
            "top_material_limit": 10,
        },
    )


def test_builds_phase1_strategy_plan_from_learning_artifact(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)
    learning = _seed_daily_learning(db_path)

    plan = build_strategy_plan(
        request={
            "request_id": "req_20260505_yzt_review",
            "target_date": "2026-05-05",
            "objective": "review_daily_learning",
        },
        learning_artifact=learning,
        policy={
            "require_preflight": True,
            "require_dry_run": True,
        },
    )

    assert plan["plan_id"] == "plan_req_20260505_yzt_review"
    assert plan["phase"] == "phase1"
    assert plan["execution_enabled"] is False
    assert plan["actions"] == []
    assert plan["strategy"]["source"] == "daily_learning"
    assert plan["strategy"]["recommendations"][0]["recommendation_type"] == "investigate_account"
    assert plan["preflight"]["status"] == "draft_only"
    assert plan["dry_run"]["status"] == "draft_only"
    assert "approval" not in plan
    assert plan["execute"]["status"] == "disabled_in_phase1"


def test_builds_strategy_plan_with_material_source_provision_recommendations(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)
    learning = _seed_daily_learning(db_path)
    material_source = {
        "workflow": "material_source",
        "phase": "phase1",
        "execution_enabled": False,
        "external_api_calls": 0,
        "plan": {
            "status": "needs_provision",
            "product": "勇者突进",
            "source_advertiser_id": "1856647522964490",
            "target_advertiser_id": "1850000000000001",
            "provision_needed": 2,
            "missing_materials": [
                {"material_id": "m003", "video_id": "v003", "name": "素材3", "score": 8.0},
                {"material_id": "m004", "video_id": "v004", "name": "素材4", "score": 7.0},
            ],
        },
    }

    plan = build_strategy_plan(
        request={
            "request_id": "req_20260505_yzt_review",
            "target_date": "2026-05-05",
            "objective": "review_daily_learning",
        },
        learning_artifact=learning,
        material_source_artifact=material_source,
        policy={
            "require_preflight": True,
            "require_dry_run": True,
        },
    )

    provision = [
        item
        for item in plan["strategy"]["recommendations"]
        if item["recommendation_type"] == "plan_material_provision"
    ]
    assert provision == [
        {
            "recommendation_type": "plan_material_provision",
            "product": "勇者突进",
            "source_advertiser_id": "1856647522964490",
            "target_advertiser_id": "1850000000000001",
            "provision_needed": 2,
            "missing_material_ids": ["m003", "m004"],
            "evidence": {
                "status": "needs_provision",
                "missing_materials": [
                    {"material_id": "m003", "video_id": "v003", "name": "素材3", "score": 8.0},
                    {"material_id": "m004", "video_id": "v004", "name": "素材4", "score": 7.0},
                ],
            },
            "allowed_phase1_output": "material_provision_plan_only",
        }
    ]
    assert plan["actions"] == []
    assert plan["dry_run"]["payloads"] == []


def test_strategy_plan_request_writes_sqlite_and_run_artifact(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)
    learning = _seed_daily_learning(db_path)

    result = run_strategy_plan_request(
        {
            "strategy_request": {
                "request_id": "req_20260505_yzt_review",
                "target_date": "2026-05-05",
                "objective": "review_daily_learning",
            }
        },
        db_path=db_path,
        runs_dir=tmp_path / "runs",
        learning_artifact=learning,
        policy={
            "require_preflight": True,
            "require_dry_run": True,
        },
    )

    artifact = Path(result["artifact_path"])
    assert artifact.exists()
    assert result["ok"] is True
    assert result["plan"]["execution_enabled"] is False

    with sqlite3.connect(db_path) as conn:
        row = conn.execute("SELECT plan_id, phase, execution_enabled, plan_json FROM strategy_plans").fetchone()

    assert row[0] == "plan_req_20260505_yzt_review"
    assert row[1] == "phase1"
    assert row[2] == 0
    saved_plan = json.loads(row[3])
    assert saved_plan["execute"]["status"] == "disabled_in_phase1"


def test_strategy_plan_cli_accepts_material_source_artifact(tmp_path: Path, capsys):
    db_path = tmp_path / "roibang.sqlite3"
    runs_dir = tmp_path / "runs"
    request_path = tmp_path / "request.json"
    policy_path = tmp_path / "policy.json"
    learning_path = tmp_path / "learning.json"
    material_source_path = tmp_path / "material-source.json"
    config_path = tmp_path / "runtime.json"
    bootstrap_database(db_path)
    learning = _seed_daily_learning(db_path)
    request_path.write_text(
        json.dumps(
            {
                "strategy_request": {
                    "request_id": "req_20260505_yzt_review",
                    "target_date": "2026-05-05",
                    "objective": "review_daily_learning",
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    policy_path.write_text(
        json.dumps(
            {
                "strategy_plan": {
                    "require_preflight": True,
                    "require_dry_run": True,
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    learning_path.write_text(json.dumps(learning, ensure_ascii=False), encoding="utf-8")
    material_source_path.write_text(
        json.dumps(
            {
                "workflow": "material_source",
                "plan": {
                    "status": "needs_provision",
                    "product": "勇者突进",
                    "source_advertiser_id": "1856647522964490",
                    "target_advertiser_id": "1850000000000001",
                    "provision_needed": 1,
                    "missing_materials": [{"material_id": "m003", "video_id": "v003"}],
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    config_path.write_text(
        json.dumps(
            {
                "environment": "test",
                "phase": "phase1",
                "database_path": str(db_path),
                "runs_dir": str(runs_dir),
                "fixtures_dir": "data/fixtures",
                "external_api_enabled": False,
                "execution_enabled": False,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    module = _load_strategy_script()

    exit_code = module.run_from_args(
        [
            "--config",
            str(config_path),
            "--request",
            str(request_path),
            "--policy",
            str(policy_path),
            "--learning-artifact",
            str(learning_path),
            "--material-source-artifact",
            str(material_source_path),
        ]
    )

    output = json.loads(capsys.readouterr().out)
    artifact = json.loads(Path(output["artifact_path"]).read_text(encoding="utf-8"))
    assert exit_code == 0
    assert artifact["plan"]["strategy"]["source"] == "daily_learning+material_source"
    assert any(
        item["recommendation_type"] == "plan_material_provision"
        for item in artifact["plan"]["strategy"]["recommendations"]
    )


def test_strategy_plan_cli_uses_latest_material_source_artifact_when_present(tmp_path: Path, capsys):
    db_path = tmp_path / "roibang.sqlite3"
    runs_dir = tmp_path / "runs"
    request_path = tmp_path / "request.json"
    policy_path = tmp_path / "policy.json"
    config_path = tmp_path / "runtime.json"
    bootstrap_database(db_path)
    learning = _seed_daily_learning(db_path)
    (runs_dir / "daily_learning").mkdir(parents=True)
    (runs_dir / "material_source").mkdir(parents=True)
    (runs_dir / "daily_learning" / "20260505T000000Z.json").write_text(
        json.dumps(learning, ensure_ascii=False),
        encoding="utf-8",
    )
    (runs_dir / "material_source" / "20260505T000000Z.json").write_text(
        json.dumps(
            {
                "workflow": "material_source",
                "plan": {
                    "status": "needs_provision",
                    "product": "勇者突进",
                    "source_advertiser_id": "1856647522964490",
                    "target_advertiser_id": "1850000000000001",
                    "provision_needed": 1,
                    "missing_materials": [{"material_id": "m009"}],
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    request_path.write_text(
        json.dumps({"strategy_request": {"request_id": "req_auto_material", "target_date": "2026-05-05"}}, ensure_ascii=False),
        encoding="utf-8",
    )
    policy_path.write_text(json.dumps({"strategy_plan": {}}, ensure_ascii=False), encoding="utf-8")
    config_path.write_text(
        json.dumps(
            {
                "environment": "test",
                "phase": "phase1",
                "database_path": str(db_path),
                "runs_dir": str(runs_dir),
                "fixtures_dir": "data/fixtures",
                "external_api_enabled": False,
                "execution_enabled": False,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    module = _load_strategy_script()

    exit_code = module.run_from_args(
        [
            "--config",
            str(config_path),
            "--request",
            str(request_path),
            "--policy",
            str(policy_path),
        ]
    )

    output = json.loads(capsys.readouterr().out)
    artifact = json.loads(Path(output["artifact_path"]).read_text(encoding="utf-8"))
    assert exit_code == 0
    provision = [
        item
        for item in artifact["plan"]["strategy"]["recommendations"]
        if item["recommendation_type"] == "plan_material_provision"
    ]
    assert provision[0]["missing_material_ids"] == ["m009"]
