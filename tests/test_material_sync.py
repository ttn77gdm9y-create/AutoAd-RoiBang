import sqlite3
from pathlib import Path

from roibang_v2.db.bootstrap import bootstrap_database
from roibang_v2.materials.library import import_material_cache_file
from roibang_v2.workflows.material_sync import build_material_supplement_plan, run_material_sync_request


def test_imports_local_material_cache_and_plans_supplement(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)

    imported = import_material_cache_file(
        Path("data/fixtures/material-cache.sample.json"),
        db_path=db_path,
    )

    plan = build_material_supplement_plan(
        db_path=db_path,
        advertiser_id="1850000000000001",
        policy={
            "available_statuses": ["APPROVED"],
            "target_available_count": 5,
            "material_type": "video",
        },
    )

    with sqlite3.connect(db_path) as conn:
        material_count = conn.execute("SELECT COUNT(*) FROM materials").fetchone()[0]
        account_count = conn.execute("SELECT COUNT(*) FROM account_materials").fetchone()[0]

    assert imported == {
        "ok": True,
        "advertiser_id": "1850000000000001",
        "materials_imported": 2,
        "account_materials_imported": 2,
        "external_api_calls": 0,
    }
    assert material_count == 2
    assert account_count == 2
    assert plan["status"] == "needs_supplement"
    assert plan["available_count"] == 2
    assert plan["supplement_needed"] == 3
    assert plan["execution_enabled"] is False
    assert plan["external_api_calls"] == 0


def test_material_sync_request_writes_phase1_artifact(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)

    result = run_material_sync_request(
        {
            "material_sync": {
                "kind": "local_cache",
                "cache_file": "data/fixtures/material-cache.sample.json",
                "advertiser_id": "1850000000000001",
                "policy": {
                    "available_statuses": ["APPROVED"],
                    "target_available_count": 5,
                    "material_type": "video",
                },
            }
        },
        db_path=db_path,
        runs_dir=tmp_path / "runs",
    )

    artifact = Path(result["artifact_path"])
    assert artifact.exists()
    assert result["ok"] is True
    assert result["import"]["external_api_calls"] == 0
    assert result["plan"]["supplement_needed"] == 3
    assert result["plan"]["actions"] == []
