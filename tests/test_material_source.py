import sqlite3
from pathlib import Path

from roibang_v2.db.bootstrap import bootstrap_database
from roibang_v2.materials.library import import_material_cache_file
from roibang_v2.materials.product_source import import_product_source_file
from roibang_v2.workflows.material_source import (
    build_material_provision_plan,
    build_material_source_preflight,
    run_material_source_request,
)


def test_imports_product_source_materials(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)

    result = import_product_source_file("data/fixtures/product-source-materials.sample.json", db_path=db_path)

    with sqlite3.connect(db_path) as conn:
        source_count = conn.execute("SELECT COUNT(*) FROM product_source_materials").fetchone()[0]
        material_count = conn.execute("SELECT COUNT(*) FROM materials").fetchone()[0]
        source_row = conn.execute(
            """
            SELECT signature, duration, file_size, create_time, tag_ids_json,
                   is_active, first_seen_at, last_seen_at
            FROM product_source_materials
            WHERE material_id = 'm001'
            """
        ).fetchone()

    assert result == {
        "ok": True,
        "product": "勇者突进",
        "source_advertiser_id": "1856647522964490",
        "organization_id": "1851650746645060",
        "materials_imported": 4,
        "product_source_materials_imported": 4,
        "inactive_product_source_materials": 0,
        "external_api_calls": 0,
    }
    assert source_count == 4
    assert material_count == 4
    assert source_row[:6] == (
        "sig-m001",
        12.5,
        1024.0,
        "2026-05-01 10:00:00",
        '["1004", "1"]',
        1,
    )
    assert source_row[6]
    assert source_row[6] == source_row[7]


def test_builds_phase1_material_provision_plan_from_source_account(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)
    import_material_cache_file("data/fixtures/material-cache.sample.json", db_path=db_path)
    import_product_source_file("data/fixtures/product-source-materials.sample.json", db_path=db_path)

    plan = build_material_provision_plan(
        db_path=db_path,
        product="勇者突进",
        source_advertiser_id="1856647522964490",
        organization_id="1851650746645060",
        target_advertiser_id="1850000000000001",
        required_material_count=4,
        material_type="video",
        available_statuses=["APPROVED"],
    )

    assert plan["phase"] == "phase1"
    assert plan["execution_enabled"] is False
    assert plan["external_api_calls"] == 0
    assert plan["status"] == "needs_provision"
    assert plan["source_advertiser_id"] == "1856647522964490"
    assert plan["target_advertiser_id"] == "1850000000000001"
    assert plan["selected_count"] == 4
    assert plan["target_existing_count"] == 2
    assert plan["provision_needed"] == 2
    assert [item["material_id"] for item in plan["missing_materials"]] == ["m003", "m004"]
    assert plan["actions"] == []


def test_material_source_request_writes_run_artifact(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)
    import_material_cache_file("data/fixtures/material-cache.sample.json", db_path=db_path)

    result = run_material_source_request(
        {
            "material_source": {
                "kind": "local_product_source",
                "source_file": "data/fixtures/product-source-materials.sample.json",
                "product": "勇者突进",
                "source_advertiser_id": "1856647522964490",
                "organization_id": "1851650746645060",
                "target_advertiser_id": "1850000000000001",
                "required_material_count": 4,
                "material_type": "video",
                "available_statuses": ["APPROVED"],
            }
        },
        db_path=db_path,
        runs_dir=tmp_path / "runs",
    )

    artifact = Path(result["artifact_path"])
    assert artifact.exists()
    assert result["ok"] is True
    assert result["import"]["external_api_calls"] == 0
    assert result["plan"]["provision_needed"] == 2
    assert result["plan"]["actions"] == []


def test_openapi_material_source_preflight_plans_source_account_reads():
    preflight = build_material_source_preflight(
        {
            "material_source": {
                "kind": "openapi_source_materials",
                "enabled": False,
                "product": "勇者突进",
                "source_accounts": [
                    {
                        "source_advertiser_id": "1856647522964490",
                        "organization_id": "1851650746645060",
                    }
                ],
                "target_advertiser_id": "1850000000000001",
                "required_material_count": 4,
                "material_type": "video",
                "available_statuses": ["APPROVED"],
                "page_size": 100,
            }
        }
    )

    assert preflight["ok"] is True
    assert preflight["execution_enabled"] is False
    assert preflight["external_api_calls"] == 0
    assert preflight["summary"] == {
        "kind": "openapi_source_materials",
        "enabled": False,
        "source_account_count": 1,
        "planned_request_count": 1,
        "target_advertiser_id": "1850000000000001",
    }
    planned = preflight["plan"]["requests"][0]
    assert planned["endpoint_key"] == "video_material_get"
    assert planned["query_params"]["advertiser_id"] == "1856647522964490"


def test_openapi_material_source_disabled_writes_preflight_artifact_without_transport(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)

    result = run_material_source_request(
        {
            "material_source": {
                "kind": "openapi_source_materials",
                "enabled": False,
                "product": "勇者突进",
                "source_accounts": [{"source_advertiser_id": "1856647522964490"}],
                "target_advertiser_id": "1850000000000001",
                "required_material_count": 4,
            }
        },
        db_path=db_path,
        runs_dir=tmp_path / "runs",
    )

    assert result["ok"] is True
    assert result["skipped"] is True
    assert result["external_api_calls"] == 0
    assert result["preflight"]["summary"]["planned_request_count"] == 1
    assert Path(result["artifact_path"]).exists()


def test_openapi_material_source_imports_readonly_source_materials(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)

    calls: list[dict] = []

    def transport(request: dict) -> dict:
        calls.append(request)
        return {
            "code": 0,
            "data": {
                "page_info": {"page": 1, "page_size": 100, "total_number": 2, "total_page": 1},
                "list": [
                    {
                        "material_id": "m101",
                        "video_id": "v101",
                        "filename": "勇者素材101.mp4",
                        "file_type": "video",
                        "review_status": "APPROVED",
                        "stat_cost": "321.5",
                    },
                    {
                        "material_id": "m102",
                        "vid": "v102",
                        "material_name": "勇者素材102",
                        "media_review_status": "APPROVED",
                        "score": "9.8",
                    },
                ],
            },
        }

    result = run_material_source_request(
        {
            "material_source": {
                "kind": "openapi_source_materials",
                "enabled": True,
                "product": "勇者突进",
                "source_accounts": [
                    {
                        "source_advertiser_id": "1856647522964490",
                        "organization_id": "1851650746645060",
                    }
                ],
                "target_advertiser_id": "1850000000000001",
                "required_material_count": 2,
                "material_type": "video",
                "available_statuses": ["APPROVED"],
                "page_size": 100,
            }
        },
        db_path=db_path,
        runs_dir=tmp_path / "runs",
        transport=transport,
    )

    with sqlite3.connect(db_path) as conn:
        source_count = conn.execute("SELECT COUNT(*) FROM product_source_materials").fetchone()[0]
        account_count = conn.execute("SELECT COUNT(*) FROM account_materials").fetchone()[0]

    assert len(calls) == 1
    assert calls[0]["endpoint_key"] == "video_material_get"
    assert result["ok"] is True
    assert result["external_api_calls"] == 1
    assert result["imports"][0]["product_source_materials_imported"] == 2
    assert result["plans"][0]["selected_count"] == 2
    assert result["plans"][0]["provision_needed"] == 2
    assert source_count == 2
    assert account_count == 2
