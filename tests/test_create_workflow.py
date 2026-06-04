import importlib.util
import json
import re
import sqlite3
from collections import Counter
from pathlib import Path

import pytest

from roibang_v2.db.bootstrap import bootstrap_database
from roibang_v2.workflows.create_dry_run import build_create_dry_run, run_create_dry_run_request
from roibang_v2.workflows.create_execute import run_create_execute_request
from roibang_v2.workflows.create_provider_adapter import (
    build_provider_payload_drafts,
    provider_adapter_contract,
)
from roibang_v2.workflows.create_provider_field_map import default_provider_field_map
from roibang_v2.workflows.create_provider_id_ledger import (
    record_create_provider_id,
    resolve_create_lookup_placeholders,
)
from roibang_v2.workflows.create_provider_field_map_check import (
    build_create_provider_field_map_check,
    run_create_provider_field_map_check_request,
)
from roibang_v2.workflows.create_phase2_provider_mapping_prep import (
    build_create_phase2_provider_mapping_prep,
    run_create_phase2_provider_mapping_prep_request,
)
from roibang_v2.workflows.create_provider_evidence_review import (
    build_create_provider_evidence_review,
    run_create_provider_evidence_review_request,
)
from roibang_v2.workflows.create_field_mapping_review_pack import (
    build_create_field_mapping_review_pack,
    run_create_field_mapping_review_pack_request,
)
from roibang_v2.workflows.create_template_slot_review_pack import (
    build_create_template_slot_review_pack,
    run_create_template_slot_review_pack_request,
)
from roibang_v2.workflows.create_phase2_template_slot_prep import (
    build_create_phase2_template_slot_prep,
    run_create_phase2_template_slot_prep_request,
)
from roibang_v2.workflows.create_phase2_template_confirmation_pack import (
    build_create_phase2_template_confirmation_pack,
    run_create_phase2_template_confirmation_pack_request,
)
from roibang_v2.workflows.create_phase2_project_naming_prep import (
    build_create_phase2_project_naming_prep,
    run_create_phase2_project_naming_prep_request,
)
from roibang_v2.workflows.create_phase2_preparation_summary import (
    build_create_phase2_preparation_summary,
    run_create_phase2_preparation_summary_request,
)
from roibang_v2.workflows.create_provider_readiness import provider_readiness_contract
from roibang_v2.workflows.create_preflight import build_create_preflight, run_create_preflight_request
from roibang_v2.workflows.create_request import run_create_request
from roibang_v2.workflows.create_strategy_plan import build_create_strategy_plan, run_create_strategy_plan_request

def _load_script(name: str):
    script_path = Path(f"scripts/{name}.py")
    if not script_path.exists():
        pytest.skip(f"{script_path} is disabled")
    spec = importlib.util.spec_from_file_location(name, script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module

def _runtime_config(tmp_path: Path, db_path: Path) -> Path:
    path = tmp_path / "runtime.json"
    path.write_text(
        json.dumps(
            {
                "environment": "test",
                "phase": "phase1",
                "database_path": str(db_path),
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

def _seed_create_db(db_path: Path) -> None:
    bootstrap_database(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO account_pool (
              advertiser_id, account_name, product, platform,
              historical_spend, source, synced_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "target-1",
                "目标账户1",
                "勇者突进",
                "WECHAT_GAME",
                1000,
                "unit_test",
                "2026-05-08T00:00:00+00:00",
            ),
        )
        for rank, material_id, cost in [
            (1, "m-high", 800),
            (2, "m-mid", 500),
            (3, "m-low", 100),
            (4, "m-extra", 50),
        ]:
            conn.execute(
                """
                INSERT INTO materials (
                  material_id, name, material_type, video_id,
                  review_status, cost_lookback, score, source, synced_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    material_id,
                    f"素材{rank}",
                    "video",
                    f"video-{rank}",
                    "APPROVED",
                    cost,
                    cost,
                    "unit_test",
                    "2026-05-08T00:00:00+00:00",
                ),
            )
            conn.execute(
                """
                INSERT INTO product_source_materials (
                  product, source_advertiser_id, organization_id,
                  material_id, video_id, name, material_type,
                  review_status, cost_lookback, score, source, synced_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "勇者突进",
                    "source-1",
                    "org-1",
                    material_id,
                    f"vsourcevideo00000000000{rank}",
                    f"素材{rank}",
                    "video",
                    "APPROVED",
                    cost,
                    cost,
                    "unit_test",
                    "2026-05-08T00:00:00+00:00",
                ),
            )

def _create_request() -> dict:
    return {
        "create_request": {
            "request_id": "create_req_20260508_yzt_wx_7r",
            "target_date": "2026-05-08",
            "product": "勇者突进",
            "platform": "WECHAT_GAME",
            "project_type": "WX_PAY_7R_GENERAL",
            "source_advertiser_id": "source-1",
            "organization_id": "org-1",
            "pool_key": "pool-yzt-wx-7r",
            "owner": "郭靖",
            "project_template_name": "微小每付7R通投",
            "batch_generated_at": "2026-05-09T13:30:45+08:00",
            "target_accounts": [
                {
                    "advertiser_id": "target-1",
                    "project_count": 1,
                    "units_per_project": 2,
                    "daily_budget": 300,
                }
            ],
            "material_requirements": {
                "material_type": "video",
                "materials_per_unit": 2,
                "dedupe_scope": "request",
            },
            "field_defaults": {
                "landing_type": "MICRO_GAME",
                "pricing": "PRICING_CPA",
                "inventory_type": "UNION",
            },
            "template_parameters": {
                "product_name": "勇者突进-福利版",
                "title_pool": ["每天送6480代金券", "首充免费再送月卡", "月卡零元直接领取"],
                "product_selling_points": ["每天送6480代金券", "首充免费再送月卡", "月卡零元直接领取"],
                "cta_pool": ["点击即玩", "不用下载", "全场免费"],
            },
            "project_name_template": "{target_date_mmdd}_{owner}_{product}_{project_template_name}_{batch_code}_{index}",
            "constraints": {
                "phase": "phase1",
                "execution_enabled": False,
                "allow_real_create": False,
            },
        }
    }

def _wx_unit_template_fields() -> dict:
    return {
        "source_name": "勇者突进-福利版",
        "product_name": "勇者突进-福利版",
        "title_pool": ["每天送6480代金券", "首充免费再送月卡", "月卡零元直接领取"],
        "product_selling_points": ["每天送6480代金券", "首充免费再送月卡", "月卡零元直接领取"],
        "cta_pool": ["点击即玩", "不用下载", "全场免费"],
        "delivery_identity": "AWEME",
        "aweme_ids": ["aweme-1"],
        "anchor_related_type": "SELECT",
        "anchor_id": "anchor-fixed",
        "anchor_type": "APP_GAME",
    }

def test_create_request_writes_plan_only_artifact_and_sqlite(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)

    result = run_create_request(
        _create_request(),
        db_path=db_path,
        runs_dir=tmp_path / "runs",
    )

    assert result["ok"] is True
    assert result["workflow"] == "create_request"
    assert result["phase"] == "phase1"
    assert result["execution_enabled"] is False
    assert result["external_api_calls"] == 0
    assert result["summary"] == {
        "request_id": "create_req_20260508_yzt_wx_7r",
        "target_date": "2026-05-08",
        "target_account_count": 1,
        "planned_project_count": 1,
        "planned_unit_count": 2,
    }
    assert Path(result["artifact_path"]).exists()

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT request_id, phase, execution_enabled, request_json FROM create_requests"
        ).fetchone()

    assert row[0] == "create_req_20260508_yzt_wx_7r"
    assert row[1] == "phase1"
    assert row[2] == 0
    assert json.loads(row[3])["project_type"] == "WX_PAY_7R_GENERAL"

def test_create_strategy_plan_allocates_candidate_materials_without_duplicates(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    _seed_create_db(db_path)

    plan = build_create_strategy_plan(
        request=_create_request()["create_request"],
        db_path=db_path,
        policy={"max_target_accounts": 5, "max_projects_per_account": 2, "max_units_per_project": 4},
    )

    assert plan["ok"] is True
    assert plan["workflow"] == "create_strategy_plan"
    assert plan["plan_id"] == "create_plan_create_req_20260508_yzt_wx_7r"
    assert plan["phase"] == "phase1"
    assert plan["execution_enabled"] is False
    assert plan["external_api_calls"] == 0
    assert plan["summary"] == {
        "plan_id": "create_plan_create_req_20260508_yzt_wx_7r",
        "request_id": "create_req_20260508_yzt_wx_7r",
        "target_date": "2026-05-08",
        "planned_project_count": 1,
        "planned_unit_count": 2,
        "planned_material_count": 4,
        "source_material_count": 4,
        "material_source": "source_material_account",
        "violation_count": 0,
    }
    units = plan["strategy"]["projects"][0]["units"]
    assert [item["material_id"] for item in units[0]["materials"]] == ["m-high", "m-mid"]
    assert [item["material_id"] for item in units[1]["materials"]] == ["m-low", "m-extra"]
    assert plan["actions"] == []
    assert plan["live_api_payloads"] == []

def test_create_strategy_plan_scale_top_materials_honors_overlap_ratio(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    _seed_create_db(db_path)
    request = _create_request()["create_request"]
    request["target_accounts"] = [
        {"advertiser_id": f"target-{index}", "project_count": 1, "units_per_project": 1, "daily_budget": 300}
        for index in range(1, 5)
    ]
    request["material_requirements"] = {
        "material_type": "video",
        "materials_per_unit": 1,
        "dedupe_scope": "max_account_overlap",
        "max_cross_account_overlap_ratio": 0.5,
        "cross_account_reuse_mode": "scale_top_materials",
        "allow_reuse_across_accounts": True,
    }
    request["material_selection"] = {
        "selection_type": "high_spend",
        "sort_by": "stat_cost_desc",
    }

    plan = build_create_strategy_plan(request=request, db_path=db_path, policy={})

    material_ids = [
        unit["materials"][0]["material_id"]
        for project in plan["strategy"]["projects"]
        for unit in project["units"]
    ]
    material_counts = Counter(material_ids)
    assert plan["ok"] is True
    assert max(material_counts.values()) == 2
    assert len(material_counts) == 2

def test_create_strategy_plan_fails_closed_when_request_deduped_materials_are_insufficient(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    _seed_create_db(db_path)
    request = _create_request()["create_request"]
    request["target_accounts"][0]["units_per_project"] = 3

    plan = build_create_strategy_plan(request=request, db_path=db_path, policy={})

    assert plan["ok"] is False
    assert plan["summary"]["planned_unit_count"] == 3
    assert plan["summary"]["planned_material_count"] == 4
    assert plan["summary"]["source_material_count"] == 4
    assert plan["summary"]["violation_count"] == 1
    assert plan["violations"] == [
        "source material account has 4 usable materials, expected 6 for dedupe_scope=request"
    ]

def test_create_strategy_plan_filters_candidates_by_policy_thresholds(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    _seed_create_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            UPDATE product_source_materials
            SET review_status = ?, score = ?, cost_lookback = ?
            WHERE product = ? AND source_advertiser_id = ? AND material_id = ?
            """,
            ("REJECTED", 900, 900, "勇者突进", "source-1", "m-high"),
        )
        conn.execute(
            """
            UPDATE product_source_materials
            SET score = ?, cost_lookback = ?
            WHERE product = ? AND source_advertiser_id = ? AND material_id = ?
            """,
            (20, 20, "勇者突进", "source-1", "m-extra"),
        )

    plan = build_create_strategy_plan(
        request=_create_request()["create_request"],
        db_path=db_path,
        policy={
            "candidate_filters": {
                "allowed_review_statuses": ["APPROVED"],
                "min_candidate_score": 100,
                "min_candidate_stat_cost": 100,
            }
        },
    )

    units = plan["strategy"]["projects"][0]["units"]
    assert plan["ok"] is False
    assert plan["summary"]["source_material_count"] == 2
    assert [item["material_id"] for item in units[0]["materials"]] == ["m-mid", "m-low"]
    assert units[1]["materials"] == []
    assert plan["violations"] == [
        "source material account has 2 usable materials, expected 4 for dedupe_scope=request"
    ]

def test_create_strategy_plan_excludes_target_account_existing_materials(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    _seed_create_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO account_materials (
              advertiser_id, material_id, video_id, material_type,
              review_status, source, synced_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "target-1",
                "m-high",
                "video-existing",
                "video",
                "APPROVED",
                "unit_test",
                "2026-05-08T00:00:00+00:00",
            ),
        )
    request = _create_request()["create_request"]
    request["target_accounts"][0]["units_per_project"] = 1

    plan = build_create_strategy_plan(
        request=request,
        db_path=db_path,
        policy={"candidate_filters": {"exclude_target_account_existing_materials": True}},
    )

    units = plan["strategy"]["projects"][0]["units"]
    assert plan["ok"] is True
    assert plan["summary"]["source_material_count"] == 3
    assert [item["material_id"] for item in units[0]["materials"]] == ["m-mid", "m-low"]
    assert "m-high" not in {item["material_id"] for item in units[0]["materials"]}

def test_create_strategy_plan_excludes_existing_materials_per_target_account(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    _seed_create_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO account_pool (
              advertiser_id, account_name, product, platform,
              historical_spend, source, synced_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "target-2",
                "目标账户2",
                "勇者突进",
                "WECHAT_GAME",
                800,
                "unit_test",
                "2026-05-08T00:00:00+00:00",
            ),
        )
        conn.execute(
            """
            INSERT INTO account_materials (
              advertiser_id, material_id, video_id, material_type,
              review_status, source, synced_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "target-1",
                "m-high",
                "video-existing",
                "video",
                "APPROVED",
                "unit_test",
                "2026-05-08T00:00:00+00:00",
            ),
        )
    request = _create_request()["create_request"]
    request["target_accounts"] = [
        {
            "advertiser_id": "target-1",
            "project_count": 1,
            "units_per_project": 1,
            "daily_budget": 300,
        },
        {
            "advertiser_id": "target-2",
            "project_count": 1,
            "units_per_project": 1,
            "daily_budget": 300,
        },
    ]
    request["material_requirements"]["materials_per_unit"] = 1

    plan = build_create_strategy_plan(
        request=request,
        db_path=db_path,
        policy={"candidate_filters": {"exclude_target_account_existing_materials": True}},
    )

    projects = plan["strategy"]["projects"]
    assert plan["ok"] is True
    assert projects[0]["advertiser_id"] == "target-1"
    assert projects[1]["advertiser_id"] == "target-2"
    assert [item["material_id"] for item in projects[0]["units"][0]["materials"]] == ["m-mid"]
    assert [item["material_id"] for item in projects[1]["units"][0]["materials"]] == ["m-high"]

def test_create_strategy_plan_uses_policy_project_naming_template(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    _seed_create_db(db_path)
    request = _create_request()["create_request"]
    request["project_name_template"] = "request-side-{advertiser_id}-{index}"

    plan = build_create_strategy_plan(
        request=request,
        db_path=db_path,
        policy={
            "project_naming": {
                "template": "{target_date_mmdd}_{owner}_{product}_{project_template_name}_{batch_code}_{index}",
                "index_width": 2,
                "invalid_char_replacement": "_",
            }
        },
    )

    project = plan["strategy"]["projects"][0]
    assert project["project_name"] == "0508_郭靖_勇者突进_微小每付7R通投_B80C4C430_01"
    assert project["naming"]["source"] == "policy"
    assert project["naming"]["template"] == "{target_date_mmdd}_{owner}_{product}_{project_template_name}_{batch_code}_{index}"
    assert project["naming"]["batch_code"] == "B80C4C430"
    assert project["naming"]["batch_code_source"]["generated_at"] == "2026-05-09T13:30:45+08:00"

def test_create_strategy_plan_uses_global_project_index_for_multi_account_names(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    _seed_create_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO account_pool (
              advertiser_id, account_name, product, platform,
              historical_spend, source, synced_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "target-2",
                "目标账户2",
                "勇者突进",
                "WECHAT_GAME",
                1000,
                "unit_test",
                "2026-05-08T00:00:00+00:00",
            ),
        )
    request = _create_request()["create_request"]
    request["target_accounts"] = [
        {"advertiser_id": "target-1", "project_count": 1, "units_per_project": 1, "daily_budget": 300},
        {"advertiser_id": "target-2", "project_count": 1, "units_per_project": 1, "daily_budget": 300},
    ]
    request["material_requirements"]["materials_per_unit"] = 1

    result = build_create_strategy_plan(
        request=request,
        db_path=db_path,
        policy={
            "project_naming": {
                "template": "{target_date_mmdd}_{owner}_{product}_{project_template_name}_{batch_code}_{index}",
                "index_width": 2,
                "invalid_char_replacement": "_",
            }
        },
    )

    projects = result["strategy"]["projects"]
    assert [project["project_index"] for project in projects] == [1, 2]
    assert [project["project_name"].rsplit("_", 1)[1] for project in projects] == ["01", "02"]
    assert len({project["project_name"] for project in projects}) == 2

def test_create_strategy_plan_can_namespace_local_keys_by_run_id(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    _seed_create_db(db_path)
    request = _create_request()["create_request"]
    request["local_key_namespace"] = "first-live-20260511-002"
    request["target_accounts"][0]["project_count"] = 2
    request["target_accounts"][0]["units_per_project"] = 1
    request["material_requirements"]["materials_per_unit"] = 1

    result = build_create_strategy_plan(request=request, db_path=db_path, policy={})

    projects = result["strategy"]["projects"]
    assert [project["project_key"] for project in projects] == [
        "target-1-first-live-20260511-002-p001",
        "target-1-first-live-20260511-002-p002",
    ]
    assert [project["units"][0]["unit_key"] for project in projects] == [
        "target-1-first-live-20260511-002-p001-u01",
        "target-1-first-live-20260511-002-p002-u01",
    ]

def test_create_preflight_rejects_project_names_outside_policy_pattern(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    _seed_create_db(db_path)
    plan = build_create_strategy_plan(request=_create_request()["create_request"], db_path=db_path, policy={})
    plan["strategy"]["projects"][0]["project_name"] = "manual-name"

    result = build_create_preflight(
        create_strategy_plan_artifact=plan,
        db_path=db_path,
        policy={"project_name_pattern": r"^\d{8}_勇者突进_WX_PAY_7R_GENERAL_target-1_\d{2}$"},
    )

    assert result["ok"] is False
    assert "project name manual-name does not match required pattern" in result["violations"]

def test_create_preflight_checks_account_budget_names_and_material_counts(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    _seed_create_db(db_path)
    plan = build_create_strategy_plan(request=_create_request()["create_request"], db_path=db_path, policy={})

    result = build_create_preflight(
        create_strategy_plan_artifact=plan,
        db_path=db_path,
        policy={
            "require_account_pool": True,
            "min_daily_budget": 100,
            "max_daily_budget": 500,
            "max_project_name_length": 80,
            "required_field_defaults": ["landing_type", "pricing", "inventory_type"],
        },
    )

    assert result["ok"] is True
    assert result["workflow"] == "create_preflight"
    assert result["status"] == "passed"
    assert result["execution_enabled"] is False
    assert result["external_api_calls"] == 0
    assert result["summary"]["violation_count"] == 0
    assert "approved_for_execute" not in result
    assert result["actions"] == []

def test_create_preflight_fails_closed_for_missing_account_and_short_materials(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    _seed_create_db(db_path)
    request = _create_request()["create_request"]
    request["target_accounts"][0]["advertiser_id"] = "missing-account"
    request["target_accounts"][0]["daily_budget"] = 20
    request["target_accounts"][0]["units_per_project"] = 3
    plan = build_create_strategy_plan(request=request, db_path=db_path, policy={})

    result = build_create_preflight(
        create_strategy_plan_artifact=plan,
        db_path=db_path,
        policy={"require_account_pool": True, "min_daily_budget": 100},
    )

    assert result["ok"] is False
    assert result["status"] == "failed"
    assert "target account missing-account is not in account_pool for 勇者突进/WECHAT_GAME" in result["violations"]
    assert "daily budget for missing-account must be at least 100" in result["violations"]
    assert "unit missing-account-p001-u03 has 0 materials, expected 2" in result["violations"]
    assert "approved_for_execute" not in result


def test_create_preflight_allows_short_materials_when_mode_allows_reuse(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    _seed_create_db(db_path)
    request = _create_request()["create_request"]
    request["material_requirements"]["materials_per_unit"] = 3
    request["material_requirements"]["dedupe_scope"] = "max_account_overlap"
    request["material_requirements"]["allow_reuse_across_accounts"] = True
    request["material_requirements"]["on_insufficient"] = "allow_reuse"
    plan = build_create_strategy_plan(request=request, db_path=db_path, policy={})

    result = build_create_preflight(
        create_strategy_plan_artifact=plan,
        db_path=db_path,
        policy={"require_account_pool": True, "min_daily_budget": 100},
    )

    assert result["ok"] is True
    assert result["status"] == "passed"
    assert not any("materials, expected" in item for item in result["violations"])


def test_create_preflight_validates_material_candidate_source_type_status_and_dedupe(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    _seed_create_db(db_path)
    plan = build_create_strategy_plan(request=_create_request()["create_request"], db_path=db_path, policy={})
    projects = plan["strategy"]["projects"]
    projects[0]["units"][0]["materials"][0]["material_id"] = "not-in-candidate-pool"
    projects[0]["units"][0]["materials"][1]["material_type"] = "image"
    projects[0]["units"][1]["materials"][0]["material_id"] = projects[0]["units"][1]["materials"][1]["material_id"]

    result = build_create_preflight(
        create_strategy_plan_artifact=plan,
        db_path=db_path,
        policy={
            "candidate_filters": {"allowed_review_statuses": ["APPROVED"]},
            "material_type": "video",
            "dedupe_scope": "request",
        },
    )

    assert result["ok"] is False
    assert "material not-in-candidate-pool is not in source material account" in result["violations"]
    assert "material m-mid type must be video, got image" in result["violations"]
    assert "material m-extra is duplicated in request scope" in result["violations"]

def test_create_preflight_rejects_existing_and_in_plan_project_name_duplicates(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    _seed_create_db(db_path)
    request = _create_request()["create_request"]
    request["target_accounts"][0]["project_count"] = 2
    request["target_accounts"][0]["units_per_project"] = 1
    request["material_requirements"]["materials_per_unit"] = 1
    plan = build_create_strategy_plan(request=request, db_path=db_path, policy={})
    projects = plan["strategy"]["projects"]
    projects[1]["project_name"] = projects[0]["project_name"]
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO projects (
              project_id, advertiser_id, name, status, source, synced_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "existing-project-1",
                "target-1",
                projects[0]["project_name"],
                "ENABLE",
                "unit_test",
                "2026-05-08T00:00:00+00:00",
            ),
        )

    result = build_create_preflight(
        create_strategy_plan_artifact=plan,
        db_path=db_path,
        policy={"reject_existing_project_names": True},
    )

    assert result["ok"] is False
    assert (
        f"project name {projects[0]['project_name']} already exists for advertiser target-1"
        in result["violations"]
    )
    assert (
        f"project name {projects[0]['project_name']} is duplicated in plan for advertiser target-1"
        in result["violations"]
    )

def test_create_dry_run_outputs_non_executable_project_unit_material_combinations(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    _seed_create_db(db_path)
    plan = build_create_strategy_plan(request=_create_request()["create_request"], db_path=db_path, policy={})
    preflight = build_create_preflight(create_strategy_plan_artifact=plan, db_path=db_path, policy={})

    result = build_create_dry_run(
        create_strategy_plan_artifact=plan,
        create_preflight_artifact=preflight,
        policy={"max_projects_per_dry_run": 5, "max_units_per_dry_run": 10},
    )

    assert result["ok"] is True
    assert result["workflow"] == "create_dry_run"
    assert result["phase"] == "phase1"
    assert result["status"] == "simulated"
    assert result["execution_enabled"] is False
    assert result["external_api_calls"] == 0
    assert result["summary"] == {
        "plan_id": "create_plan_create_req_20260508_yzt_wx_7r",
        "request_id": "create_req_20260508_yzt_wx_7r",
        "target_date": "2026-05-08",
        "project_count": 1,
        "unit_count": 2,
        "material_count": 4,
        "violation_count": 0,
    }
    task = result["candidate_tasks"][0]
    assert task["task_type"] == "create_project_candidate"
    assert task["executable"] is False
    assert task["live_api_payloads"] == []
    assert task["payload_schema_ref"] == "phase1.create_payload.v1"
    assert task["idempotency_key"]["scope"] == "create_project"
    assert re.fullmatch(r"[0-9a-f]{64}", task["idempotency_key"]["value"])
    assert task["idempotency_key"]["source_fields"] == {
        "plan_id": "create_plan_create_req_20260508_yzt_wx_7r",
        "request_id": "create_req_20260508_yzt_wx_7r",
        "target_date": "2026-05-08",
        "advertiser_id": "target-1",
        "project_key": "target-1-p001",
    }
    assert [unit["unit_key"] for unit in task["units"]] == ["target-1-p001-u01", "target-1-p001-u02"]
    assert task["units"][0]["idempotency_key"]["scope"] == "create_unit"
    assert re.fullmatch(r"[0-9a-f]{64}", task["units"][0]["idempotency_key"]["value"])
    assert task["units"][0]["materials"][0]["idempotency_key"]["scope"] == "bind_material"
    assert re.fullmatch(r"[0-9a-f]{64}", task["units"][0]["materials"][0]["idempotency_key"]["value"])
    assert task["redacted_payload_drafts"][0] == {
        "operation": "create_project",
        "transport": "disabled_schema_only",
        "executable": False,
        "idempotency_key": task["idempotency_key"]["value"],
        "endpoint": "",
            "payload": {
                "advertiser_id": "target-1",
                "project_name": "0508_郭靖_勇者突进_微小每付7R通投_B80C4C430_01",
                "daily_budget": 300.0,
                "operation": "DISABLE",
                "field_defaults": {
                    "landing_type": "MICRO_GAME",
                    "pricing": "PRICING_CPA",
                "inventory_type": "UNION",
            },
        },
    }
    assert [draft["operation"] for draft in task["redacted_payload_drafts"]] == [
        "create_project",
        "bind_material",
        "bind_material",
        "bind_material",
        "bind_material",
        "lookup_target_material",
        "lookup_target_material",
        "lookup_target_material",
        "lookup_target_material",
        "create_unit",
        "create_unit",
    ]
    assert task["redacted_payload_drafts"][1]["payload"]["material_id"] == "m-high"
    assert task["redacted_payload_drafts"][5]["payload"]["source_video_id"] == "vsourcevideo000000000001"
    assert task["redacted_payload_drafts"][9]["payload"]["unit_key"] == "target-1-p001-u01"
    assert task["redacted_payload_drafts"][9]["payload"]["promotion_materials"]["video_material_list"][0]["video_id"] == "<lookup:target_video:target-1:vsourcevideo000000000001>"
    assert result["payload_schema"]["version"] == "phase1.create_payload.v1"
    assert result["payload_schema"]["mode"] == "schema_only"
    assert result["payload_schema"]["execution_enabled"] is False
    assert result["payload_schema"]["external_api_enabled"] is False
    assert result["payload_schema"]["live_payload_generation_enabled"] is False
    assert result["payload_schema"]["endpoints"] == {
        "create_project": "",
        "create_unit": "",
        "lookup_target_material": "",
        "bind_material": "",
    }
    assert result["payload_schema"]["required_fields"]["create_project"] == [
        "advertiser_id",
        "project_name",
        "daily_budget",
        "operation",
        "field_defaults.landing_type",
        "field_defaults.pricing",
        "field_defaults.inventory_type",
    ]
    assert task["project_type"] == "WX_PAY_7R_GENERAL"
    assert "project_type" not in task["redacted_payload_drafts"][0]["payload"]
    assert result["payload_schema"]["required_fields"]["create_unit"] == [
        "advertiser_id",
        "project_key",
        "project_id",
        "unit_key",
        "promotion_name",
        "promotion_materials.video_material_list",
        "promotion_materials.title_material_list",
        "promotion_materials.call_to_action_buttons",
        "source",
        "operation",
        "field_defaults.landing_type",
        "field_defaults.pricing",
        "field_defaults.inventory_type",
    ]
    assert result["payload_schema"]["required_fields"]["bind_material"] == [
        "source_advertiser_id",
        "target_advertiser_ids",
        "source_video_ids",
        "project_key",
        "unit_key",
        "material_id",
        "source_video_id",
    ]
    assert result["payload_contract"] == {
        "status": "passed",
        "schema_version": "phase1.create_payload.v1",
        "checked_project_count": 1,
        "checked_unit_count": 2,
        "checked_material_lookup_count": 4,
        "checked_material_binding_count": 4,
        "missing_fields": [],
    }
    assert result["idempotency_contract"] == {
        "status": "passed",
        "checked_key_count": 7,
        "duplicate_keys": [],
    }
    assert result["payload_draft_contract"] == {
        "status": "passed",
        "draft_count": 11,
        "ordered_operations": ["create_project", "bind_material", "lookup_target_material", "create_unit"],
        "live_payload_count": 0,
        "executable_draft_count": 0,
        "redacted": True,
    }
    assert result["provider_adapter"] == {
        "status": "draft_unverified",
        "provider": "oceanengine",
        "transport": "disabled_provider_adapter",
        "mapping_verified": False,
        "executable": False,
        "field_mapping_version": "phase1.oceanengine.create_payload.draft.v1",
    }
    assert result["provider_adapter_contract"] == {
        "status": "draft_unverified",
        "provider": "oceanengine",
        "mapping_verified": False,
        "draft_count": 11,
        "live_payload_count": 0,
        "executable_draft_count": 0,
        "unmapped_payload_field_count": 0,
        "unmapped_payload_fields": [],
    }
    assert result["provider_field_map"]["provider"] == "oceanengine"
    assert result["provider_field_map"]["mapping_verified"] is False
    assert result["provider_field_map"]["source"] == "phase1_placeholder_no_legacy_reference"
    assert result["provider_field_map"]["field_mapping_version"] == "phase1.oceanengine.create_payload.draft.v1"
    assert result["provider_field_map"]["operations"]["create_project"][0] == {
        "internal_field": "advertiser_id",
        "provider_field": "",
        "purpose": "target advertiser account id",
        "verified": False,
        "required": True,
        "source": "internal_phase1_schema",
    }
    assert result["provider_field_map"]["operations"]["bind_material"][-1] == {
        "internal_field": "source_video_id",
        "provider_field": "",
        "purpose": "source video identity",
        "verified": False,
        "required": True,
        "source": "internal_phase1_schema",
    }
    assert result["provider_field_map_contract"] == {
        "status": "unverified",
        "provider": "oceanengine",
        "mapping_verified": False,
        "operation_count": 4,
            "field_count": 35,
            "verified_field_count": 0,
            "unverified_field_count": 35,
            "missing_provider_field_count": 35,
        "missing_required_field_count": 0,
        "missing_required_fields": [],
        "duplicate_internal_field_count": 0,
        "duplicate_internal_fields": [],
        "duplicate_provider_field_count": 0,
        "duplicate_provider_fields": [],
        "unknown_internal_field_count": 0,
        "unknown_internal_fields": [],
        "provider_mismatch_count": 0,
        "provider_mismatches": [],
        "field_mapping_version_mismatch_count": 0,
        "field_mapping_version_mismatches": [],
    }
    assert result["provider_readiness_contract"] == {
        "status": "not_ready",
        "ready_for_live_execute": False,
        "provider": "oceanengine",
        "checks": {
            "provider_adapter_mapping_verified": False,
            "provider_field_map_verified": False,
            "provider_payloads_fully_mapped": True,
            "payload_drafts_non_executable": True,
            "live_payload_count_zero": True,
        },
        "blocking_reasons": [
            "provider adapter mapping is not verified",
            "provider field map is not verified",
        ],
    }
    assert result["provider_payload_drafts"][0]["operation"] == "create_project"
    assert result["provider_payload_drafts"][0]["provider"] == "oceanengine"
    assert result["provider_payload_drafts"][0]["mapping_verified"] is False
    assert result["provider_payload_drafts"][0]["field_mapping_applied"] is False
    assert result["provider_payload_drafts"][0]["executable"] is False
    assert result["provider_payload_drafts"][0]["payload"]["advertiser_id"] == "target-1"
    assert result["provider_payload_drafts"][0]["payload"]["project_name"] == "0508_郭靖_勇者突进_微小每付7R通投_B80C4C430_01"
    assert result["provider_payload_draft_digest"]["algorithm"] == "sha256"
    assert re.fullmatch(r"[0-9a-f]{64}", result["provider_payload_draft_digest"]["value"])
    assert result["provider_payload_draft_digest"]["provider_payload_draft_count"] == 11
    assert result["redacted_payload_drafts"][0]["operation"] == "create_project"
    assert result["redacted_payload_drafts"][0]["payload"]["project_key"] == "target-1-p001"
    assert result["redacted_payload_drafts"][0]["payload"]["materials"] == "<redacted:4 material ids>"
    assert "approved_for_execute" not in result
    assert result["actions"] == []

def test_create_dry_run_emits_non_executable_candidate_provider_payloads_for_phase2_mapping(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    _seed_create_db(db_path)
    plan = build_create_strategy_plan(request=_create_request()["create_request"], db_path=db_path, policy={})
    preflight = build_create_preflight(create_strategy_plan_artifact=plan, db_path=db_path, policy={})

    result = build_create_dry_run(
        create_strategy_plan_artifact=plan,
        create_preflight_artifact=preflight,
        policy={
            "provider_adapter": {
                "provider": "oceanengine",
                "field_mapping_version": "phase2.oceanengine.create_payload.prep.v1",
                "mapping_verified": False,
            },
            "provider_field_map_path": "configs/provider-field-maps/oceanengine.create.phase2-prep.example.json",
            "live_api": {
                "endpoints": {
                    "create_project": "/open_api/v3.0/project/create/",
                    "create_unit": "/open_api/v3.0/promotion/create/",
                    "bind_material": "/open_api/2/file/material/bind/",
                }
            },
        },
    )

    project_draft = result["provider_payload_drafts"][0]
    assert project_draft["operation"] == "create_project"
    assert project_draft["field_mapping_mode"] == "candidate"
    assert project_draft["candidate_field_mapping_applied"] is True
    assert project_draft["field_mapping_applied"] is False
    assert project_draft["executable"] is False
    assert project_draft["endpoint"] == "/open_api/v3.0/project/create/"
    assert project_draft["payload"] == {
        "advertiser_id": "target-1",
        "name": "0508_郭靖_勇者突进_微小每付7R通投_B80C4C430_01",
        "landing_type": "MICRO_GAME",
        "delivery_setting": {"budget": 300.0, "pricing": "PRICING_CPA"},
        "delivery_range": {"inventory_type": ["UNION"], "inventory_catalog": "UNIVERSAL_SMART"},
    }
    assert project_draft["candidate_unverified_field_count"] == 0
    assert project_draft["candidate_unverified_fields"] == []
    assert "candidate provider fields require evidence review before execution" in project_draft["non_executable_reasons"]

    unit_draft = next(draft for draft in result["provider_payload_drafts"] if draft["operation"] == "create_unit")
    assert unit_draft["field_mapping_mode"] == "candidate"
    assert unit_draft["payload"]["project_id"] == "<lookup:target-1-p001>"
    assert unit_draft["payload"]["name"] == "0508_郭靖_勇者突进_微小每付7R通投_B80C4C430_01_U01"
    assert "landing_type" not in unit_draft["payload"]
    assert "pricing" not in unit_draft["payload"]
    assert "inventory_type" not in unit_draft["payload"]
    assert "project_key" not in unit_draft["payload"]
    assert "unit_key" not in unit_draft["payload"]

    material_draft = next(draft for draft in result["provider_payload_drafts"] if draft["operation"] == "bind_material")
    assert material_draft["field_mapping_mode"] == "candidate"
    assert material_draft["endpoint"] == "/open_api/2/file/material/bind/"
    assert material_draft["payload"] == {
        "advertiser_id": "source-1",
        "target_advertiser_ids": ["target-1"],
        "video_ids": ["vsourcevideo000000000001"],
    }
    assert "project_key" not in material_draft["payload"]
    assert "unit_key" not in material_draft["payload"]
    assert "project_id" not in material_draft["payload"]
    assert "promotion_id" not in material_draft["payload"]
    assert "material_id" not in material_draft["payload"]

    lookup_draft = next(draft for draft in result["provider_payload_drafts"] if draft["operation"] == "lookup_target_material")
    assert lookup_draft["field_mapping_mode"] == "candidate"
    assert lookup_draft["payload"] == {
        "target_advertiser_id": "target-1",
        "source_video_id": "vsourcevideo000000000001",
        "material_id": "m-high",
    }

    assert result["provider_adapter_contract"]["executable_draft_count"] == 0
    assert result["provider_adapter_contract"]["unmapped_payload_field_count"] == 0
    assert result["provider_readiness_contract"]["ready_for_live_execute"] is False
    assert result["execution_enabled"] is False
    assert result["external_api_calls"] == 0
    assert result["actions"] == []


def test_provider_adapter_converts_micro_app_instance_id_to_integer_for_project_payload():
    drafts = build_provider_payload_drafts(
        tasks=[
            {
                "redacted_payload_drafts": [
                    {
                        "operation": "create_project",
                        "payload": {
                            "advertiser_id": "target-1",
                            "project_name": "首单项目",
                            "daily_budget": 300,
                            "operation": "DISABLE",
                            "field_defaults": {
                                "landing_type": "MICRO_GAME",
                                "pricing": "PRICING_OCPM",
                                "inventory_type": "INVENTORY_FEED",
                                "micro_app_instance_id": "1856457631493124",
                            },
                        },
                    },
                ],
            }
        ],
        adapter={
            "provider": "oceanengine",
            "field_mapping_version": "phase2.oceanengine.create_payload.prep.v1",
            "mapping_verified": True,
        },
        provider_field_map={
            "provider": "oceanengine",
            "field_mapping_version": "phase2.oceanengine.create_payload.prep.v1",
            "mapping_verified": True,
            "operations": {
                "create_project": [
                    {"internal_field": "advertiser_id", "provider_field": "advertiser_id", "verified": True},
                    {"internal_field": "project_name", "provider_field": "name", "verified": True},
                    {"internal_field": "daily_budget", "provider_field": "delivery_setting.budget", "verified": True},
                    {"internal_field": "operation", "mapping_kind": "local_only", "local_only_confirmed": True},
                    {"internal_field": "field_defaults.landing_type", "provider_field": "landing_type", "verified": True},
                    {
                        "internal_field": "field_defaults.pricing",
                        "provider_field": "delivery_setting.pricing",
                        "verified": True,
                    },
                    {
                        "internal_field": "field_defaults.inventory_type",
                        "provider_field": "delivery_range.inventory_type",
                        "verified": True,
                    },
                ]
            },
        },
        provider_field_map_contract={"status": "verified"},
    )

    assert drafts[0]["payload"]["micro_app_instance_id"] == 1856457631493124

def test_create_dry_run_can_load_provider_field_map_from_json_config(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    _seed_create_db(db_path)
    plan = build_create_strategy_plan(request=_create_request()["create_request"], db_path=db_path, policy={})
    preflight = build_create_preflight(create_strategy_plan_artifact=plan, db_path=db_path, policy={})
    field_map_path = tmp_path / "provider-field-map.json"
    field_map_path.write_text(
        json.dumps(
            {
                "provider": "oceanengine",
                "field_mapping_version": "phase1.oceanengine.create_payload.draft.v1",
                "mapping_verified": True,
                "source": "unit_test_config",
                "operations": {
                    "create_project": [
                        {
                            "internal_field": "advertiser_id",
                            "provider_field": "advertiser_id",
                            "purpose": "target advertiser account id",
                            "verified": True,
                            "required": True,
                            "source": "unit_test",
                        },
                        {
                            "internal_field": "project_name",
                            "provider_field": "name",
                            "purpose": "planned project name",
                            "verified": True,
                            "required": True,
                            "source": "unit_test",
                        },
                        {
                            "internal_field": "project_type",
                            "provider_field": "",
                            "mapping_kind": "local_only",
                            "local_only_confirmed": True,
                            "purpose": "internal project type",
                            "verified": True,
                            "required": True,
                            "source": "unit_test",
                        },
                            {
                                "internal_field": "daily_budget",
                                "provider_field": "budget",
                                "purpose": "planned project daily budget",
                                "verified": True,
                                "required": True,
                                "source": "unit_test",
                            },
                            {
                                "internal_field": "operation",
                                "provider_field": "operation",
                                "purpose": "project initial status",
                                "verified": True,
                                "required": True,
                                "source": "unit_test",
                            },
                            {
                                "internal_field": "field_defaults.landing_type",
                                "provider_field": "landing_type",
                            "purpose": "default landing type",
                            "verified": True,
                            "required": True,
                            "source": "unit_test",
                        },
                        {
                            "internal_field": "field_defaults.pricing",
                            "provider_field": "pricing",
                            "purpose": "default pricing type",
                            "verified": True,
                            "required": True,
                            "source": "unit_test",
                        },
                        {
                            "internal_field": "field_defaults.inventory_type",
                            "provider_field": "delivery_range.inventory_type",
                            "purpose": "default inventory type",
                            "verified": True,
                            "required": True,
                            "source": "unit_test",
                        },
                    ],
                    "create_unit": [
                        {
                            "internal_field": "advertiser_id",
                            "provider_field": "advertiser_id",
                            "purpose": "target advertiser account id",
                            "verified": True,
                            "required": True,
                            "source": "unit_test",
                        },
                        {
                            "internal_field": "project_key",
                            "provider_field": "local_project_key",
                            "purpose": "local planned project key",
                            "verified": True,
                            "required": True,
                            "source": "unit_test",
                        },
                        {
                            "internal_field": "project_id",
                            "provider_field": "project_id",
                            "purpose": "provider project id lookup placeholder",
                            "verified": True,
                            "required": True,
                            "source": "unit_test",
                        },
                        {
                            "internal_field": "unit_key",
                            "provider_field": "local_unit_key",
                            "purpose": "local planned unit key",
                            "verified": True,
                            "required": True,
                            "source": "unit_test",
                        },
                        {
                            "internal_field": "promotion_name",
                            "provider_field": "promotion_name",
                            "purpose": "planned provider-facing unit name",
                            "verified": True,
                            "required": True,
                            "source": "unit_test",
                        },
                        {
                            "internal_field": "field_defaults.landing_type",
                            "provider_field": "landing_type",
                            "purpose": "default landing type",
                            "verified": True,
                            "required": True,
                            "source": "unit_test",
                        },
                        {
                            "internal_field": "field_defaults.pricing",
                            "provider_field": "pricing",
                            "purpose": "default pricing type",
                            "verified": True,
                            "required": True,
                            "source": "unit_test",
                        },
                        {
                            "internal_field": "field_defaults.inventory_type",
                            "provider_field": "inventory_type",
                            "purpose": "default inventory type",
                            "verified": True,
                            "required": True,
                            "source": "unit_test",
                        },
                    ],
                    "bind_material": [
                        {
                            "internal_field": "source_advertiser_id",
                            "provider_field": "advertiser_id",
                            "purpose": "source material advertiser account id",
                            "verified": True,
                            "required": True,
                            "source": "unit_test",
                        },
                        {
                            "internal_field": "target_advertiser_ids",
                            "provider_field": "target_advertiser_ids",
                            "purpose": "target advertiser account ids for material push",
                            "verified": True,
                            "required": True,
                            "source": "unit_test",
                        },
                        {
                            "internal_field": "source_video_ids",
                            "provider_field": "video_ids",
                            "purpose": "source account video ids to push",
                            "verified": True,
                            "required": True,
                            "source": "unit_test",
                        },
                        {
                            "internal_field": "project_key",
                            "provider_field": "",
                            "purpose": "local planned project key",
                            "verified": True,
                            "required": True,
                            "source": "unit_test",
                            "mapping_kind": "local_lookup_key",
                        },
                        {
                            "internal_field": "unit_key",
                            "provider_field": "",
                            "purpose": "local planned unit key",
                            "verified": True,
                            "required": True,
                            "source": "unit_test",
                            "mapping_kind": "local_lookup_key",
                        },
                        {
                            "internal_field": "material_id",
                            "provider_field": "",
                            "purpose": "source material identity",
                            "verified": True,
                            "required": True,
                            "source": "unit_test",
                            "mapping_kind": "local_only",
                        },
                        {
                            "internal_field": "source_video_id",
                            "provider_field": "",
                            "purpose": "source video identity",
                            "verified": True,
                            "required": True,
                            "source": "unit_test",
                            "mapping_kind": "local_only",
                        },
                    ],
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = build_create_dry_run(
        create_strategy_plan_artifact=plan,
        create_preflight_artifact=preflight,
        policy={
            "provider_adapter": {
                "provider": "oceanengine",
                "field_mapping_version": "phase1.oceanengine.create_payload.draft.v1",
                "mapping_verified": True,
            },
            "provider_field_map_path": str(field_map_path),
        },
    )

    assert result["provider_field_map"]["source"] == "unit_test_config"
    assert result["provider_field_map_contract"] == {
        "status": "unverified",
        "provider": "oceanengine",
        "mapping_verified": True,
        "operation_count": 3,
            "field_count": 23,
            "verified_field_count": 23,
        "unverified_field_count": 0,
        "missing_provider_field_count": 0,
        "missing_required_field_count": 12,
        "missing_required_fields": [
            {"operation": "create_unit", "internal_field": "promotion_materials.video_material_list"},
            {"operation": "create_unit", "internal_field": "promotion_materials.title_material_list"},
            {"operation": "create_unit", "internal_field": "promotion_materials.call_to_action_buttons"},
            {"operation": "create_unit", "internal_field": "promotion_materials.mini_program_info"},
            {"operation": "create_unit", "internal_field": "source"},
            {"operation": "create_unit", "internal_field": "operation"},
            {"operation": "lookup_target_material", "internal_field": "source_advertiser_id"},
            {"operation": "lookup_target_material", "internal_field": "target_advertiser_id"},
            {"operation": "lookup_target_material", "internal_field": "source_video_id"},
            {"operation": "lookup_target_material", "internal_field": "material_id"},
            {"operation": "lookup_target_material", "internal_field": "target_video_id"},
            {"operation": "lookup_target_material", "internal_field": "target_video_cover_id"},
        ],
        "duplicate_internal_field_count": 0,
        "duplicate_internal_fields": [],
        "duplicate_provider_field_count": 0,
        "duplicate_provider_fields": [],
        "unknown_internal_field_count": 0,
        "unknown_internal_fields": [],
        "provider_mismatch_count": 0,
        "provider_mismatches": [],
        "field_mapping_version_mismatch_count": 0,
        "field_mapping_version_mismatches": [],
    }
    assert result["provider_readiness_contract"] == {
        "status": "not_ready",
        "ready_for_live_execute": False,
        "provider": "oceanengine",
        "checks": {
            "provider_adapter_mapping_verified": True,
            "provider_field_map_verified": False,
            "provider_payloads_fully_mapped": True,
            "payload_drafts_non_executable": True,
            "live_payload_count_zero": True,
        },
        "blocking_reasons": ["provider field map is not verified"],
    }
    assert result["execution_enabled"] is False
    assert result["external_api_calls"] == 0
    assert result["provider_payload_drafts"][0]["mapping_verified"] is True
    assert result["provider_payload_drafts"][0]["field_mapping_applied"] is False
    assert result["provider_payload_drafts"][0]["payload"]["advertiser_id"] == "target-1"
    assert result["provider_payload_drafts"][0]["payload"]["name"] == "0508_郭靖_勇者突进_微小每付7R通投_B80C4C430_01"
    assert result["provider_payload_drafts"][0]["payload"]["budget"] == 300.0
    assert result["provider_payload_drafts"][0]["payload"]["operation"] == "DISABLE"
    unit_draft = next(draft for draft in result["provider_payload_drafts"] if draft["operation"] == "create_unit")
    assert unit_draft["field_mapping_applied"] is False
    assert unit_draft["payload"]["project_key"] == "target-1-p001"
    assert unit_draft["payload"]["project_id"] == "<lookup:target-1-p001>"
    assert unit_draft["payload"]["unit_key"] == "target-1-p001-u01"
    assert unit_draft["payload"]["promotion_name"] == "0508_郭靖_勇者突进_微小每付7R通投_B80C4C430_01_U01"
    material_draft = next(draft for draft in result["provider_payload_drafts"] if draft["operation"] == "bind_material")
    assert material_draft["field_mapping_applied"] is False
    assert material_draft["candidate_field_mapping_applied"] is True
    assert material_draft["payload"] == {
        "advertiser_id": "source-1",
        "target_advertiser_ids": ["target-1"],
        "video_ids": ["vsourcevideo000000000001"],
    }
    assert "source_video_id" not in material_draft["payload"]
    assert result["candidate_tasks"][0]["units"][0]["materials"][0]["source_video_id"] == "vsourcevideo000000000001"
    assert "unit_key" not in material_draft["payload"]
    assert result["actions"] == []

def test_create_dry_run_generates_promotion_name_and_lookup_placeholders(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    _seed_create_db(db_path)
    plan = build_create_strategy_plan(request=_create_request()["create_request"], db_path=db_path, policy={})
    preflight = build_create_preflight(create_strategy_plan_artifact=plan, db_path=db_path, policy={})

    result = build_create_dry_run(create_strategy_plan_artifact=plan, create_preflight_artifact=preflight, policy={})

    task = result["candidate_tasks"][0]
    first_unit = task["units"][0]
    assert first_unit["unit_key"] == "target-1-p001-u01"
    assert first_unit["promotion_name"] == "0508_郭靖_勇者突进_微小每付7R通投_B80C4C430_01_U01"

    unit_draft = next(draft for draft in task["redacted_payload_drafts"] if draft["operation"] == "create_unit")
    assert unit_draft["payload"]["unit_key"] == "target-1-p001-u01"
    assert unit_draft["payload"]["promotion_name"] == "0508_郭靖_勇者突进_微小每付7R通投_B80C4C430_01_U01"
    assert unit_draft["payload"]["project_id"] == "<lookup:target-1-p001>"

    material_draft = next(draft for draft in task["redacted_payload_drafts"] if draft["operation"] == "bind_material")
    assert material_draft["payload"]["source_advertiser_id"] == "source-1"
    assert material_draft["payload"]["target_advertiser_ids"] == ["target-1"]
    assert material_draft["payload"]["source_video_ids"] == ["vsourcevideo000000000001"]
    assert "source_video_id" not in material_draft["payload"]
    assert first_unit["materials"][0]["source_video_id"] == "vsourcevideo000000000001"
    assert result["payload_contract"]["status"] == "passed"
    assert result["execution_enabled"] is False
    assert result["external_api_calls"] == 0
    assert result["actions"] == []

def test_create_dry_run_uses_fixed_template_cover_without_requiring_lookup_cover(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    _seed_create_db(db_path)
    request = _create_request()["create_request"]
    request["template_parameters"] = {**request["template_parameters"], "fixed_video_cover_id": "fixed-cover-001"}
    plan = build_create_strategy_plan(request=request, db_path=db_path, policy={})
    preflight = build_create_preflight(create_strategy_plan_artifact=plan, db_path=db_path, policy={})

    result = build_create_dry_run(create_strategy_plan_artifact=plan, create_preflight_artifact=preflight, policy={})

    assert result["ok"] is True
    assert result["payload_contract"]["status"] == "passed"
    first_unit = result["candidate_tasks"][0]["units"][0]
    assert "target_video_cover_id" not in first_unit["materials"][0]
    assert first_unit["promotion_materials"]["video_material_list"][0]["video_cover_id"] == "fixed-cover-001"
    requirements = result["provider_id_ledger_requirements"]["required_before_create_unit"]
    assert all(row["entity_type"] != "target_video_cover" for row in requirements)
    lookup_draft = next(
        draft
        for draft in result["candidate_tasks"][0]["redacted_payload_drafts"]
        if draft["operation"] == "lookup_target_material"
    )
    assert lookup_draft["expected_outputs"] == {
        "target_video_id": "<lookup:target_video:target-1:vsourcevideo000000000001>"
    }
    assert result["violations"] == []

def test_create_dry_run_does_not_send_anchor_material_when_template_anchor_is_off(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    _seed_create_db(db_path)
    request = _create_request()["create_request"]
    request["template_parameters"] = {
        **request["template_parameters"],
        "delivery_identity": "AWEME",
        "aweme_ids": ["aweme-1"],
        "anchor_related_type": "OFF",
        "anchor_id": "anchor-should-not-be-sent",
        "anchor_type": "APP_GAME",
    }
    request["target_accounts"][0]["units_per_project"] = 1
    plan = build_create_strategy_plan(request=request, db_path=db_path, policy={})
    preflight = build_create_preflight(create_strategy_plan_artifact=plan, db_path=db_path, policy={})

    result = build_create_dry_run(create_strategy_plan_artifact=plan, create_preflight_artifact=preflight, policy={})

    first_unit = result["candidate_tasks"][0]["units"][0]
    assert first_unit["native_setting"]["anchor_related_type"] == "OFF"
    assert "anchor_material_list" not in first_unit["promotion_materials"]
    unit_draft = next(
        draft
        for draft in result["candidate_tasks"][0]["redacted_payload_drafts"]
        if draft["operation"] == "create_unit"
    )
    assert "anchor_material_list" not in unit_draft["payload"]["promotion_materials"]

def test_create_dry_run_does_not_send_placeholder_mini_program_info(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    _seed_create_db(db_path)
    request = _create_request()["create_request"]
    request["template_parameters"] = {**request["template_parameters"], "effective_touch_url": "<fixed-in-yzt-script>"}
    request["target_accounts"][0]["units_per_project"] = 1
    plan = build_create_strategy_plan(request=request, db_path=db_path, policy={})
    preflight = build_create_preflight(create_strategy_plan_artifact=plan, db_path=db_path, policy={})

    result = build_create_dry_run(create_strategy_plan_artifact=plan, create_preflight_artifact=preflight, policy={})

    first_unit = result["candidate_tasks"][0]["units"][0]
    assert "mini_program_info" not in first_unit["promotion_materials"]
    unit_draft = next(
        draft
        for draft in result["candidate_tasks"][0]["redacted_payload_drafts"]
        if draft["operation"] == "create_unit"
    )
    assert "mini_program_info" not in unit_draft["payload"]["promotion_materials"]

def test_create_dry_run_uses_copy_title_pool_manual_anchor_and_product_source(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    _seed_create_db(db_path)
    request = _create_request()["create_request"]
    request["target_accounts"][0]["units_per_project"] = 1
    request["material_requirements"]["materials_per_unit"] = 2
    request["template_parameters"] = {
        "product_name": "勇者突进-福利版",
        "title_pool": ["每天送6480代金券", "首充免费再送月卡", "月卡零元直接领取"],
        "product_selling_points": ["每天送6480代金券", "首充免费再送月卡", "月卡零元直接领取"],
        "cta_pool": ["点击即玩", "不用下载", "全场免费"],
        "delivery_identity": "AWEME",
        "aweme_ids": ["aweme-1"],
        "anchor_related_type": "SELECT",
        "anchor_id": "anchor-fixed",
        "anchor_type": "APP_GAME",
    }
    plan = build_create_strategy_plan(request=request, db_path=db_path, policy={})
    preflight = build_create_preflight(create_strategy_plan_artifact=plan, db_path=db_path, policy={})

    result = build_create_dry_run(create_strategy_plan_artifact=plan, create_preflight_artifact=preflight, policy={})

    unit_draft = next(
        draft
        for draft in result["candidate_tasks"][0]["redacted_payload_drafts"]
        if draft["operation"] == "create_unit"
    )
    payload = unit_draft["payload"]
    promotion_materials = payload["promotion_materials"]
    assert payload["source"] == "勇者突进-福利版"
    assert promotion_materials["title_material_list"] == [
        {"title": "每天送6480代金券"},
        {"title": "首充免费再送月卡"},
    ]
    assert len(promotion_materials["title_material_list"]) == len(promotion_materials["video_material_list"])
    assert promotion_materials["call_to_action_buttons"] == ["点击即玩", "不用下载", "全场免费"]
    assert promotion_materials["product_info"]["selling_points"] == [
        "每天送6480代金券",
        "首充免费再送月卡",
        "月卡零元直接领取",
    ]
    assert promotion_materials["anchor_material_list"] == [
        {"anchor_id": "anchor-fixed", "anchor_type": "APP_GAME"}
    ]
    assert payload["native_setting"]["anchor_related_type"] == "SELECT"


def test_create_dry_run_applies_mode_unit_creative_selection_rules(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    _seed_create_db(db_path)
    request = _create_request()["create_request"]
    request["target_accounts"][0]["units_per_project"] = 2
    request["template_parameters"] = {
        "product_name": "勇者突进-福利版",
        "title_pool": ["标题1", "标题2", "标题3", "标题4", "标题5"],
        "product_selling_points": ["卖点1", "卖点2", "卖点3", "卖点4", "卖点5"],
        "cta_pool": ["点击即玩", "不用下载", "全场免费", "全场福利", "限时福利"],
        "delivery_identity": "AWEME",
        "aweme_ids": ["aweme-1", "aweme-2"],
        "anchor_related_type": "SELECT",
        "anchor_id": "anchor-fixed",
        "anchor_type": "APP_GAME",
        "unit_creative_selection": {
            "title_strategy": "deterministic_shuffle_per_unit",
            "cta_min_count": 2,
            "cta_max_count": 3,
            "product_selling_point_min_count": 2,
            "product_selling_point_max_count": 3,
            "aweme_select_count": 1,
        },
    }
    plan = build_create_strategy_plan(request=request, db_path=db_path, policy={})
    preflight = build_create_preflight(create_strategy_plan_artifact=plan, db_path=db_path, policy={})

    first = build_create_dry_run(create_strategy_plan_artifact=plan, create_preflight_artifact=preflight, policy={})
    second = build_create_dry_run(create_strategy_plan_artifact=plan, create_preflight_artifact=preflight, policy={})

    unit_drafts = [
        draft
        for draft in first["candidate_tasks"][0]["redacted_payload_drafts"]
        if draft["operation"] == "create_unit"
    ]
    assert len(unit_drafts) == 2
    for draft in unit_drafts:
        payload = draft["payload"]
        promotion_materials = payload["promotion_materials"]
        assert len(promotion_materials["title_material_list"]) == len(promotion_materials["video_material_list"])
        assert 2 <= len(promotion_materials["call_to_action_buttons"]) <= 3
        assert 2 <= len(promotion_materials["product_info"]["selling_points"]) <= 3
        assert payload["native_setting"]["aweme_id"] in {"aweme-1", "aweme-2"}
        assert promotion_materials["anchor_material_list"] == [{"anchor_id": "anchor-fixed", "anchor_type": "APP_GAME"}]
    assert first["candidate_tasks"][0]["redacted_payload_drafts"] == second["candidate_tasks"][0]["redacted_payload_drafts"]


def test_create_dry_run_rotates_titles_within_account_before_reuse(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    _seed_create_db(db_path)
    request = _create_request()["create_request"]
    request["target_accounts"][0]["project_count"] = 2
    request["target_accounts"][0]["units_per_project"] = 1
    request["material_requirements"]["materials_per_unit"] = 2
    request["template_parameters"] = {
        "product_name": "勇者突进-福利版",
        "title_pool": ["标题1", "标题2", "标题3", "标题4"],
        "product_selling_points": ["卖点1", "卖点2", "卖点3"],
        "cta_pool": ["点击即玩", "不用下载", "全场免费"],
        "unit_creative_selection": {
            "title_strategy": "deterministic_shuffle_per_unit",
            "cta_min_count": 2,
            "cta_max_count": 3,
            "product_selling_point_min_count": 2,
            "product_selling_point_max_count": 3,
        },
    }
    plan = build_create_strategy_plan(request=request, db_path=db_path, policy={})
    preflight = build_create_preflight(create_strategy_plan_artifact=plan, db_path=db_path, policy={})

    result = build_create_dry_run(create_strategy_plan_artifact=plan, create_preflight_artifact=preflight, policy={})

    unit_drafts = [
        draft
        for task in result["candidate_tasks"]
        for draft in task["redacted_payload_drafts"]
        if draft["operation"] == "create_unit"
    ]
    assert len(unit_drafts) == 2
    title_sets = [
        {row["title"] for row in draft["payload"]["promotion_materials"]["title_material_list"]}
        for draft in unit_drafts
    ]
    assert title_sets[0].isdisjoint(title_sets[1])
    assert "_account_unit_ordinal" not in unit_drafts[0]["payload"]


def test_wx_mini_game_templates_keep_unit_material_contract_clean():
    catalog = json.loads(Path("configs/create-templates/wx-mini-game.json").read_text(encoding="utf-8"))

    for template_key, template in catalog["templates"].items():
        assert template["anchor_related_type"] == "SELECT", template_key
        assert template["anchor_id"], template_key
        assert template["anchor_type"] == "APP_GAME", template_key
        assert template["source_name"] == template["product_name"], template_key
        assert len(template["title_pool"]) >= 3, template_key
        assert len(template["product_selling_points"]) >= 3, template_key
        assert template["title_pool"] != template["product_selling_points"], template_key
        assert all(title not in template["product_selling_points"] for title in template["title_pool"][:4]), template_key
        assert any(("，" in title or "！" in title or "？" in title) for title in template["title_pool"]), template_key
        assert len(template["cta_pool"]) >= 3, template_key

def test_wx_mini_game_templates_follow_gender_and_7r_matrix():
    templates = json.loads(Path("configs/create-templates/wx-mini-game.json").read_text(encoding="utf-8"))["templates"]

    expected = {
        "wx_pay_general": {"gender": None, "requires_roi_goal": False, "deep_external_action": None},
        "wx_pay_male": {"gender": "GENDER_MALE", "requires_roi_goal": False, "deep_external_action": None},
        "wx_7r_general": {
            "gender": None,
            "requires_roi_goal": True,
            "deep_external_action": "AD_CONVERT_TYPE_PURCHASE_ROI_7D",
        },
        "wx_7r_male": {
            "gender": "GENDER_MALE",
            "requires_roi_goal": True,
            "deep_external_action": "AD_CONVERT_TYPE_PURCHASE_ROI_7D",
        },
    }
    shared_fields = [
        "source_name",
        "product_name",
        "title_pool",
        "product_selling_points",
        "cta_pool",
        "landing_url",
        "micro_app_instance_id",
        "delivery_identity",
        "aweme_ids",
        "anchor_id",
        "anchor_type",
        "product_image_id",
        "fixed_video_cover_id",
    ]

    baseline = templates["wx_7r_male"]
    for template_key, values in expected.items():
        template = templates[template_key]
        fixed = template["project_fixed"]
        assert template["requires_roi_goal"] is values["requires_roi_goal"], template_key
        assert fixed.get("audience_gender") == values["gender"], template_key
        assert fixed.get("deep_external_action") == values["deep_external_action"], template_key
        assert ("roi_goal" not in fixed), template_key
        for field in shared_fields:
            assert template[field] == baseline[field], (template_key, field)

def test_provider_payload_contract_blocks_unmapped_internal_payload_fields():
    field_map = default_provider_field_map(
        {
            "provider_adapter": {
                "provider": "oceanengine",
                "field_mapping_version": "phase1.oceanengine.create_payload.draft.v1",
            }
        }
    )
    field_map["mapping_verified"] = True
    for entries in field_map["operations"].values():
        for entry in entries:
            entry["provider_field"] = entry["internal_field"]
            entry["verified"] = True
    field_contract = {
        "status": "verified",
        "provider": "oceanengine",
        "mapping_verified": True,
    }
    adapter = {
        "provider": "oceanengine",
        "transport": "disabled_provider_adapter",
        "mapping_verified": True,
        "field_mapping_version": "phase1.oceanengine.create_payload.draft.v1",
    }
    tasks = [
        {
            "live_api_payloads": [],
            "redacted_payload_drafts": [
                {
                    "operation": "create_project",
                    "idempotency_key": "idem-1",
                    "endpoint": "",
                        "payload": {
                            "advertiser_id": "target-1",
                            "project_name": "name-1",
                            "daily_budget": 300.0,
                            "field_defaults": {},
                            "new_internal_field": "must-not-pass-through",
                    },
                }
            ],
        }
    ]

    provider_payload_drafts = build_provider_payload_drafts(
        tasks=tasks,
        adapter=adapter,
        provider_field_map=field_map,
        provider_field_map_contract=field_contract,
    )
    adapter_contract = provider_adapter_contract(
        adapter=adapter,
        provider_payload_drafts=provider_payload_drafts,
        tasks=tasks,
    )
    readiness = provider_readiness_contract(
        provider_adapter_contract=adapter_contract,
        provider_field_map_contract=field_contract,
        payload_draft_contract={
            "executable_draft_count": 0,
            "live_payload_count": 0,
        },
    )

    assert provider_payload_drafts[0]["field_mapping_applied"] is False
    assert provider_payload_drafts[0]["unmapped_payload_fields"] == [
        {"operation": "create_project", "internal_field": "new_internal_field"}
    ]
    assert adapter_contract["unmapped_payload_field_count"] == 1
    assert readiness["ready_for_live_execute"] is False
    assert "provider payload drafts contain unmapped internal fields" in readiness["blocking_reasons"]

def test_create_dry_run_falls_back_to_unverified_provider_field_map_for_bad_config(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    _seed_create_db(db_path)
    plan = build_create_strategy_plan(request=_create_request()["create_request"], db_path=db_path, policy={})
    preflight = build_create_preflight(create_strategy_plan_artifact=plan, db_path=db_path, policy={})
    field_map_path = tmp_path / "bad-provider-field-map.json"
    field_map_path.write_text(json.dumps({"provider": "oceanengine"}), encoding="utf-8")

    result = build_create_dry_run(
        create_strategy_plan_artifact=plan,
        create_preflight_artifact=preflight,
        policy={"provider_field_map_path": str(field_map_path)},
    )

    assert result["provider_field_map"]["source"] == "phase1_placeholder_invalid_provider_field_map_config"
    assert result["provider_field_map_contract"]["status"] == "unverified"
    assert result["provider_field_map_digest"]["algorithm"] == "sha256"
    assert re.fullmatch(r"[0-9a-f]{64}", result["provider_field_map_digest"]["value"])
    assert result["provider_readiness_contract"]["ready_for_live_execute"] is False

def test_create_provider_field_map_check_reports_unverified_example_config():
    result = build_create_provider_field_map_check(
        policy={
            "provider_adapter": {
                "provider": "oceanengine",
                "field_mapping_version": "phase1.oceanengine.create_payload.draft.v1",
            },
            "provider_field_map_path": "configs/provider-field-maps/oceanengine.create.phase1.example.json",
        }
    )

    assert result["ok"] is True
    assert result["workflow"] == "create_provider_field_map_check"
    assert result["phase"] == "phase1"
    assert result["execution_enabled"] is False
    assert result["external_api_calls"] == 0
    assert result["status"] == "unverified"
    assert result["summary"] == {
        "provider": "oceanengine",
        "field_map_path": "configs/provider-field-maps/oceanengine.create.phase1.example.json",
        "operation_count": 4,
        "field_count": 35,
        "verified_field_count": 0,
        "missing_provider_field_count": 35,
        "missing_required_field_count": 0,
        "duplicate_internal_field_count": 0,
        "duplicate_provider_field_count": 0,
        "unknown_internal_field_count": 0,
        "provider_mismatch_count": 0,
        "field_mapping_version_mismatch_count": 0,
        "ready_for_live_execute": False,
    }
    assert result["provider_field_map_contract"]["status"] == "unverified"
    assert result["provider_readiness_contract"]["ready_for_live_execute"] is False
    assert result["missing_provider_fields"][0] == {
        "operation": "create_project",
        "internal_field": "advertiser_id",
    }
    assert result["missing_required_fields"] == []
    assert result["unverified_fields"][0] == {
        "operation": "create_project",
        "internal_field": "advertiser_id",
    }
    assert result["violations"] == []
    assert result["actions"] == []

def test_create_provider_field_map_check_requires_top_level_mapping_verified(tmp_path: Path):
    field_map = default_provider_field_map(
        {
            "provider_adapter": {
                "provider": "oceanengine",
                "field_mapping_version": "phase1.oceanengine.create_payload.draft.v1",
            }
        }
    )
    field_map["source"] = "unit_test_rows_verified_but_map_not_confirmed"
    for entries in field_map["operations"].values():
        for entry in entries:
            entry["provider_field"] = entry["internal_field"]
            entry["verified"] = True
            entry["source"] = "unit_test"
    field_map_path = tmp_path / "rows-verified-map-not-confirmed.json"
    field_map_path.write_text(json.dumps(field_map, ensure_ascii=False), encoding="utf-8")

    result = build_create_provider_field_map_check(
        policy={
            "provider_adapter": {
                "provider": "oceanengine",
                "field_mapping_version": "phase1.oceanengine.create_payload.draft.v1",
                "mapping_verified": True,
            },
            "provider_field_map_path": str(field_map_path),
        }
    )

    assert result["status"] == "unverified"
    assert result["provider_field_map_contract"]["mapping_verified"] is False
    assert result["provider_readiness_contract"]["ready_for_live_execute"] is False
    assert "provider field map is not verified" in result["provider_readiness_contract"]["blocking_reasons"]

def test_create_provider_field_map_check_marks_bad_config_invalid(tmp_path: Path):
    bad_path = tmp_path / "bad-field-map.json"
    bad_path.write_text(json.dumps({"provider": "oceanengine"}), encoding="utf-8")

    result = build_create_provider_field_map_check(policy={"provider_field_map_path": str(bad_path)})

    assert result["ok"] is False
    assert result["status"] == "invalid"
    assert result["provider_field_map"]["source"] == "phase1_placeholder_invalid_provider_field_map_config"
    assert "provider field map config is missing or malformed" in result["violations"]
    assert result["actions"] == []

def test_create_provider_field_map_check_detects_missing_required_internal_field(tmp_path: Path):
    field_map = default_provider_field_map(
        {
            "provider_adapter": {
                "provider": "oceanengine",
                "field_mapping_version": "phase1.oceanengine.create_payload.draft.v1",
            }
        }
    )
    field_map["mapping_verified"] = True
    field_map["source"] = "unit_test_missing_required_field"
    for entries in field_map["operations"].values():
        for entry in entries:
            entry["provider_field"] = entry["internal_field"]
            entry["verified"] = True
            entry["source"] = "unit_test"
    field_map["operations"]["bind_material"] = [
        entry for entry in field_map["operations"]["bind_material"] if entry["internal_field"] != "material_id"
    ]
    field_map_path = tmp_path / "missing-material-id-field-map.json"
    field_map_path.write_text(json.dumps(field_map, ensure_ascii=False), encoding="utf-8")

    result = build_create_provider_field_map_check(
        policy={
            "provider_adapter": {
                "provider": "oceanengine",
                "field_mapping_version": "phase1.oceanengine.create_payload.draft.v1",
                "mapping_verified": True,
            },
            "provider_field_map_path": str(field_map_path),
        }
    )

    assert result["ok"] is True
    assert result["status"] == "unverified"
    assert result["provider_field_map_contract"]["status"] == "unverified"
    assert result["provider_field_map_digest"]["algorithm"] == "sha256"
    assert re.fullmatch(r"[0-9a-f]{64}", result["provider_field_map_digest"]["value"])
    assert result["provider_field_map_contract"]["missing_required_field_count"] == 1
    assert result["provider_field_map_contract"]["missing_required_fields"] == [
        {"operation": "bind_material", "internal_field": "material_id"}
    ]
    assert result["missing_required_fields"] == [
        {"operation": "bind_material", "internal_field": "material_id"}
    ]
    assert result["provider_readiness_contract"]["ready_for_live_execute"] is False
    assert "provider field map is not verified" in result["provider_readiness_contract"]["blocking_reasons"]

def test_create_provider_field_map_check_detects_duplicate_and_unknown_internal_fields(tmp_path: Path):
    field_map = default_provider_field_map(
        {
            "provider_adapter": {
                "provider": "oceanengine",
                "field_mapping_version": "phase1.oceanengine.create_payload.draft.v1",
            }
        }
    )
    field_map["mapping_verified"] = True
    field_map["source"] = "unit_test_duplicate_unknown_fields"
    for entries in field_map["operations"].values():
        for entry in entries:
            entry["provider_field"] = entry["internal_field"]
            entry["verified"] = True
            entry["source"] = "unit_test"
    field_map["operations"]["create_project"].append(
        {
            "internal_field": "advertiser_id",
            "provider_field": "advertiser_id",
            "purpose": "duplicate target advertiser account id",
            "verified": True,
            "required": True,
            "source": "unit_test",
        }
    )
    field_map["operations"]["create_unit"].append(
        {
            "internal_field": "unknown_field",
            "provider_field": "unknown_provider_field",
            "purpose": "unknown unit field",
            "verified": True,
            "required": False,
            "source": "unit_test",
        }
    )
    field_map_path = tmp_path / "duplicate-unknown-field-map.json"
    field_map_path.write_text(json.dumps(field_map, ensure_ascii=False), encoding="utf-8")

    result = build_create_provider_field_map_check(
        policy={
            "provider_adapter": {
                "provider": "oceanengine",
                "field_mapping_version": "phase1.oceanengine.create_payload.draft.v1",
                "mapping_verified": True,
            },
            "provider_field_map_path": str(field_map_path),
        }
    )

    assert result["status"] == "unverified"
    assert result["provider_field_map_digest"]["algorithm"] == "sha256"
    assert re.fullmatch(r"[0-9a-f]{64}", result["provider_field_map_digest"]["value"])
    assert result["provider_field_map_contract"]["duplicate_internal_field_count"] == 1
    assert result["provider_field_map_contract"]["duplicate_internal_fields"] == [
        {"operation": "create_project", "internal_field": "advertiser_id"}
    ]
    assert result["provider_field_map_contract"]["unknown_internal_field_count"] == 1
    assert result["provider_field_map_contract"]["unknown_internal_fields"] == [
        {"operation": "create_unit", "internal_field": "unknown_field"}
    ]
    assert result["duplicate_internal_fields"] == [
        {"operation": "create_project", "internal_field": "advertiser_id"}
    ]
    assert result["unknown_internal_fields"] == [
        {"operation": "create_unit", "internal_field": "unknown_field"}
    ]
    assert result["provider_readiness_contract"]["ready_for_live_execute"] is False

def test_create_provider_field_map_check_detects_duplicate_provider_fields(tmp_path: Path):
    field_map = default_provider_field_map(
        {
            "provider_adapter": {
                "provider": "oceanengine",
                "field_mapping_version": "phase1.oceanengine.create_payload.draft.v1",
            }
        }
    )
    field_map["mapping_verified"] = True
    field_map["source"] = "unit_test_duplicate_provider_fields"
    for entries in field_map["operations"].values():
        for entry in entries:
            entry["provider_field"] = entry["internal_field"]
            entry["verified"] = True
            entry["source"] = "unit_test"
    for entry in field_map["operations"]["create_project"]:
        if entry["internal_field"] == "project_name":
            entry["provider_field"] = "advertiser_id"
    field_map_path = tmp_path / "duplicate-provider-field-map.json"
    field_map_path.write_text(json.dumps(field_map, ensure_ascii=False), encoding="utf-8")

    result = build_create_provider_field_map_check(
        policy={
            "provider_adapter": {
                "provider": "oceanengine",
                "field_mapping_version": "phase1.oceanengine.create_payload.draft.v1",
                "mapping_verified": True,
            },
            "provider_field_map_path": str(field_map_path),
        }
    )

    assert result["status"] == "unverified"
    assert result["summary"]["duplicate_provider_field_count"] == 1
    assert result["provider_field_map_contract"]["duplicate_provider_field_count"] == 1
    assert result["provider_field_map_contract"]["duplicate_provider_fields"] == [
        {
            "operation": "create_project",
            "provider_field": "advertiser_id",
            "internal_fields": ["advertiser_id", "project_name"],
        }
    ]
    assert result["duplicate_provider_fields"] == [
        {
            "operation": "create_project",
            "provider_field": "advertiser_id",
            "internal_fields": ["advertiser_id", "project_name"],
        }
    ]
    assert result["provider_readiness_contract"]["ready_for_live_execute"] is False

def test_create_provider_field_map_check_detects_provider_and_version_mismatch(tmp_path: Path):
    field_map = default_provider_field_map(
        {
            "provider_adapter": {
                "provider": "other_provider",
                "field_mapping_version": "phase1.other.create_payload.draft.v9",
            }
        }
    )
    field_map["mapping_verified"] = True
    field_map["source"] = "unit_test_provider_version_mismatch"
    for entries in field_map["operations"].values():
        for entry in entries:
            entry["provider_field"] = entry["internal_field"]
            entry["verified"] = True
            entry["source"] = "unit_test"
    field_map_path = tmp_path / "provider-version-mismatch-field-map.json"
    field_map_path.write_text(json.dumps(field_map, ensure_ascii=False), encoding="utf-8")

    result = build_create_provider_field_map_check(
        policy={
            "provider_adapter": {
                "provider": "oceanengine",
                "field_mapping_version": "phase1.oceanengine.create_payload.draft.v1",
                "mapping_verified": True,
            },
            "provider_field_map_path": str(field_map_path),
        }
    )

    assert result["status"] == "unverified"
    assert result["provider_field_map_contract"]["provider_mismatch_count"] == 1
    assert result["provider_field_map_contract"]["provider_mismatches"] == [
        {"expected": "oceanengine", "actual": "other_provider"}
    ]
    assert result["provider_field_map_contract"]["field_mapping_version_mismatch_count"] == 1
    assert result["provider_field_map_contract"]["field_mapping_version_mismatches"] == [
        {
            "expected": "phase1.oceanengine.create_payload.draft.v1",
            "actual": "phase1.other.create_payload.draft.v9",
        }
    ]
    assert result["provider_readiness_contract"]["ready_for_live_execute"] is False

def test_run_create_provider_field_map_check_request_writes_artifact(tmp_path: Path):
    result = run_create_provider_field_map_check_request(
        {
            "create_provider_field_map_check": {
                "policy": {
                    "provider_field_map_path": "configs/provider-field-maps/oceanengine.create.phase1.example.json"
                }
            }
        },
        runs_dir=tmp_path / "runs",
    )

    assert Path(result["artifact_path"]).exists()
    assert result["workflow"] == "create_provider_field_map_check"
    assert result["summary"]["field_count"] == 35

def test_create_provider_field_map_check_cli_uses_policy_config(tmp_path: Path, capsys):
    db_path = tmp_path / "roibang.sqlite3"
    runtime_path = _runtime_config(tmp_path, db_path)
    module = _load_script("run_create_provider_field_map_check")

    exit_code = module.run_from_args(["--config", str(runtime_path), "--policy", "policies/create-policy.example.json"])

    output = json.loads(capsys.readouterr().out)
    artifact = json.loads(Path(output["artifact_path"]).read_text(encoding="utf-8"))
    assert exit_code == 0
    assert output["status"] == "verified"
    assert artifact["workflow"] == "create_provider_field_map_check"
    assert artifact["summary"]["field_map_path"] == "configs/provider-field-maps/oceanengine.create.phase2-prep.example.json"
    assert artifact["execution_enabled"] is False
    assert artifact["external_api_calls"] == 0
    assert artifact["actions"] == []

def test_create_field_mapping_review_pack_lists_fields_without_requiring_user_input_now():
    result = build_create_field_mapping_review_pack(
        policy={
            "provider_adapter": {
                "provider": "oceanengine",
                "field_mapping_version": "phase1.oceanengine.create_payload.draft.v1",
            },
            "provider_field_map_path": "configs/provider-field-maps/oceanengine.create.phase1.example.json",
        }
    )

    assert result["ok"] is True
    assert result["workflow"] == "create_field_mapping_review_pack"
    assert result["phase"] == "phase1"
    assert result["execution_enabled"] is False
    assert result["external_api_calls"] == 0
    assert result["status"] == "needs_review"
    assert result["required_user_input_now"] is False
    assert result["summary"] == {
        "provider": "oceanengine",
        "field_mapping_version": "phase1.oceanengine.create_payload.draft.v1",
        "field_map_path": "configs/provider-field-maps/oceanengine.create.phase1.example.json",
        "operation_count": 4,
        "field_count": 35,
        "needs_provider_field_count": 35,
        "needs_verification_count": 35,
        "ready_for_live_execute": False,
    }
    assert result["review_contract"] == {
        "status": "needs_review",
            "field_count": 35,
            "needs_provider_field_count": 35,
            "needs_verification_count": 35,
        "verified_field_count": 0,
        "missing_required_field_count": 0,
        "duplicate_internal_field_count": 0,
        "duplicate_provider_field_count": 0,
        "unknown_internal_field_count": 0,
    }
    first_section = result["review_sections"][0]
    assert first_section["operation"] == "create_project"
    assert first_section["endpoint"] == ""
    assert first_section["field_source"] == "create_strategy_plan.strategy.projects[]"
    assert first_section["fields"][0] == {
        "internal_field": "advertiser_id",
        "provider_field": "",
        "required": True,
        "verified": False,
        "purpose": "target advertiser account id",
        "source": "internal_phase1_schema",
        "review_status": "needs_provider_field",
    }
    assert result["provider_readiness_contract"]["ready_for_live_execute"] is False
    assert result["violations"] == []
    assert result["actions"] == []

def test_run_create_field_mapping_review_pack_request_writes_artifact(tmp_path: Path):
    result = run_create_field_mapping_review_pack_request(
        {
            "create_field_mapping_review_pack": {
                "policy": {
                    "provider_field_map_path": "configs/provider-field-maps/oceanengine.create.phase1.example.json"
                }
            }
        },
        runs_dir=tmp_path / "runs",
    )

    artifact = json.loads(Path(result["artifact_path"]).read_text(encoding="utf-8"))
    assert result["workflow"] == "create_field_mapping_review_pack"
    assert result["summary"]["field_count"] == 35
    assert artifact["workflow"] == "create_field_mapping_review_pack"
    assert artifact["actions"] == []

def test_create_field_mapping_review_pack_cli_uses_policy_config(tmp_path: Path, capsys):
    db_path = tmp_path / "roibang.sqlite3"
    runtime_path = _runtime_config(tmp_path, db_path)
    module = _load_script("run_create_field_mapping_review_pack")

    exit_code = module.run_from_args(["--config", str(runtime_path), "--policy", "policies/create-policy.example.json"])

    output = json.loads(capsys.readouterr().out)
    artifact = json.loads(Path(output["artifact_path"]).read_text(encoding="utf-8"))
    assert exit_code == 0
    assert output["workflow"] == "create_field_mapping_review_pack"
    assert output["status"] == "verified"
    assert artifact["summary"]["field_map_path"] == "configs/provider-field-maps/oceanengine.create.phase2-prep.example.json"
    assert artifact["required_user_input_now"] is False
    assert artifact["execution_enabled"] is False
    assert artifact["external_api_calls"] == 0
    assert artifact["actions"] == []

def test_create_phase2_provider_mapping_prep_builds_review_matrix_without_execute():
    result = build_create_phase2_provider_mapping_prep(
        policy={
            "provider_adapter": {
                "provider": "oceanengine",
                "field_mapping_version": "phase2.oceanengine.create_payload.prep.v1",
            },
            "provider_field_map_path": "configs/provider-field-maps/oceanengine.create.phase2-prep.example.json",
            "live_api": {
                "endpoints": {
                    "create_project": "/open_api/v3.0/project/create/",
                    "create_unit": "/open_api/v3.0/promotion/create/",
                    "bind_material": "/open_api/2/file/material/bind/",
                }
            },
        }
    )

    assert result["ok"] is True
    assert result["workflow"] == "create_phase2_provider_mapping_prep"
    assert result["phase"] == "phase2_preparation"
    assert result["execution_enabled"] is False
    assert result["external_api_calls"] == 0
    assert result["status"] == "needs_review"
    assert result["summary"] == {
        "provider": "oceanengine",
        "field_mapping_version": "phase2.oceanengine.create_payload.prep.v1",
            "field_map_path": "configs/provider-field-maps/oceanengine.create.phase2-prep.example.json",
            "operation_count": 4,
            "field_count": 39,
            "candidate_provider_field_count": 25,
            "verified_field_count": 25,
            "unresolved_field_count": 0,
        "open_question_count": 6,
        "ready_for_live_payload_development": False,
        "ready_for_live_execute": False,
    }
    assert result["phase2_preparation_contract"] == {
        "review_only": True,
        "live_payload_generation_enabled": False,
        "create_execute_hard_block_required": True,
        "next_required_reviews": [
            "provider_field_mapping",
            "template_slots",
            "project_naming_rules",
        ],
    }
    project_section = result["review_matrix"][0]
    assert project_section["operation"] == "create_project"
    assert project_section["endpoint"] == "/open_api/v3.0/project/create/"
    assert project_section["field_source"] == "create_strategy_plan.strategy.projects[]"
    assert project_section["fields"][0] == {
        "internal_field": "advertiser_id",
        "provider_field": "advertiser_id",
        "provider_object": "project_create_request",
        "mapping_kind": "direct",
        "value_source": "create_strategy_plan.strategy.projects[].advertiser_id",
        "evidence_refs": ["oceanengine_openapi_project_create_request"],
        "open_questions": [],
        "review_status": "verified",
    }
    unresolved = [
        item
        for item in result["unresolved_mappings"]
        if item["operation"] == "create_project" and item["internal_field"] == "field_defaults.landing_type"
    ]
    assert unresolved == []
    assert result["provider_field_map_contract"]["status"] == "verified"
    assert result["provider_readiness_contract"]["ready_for_live_execute"] is False
    assert result["violations"] == []
    assert result["actions"] == []

def test_run_create_phase2_provider_mapping_prep_request_writes_artifact(tmp_path: Path):
    result = run_create_phase2_provider_mapping_prep_request(
        {
            "create_phase2_provider_mapping_prep": {
                "policy": {
                    "provider_adapter": {
                        "provider": "oceanengine",
                        "field_mapping_version": "phase2.oceanengine.create_payload.prep.v1",
                    },
                    "provider_field_map_path": "configs/provider-field-maps/oceanengine.create.phase2-prep.example.json",
                }
            }
        },
        runs_dir=tmp_path / "runs",
    )

    artifact = json.loads(Path(result["artifact_path"]).read_text(encoding="utf-8"))
    assert result["workflow"] == "create_phase2_provider_mapping_prep"
    assert result["summary"]["field_count"] == 39
    assert artifact["phase"] == "phase2_preparation"
    assert artifact["execution_enabled"] is False
    assert artifact["external_api_calls"] == 0
    assert artifact["actions"] == []

def test_create_phase2_provider_mapping_prep_cli_uses_policy_config(tmp_path: Path, capsys):
    db_path = tmp_path / "roibang.sqlite3"
    runtime_path = _runtime_config(tmp_path, db_path)
    module = _load_script("run_create_phase2_provider_mapping_prep")

    exit_code = module.run_from_args(["--config", str(runtime_path), "--policy", "policies/create-policy.example.json"])

    output = json.loads(capsys.readouterr().out)
    artifact = json.loads(Path(output["artifact_path"]).read_text(encoding="utf-8"))
    assert exit_code == 0
    assert output["workflow"] == "create_phase2_provider_mapping_prep"
    assert output["status"] == "needs_review"
    assert artifact["phase"] == "phase2_preparation"
    assert artifact["summary"]["field_map_path"] == "configs/provider-field-maps/oceanengine.create.phase2-prep.example.json"
    assert artifact["execution_enabled"] is False
    assert artifact["external_api_calls"] == 0
    assert artifact["actions"] == []

def test_create_provider_evidence_review_flags_unreviewed_phase2_evidence():
    result = build_create_provider_evidence_review(
        policy={
            "provider_adapter": {
                "provider": "oceanengine",
                "field_mapping_version": "phase2.oceanengine.create_payload.prep.v1",
            },
            "provider_field_map_path": "configs/provider-field-maps/oceanengine.create.phase2-prep.example.json",
            "provider_evidence_catalog_path": "configs/provider-evidence/oceanengine.create.phase2-review.example.json",
        }
    )

    assert result["ok"] is True
    assert result["workflow"] == "create_provider_evidence_review"
    assert result["phase"] == "phase2_preparation"
    assert result["execution_enabled"] is False
    assert result["external_api_calls"] == 0
    assert result["status"] == "needs_review"
    assert result["summary"] == {
        "provider": "oceanengine",
        "field_mapping_version": "phase2.oceanengine.create_payload.prep.v1",
        "field_map_path": "configs/provider-field-maps/oceanengine.create.phase2-prep.example.json",
        "evidence_catalog_path": "configs/provider-evidence/oceanengine.create.phase2-review.example.json",
        "field_count": 39,
        "catalog_evidence_count": 4,
        "reviewed_evidence_count": 4,
        "ready_field_count": 25,
        "unresolved_field_count": 0,
        "evidence_status_counts": {
            "local_only_confirmed": 14,
            "verified": 25,
        },
        "ready_for_live_payload_development": False,
        "ready_for_live_execute": False,
    }
    first_section = result["evidence_review_sections"][0]
    assert first_section["operation"] == "create_project"
    assert first_section["fields"][0] == {
        "internal_field": "advertiser_id",
        "provider_field": "advertiser_id",
        "mapping_kind": "direct",
        "evidence_refs": ["oceanengine_openapi_project_create_request"],
        "evidence_status": "verified",
        "evidence_issues": [],
    }
    unresolved_local = [
        item
        for item in result["unresolved_evidence_items"]
        if item["operation"] == "create_unit" and item["internal_field"] == "project_key"
    ]
    assert unresolved_local == []
    assert result["phase2_provider_evidence_contract"] == {
        "review_only": True,
        "external_api_allowed": False,
        "live_payload_generation_enabled": False,
        "create_execute_hard_block_required": True,
        "mapping_verified_must_remain_false": True,
    }
    assert result["operator_guide"] == {
        "status": "needs_review",
        "title": "平台字段证据仍需人工复核",
        "ordered_steps": [
            "先补证据目录里的 source_url 或 captured_request_ref。",
            "人工核对后，把对应 evidence.reviewed 改为 true，并填写 reviewed_by 和 reviewed_at。",
            "确认 local-only 字段不会进入平台 payload 后，再在字段映射里标记 local_only_confirmed=true。",
            "证据和字段都确认后，才考虑把具体字段 verified 改为 true。",
            "重新运行 provider evidence review 脚本查看剩余项。",
        ],
        "blocked_until": [
            "所有平台字段都有已复核证据",
            "所有 local-only 字段已明确确认",
            "create_execute 仍保持 hard-blocked",
        ],
        "next_command": "PYTHONPATH=src python3 scripts/run_create_provider_evidence_review.py --config configs/runtime.example.json --policy policies/create-policy.example.json",
    }
    assert result["evidence_worksheet"]["summary"] == {
        "worksheet_version": "phase2.provider_evidence_worksheet.v1",
            "row_count": 39,
        "requires_evidence_review_count": 0,
        "requires_local_confirmation_count": 0,
        "requires_provider_field_count": 0,
            "ready_row_count": 39,
    }
    assert result["evidence_worksheet"]["rows"][0] == {
        "operation": "create_project",
        "internal_field": "advertiser_id",
        "provider_field": "advertiser_id",
        "mapping_kind": "direct",
        "evidence_status": "verified",
        "evidence_refs": ["oceanengine_openapi_project_create_request"],
        "fill_required": [],
        "do_not_change": [
            "execution_enabled",
            "external_api_calls",
            "actions",
        ],
    }
    assert result["manual_review_workbench"]["summary"] == {
        "workbench_version": "phase2.manual_review_workbench.v1",
        "candidate_field_count": 0,
        "local_only_confirmation_count": 0,
        "evidence_review_count": 0,
        "ready_to_edit_json": True,
        "execution_enabled": False,
        "external_api_calls": 0,
    }
    assert result["manual_review_workbench"]["candidate_fields"] == []
    assert result["manual_review_workbench"]["local_only_confirmations"] == []
    assert result["manual_review_workbench"]["evidence_reviews"] == []
    local_only_row = [
        row
        for row in result["evidence_worksheet"]["rows"]
        if row["operation"] == "create_unit" and row["internal_field"] == "project_key"
    ][0]
    assert local_only_row["fill_required"] == []
    assert result["provider_field_gap_report"]["summary"] == {
        "gap_count": 0,
        "operation_counts": {},
        "ready_for_live_payload_development": False,
    }
    assert result["provider_field_gap_report"]["rows"] == []
    assert result["provider_field_gap_resolution_plan"]["summary"] == {
        "plan_version": "phase2.provider_field_gap_resolution.v1",
        "gap_count": 0,
        "manual_review_required": False,
        "ready_for_live_payload_development": False,
    }
    assert result["provider_field_gap_resolution_plan"]["items"] == []
    assert [
        item
        for item in result["provider_field_gap_resolution_plan"]["items"]
        if item["operation"] == "bind_material" and item["internal_field"] == "source_video_id"
    ] == []
    assert result["project_type_local_usage_review"]["summary"] == {
        "review_version": "phase2.project_type_local_usage_review.v1",
        "internal_field": "project_type",
        "local_usage_evidence_count": 6,
        "blocking_item_count": 0,
        "manual_confirmation_required": True,
        "ready_to_mark_local_only": True,
    }
    assert result["project_type_local_usage_review"]["local_usage_evidence"][0] == {
        "usage_kind": "template_selector",
        "source": "create_phase2_yzt_create_preview._project_type",
        "meaning": "从项目模板名称推导本地 project_type，用于区分 WX_PAY 和 WX_PAY_7R。",
    }
    assert result["project_type_local_usage_review"]["blocking_items"] == []
    assert result["field_gap_convergence_plan"]["summary"] == {
        "plan_version": "phase2.field_gap_convergence.v1",
        "project_type_ready_for_manual_local_only_confirmation": True,
        "remaining_provider_field_gap_count": 0,
        "field_defaults_split_item_count": 0,
        "source_video_id_review_required": False,
        "ready_for_live_payload_development": False,
    }
    assert result["field_gap_convergence_plan"]["project_type_decision"] == {
        "operation": "create_project",
        "internal_field": "project_type",
        "recommended_mapping_kind": "local_only",
        "local_only_confirmed": False,
        "reason": "已从禁用请求体 schema 和 dry-run payload 移除，只保留本地模板、命名、批次码和复盘用途。",
        "blocked_until": ["人工确认 local_only_confirmed=true"],
    }
    assert result["field_gap_convergence_plan"]["field_defaults_split_plan"]["items"] == []
    assert result["field_gap_convergence_plan"]["source_video_id_review"] == {
        "operation": "bind_material",
        "internal_field": "source_video_id",
        "recommended_mapping_kind": "local_only",
        "local_only_confirmed": False,
        "reason": "保留在本地材料对象中用于源视频追溯，已从禁用请求体 schema 和 dry-run payload 移除。",
        "blocked_until": ["人工确认 local_only_confirmed=true"],
    }
    assert result["violations"] == []
    assert result["actions"] == []

def test_create_provider_evidence_review_rejects_missing_catalog(tmp_path: Path):
    result = build_create_provider_evidence_review(
        policy={
            "provider_field_map_path": "configs/provider-field-maps/oceanengine.create.phase2-prep.example.json",
            "provider_evidence_catalog_path": str(tmp_path / "missing.json"),
        }
    )

    assert result["ok"] is False
    assert result["status"] == "invalid"
    assert result["summary"]["catalog_evidence_count"] == 0
    assert result["violations"] == ["provider evidence catalog config is missing or malformed"]
    assert result["execution_enabled"] is False
    assert result["external_api_calls"] == 0
    assert result["actions"] == []

def test_create_provider_evidence_review_accepts_explicit_local_only_confirmation(tmp_path: Path):
    field_map = json.loads(
        Path("configs/provider-field-maps/oceanengine.create.phase2-prep.example.json").read_text(encoding="utf-8")
    )
    for rows in field_map["operations"].values():
        for entry in rows:
            if entry.get("mapping_kind") in {"local_lookup_key", "local_only"}:
                entry["local_only_confirmed"] = True
                entry["local_only_confirmation_note"] = "unit test confirms the field is used only for local lookup"
    field_map_path = tmp_path / "field-map.json"
    field_map_path.write_text(json.dumps(field_map, ensure_ascii=False), encoding="utf-8")

    result = build_create_provider_evidence_review(
        policy={
            "provider_field_map_path": str(field_map_path),
            "provider_evidence_catalog_path": "configs/provider-evidence/oceanengine.create.phase2-review.example.json",
        }
    )

    assert result["summary"]["evidence_status_counts"] == {
        "local_only_confirmed": 14,
        "verified": 25,
    }
    assert result["summary"]["unresolved_field_count"] == 0
    assert result["evidence_worksheet"]["summary"]["requires_local_confirmation_count"] == 0
    confirmed_rows = [
        row
        for row in result["evidence_worksheet"]["rows"]
        if row["evidence_status"] == "local_only_confirmed"
    ]
    assert len(confirmed_rows) == 14
    assert all(row["fill_required"] == [] for row in confirmed_rows)
    assert result["execution_enabled"] is False
    assert result["external_api_calls"] == 0
    assert result["actions"] == []

def test_run_create_provider_evidence_review_request_writes_artifact(tmp_path: Path):
    result = run_create_provider_evidence_review_request(
        {
            "create_provider_evidence_review": {
                "policy": {
                    "provider_field_map_path": "configs/provider-field-maps/oceanengine.create.phase2-prep.example.json",
                    "provider_evidence_catalog_path": "configs/provider-evidence/oceanengine.create.phase2-review.example.json",
                }
            }
        },
        runs_dir=tmp_path / "runs",
    )

    artifact = json.loads(Path(result["artifact_path"]).read_text(encoding="utf-8"))
    assert result["workflow"] == "create_provider_evidence_review"
    assert result["summary"]["field_count"] == 39
    assert artifact["workflow"] == "create_provider_evidence_review"
    assert artifact["execution_enabled"] is False
    assert artifact["external_api_calls"] == 0
    assert artifact["actions"] == []

def test_create_provider_evidence_review_cli_uses_policy_config(tmp_path: Path, capsys):
    db_path = tmp_path / "roibang.sqlite3"
    runtime_path = _runtime_config(tmp_path, db_path)
    module = _load_script("run_create_provider_evidence_review")

    exit_code = module.run_from_args(["--config", str(runtime_path), "--policy", "policies/create-policy.example.json"])

    output = json.loads(capsys.readouterr().out)
    artifact = json.loads(Path(output["artifact_path"]).read_text(encoding="utf-8"))
    assert exit_code == 0
    assert output["workflow"] == "create_provider_evidence_review"
    assert output["status"] == "needs_review"
    assert artifact["phase"] == "phase2_preparation"
    assert artifact["summary"]["evidence_catalog_path"] == "configs/provider-evidence/oceanengine.create.phase2-review.example.json"
    assert output["operator_guide"]["status"] == "needs_review"
    assert output["evidence_worksheet_summary"]["row_count"] == 39
    assert output["provider_field_gap_summary"]["gap_count"] == 0
    assert output["provider_field_gap_resolution_summary"]["gap_count"] == 0
    assert output["project_type_local_usage_summary"]["ready_to_mark_local_only"] is True
    assert output["field_gap_convergence_summary"]["remaining_provider_field_gap_count"] == 0
    assert output["manual_review_workbench_summary"] == {
        "workbench_version": "phase2.manual_review_workbench.v1",
        "candidate_field_count": 0,
        "local_only_confirmation_count": 0,
        "evidence_review_count": 0,
        "ready_to_edit_json": True,
        "execution_enabled": False,
        "external_api_calls": 0,
    }
    assert output["manual_review_next_items"] == {
        "candidate_fields": [],
        "local_only_confirmations": [],
        "evidence_reviews": [],
    }
    assert artifact["evidence_worksheet"]["summary"]["requires_evidence_review_count"] == 0
    assert artifact["provider_field_gap_report"]["summary"]["operation_counts"] == {}
    assert artifact["provider_field_gap_resolution_plan"]["summary"]["manual_review_required"] is False
    assert artifact["project_type_local_usage_review"]["summary"]["blocking_item_count"] == 0
    assert artifact["field_gap_convergence_plan"]["summary"]["field_defaults_split_item_count"] == 0
    assert artifact["execution_enabled"] is False
    assert artifact["external_api_calls"] == 0
    assert artifact["actions"] == []

def test_create_template_slot_review_pack_lists_request_and_policy_slots_without_user_input_now():
    request = _create_request()["create_request"]
    result = build_create_template_slot_review_pack(
        create_request=request,
        policy={
            "create_strategy_plan": {
                "project_naming": {
                    "template": "{target_date_mmdd}_{owner}_{product}_{project_template_name}_{batch_code}_{index}",
                    "index_width": 2,
                    "invalid_char_replacement": "_",
                }
            },
            "create_preflight": {
                "required_field_defaults": ["landing_type", "pricing", "inventory_type"],
                "min_daily_budget": 100,
                "max_daily_budget": 1000,
            },
        },
    )

    assert result["ok"] is True
    assert result["workflow"] == "create_template_slot_review_pack"
    assert result["phase"] == "phase1"
    assert result["execution_enabled"] is False
    assert result["external_api_calls"] == 0
    assert result["status"] == "needs_review"
    assert result["required_user_input_now"] is False
    assert result["summary"] == {
        "request_id": "create_req_20260508_yzt_wx_7r",
        "target_date": "2026-05-08",
        "product": "勇者突进",
        "platform": "WECHAT_GAME",
        "project_type": "WX_PAY_7R_GENERAL",
        "slot_count": 12,
        "configured_slot_count": 12,
        "missing_value_slot_count": 0,
        "needs_review_slot_count": 12,
    }
    assert result["template_contract"] == {
        "status": "needs_review",
        "slot_count": 12,
        "configured_slot_count": 12,
        "missing_value_slot_count": 0,
        "needs_review_slot_count": 12,
        "required_defaults": ["landing_type", "pricing", "inventory_type"],
    }
    project_section = result["review_sections"][0]
    assert project_section["operation"] == "create_project"
    assert project_section["slots"][0] == {
        "slot_key": "project_name_template",
        "source": "policy.create_strategy_plan.project_naming.template",
        "value_preview": "{target_date_mmdd}_{owner}_{product}_{project_template_name}_{batch_code}_{index}",
        "required": True,
        "configured": True,
        "review_status": "needs_review",
    }
    assert project_section["slots"][2]["slot_key"] == "daily_budget"
    assert project_section["slots"][2]["value_preview"] == "<per-target-account>"
    assert result["violations"] == []
    assert result["actions"] == []

def test_run_create_template_slot_review_pack_request_writes_artifact(tmp_path: Path):
    result = run_create_template_slot_review_pack_request(
        {
            "create_template_slot_review_pack": {
                "create_request": _create_request()["create_request"],
                "policy": {"create_preflight": {"required_field_defaults": ["landing_type"]}},
            }
        },
        runs_dir=tmp_path / "runs",
    )

    artifact = json.loads(Path(result["artifact_path"]).read_text(encoding="utf-8"))
    assert result["workflow"] == "create_template_slot_review_pack"
    assert result["required_user_input_now"] is False
    assert artifact["workflow"] == "create_template_slot_review_pack"
    assert artifact["actions"] == []

def test_create_template_slot_review_pack_cli_uses_request_and_policy_config(tmp_path: Path, capsys):
    db_path = tmp_path / "roibang.sqlite3"
    runtime_path = _runtime_config(tmp_path, db_path)
    module = _load_script("run_create_template_slot_review_pack")

    exit_code = module.run_from_args(
        [
            "--config",
            str(runtime_path),
            "--request",
            "configs/requests/example.create-request.json",
            "--policy",
            "policies/create-policy.example.json",
        ]
    )

    output = json.loads(capsys.readouterr().out)
    artifact = json.loads(Path(output["artifact_path"]).read_text(encoding="utf-8"))
    assert exit_code == 0
    assert output["workflow"] == "create_template_slot_review_pack"
    assert output["status"] == "needs_review"
    assert artifact["summary"]["request_id"] == "create_req_20260508_yzt_wx_7r"
    assert artifact["summary"]["slot_count"] == 12
    assert artifact["required_user_input_now"] is False
    assert artifact["execution_enabled"] is False
    assert artifact["external_api_calls"] == 0
    assert artifact["actions"] == []

def test_create_phase2_template_slot_prep_lists_defaults_without_execute():
    result = build_create_phase2_template_slot_prep(
        create_request=_create_request()["create_request"],
        policy={
            "create_phase2_template_slot_prep": {
                "product_template_catalog": {
                    "product": "勇者突进",
                    "platform": "WECHAT_GAME",
                    "templates": [
                        {
                            "template_key": "wx_pay_male",
                            "project_template_name": "微小每付男",
                            "optimize_goal": {"frontend_label": "优化目标", "value": "AD_CONVERT_TYPE_PAY", "label": "付费"},
                            "deep_external_action": {
                                "frontend_label": "深度优化目标",
                                "required": False,
                                "value": None,
                                "label": "不选择",
                            },
                            "deep_optimization_method": {
                                "frontend_label": "深度优化方式",
                                "value": "PAY_PER_ACTION",
                                "label": "每次付费",
                                "provider_field": "deep_bid_type",
                            },
                            "provider_deep_bid_type": {"value": "BID_PER_ACTION", "review_status": "needs_mapping_review"},
                            "roi_goal": {"frontend_label": "ROI系数", "required": False, "value": None, "label": "不填"},
                            "gender": {"value": "1", "label": "男"},
                            "age": {"value": [], "label": "不限"},
                        },
                        {
                            "template_key": "wx_pay_general",
                            "project_template_name": "微小每付通投",
                            "optimize_goal": {"frontend_label": "优化目标", "value": "AD_CONVERT_TYPE_PAY", "label": "付费"},
                            "deep_external_action": {
                                "frontend_label": "深度优化目标",
                                "required": False,
                                "value": None,
                                "label": "不选择",
                            },
                            "deep_optimization_method": {
                                "frontend_label": "深度优化方式",
                                "value": "PAY_PER_ACTION",
                                "label": "每次付费",
                                "provider_field": "deep_bid_type",
                            },
                            "provider_deep_bid_type": {"value": "BID_PER_ACTION", "review_status": "needs_mapping_review"},
                            "roi_goal": {"frontend_label": "ROI系数", "required": False, "value": None, "label": "不填"},
                            "gender": {"value": "NONE", "label": "不限"},
                            "age": {"value": [], "label": "不限"},
                        },
                        {
                            "template_key": "wx_7r_male",
                            "project_template_name": "微小每付7R男",
                            "optimize_goal": {"frontend_label": "优化目标", "value": "AD_CONVERT_TYPE_PAY", "label": "付费"},
                            "deep_external_action": {
                                "frontend_label": "深度优化目标",
                                "required": True,
                                "value": "AD_CONVERT_TYPE_PURCHASE_ROI_7D",
                                "label": "7日ROI",
                            },
                            "deep_optimization_method": {
                                "frontend_label": "深度优化方式",
                                "value": "PAY_PER_ACTION",
                                "label": "每次付费",
                                "provider_field": "deep_bid_type",
                            },
                            "provider_deep_bid_type": {
                                "value": "PER_AND_SEVEN_PAY_ROI",
                                "review_status": "needs_mapping_review",
                            },
                            "roi_goal": {"frontend_label": "ROI系数", "required": True, "label": "填写7日ROI目标"},
                            "gender": {"value": "1", "label": "男"},
                            "age": {"value": [], "label": "不限"},
                        },
                        {
                            "template_key": "wx_7r_general",
                            "project_template_name": "微小每付7R通投",
                            "optimize_goal": {"frontend_label": "优化目标", "value": "AD_CONVERT_TYPE_PAY", "label": "付费"},
                            "deep_external_action": {
                                "frontend_label": "深度优化目标",
                                "required": True,
                                "value": "AD_CONVERT_TYPE_PURCHASE_ROI_7D",
                                "label": "7日ROI",
                            },
                            "deep_optimization_method": {
                                "frontend_label": "深度优化方式",
                                "value": "PAY_PER_ACTION",
                                "label": "每次付费",
                                "provider_field": "deep_bid_type",
                            },
                            "provider_deep_bid_type": {
                                "value": "PER_AND_SEVEN_PAY_ROI",
                                "review_status": "needs_mapping_review",
                            },
                            "roi_goal": {"frontend_label": "ROI系数", "required": True, "label": "填写7日ROI目标"},
                            "gender": {"value": "NONE", "label": "不限"},
                            "age": {"value": [], "label": "不限"},
                        },
                    ],
                },
            },
            "create_strategy_plan": {
                "project_naming": {
                    "template": "{target_date_mmdd}_{owner}_{product}_{project_template_name}_{batch_code}_{index}",
                    "index_width": 2,
                    "invalid_char_replacement": "_",
                }
            },
            "create_preflight": {
                "required_field_defaults": ["landing_type", "pricing", "inventory_type"],
                "min_daily_budget": 100,
                "max_daily_budget": 1000,
                "project_name_pattern": "^\\d{4}_.+_.+_.+_B[0-9A-F]{8}_\\d{2}$",
            },
        },
    )

    assert result["ok"] is True
    assert result["workflow"] == "create_phase2_template_slot_prep"
    assert result["phase"] == "phase2_preparation"
    assert result["execution_enabled"] is False
    assert result["external_api_calls"] == 0
    assert result["status"] == "needs_review"
    assert result["summary"] == {
        "request_id": "create_req_20260508_yzt_wx_7r",
        "product": "勇者突进",
        "platform": "WECHAT_GAME",
        "project_type": "WX_PAY_7R_GENERAL",
        "slot_count": 12,
        "configured_slot_count": 12,
        "missing_value_slot_count": 0,
        "needs_review_slot_count": 12,
        "confirmation_group_count": 3,
        "confirmation_draft_item_count": 12,
        "confirmation_checklist_item_count": 12,
        "product_template_count": 4,
        "ready_for_live_payload_development": False,
        "ready_for_live_execute": False,
    }
    assert result["phase2_preparation_contract"] == {
        "review_only": True,
        "live_payload_generation_enabled": False,
        "create_execute_hard_block_required": True,
        "next_required_reviews": [
            "template_slots",
            "project_naming_rules",
            "live_payload_generation",
        ],
    }
    first_slot = result["review_matrix"][0]["slots"][0]
    assert first_slot == {
        "slot_key": "project_name_template",
        "value_preview": "{target_date_mmdd}_{owner}_{product}_{project_template_name}_{batch_code}_{index}",
        "value_source": "policy.create_strategy_plan.project_naming.template",
        "value_scope": "fixed_template",
        "required": True,
        "configured": True,
        "review_status": "needs_review",
        "open_questions": [
            "Confirm this fixed value can be used for real create payloads."
        ],
    }
    assert result["template_slot_contract"] == {
        "status": "needs_review",
        "slot_count": 12,
        "configured_slot_count": 12,
        "missing_value_slot_count": 0,
        "needs_review_slot_count": 12,
        "required_defaults": ["landing_type", "pricing", "inventory_type"],
        "daily_budget_bounds": {"min": 100, "max": 1000},
        "project_name_pattern": "^\\d{4}_.+_.+_.+_B[0-9A-F]{8}_\\d{2}$",
    }
    assert [group["group"] for group in result["template_confirmation_groups"]] == [
        "fixed_template_defaults",
        "per_target_account_values",
        "strategy_selected_values",
    ]
    assert [group["item_count"] for group in result["template_confirmation_groups"]] == [9, 2, 1]
    assert result["template_confirmation_groups"][0]["items"][0] == {
        "operation": "create_project",
        "slot_key": "project_name_template",
        "value_preview": "{target_date_mmdd}_{owner}_{product}_{project_template_name}_{batch_code}_{index}",
        "value_source": "policy.create_strategy_plan.project_naming.template",
        "review_status": "needs_review",
        "confirmation_question": "确认这个固定值未来可以用于真实创建模板。",
    }
    assert result["template_confirmation_groups"][1]["items"][0] == {
        "operation": "create_project",
        "slot_key": "daily_budget",
        "value_preview": "<per-target-account>",
        "value_source": "create_request.target_accounts[].daily_budget",
        "review_status": "needs_review",
        "confirmation_question": "确认每个目标账户可以安全使用各自的值。",
    }
    assert result["template_confirmation_groups"][2]["items"][0] == {
        "operation": "bind_material",
        "slot_key": "material_id",
        "value_preview": "<selected-by-create-strategy-plan>",
        "value_source": "product_source_materials.material_id",
        "review_status": "needs_review",
        "confirmation_question": "确认这个值由固定脚本规则选择，不由运行中的 AI 临场判断。",
    }
    assert result["template_confirmation_draft"][0] == {
        "operation": "create_project",
        "slot_key": "project_name_template",
        "current_value": "{target_date_mmdd}_{owner}_{product}_{project_template_name}_{batch_code}_{index}",
        "value_source": "policy.create_strategy_plan.project_naming.template",
        "value_scope": "fixed_template",
        "decision_status": "pending_confirmation",
        "suggested_decision": "keep_current_value",
        "confirmation_question": "确认这个固定值未来可以用于真实创建模板。",
    }
    assert result["template_confirmation_draft"][2] == {
        "operation": "create_project",
        "slot_key": "daily_budget",
        "current_value": "<per-target-account>",
        "value_source": "create_request.target_accounts[].daily_budget",
        "value_scope": "per_target_account",
        "decision_status": "pending_confirmation",
        "suggested_decision": "keep_per_account_value",
        "confirmation_question": "确认每个目标账户可以安全使用各自的值。",
    }
    assert result["template_confirmation_draft"][-1] == {
        "operation": "bind_material",
        "slot_key": "material_id",
        "current_value": "<selected-by-create-strategy-plan>",
        "value_source": "product_source_materials.material_id",
        "value_scope": "selected_by_strategy",
        "decision_status": "pending_confirmation",
        "suggested_decision": "keep_strategy_selection",
        "confirmation_question": "确认这个值由固定脚本规则选择，不由运行中的 AI 临场判断。",
    }
    assert result["template_confirmation_checklist"][0] == {
        "item_no": 1,
        "section": "项目",
        "field": "项目命名规则",
        "current_value": "{target_date_mmdd}_{owner}_{product}_{project_template_name}_{batch_code}_{index}",
        "source": "策略配置",
        "suggested_action": "建议保留当前值",
        "needs_user_confirmation": True,
        "question": "项目的项目命名规则是否确认使用当前值？",
    }
    assert result["template_confirmation_checklist"][2] == {
        "item_no": 3,
        "section": "项目",
        "field": "日预算",
        "current_value": "<per-target-account>",
        "source": "每个账户单独填写",
        "suggested_action": "建议保留按账户填写",
        "needs_user_confirmation": True,
        "question": "项目的日预算是否确认按账户填写？",
    }
    assert result["template_confirmation_checklist"][-1] == {
        "item_no": 12,
        "section": "素材绑定",
        "field": "素材选择",
        "current_value": "<selected-by-create-strategy-plan>",
        "source": "固定脚本规则选择",
        "suggested_action": "建议保留固定脚本选择",
        "needs_user_confirmation": True,
        "question": "素材绑定的素材选择是否确认由固定脚本选择？",
    }
    assert result["product_template_catalog"] == {
        "product": "勇者突进",
        "platform": "WECHAT_GAME",
        "templates": [
            {
                "template_key": "wx_pay_male",
                "project_template_name": "微小每付男",
                "optimize_goal": {"frontend_label": "优化目标", "value": "AD_CONVERT_TYPE_PAY", "label": "付费"},
                "deep_external_action": {
                    "frontend_label": "深度优化目标",
                    "required": False,
                    "value": None,
                    "label": "不选择",
                },
                "deep_optimization_method": {
                    "frontend_label": "深度优化方式",
                    "value": "PAY_PER_ACTION",
                    "label": "每次付费",
                    "provider_field": "deep_bid_type",
                },
                "provider_deep_bid_type": {"value": "BID_PER_ACTION", "review_status": "needs_mapping_review"},
                "roi_goal": {"frontend_label": "ROI系数", "required": False, "value": None, "label": "不填"},
                "gender": {"value": "1", "label": "男"},
                "age": {"value": [], "label": "不限"},
            },
            {
                "template_key": "wx_pay_general",
                "project_template_name": "微小每付通投",
                "optimize_goal": {"frontend_label": "优化目标", "value": "AD_CONVERT_TYPE_PAY", "label": "付费"},
                "deep_external_action": {
                    "frontend_label": "深度优化目标",
                    "required": False,
                    "value": None,
                    "label": "不选择",
                },
                "deep_optimization_method": {
                    "frontend_label": "深度优化方式",
                    "value": "PAY_PER_ACTION",
                    "label": "每次付费",
                    "provider_field": "deep_bid_type",
                },
                "provider_deep_bid_type": {"value": "BID_PER_ACTION", "review_status": "needs_mapping_review"},
                "roi_goal": {"frontend_label": "ROI系数", "required": False, "value": None, "label": "不填"},
                "gender": {"value": "NONE", "label": "不限"},
                "age": {"value": [], "label": "不限"},
            },
            {
                "template_key": "wx_7r_male",
                "project_template_name": "微小每付7R男",
                "optimize_goal": {"frontend_label": "优化目标", "value": "AD_CONVERT_TYPE_PAY", "label": "付费"},
                "deep_external_action": {
                    "frontend_label": "深度优化目标",
                    "required": True,
                    "value": "AD_CONVERT_TYPE_PURCHASE_ROI_7D",
                    "label": "7日ROI",
                },
                "deep_optimization_method": {
                    "frontend_label": "深度优化方式",
                    "value": "PAY_PER_ACTION",
                    "label": "每次付费",
                    "provider_field": "deep_bid_type",
                },
                "provider_deep_bid_type": {
                    "value": "PER_AND_SEVEN_PAY_ROI",
                    "review_status": "needs_mapping_review",
                },
                "roi_goal": {"frontend_label": "ROI系数", "required": True, "label": "填写7日ROI目标"},
                "gender": {"value": "1", "label": "男"},
                "age": {"value": [], "label": "不限"},
            },
            {
                "template_key": "wx_7r_general",
                "project_template_name": "微小每付7R通投",
                "optimize_goal": {"frontend_label": "优化目标", "value": "AD_CONVERT_TYPE_PAY", "label": "付费"},
                "deep_external_action": {
                    "frontend_label": "深度优化目标",
                    "required": True,
                    "value": "AD_CONVERT_TYPE_PURCHASE_ROI_7D",
                    "label": "7日ROI",
                },
                "deep_optimization_method": {
                    "frontend_label": "深度优化方式",
                    "value": "PAY_PER_ACTION",
                    "label": "每次付费",
                    "provider_field": "deep_bid_type",
                },
                "provider_deep_bid_type": {
                    "value": "PER_AND_SEVEN_PAY_ROI",
                    "review_status": "needs_mapping_review",
                },
                "roi_goal": {"frontend_label": "ROI系数", "required": True, "label": "填写7日ROI目标"},
                "gender": {"value": "NONE", "label": "不限"},
                "age": {"value": [], "label": "不限"},
            },
        ],
    }
    assert result["unresolved_slots"][0] == {
        "operation": "create_project",
        "slot_key": "project_name_template",
        "review_status": "needs_review",
        "open_questions": [
            "Confirm this fixed value can be used for real create payloads."
        ],
    }
    assert result["violations"] == []
    assert result["actions"] == []

def test_create_phase2_yzt_create_preview_builds_manual_config_preview_without_execute():
    from roibang_v2.workflows.create_phase2_yzt_create_preview import build_create_phase2_yzt_create_preview

    result = build_create_phase2_yzt_create_preview(
        preview_config={
            "template_name": "微小每付7R男",
            "owner": "郭靖",
            "target_date": "2026-05-09",
            "batch_generated_at": "2026-05-09T14:10:00+08:00",
            "daily_budget": 8888,
            "roi_coefficient": 0.41,
            "accounts": [
                {
                    "advertiser_id": "target-1",
                    "project_count": 2,
                }
            ],
        },
        policy={
            "create_strategy_plan": {
                "project_naming": {
                    "template": "{target_date_mmdd}_{owner}_{product}_{project_template_name}_{batch_code}_{index}",
                    "index_width": 2,
                    "invalid_char_replacement": "_",
                }
            },
            "create_phase2_template_slot_prep": {
                "product_template_catalog": {
                    "product": "勇者突进",
                    "platform": "WECHAT_GAME",
                    "script_scope": "勇者突进微信小游戏专用",
                    "templates": [
                        {
                            "template_key": "wx_7r_male",
                            "project_template_name": "微小每付7R男",
                            "optimize_goal": {"frontend_label": "优化目标", "value": "AD_CONVERT_TYPE_PAY", "label": "付费"},
                            "deep_external_action": {
                                "frontend_label": "深度优化目标",
                                "required": True,
                                "value": "AD_CONVERT_TYPE_PURCHASE_ROI_7D",
                                "label": "7日ROI",
                            },
                            "deep_optimization_method": {
                                "frontend_label": "深度优化方式",
                                "value": "PAY_PER_ACTION",
                                "label": "每次付费",
                                "provider_field": "deep_bid_type",
                            },
                            "provider_deep_bid_type": {
                                "value": "PER_AND_SEVEN_PAY_ROI",
                                "review_status": "needs_mapping_review",
                            },
                            "roi_goal": {"frontend_label": "ROI系数", "required": True, "label": "填写7日ROI目标"},
                            "gender": {"value": "1", "label": "男", "openapi_value": "GENDER_MALE"},
                            "age": {"value": [], "label": "不限", "openapi_value": []},
                        }
                    ],
                }
            },
        },
    )

    assert result["ok"] is True
    assert result["workflow"] == "create_phase2_yzt_create_preview"
    assert result["phase"] == "phase2_preparation"
    assert result["execution_enabled"] is False
    assert result["external_api_calls"] == 0
    assert result["status"] == "ready_for_review"
    assert result["summary"] == {
        "product": "勇者突进",
        "platform": "WECHAT_GAME",
        "launch_mode": "create_only",
        "template_name": "微小每付7R男",
        "target_account_count": 1,
        "preview_project_count": 2,
        "requires_roi_coefficient": True,
        "preview_check_count": 7,
        "failed_preview_check_count": 0,
        "ready_for_live_execute": False,
    }
    assert result["fixed_script_fields"] == {
        "product": "勇者突进",
        "platform": "WECHAT_GAME",
        "script_scope": "勇者突进微信小游戏专用",
        "effective_touch_url_source": "fixed_in_yzt_script",
        "marketing_scene": "短视频+图文",
        "optimize_goal": "付费",
        "age": "不限",
    }
    assert result["selected_template"]["project_template_name"] == "微小每付7R男"
    assert result["selected_template"]["roi_goal"]["frontend_label"] == "ROI系数"
    assert result["preview_projects"] == [
        {
            "advertiser_id": "target-1",
            "project_index": 1,
            "project_name": "0509_郭靖_勇者突进_微小每付7R男_B2CB8A48E_01",
            "project_template_name": "微小每付7R男",
            "owner": "郭靖",
            "daily_budget": 8888,
            "roi_coefficient": 0.41,
            "gender": "男",
            "age": "不限",
            "effective_touch_url": "<fixed-in-yzt-script>",
        },
        {
            "advertiser_id": "target-1",
            "project_index": 2,
            "project_name": "0509_郭靖_勇者突进_微小每付7R男_B2CB8A48E_02",
            "project_template_name": "微小每付7R男",
            "owner": "郭靖",
            "daily_budget": 8888,
            "roi_coefficient": 0.41,
            "gender": "男",
            "age": "不限",
            "effective_touch_url": "<fixed-in-yzt-script>",
        },
    ]
    assert result["manual_run"] == {
        "script": "scripts/run_create_phase2_yzt_create_preview.py",
        "config": "configs/create/yzt-wx-mini-game.preview.example.json",
        "command": "PYTHONPATH=src python3 scripts/run_create_phase2_yzt_create_preview.py --config configs/runtime.example.json --preview-config configs/create/yzt-wx-mini-game.preview.example.json --policy policies/create-policy.example.json",
    }
    assert result["standard_create_request"] == {
        "request_id": "create_req_20260509_yzt_preview",
        "target_date": "2026-05-09",
        "product": "勇者突进",
        "platform": "WECHAT_GAME",
        "project_type": "WX_PAY_7R",
        "source_advertiser_id": "source-advertiser-id",
        "organization_id": "",
        "pool_key": "yzt_wx_7r_all_history",
        "owner": "郭靖",
        "project_template_name": "微小每付7R男",
        "batch_generated_at": "2026-05-09T14:10:00+08:00",
        "batch_code": "B2CB8A48E",
        "target_accounts": [
            {
                "advertiser_id": "target-1",
                "project_count": 2,
                "units_per_project": 1,
                "daily_budget": 8888,
            }
        ],
        "material_requirements": {
            "material_type": "video",
            "materials_per_unit": 2,
            "dedupe_scope": "request",
        },
        "field_defaults": {
            "landing_type": "MICRO_GAME",
            "pricing": "PRICING_OCPM",
            "inventory_type": "INVENTORY_FEED",
        },
        "project_name_template": "{target_date_mmdd}_{owner}_{product}_{project_template_name}_{batch_code}_{index}",
        "constraints": {
            "phase": "phase1",
            "execution_enabled": False,
            "allow_real_create": False,
        },
            "template_parameters": {
                "template_name": "微小每付7R男",
                "roi_coefficient": 0.41,
                "gender": "男",
                "age": "不限",
                "effective_touch_url": "<fixed-in-yzt-script>",
                "template_key": "wx_7r_male",
            },
        }
    assert result["chain_handoff"] == {
        "standard_create_request_ready": True,
        "next_safe_chain_steps": [
            "create_request",
            "create_strategy_plan",
            "create_preflight",
            "create_dry_run",
        ],
        "execute_allowed": False,
    }
    assert result["preview_checks"][0] == {
        "check": "runtime_safety",
        "status": "passed",
        "message": "execution is disabled and no external API calls are planned",
    }
    assert result["preview_checks"][-1] == {
        "check": "effective_touch_url_fixed",
        "status": "passed",
        "message": "有效触点由固定创建链路提供",
    }
    assert result["config_contract"]["real_create_allowed"] is False
    assert result["manual_config_contract"] == {
        "human_editable_fields": [
            {"field": "template_name", "meaning": "选择模板，比如微小每付7R男、微小每付通投"},
            {"field": "owner", "meaning": "归属，用在项目名里"},
            {"field": "target_date", "meaning": "投放日期，用在项目名里"},
            {"field": "batch_generated_at", "meaning": "批次生成时间，用来生成批次码"},
            {"field": "defaults.daily_budget", "meaning": "默认日预算"},
            {"field": "defaults.project_count", "meaning": "每个账户默认建几个项目"},
            {"field": "defaults.units_per_project", "meaning": "每个项目默认建几个单元"},
            {"field": "roi_coefficient", "meaning": "ROI系数，只有7R模板需要填"},
            {"field": "accounts[].advertiser_id", "meaning": "目标账户"},
            {"field": "accounts[].project_count", "meaning": "单个账户覆盖项目数量，可不填"},
            {"field": "accounts[].daily_budget", "meaning": "单个账户覆盖预算，可不填"},
        ],
        "script_fixed_fields": [
            "product",
            "platform",
            "source_advertiser_id",
            "pool_key",
            "material_requirements",
            "field_defaults",
            "effective_touch_url",
            "marketing_scene",
            "optimize_goal",
            "age",
        ],
        "real_create_allowed": False,
    }
    assert result["violations"] == []
    assert result["actions"] == []

def test_create_phase2_yzt_preview_standard_request_can_enter_create_request_step(tmp_path: Path):
    from roibang_v2.workflows.create_phase2_yzt_create_preview import build_create_phase2_yzt_create_preview

    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)
    preview = build_create_phase2_yzt_create_preview(
        preview_config={
            "template_name": "微小每付通投",
            "owner": "郭靖",
            "target_date": "2026-05-09",
            "batch_generated_at": "2026-05-09T14:35:00+08:00",
            "defaults": {"daily_budget": 8888, "project_count": 1},
            "accounts": [{"advertiser_id": "target-1"}],
        },
        policy={
            "create_strategy_plan": {
                "project_naming": {
                    "template": "{target_date_mmdd}_{owner}_{product}_{project_template_name}_{batch_code}_{index}",
                    "index_width": 2,
                    "invalid_char_replacement": "_",
                }
            },
            "create_phase2_template_slot_prep": {
                "product_template_catalog": {
                    "product": "勇者突进",
                    "platform": "WECHAT_GAME",
                    "script_scope": "勇者突进微信小游戏专用",
                    "templates": [
                        {
                            "template_key": "wx_pay_general",
                            "project_template_name": "微小每付通投",
                            "roi_goal": {"frontend_label": "ROI系数", "required": False, "value": None, "label": "不填"},
                            "gender": {"value": "NONE", "label": "不限"},
                            "age": {"value": [], "label": "不限"},
                        }
                    ],
                }
            },
        },
    )

    request_result = run_create_request(
        {"create_request": preview["standard_create_request"]},
        db_path=db_path,
        runs_dir=tmp_path / "runs",
    )

    assert preview["ok"] is True
    assert request_result["ok"] is True
    assert request_result["workflow"] == "create_request"
    assert request_result["execution_enabled"] is False
    assert request_result["external_api_calls"] == 0
    assert request_result["summary"]["planned_project_count"] == 1
    assert request_result["request"]["template_parameters"] == {
        "template_name": "微小每付通投",
        "roi_coefficient": None,
        "gender": "不限",
        "age": "不限",
        "effective_touch_url": "<fixed-in-yzt-script>",
        "template_key": "wx_pay_general",
    }
    assert request_result["actions"] == []

def test_create_phase2_yzt_dry_chain_runs_preview_to_dry_run_without_execute(tmp_path: Path):
    from roibang_v2.workflows.create_phase2_yzt_dry_chain import run_create_phase2_yzt_dry_chain_request

    db_path = tmp_path / "roibang.sqlite3"
    _seed_create_db(db_path)
    result = run_create_phase2_yzt_dry_chain_request(
        {
            "create_phase2_yzt_dry_chain": {
                "preview_config": {
                    "template_name": "微小每付7R男",
                    "owner": "郭靖",
                    "target_date": "2026-05-09",
                    "batch_generated_at": "2026-05-09T14:45:00+08:00",
                    "source_advertiser_id": "source-1",
                    "organization_id": "org-1",
                    "pool_key": "pool-yzt-wx-7r",
                    "defaults": {"daily_budget": 300, "project_count": 1, "units_per_project": 1},
                    "roi_coefficient": 0.41,
                    "accounts": [{"advertiser_id": "target-1"}],
                },
                "policy": {
                    "create_strategy_plan": {
                        "max_target_accounts": 20,
                        "max_projects_per_account": 10,
                        "max_units_per_project": 20,
                        "project_naming": {
                            "template": "{target_date_mmdd}_{owner}_{product}_{project_template_name}_{batch_code}_{index}",
                            "index_width": 2,
                            "invalid_char_replacement": "_",
                        },
                        "candidate_filters": {"allowed_review_statuses": ["APPROVED"]},
                    },
                    "create_preflight": {
                        "require_account_pool": True,
                        "reject_existing_project_names": True,
                        "min_daily_budget": 100,
                        "max_daily_budget": 1000,
                        "max_project_name_length": 80,
                        "project_name_pattern": "^\\d{4}_.+_.+_.+_B[0-9A-F]{8}_\\d{2}$",
                        "required_field_defaults": ["landing_type", "pricing", "inventory_type"],
                    },
                    "create_dry_run": {
                        "max_projects_per_dry_run": 50,
                        "max_units_per_dry_run": 500,
                        "provider_field_map_path": "configs/provider-field-maps/oceanengine.create.phase1.example.json",
                    },
                    "create_phase2_template_slot_prep": {
                        "product_template_catalog": {
                            "product": "勇者突进",
                            "platform": "WECHAT_GAME",
                            "script_scope": "勇者突进微信小游戏专用",
                            "templates": [
                                {
                                    "template_key": "wx_7r_male",
                                    "project_template_name": "微小每付7R男",
                                    **_wx_unit_template_fields(),
                                    "roi_goal": {"frontend_label": "ROI系数", "required": True, "label": "填写7日ROI目标"},
                                    "gender": {"value": "1", "label": "男"},
                                    "age": {"value": [], "label": "不限"},
                                }
                            ],
                        }
                    },
                },
            }
        },
        db_path=db_path,
        runs_dir=tmp_path / "runs",
    )

    assert result["ok"] is True
    assert result["workflow"] == "create_phase2_yzt_dry_chain"
    assert result["phase"] == "phase2_preparation"
    assert result["execution_enabled"] is False
    assert result["external_api_calls"] == 0
    assert result["status"] == "simulated"
    assert result["summary"] == {
        "template_name": "微小每付7R男",
        "preview_project_count": 1,
        "create_request_project_count": 1,
        "strategy_project_count": 1,
        "preflight_status": "passed",
        "dry_run_status": "simulated",
        "ready_for_live_execute": False,
    }
    assert result["chain_steps"] == [
        {"step": "preview", "workflow": "create_phase2_yzt_create_preview", "ok": True, "status": "ready_for_review"},
        {"step": "create_request", "workflow": "create_request", "ok": True, "status": "recorded"},
        {"step": "strategy_plan", "workflow": "create_strategy_plan", "ok": True, "status": "planned"},
        {"step": "preflight", "workflow": "create_preflight", "ok": True, "status": "passed"},
        {"step": "provider_field_map_check", "workflow": "create_provider_field_map_check", "ok": True, "status": "unverified"},
        {"step": "dry_run", "workflow": "create_dry_run", "ok": True, "status": "simulated"},
    ]
    assert result["artifacts"]["preview"].endswith(".json")
    assert result["artifacts"]["dry_run"].endswith(".json")
    assert result["dry_run_summary"]["project_count"] == 1
    assert result["dry_run_summary"]["unit_count"] == 1
    assert "approved_for_execute" not in result
    assert result["blocking_summary"] == {
        "blocked_reason_count": 0,
        "plain_language": "完整本地预演已通过，但真实创建仍然关闭。",
        "needs_real_create": False,
    }
    assert result["human_next_steps"] == ["人工复核完整预演产物里的项目名、账户、预算和素材分配。"]
    assert result["violations"] == []
    assert result["actions"] == []

def test_create_phase2_yzt_dry_chain_cli_uses_manual_config_without_execute(tmp_path: Path, capsys):
    db_path = tmp_path / "roibang.sqlite3"
    _seed_create_db(db_path)
    runtime_path = _runtime_config(tmp_path, db_path)
    preview_path = tmp_path / "yzt-preview.json"
    policy_path = tmp_path / "strategy.json"
    preview_path.write_text(
        json.dumps(
            {
                "yzt_create_preview": {
                    "template_name": "微小每付7R男",
                    "owner": "郭靖",
                    "target_date": "2026-05-09",
                    "batch_generated_at": "2026-05-09T14:45:00+08:00",
                    "source_advertiser_id": "source-1",
                    "organization_id": "org-1",
                    "pool_key": "pool-yzt-wx-7r",
                    "defaults": {"daily_budget": 300, "project_count": 1, "units_per_project": 1},
                    "roi_coefficient": 0.41,
                    "accounts": [{"advertiser_id": "target-1"}],
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    policy_path.write_text(
        json.dumps(
            {
                "create_strategy_plan": {
                    "max_target_accounts": 20,
                    "max_projects_per_account": 10,
                    "max_units_per_project": 20,
                    "project_naming": {
                        "template": "{target_date_mmdd}_{owner}_{product}_{project_template_name}_{batch_code}_{index}",
                        "index_width": 2,
                        "invalid_char_replacement": "_",
                    },
                    "candidate_filters": {"allowed_review_statuses": ["APPROVED"]},
                },
                "create_preflight": {
                    "require_account_pool": True,
                    "reject_existing_project_names": True,
                    "min_daily_budget": 100,
                    "max_daily_budget": 1000,
                    "max_project_name_length": 80,
                    "project_name_pattern": "^\\d{4}_.+_.+_.+_B[0-9A-F]{8}_\\d{2}$",
                    "required_field_defaults": ["landing_type", "pricing", "inventory_type"],
                },
                "create_dry_run": {
                    "max_projects_per_dry_run": 50,
                    "max_units_per_dry_run": 500,
                    "provider_field_map_path": "configs/provider-field-maps/oceanengine.create.phase1.example.json",
                },
                "create_phase2_template_slot_prep": {
                    "product_template_catalog": {
                        "product": "勇者突进",
                        "platform": "WECHAT_GAME",
                        "script_scope": "勇者突进微信小游戏专用",
                        "templates": [
                            {
                                "template_key": "wx_7r_male",
                                "project_template_name": "微小每付7R男",
                                **_wx_unit_template_fields(),
                                "roi_goal": {"frontend_label": "ROI系数", "required": True},
                                "gender": {"value": "1", "label": "男"},
                                "age": {"value": [], "label": "不限"},
                            }
                        ],
                    }
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    module = _load_script("run_create_phase2_yzt_dry_chain")

    exit_code = module.run_from_args(
        [
            "--config",
            str(runtime_path),
            "--preview-config",
            str(preview_path),
            "--policy",
            str(policy_path),
        ]
    )

    output = json.loads(capsys.readouterr().out)
    artifact = json.loads(Path(output["artifact_path"]).read_text(encoding="utf-8"))
    assert exit_code == 0
    assert output["workflow"] == "create_phase2_yzt_dry_chain"
    assert output["status"] == "simulated"
    assert output["summary"]["template_name"] == "微小每付7R男"
    assert output["execution_enabled"] is False
    assert output["external_api_calls"] == 0
    assert output["chain_steps"][-1]["step"] == "dry_run"
    assert "approved_for_execute" not in artifact
    assert artifact["actions"] == []

def test_create_first_live_local_chain_accepts_create_plan_without_execute(tmp_path: Path):
    from roibang_v2.workflows.create_first_live_local_chain import run_create_first_live_local_chain_request

    db_path = tmp_path / "roibang.sqlite3"
    _seed_create_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute("DELETE FROM product_source_materials")
    create_plan = {
        "plan_id": "first-live-20260511-001",
        "product": "勇者突进",
        "platform": "WECHAT_GAME",
        "template_name": "微小每付7R男",
        "owner": "郭靖",
        "target_date": "2026-05-09",
        "batch_generated_at": "2026-05-09T14:45:00+08:00",
        "launch_mode": "create_only",
        "roi_coefficient": 0.41,
        "source_advertiser_id": "source-1",
        "organization_id": "org-1",
        "pool_key": "pool-yzt-wx-7r",
        "target_accounts": [
            {
                "advertiser_id": "target-1",
                "project_count": 2,
                "unit_count_per_project": 3,
                "daily_budget": 300,
            }
        ],
        "materials": [
            {"source_material_id": "m-high", "source_video_id": "vsourcevideo000000000001"},
            {"source_material_id": "m-mid", "source_video_id": "vsourcevideo000000000002"},
            {"source_material_id": "m-low", "source_video_id": "vsourcevideo000000000003"},
            {"source_material_id": "m-extra", "source_video_id": "vsourcevideo000000000004"},
        ],
        "reason": "首单链路验证",
    }
    policy = {
        "first_live_run": {
            "advertiser_id": "target-1",
            "max_project_count": 1,
            "max_unit_count": 2,
            "max_material_count": 4,
        },
        "create_plan": {
            "max_target_accounts": 2,
            "max_projects_per_account": 3,
            "max_units_per_project": 3,
            "max_materials": 4,
            "min_daily_budget": 100,
            "max_daily_budget": 1000,
        },
        "create_strategy_plan": {
            "max_target_accounts": 20,
            "max_projects_per_account": 10,
            "max_units_per_project": 20,
            "project_naming": {
                "template": "{target_date_mmdd}_{owner}_{product}_{project_template_name}_{batch_code}_{index}",
                "index_width": 2,
                "invalid_char_replacement": "_",
            },
            "candidate_filters": {"allowed_review_statuses": ["APPROVED"]},
        },
        "create_preflight": {
            "require_account_pool": True,
            "reject_existing_project_names": True,
            "min_daily_budget": 100,
            "max_daily_budget": 1000,
            "max_project_name_length": 80,
            "project_name_pattern": "^\\d{4}_.+_.+_.+_B[0-9A-F]{8}_\\d{2}$",
            "required_field_defaults": ["landing_type", "pricing", "inventory_type"],
        },
        "create_dry_run": {
            "max_projects_per_dry_run": 50,
            "max_units_per_dry_run": 500,
            "provider_field_map_path": "configs/provider-field-maps/oceanengine.create.phase1.example.json",
        },
        "create_phase2_template_slot_prep": {
            "product_template_catalog": {
                "product": "勇者突进",
                "platform": "WECHAT_GAME",
                "script_scope": "勇者突进微信小游戏专用",
                "templates": [
                    {
                        "template_key": "wx_7r_male",
                        "project_template_name": "微小每付7R男",
                        **_wx_unit_template_fields(),
                        "roi_goal": {"frontend_label": "ROI系数", "required": True},
                        "gender": {"value": "1", "label": "男"},
                        "age": {"value": [], "label": "不限"},
                    }
                ],
            }
        },
    }

    result = run_create_first_live_local_chain_request(
        {
            "create_first_live_local_chain": {
                "create_plan": create_plan,
                "preview_config_path": "configs/create-plans/first-live.local.json",
                "policy": policy,
            }
        },
        db_path=db_path,
        runs_dir=tmp_path / "runs",
    )

    assert result["ok"] is True
    assert result["status"] == "ready_for_execute_script"
    assert result["execution_enabled"] is False
    assert result["external_api_calls"] == 0
    assert result["create_plan_validation"]["ok"] is True
    assert result["summary"]["project_count"] == 1
    assert result["summary"]["unit_count"] == 1
    assert result["summary"]["material_count"] == 4
    derived = result["first_live_scope"]["derived_preview_config"]
    assert derived["create_plan"]["plan_id"] == "first-live-20260511-001"
    assert derived["accounts"] == [
        {"advertiser_id": "target-1", "project_count": 1, "units_per_project": 1, "daily_budget": 300}
    ]
    assert derived["material_requirements"]["materials_per_unit"] == 4
    assert result["dry_chain"]["dry_run_summary"]["material_count"] == 4
    create_execute = json.loads(Path(result["artifacts"]["create_execute"]).read_text(encoding="utf-8"))
    assert create_execute["summary"]["plan_id"] == "first-live-20260511-001"
    assert result["artifacts"]["create_execute"]
    assert result["actions"] == []


def test_create_preview_external_7r_template_puts_roi_goal_into_project_defaults():
    from roibang_v2.workflows.create_phase2_yzt_create_preview import build_create_phase2_yzt_create_preview

    result = build_create_phase2_yzt_create_preview(
        preview_config={
            "template_key": "wx_7r_male",
            "template_name": "微小每付7R男",
            "owner": "郭靖",
            "target_date": "2026-05-09",
            "batch_generated_at": "2026-05-09T14:10:00+08:00",
            "defaults": {"daily_budget": 300, "cpa_bid": 103, "project_count": 1, "units_per_project": 1},
            "roi_coefficient": 0.41,
            "accounts": [{"advertiser_id": "target-1"}],
        },
        policy={
            "create_phase2_template_slot_prep": {
                "template_catalog_path": "configs/create-templates/wx-mini-game.json"
            }
        },
    )

    assert result["summary"]["requires_roi_coefficient"] is True
    assert result["standard_create_request"]["field_defaults"]["roi_goal"] == 0.41
    assert result["standard_create_request"]["template_parameters"]["roi_coefficient"] == 0.41

def test_create_first_live_local_chain_cli_uses_manual_config_without_execute(tmp_path: Path, capsys):
    db_path = tmp_path / "roibang.sqlite3"
    _seed_create_db(db_path)
    runtime_path = _runtime_config(tmp_path, db_path)
    preview_path = tmp_path / "yzt-preview.json"
    policy_path = tmp_path / "strategy.json"
    preview_path.write_text(
        json.dumps(
            {
                "yzt_create_preview": {
                    "template_name": "微小每付7R男",
                    "owner": "郭靖",
                    "target_date": "2026-05-09",
                    "batch_generated_at": "2026-05-09T14:45:00+08:00",
                    "source_advertiser_id": "source-1",
                    "organization_id": "org-1",
                    "pool_key": "pool-yzt-wx-7r",
                    "defaults": {"daily_budget": 300, "project_count": 2, "units_per_project": 2},
                    "roi_coefficient": 0.41,
                    "accounts": [{"advertiser_id": "target-1"}],
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    policy_path.write_text(
        json.dumps(
            {
                "first_live_run": {"advertiser_id": "target-1", "max_project_count": 1, "max_unit_count": 2, "max_material_count": 4},
                "create_strategy_plan": {
                    "max_target_accounts": 20,
                    "max_projects_per_account": 10,
                    "max_units_per_project": 20,
                    "project_naming": {
                        "template": "{target_date_mmdd}_{owner}_{product}_{project_template_name}_{batch_code}_{index}",
                        "index_width": 2,
                        "invalid_char_replacement": "_",
                    },
                    "candidate_filters": {"allowed_review_statuses": ["APPROVED"]},
                },
                "create_preflight": {
                    "require_account_pool": True,
                    "reject_existing_project_names": True,
                    "min_daily_budget": 100,
                    "max_daily_budget": 1000,
                    "max_project_name_length": 80,
                    "project_name_pattern": "^\\d{4}_.+_.+_.+_B[0-9A-F]{8}_\\d{2}$",
                    "required_field_defaults": ["landing_type", "pricing", "inventory_type"],
                },
                "create_dry_run": {
                    "max_projects_per_dry_run": 50,
                    "max_units_per_dry_run": 500,
                    "provider_field_map_path": "configs/provider-field-maps/oceanengine.create.phase1.example.json",
                },
                "create_phase2_template_slot_prep": {
                    "product_template_catalog": {
                        "product": "勇者突进",
                        "platform": "WECHAT_GAME",
                        "script_scope": "勇者突进微信小游戏专用",
                        "templates": [
                            {
                                "template_key": "wx_7r_male",
                                "project_template_name": "微小每付7R男",
                                **_wx_unit_template_fields(),
                                "roi_goal": {"frontend_label": "ROI系数", "required": True},
                                "gender": {"value": "1", "label": "男"},
                                "age": {"value": [], "label": "不限"},
                            }
                        ],
                    }
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    module = _load_script("run_create_first_live_local_chain")

    exit_code = module.run_from_args(
        [
            "--config",
            str(runtime_path),
            "--preview-config",
            str(preview_path),
            "--policy",
            str(policy_path),
        ]
    )

    output = json.loads(capsys.readouterr().out)
    artifact = json.loads(Path(output["artifact_path"]).read_text(encoding="utf-8"))
    assert exit_code == 0
    assert output["workflow"] == "create_first_live_local_chain"
    assert output["status"] == "ready_for_execute_script"
    assert output["summary"]["project_count"] == 1
    assert output["summary"]["unit_count"] == 2
    assert output["execution_enabled"] is False
    assert output["external_api_calls"] == 0
    assert output["artifacts"]["create_execute"]
    assert Path(output["artifacts"]["create_execute"]).exists()
    assert output["artifacts"]["create_execute_handoff"] == str(tmp_path / "runs" / "create_execute" / "first-live.local.json")
    assert Path(output["artifacts"]["create_execute_handoff"]).exists()
    assert "approved_for_execute" not in artifact
    assert artifact["actions"] == []

def test_create_first_live_local_chain_cli_accepts_create_plan_without_execute(tmp_path: Path, capsys):
    db_path = tmp_path / "roibang.sqlite3"
    _seed_create_db(db_path)
    runtime_path = _runtime_config(tmp_path, db_path)
    plan_path = tmp_path / "first-live.local.json"
    policy_path = tmp_path / "strategy.json"
    plan_path.write_text(
        json.dumps(
            {
                "plan_id": "first-live-20260511-001",
                "product": "勇者突进",
                "platform": "WECHAT_GAME",
                "launch_mode": "create_only",
                "template_name": "微小每付7R男",
                "owner": "郭靖",
                "target_date": "2026-05-09",
                "batch_generated_at": "2026-05-09T14:45:00+08:00",
                "roi_coefficient": 0.41,
                "source_advertiser_id": "source-1",
                "organization_id": "org-1",
                "pool_key": "pool-yzt-wx-7r",
                "target_accounts": [
                        {
                            "advertiser_id": "target-1",
                            "project_count": 1,
                            "unit_count_per_project": 1,
                            "daily_budget": 300,
                        }
                ],
                "materials": [
                    {"source_material_id": "m-high", "source_video_id": "vsourcevideo000000000001"},
                    {"source_material_id": "m-mid", "source_video_id": "vsourcevideo000000000002"},
                ],
                "reason": "首单链路验证",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    policy_path.write_text(
        json.dumps(
            {
                "first_live_run": {"advertiser_id": "target-1", "max_project_count": 1, "max_unit_count": 2, "max_material_count": 4},
                "create_plan": {
                    "max_target_accounts": 2,
                    "max_projects_per_account": 2,
                    "max_units_per_project": 2,
                    "max_materials": 4,
                    "min_daily_budget": 100,
                    "max_daily_budget": 1000,
                },
                "create_strategy_plan": {
                    "max_target_accounts": 20,
                    "max_projects_per_account": 10,
                    "max_units_per_project": 20,
                    "project_naming": {
                        "template": "{target_date_mmdd}_{owner}_{product}_{project_template_name}_{batch_code}_{index}",
                        "index_width": 2,
                        "invalid_char_replacement": "_",
                    },
                    "candidate_filters": {"allowed_review_statuses": ["APPROVED"]},
                },
                "create_preflight": {
                    "require_account_pool": True,
                    "reject_existing_project_names": True,
                    "min_daily_budget": 100,
                    "max_daily_budget": 1000,
                    "max_project_name_length": 80,
                    "project_name_pattern": "^\\d{4}_.+_.+_.+_B[0-9A-F]{8}_\\d{2}$",
                    "required_field_defaults": ["landing_type", "pricing", "inventory_type"],
                },
                "create_dry_run": {
                    "max_projects_per_dry_run": 50,
                    "max_units_per_dry_run": 500,
                    "provider_field_map_path": "configs/provider-field-maps/oceanengine.create.phase1.example.json",
                },
                "create_phase2_template_slot_prep": {
                    "product_template_catalog": {
                        "product": "勇者突进",
                        "platform": "WECHAT_GAME",
                        "script_scope": "勇者突进微信小游戏专用",
                        "templates": [
                            {
                                "template_key": "wx_7r_male",
                                "project_template_name": "微小每付7R男",
                                **_wx_unit_template_fields(),
                                "roi_goal": {"frontend_label": "ROI系数", "required": True},
                                "gender": {"value": "1", "label": "男"},
                                "age": {"value": [], "label": "不限"},
                            }
                        ],
                    }
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    module = _load_script("run_create_first_live_local_chain")

    exit_code = module.run_from_args(
        [
            "--config",
            str(runtime_path),
            "--plan",
            str(plan_path),
            "--policy",
            str(policy_path),
        ]
    )

    output = json.loads(capsys.readouterr().out)
    artifact = json.loads(Path(output["artifact_path"]).read_text(encoding="utf-8"))
    assert exit_code == 0
    assert output["workflow"] == "create_first_live_local_chain"
    assert output["status"] == "ready_for_execute_script"
    assert output["summary"]["project_count"] == 1
    assert output["summary"]["unit_count"] == 1
    assert output["execution_enabled"] is False
    assert output["external_api_calls"] == 0
    assert output["artifacts"]["create_execute"]
    assert output["artifacts"]["create_execute_handoff"] == str(tmp_path / "runs" / "create_execute" / "first-live.local.json")
    assert Path(output["artifacts"]["create_execute_handoff"]).read_text(encoding="utf-8") == Path(output["artifacts"]["create_execute"]).read_text(encoding="utf-8")
    assert artifact["create_plan_validation"]["ok"] is True
    assert artifact["first_live_scope"]["derived_preview_config"]["create_plan"]["plan_id"] == "first-live-20260511-001"
    create_execute = json.loads(Path(output["artifacts"]["create_execute"]).read_text(encoding="utf-8"))
    assert create_execute["summary"]["plan_id"] == "first-live-20260511-001"
    assert artifact["actions"] == []

def test_create_first_live_local_chain_cli_blocks_example_or_placeholder_config(tmp_path: Path, capsys):
    db_path = tmp_path / "roibang.sqlite3"
    runtime_path = _runtime_config(tmp_path, db_path)
    preview_path = tmp_path / "yzt-preview.example.json"
    policy_path = tmp_path / "strategy.json"
    preview_path.write_text(
        json.dumps(
            {
                "yzt_create_preview": {
                    "template_name": "微小每付7R男",
                    "owner": "郭靖",
                    "target_date": "2026-05-09",
                    "batch_generated_at": "2026-05-09T14:45:00+08:00",
                    "source_advertiser_id": "source-advertiser-id",
                    "pool_key": "pool-yzt-wx-7r",
                    "defaults": {"daily_budget": 300, "project_count": 1, "units_per_project": 1},
                    "roi_coefficient": 0.41,
                    "accounts": [{"advertiser_id": "target-advertiser-id"}],
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    policy_path.write_text(json.dumps({"first_live_run": {"advertiser_id": "target-advertiser-id"}}, ensure_ascii=False), encoding="utf-8")
    module = _load_script("run_create_first_live_local_chain")

    exit_code = module.run_from_args(
        [
            "--config",
            str(runtime_path),
            "--preview-config",
            str(preview_path),
            "--policy",
            str(policy_path),
        ]
    )

    output = json.loads(capsys.readouterr().out)
    artifact = json.loads(Path(output["artifact_path"]).read_text(encoding="utf-8"))
    assert exit_code == 1
    assert output["workflow"] == "create_first_live_local_chain"
    assert output["status"] == "blocked"
    assert output["execution_enabled"] is False
    assert output["external_api_calls"] == 0
    assert output["summary"]["project_count"] == 0
    assert output["chain_steps"] == []
    assert any("示例配置" in item for item in output["human_next_steps"])
    assert any("占位" in item for item in output["human_next_steps"])
    assert artifact["first_live_scope"]["derived_preview_config"] == {}
    assert artifact["artifacts"] == {"dry_chain": "", "dry_run": "", "create_execute": ""}
    assert artifact["preparation_check"] == {}
    assert artifact["dry_chain"] == {}
    assert artifact["actions"] == []

def test_create_phase2_yzt_dry_chain_summarizes_blocked_manual_config_in_chinese(tmp_path: Path):
    from roibang_v2.workflows.create_phase2_yzt_dry_chain import run_create_phase2_yzt_dry_chain_request

    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)
    result = run_create_phase2_yzt_dry_chain_request(
        {
            "create_phase2_yzt_dry_chain": {
                "preview_config": {
                    "template_name": "微小每付7R男",
                    "owner": "郭靖",
                    "target_date": "2026-05-09",
                    "batch_generated_at": "2026-05-09T14:45:00+08:00",
                    "source_advertiser_id": "source-advertiser-id",
                    "organization_id": "",
                    "pool_key": "yzt_wx_7r_all_history",
                    "defaults": {"daily_budget": 8888, "project_count": 1, "units_per_project": 1},
                    "roi_coefficient": 0.41,
                    "accounts": [{"advertiser_id": "target-advertiser-id"}],
                },
                "policy": {
                    "create_strategy_plan": {
                        "project_naming": {
                            "template": "{target_date_mmdd}_{owner}_{product}_{project_template_name}_{batch_code}_{index}",
                            "index_width": 2,
                            "invalid_char_replacement": "_",
                        },
                    },
                    "create_preflight": {
                        "require_account_pool": True,
                        "min_daily_budget": 100,
                        "max_daily_budget": 1000,
                        "required_field_defaults": ["landing_type", "pricing", "inventory_type"],
                    },
                    "create_dry_run": {
                        "provider_field_map_path": "configs/provider-field-maps/oceanengine.create.phase1.example.json",
                    },
                    "create_phase2_template_slot_prep": {
                        "product_template_catalog": {
                            "product": "勇者突进",
                            "platform": "WECHAT_GAME",
                            "script_scope": "勇者突进微信小游戏专用",
                            "templates": [
                                {
                                    "template_key": "wx_7r_male",
                                    "project_template_name": "微小每付7R男",
                                    **_wx_unit_template_fields(),
                                    "roi_goal": {"frontend_label": "ROI系数", "required": True},
                                    "gender": {"value": "1", "label": "男"},
                                    "age": {"value": [], "label": "不限"},
                                }
                            ],
                        }
                    },
                },
            }
        },
        db_path=db_path,
        runs_dir=tmp_path / "runs",
    )

    assert result["ok"] is False
    assert result["status"] == "blocked"
    assert result["blocking_summary"]["blocked_reason_count"] == len(result["violations"])
    assert result["human_next_steps"] == [
        "把预算改到策略允许范围内，或先调整策略里的预算上限。",
        "把目标账户换成本地账户池里存在的账户，或先同步账户池。",
        "先同步源素材账户，确保素材数量够这次预演使用。",
        "等前面的检查通过后，再重新跑完整预演。",
    ]

def test_create_phase2_yzt_create_preview_uses_defaults_and_marks_checks():
    from roibang_v2.workflows.create_phase2_yzt_create_preview import build_create_phase2_yzt_create_preview

    result = build_create_phase2_yzt_create_preview(
        preview_config={
            "template_name": "微小每付7R男",
            "owner": "郭靖",
            "target_date": "2026-05-09",
            "batch_generated_at": "2026-05-09T14:30:00+08:00",
            "defaults": {
                "daily_budget": 8888,
                "project_count": 1,
            },
            "roi_coefficient": 0.41,
            "accounts": [
                {"advertiser_id": "target-1", "project_count": 2},
                {"advertiser_id": "target-2", "daily_budget": 9999},
            ],
        },
        policy={
            "create_strategy_plan": {
                "project_naming": {
                    "template": "{target_date_mmdd}_{owner}_{product}_{project_template_name}_{batch_code}_{index}",
                    "index_width": 2,
                    "invalid_char_replacement": "_",
                }
            },
            "create_phase2_template_slot_prep": {
                "product_template_catalog": {
                    "product": "勇者突进",
                    "platform": "WECHAT_GAME",
                    "script_scope": "勇者突进微信小游戏专用",
                    "templates": [
                        {
                            "template_key": "wx_7r_male",
                            "project_template_name": "微小每付7R男",
                            **_wx_unit_template_fields(),
                            "roi_goal": {"frontend_label": "ROI系数", "required": True, "label": "填写7日ROI目标"},
                            "gender": {"value": "1", "label": "男"},
                            "age": {"value": [], "label": "不限"},
                        }
                    ],
                }
            },
        },
    )

    assert result["ok"] is True
    assert result["summary"]["target_account_count"] == 2
    assert result["summary"]["preview_project_count"] == 3
    assert result["summary"]["preview_check_count"] == 7
    assert result["summary"]["failed_preview_check_count"] == 0
    assert [project["daily_budget"] for project in result["preview_projects"]] == [8888, 8888, 9999]
    assert [project["project_name"] for project in result["preview_projects"]] == [
        "0509_郭靖_勇者突进_微小每付7R男_BD2545755_01",
        "0509_郭靖_勇者突进_微小每付7R男_BD2545755_02",
        "0509_郭靖_勇者突进_微小每付7R男_BD2545755_03",
    ]
    assert result["preview_checks"] == [
        {
            "check": "runtime_safety",
            "status": "passed",
            "message": "execution is disabled and no external API calls are planned",
        },
        {
            "check": "template_known",
            "status": "passed",
            "template_name": "微小每付7R男",
        },
        {
            "check": "target_accounts",
            "status": "passed",
            "account_count": 2,
        },
        {
            "check": "daily_budget",
            "status": "passed",
            "message": "all preview projects have positive daily budget",
        },
        {
            "check": "roi_coefficient",
            "status": "passed",
            "message": "ROI系数已填写",
        },
        {
            "check": "project_names_unique",
            "status": "passed",
            "project_name_count": 3,
        },
        {
            "check": "effective_touch_url_fixed",
            "status": "passed",
            "message": "有效触点由固定创建链路提供",
        },
    ]
    assert result["config_contract"] == {
        "editable_fields": [
            "template_name",
            "owner",
            "target_date",
            "batch_generated_at",
            "defaults.daily_budget",
            "defaults.project_count",
            "roi_coefficient",
            "accounts[].advertiser_id",
            "accounts[].project_count",
            "accounts[].daily_budget",
        ],
        "fixed_fields": [
            "product",
            "platform",
            "effective_touch_url",
            "marketing_scene",
            "optimize_goal",
            "age",
        ],
        "real_create_allowed": False,
    }
    assert result["violations"] == []
    assert result["actions"] == []

def test_run_create_phase2_yzt_create_preview_request_writes_artifact(tmp_path: Path):
    from roibang_v2.workflows.create_phase2_yzt_create_preview import run_create_phase2_yzt_create_preview_request

    result = run_create_phase2_yzt_create_preview_request(
        {
            "create_phase2_yzt_create_preview": {
                "preview_config": {
                    "template_name": "微小每付通投",
                    "owner": "郭靖",
                    "target_date": "2026-05-09",
                    "batch_generated_at": "2026-05-09T14:20:00+08:00",
                    "daily_budget": 8888,
                    "accounts": [{"advertiser_id": "target-1", "project_count": 1}],
                },
                "policy": {
                    "create_phase2_template_slot_prep": {
                        "product_template_catalog": {
                            "product": "勇者突进",
                            "platform": "WECHAT_GAME",
                            "script_scope": "勇者突进微信小游戏专用",
                            "templates": [
                                {
                                    "template_key": "wx_pay_general",
                                    "project_template_name": "微小每付通投",
                                    "roi_goal": {"frontend_label": "ROI系数", "required": False, "value": None, "label": "不填"},
                                    "gender": {"value": "NONE", "label": "不限"},
                                    "age": {"value": [], "label": "不限"},
                                }
                            ],
                        }
                    }
                },
            }
        },
        runs_dir=tmp_path / "runs",
    )

    artifact = json.loads(Path(result["artifact_path"]).read_text(encoding="utf-8"))
    assert result["workflow"] == "create_phase2_yzt_create_preview"
    assert result["summary"]["template_name"] == "微小每付通投"
    assert result["summary"]["requires_roi_coefficient"] is False
    assert artifact["execution_enabled"] is False
    assert artifact["external_api_calls"] == 0
    assert artifact["actions"] == []

def test_create_phase2_yzt_create_preview_cli_uses_manual_config(tmp_path: Path, capsys):
    db_path = tmp_path / "roibang.sqlite3"
    runtime_path = _runtime_config(tmp_path, db_path)
    module = _load_script("run_create_phase2_yzt_create_preview")

    exit_code = module.run_from_args(
        [
            "--config",
            str(runtime_path),
            "--preview-config",
            "configs/create/yzt-wx-mini-game.preview.example.json",
            "--policy",
            "policies/create-policy.example.json",
        ]
    )

    output = json.loads(capsys.readouterr().out)
    artifact = json.loads(Path(output["artifact_path"]).read_text(encoding="utf-8"))
    assert exit_code == 0
    assert output["workflow"] == "create_phase2_yzt_create_preview"
    assert output["summary"]["product"] == "勇者突进"
    assert output["summary"]["template_name"] == "微小每付7R男"
    assert output["execution_enabled"] is False
    assert output["external_api_calls"] == 0
    assert artifact["fixed_script_fields"]["effective_touch_url_source"] == "fixed_in_yzt_script"
    assert artifact["actions"] == []

def test_yzt_preview_example_config_only_contains_human_editable_fields():
    payload = json.loads(Path("configs/create/yzt-wx-mini-game.preview.example.json").read_text(encoding="utf-8"))

    preview_config = payload["yzt_create_preview"]

    assert set(preview_config) == {
        "template_name",
        "owner",
        "target_date",
        "batch_generated_at",
        "defaults",
        "roi_coefficient",
        "accounts",
    }
    assert set(preview_config["defaults"]) == {"daily_budget", "project_count", "units_per_project"}
    assert set(preview_config["accounts"][0]) <= {"advertiser_id", "project_count", "daily_budget"}

def test_yzt_preview_local_config_path_is_ignored_and_documented():
    gitignore = Path(".gitignore").read_text(encoding="utf-8")
    readme = Path("README.md").read_text(encoding="utf-8")
    closeout = Path("docs/phase-2-preparation-closeout.md").read_text(encoding="utf-8")

    assert "configs/create/*.local.json" in gitignore
    assert "configs/create/yzt-wx-mini-game.preview.local.json" in readme
    assert "configs/create/yzt-wx-mini-game.preview.local.json" in closeout
    assert "不要提交真实账户" in readme

def test_prepare_yzt_local_preview_config_creates_private_copy(tmp_path: Path):
    from roibang_v2.workflows.create_phase2_yzt_local_config_prepare import prepare_yzt_local_preview_config

    example_path = tmp_path / "configs" / "create" / "yzt-wx-mini-game.preview.example.json"
    local_path = tmp_path / "configs" / "create" / "yzt-wx-mini-game.preview.local.json"
    example_path.parent.mkdir(parents=True)
    example_path.write_text(
        json.dumps(
            {
                "yzt_create_preview": {
                    "template_name": "微小每付7R男",
                    "accounts": [{"advertiser_id": "target-advertiser-id"}],
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = prepare_yzt_local_preview_config(example_path=example_path, local_path=local_path)

    assert result["ok"] is True
    assert result["workflow"] == "create_phase2_yzt_local_config_prepare"
    assert result["phase"] == "phase2_preparation"
    assert result["execution_enabled"] is False
    assert result["external_api_calls"] == 0
    assert result["status"] == "created"
    assert result["summary"]["created"] is True
    assert result["summary"]["local_config"] == str(local_path)
    assert local_path.read_text(encoding="utf-8") == example_path.read_text(encoding="utf-8")
    assert "configs/create/*.local.json" in result["safety_notes"][0]
    assert "--preview-config" in result["operator_guide"]["next_commands"][0]
    assert str(local_path) in result["operator_guide"]["next_commands"][0]
    assert result["actions"] == []

def test_prepare_yzt_local_preview_config_does_not_overwrite_existing_private_copy(tmp_path: Path):
    from roibang_v2.workflows.create_phase2_yzt_local_config_prepare import prepare_yzt_local_preview_config

    example_path = tmp_path / "example.json"
    local_path = tmp_path / "local.json"
    example_path.write_text('{"yzt_create_preview":{"template_name":"微小每付通投"}}', encoding="utf-8")
    local_path.write_text('{"yzt_create_preview":{"accounts":[{"advertiser_id":"real-local-account"}]}}', encoding="utf-8")

    result = prepare_yzt_local_preview_config(example_path=example_path, local_path=local_path)

    assert result["ok"] is True
    assert result["status"] == "already_exists"
    assert result["summary"]["created"] is False
    assert "real-local-account" in local_path.read_text(encoding="utf-8")
    assert result["human_next_steps"][0] == "本地私有配置已存在；直接编辑它，不会自动覆盖。"

def test_prepare_yzt_local_preview_config_cli_outputs_operator_guide(tmp_path: Path, capsys):
    example_path = tmp_path / "example.json"
    local_path = tmp_path / "local.json"
    example_path.write_text('{"yzt_create_preview":{"template_name":"微小每付7R通投"}}', encoding="utf-8")

    module = _load_script("run_create_phase2_yzt_local_config_prepare")
    exit_code = module.run_from_args(["--example-config", str(example_path), "--local-config", str(local_path)])
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output["workflow"] == "create_phase2_yzt_local_config_prepare"
    assert output["status"] == "created"
    assert output["operator_guide"]["editable_fields"][0]["field"] == "template_name"
    assert output["operator_guide"]["editable_fields"][0]["english_meaning"] == "template name，模板名"
    assert local_path.exists()

def test_yzt_preview_example_config_blocks_placeholder_accounts():
    from roibang_v2.workflows.create_phase2_yzt_config_check import build_create_phase2_yzt_config_check

    payload = json.loads(Path("configs/create/yzt-wx-mini-game.preview.example.json").read_text(encoding="utf-8"))
    policy = json.loads(Path("policies/create-policy.example.json").read_text(encoding="utf-8"))

    result = build_create_phase2_yzt_config_check(
        preview_config=payload["yzt_create_preview"],
        policy=policy,
    )

    assert result["ok"] is False
    assert result["status"] == "needs_fix"
    assert result["summary"]["ready_for_preview"] is False
    assert result["summary"]["placeholder_account_count"] == 2
    assert result["violations"] == [
        "accounts[0].advertiser_id 是占位账户，请换成真实账户ID",
        "accounts[1].advertiser_id 是占位账户，请换成真实账户ID",
    ]
    assert result["human_next_steps"] == ["把 target-advertiser-id 这种占位账户换成真实账户ID。"]

def test_create_phase2_yzt_config_check_blocks_bad_manual_config():
    from roibang_v2.workflows.create_phase2_yzt_config_check import build_create_phase2_yzt_config_check

    result = build_create_phase2_yzt_config_check(
        preview_config={
            "template_name": "微小每付7R男",
            "owner": "郭靖",
            "target_date": "2026-05-09",
            "batch_generated_at": "2026-05-09T14:10:00+08:00",
            "defaults": {"daily_budget": 8888, "project_count": 0, "units_per_project": 1},
            "accounts": [{"advertiser_id": ""}],
        },
        policy={
            "create_preflight": {"min_daily_budget": 100, "max_daily_budget": 1000},
            "create_phase2_template_slot_prep": {
                "product_template_catalog": {
                    "product": "勇者突进",
                    "platform": "WECHAT_GAME",
                    "script_scope": "勇者突进微信小游戏专用",
                    "templates": [
                        {
                            "template_key": "wx_7r_male",
                            "project_template_name": "微小每付7R男",
                            **_wx_unit_template_fields(),
                            "roi_goal": {"frontend_label": "ROI系数", "required": True},
                            "gender": {"value": "1", "label": "男"},
                            "age": {"value": [], "label": "不限"},
                        }
                    ],
                }
            },
        },
    )

    assert result["ok"] is False
    assert result["workflow"] == "create_phase2_yzt_config_check"
    assert result["phase"] == "phase2_preparation"
    assert result["execution_enabled"] is False
    assert result["external_api_calls"] == 0
    assert result["status"] == "needs_fix"
    assert result["summary"] == {
        "template_name": "微小每付7R男",
        "account_count": 1,
        "placeholder_account_count": 0,
        "violation_count": 4,
        "ready_for_preview": False,
    }
    assert result["violations"] == [
        "accounts[0].advertiser_id 不能为空",
        "默认日预算 8888 超过策略上限 1000",
        "默认项目数必须大于0",
        "微小每付7R男 需要填写ROI系数",
    ]
    assert result["human_next_steps"] == [
        "补齐账户ID。",
        "把默认预算改到 100 到 1000 之间，或调整策略预算范围。",
        "把默认项目数改成大于0。",
        "填写ROI系数，或改用不需要ROI系数的模板。",
    ]
    assert result["actions"] == []

def test_run_create_phase2_yzt_config_check_request_writes_artifact(tmp_path: Path):
    from roibang_v2.workflows.create_phase2_yzt_config_check import run_create_phase2_yzt_config_check_request

    result = run_create_phase2_yzt_config_check_request(
        {
            "create_phase2_yzt_config_check": {
                "preview_config": {
                    "template_name": "微小每付通投",
                    "owner": "郭靖",
                    "target_date": "2026-05-09",
                    "batch_generated_at": "2026-05-09T14:10:00+08:00",
                    "defaults": {"daily_budget": 300, "project_count": 1, "units_per_project": 1},
                    "accounts": [{"advertiser_id": "target-1"}],
                },
                "policy": {
                    "create_preflight": {"min_daily_budget": 100, "max_daily_budget": 1000},
                    "create_phase2_template_slot_prep": {
                        "product_template_catalog": {
                            "product": "勇者突进",
                            "platform": "WECHAT_GAME",
                            "script_scope": "勇者突进微信小游戏专用",
                            "templates": [
                                {
                                    "template_key": "wx_pay_general",
                                    "project_template_name": "微小每付通投",
                                    "roi_goal": {"frontend_label": "ROI系数", "required": False},
                                    "gender": {"value": "NONE", "label": "不限"},
                                    "age": {"value": [], "label": "不限"},
                                }
                            ],
                        }
                    },
                },
            }
        },
        runs_dir=tmp_path / "runs",
    )

    artifact = json.loads(Path(result["artifact_path"]).read_text(encoding="utf-8"))
    assert result["ok"] is True
    assert result["status"] == "passed"
    assert result["summary"]["ready_for_preview"] is True
    assert result["violations"] == []
    assert artifact["workflow"] == "create_phase2_yzt_config_check"
    assert artifact["actions"] == []

def test_create_phase2_yzt_config_check_cli_uses_manual_config(tmp_path: Path, capsys):
    runtime_path = _runtime_config(tmp_path, tmp_path / "roibang.sqlite3")
    preview_path = tmp_path / "preview.json"
    policy_path = tmp_path / "policy.json"
    preview_path.write_text(
        json.dumps(
            {
                "yzt_create_preview": {
                    "template_name": "微小每付通投",
                    "owner": "郭靖",
                    "target_date": "2026-05-09",
                    "batch_generated_at": "2026-05-09T14:10:00+08:00",
                    "defaults": {"daily_budget": 300, "project_count": 1, "units_per_project": 1},
                    "accounts": [{"advertiser_id": "target-1"}],
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    policy_path.write_text(
        json.dumps(
            {
                "create_preflight": {"min_daily_budget": 100, "max_daily_budget": 1000},
                "create_phase2_template_slot_prep": {
                    "product_template_catalog": {
                        "product": "勇者突进",
                        "platform": "WECHAT_GAME",
                        "script_scope": "勇者突进微信小游戏专用",
                        "templates": [
                            {
                                "template_key": "wx_pay_general",
                                "project_template_name": "微小每付通投",
                                "roi_goal": {"frontend_label": "ROI系数", "required": False},
                                "gender": {"value": "NONE", "label": "不限"},
                                "age": {"value": [], "label": "不限"},
                            }
                        ],
                    }
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    module = _load_script("run_create_phase2_yzt_config_check")

    exit_code = module.run_from_args(
        [
            "--config",
            str(runtime_path),
            "--preview-config",
            str(preview_path),
            "--policy",
            str(policy_path),
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["workflow"] == "create_phase2_yzt_config_check"
    assert output["status"] == "passed"
    assert output["summary"]["ready_for_preview"] is True
    assert output["execution_enabled"] is False
    assert output["external_api_calls"] == 0
    assert output["human_next_steps"] == ["配置可以进入预览；下一步运行勇者突进创建预览。"]

def test_create_phase2_yzt_account_pool_check_reports_missing_accounts(tmp_path: Path):
    from roibang_v2.workflows.create_phase2_yzt_account_pool_check import (
        run_create_phase2_yzt_account_pool_check_request,
    )

    db_path = tmp_path / "roibang.sqlite3"
    _seed_create_db(db_path)

    result = run_create_phase2_yzt_account_pool_check_request(
        {
            "create_phase2_yzt_account_pool_check": {
                "preview_config": {
                    "template_name": "微小每付7R男",
                    "accounts": [
                        {"advertiser_id": "target-1"},
                        {"advertiser_id": "missing-account"},
                    ],
                },
                "policy": {
                    "create_phase2_template_slot_prep": {
                        "product_template_catalog": {
                            "product": "勇者突进",
                            "platform": "WECHAT_GAME",
                        }
                    }
                },
            }
        },
        db_path=db_path,
        runs_dir=tmp_path / "runs",
    )

    artifact = json.loads(Path(result["artifact_path"]).read_text(encoding="utf-8"))
    assert result["ok"] is False
    assert result["workflow"] == "create_phase2_yzt_account_pool_check"
    assert result["phase"] == "phase2_preparation"
    assert result["execution_enabled"] is False
    assert result["external_api_calls"] == 0
    assert result["status"] == "needs_account_pool_sync"
    assert result["summary"] == {
        "product": "勇者突进",
        "platform": "WECHAT_GAME",
        "requested_account_count": 2,
        "found_account_count": 1,
        "missing_account_count": 1,
        "ready_for_dry_chain": False,
    }
    assert result["account_checks"] == [
        {"advertiser_id": "target-1", "status": "found", "account_name": "目标账户1"},
        {"advertiser_id": "missing-account", "status": "missing", "account_name": ""},
    ]
    assert result["violations"] == ["账户 missing-account 不在本地账户池：勇者突进/WECHAT_GAME"]
    assert result["human_next_steps"] == ["先同步账户池，或把配置里的账户ID改成本地账户池已有账户。"]
    assert result["actions"] == []
    assert artifact["account_checks"] == result["account_checks"]

def test_create_phase2_yzt_account_pool_check_cli_uses_manual_config(tmp_path: Path, capsys):
    db_path = tmp_path / "roibang.sqlite3"
    _seed_create_db(db_path)
    runtime_path = _runtime_config(tmp_path, db_path)
    preview_path = tmp_path / "preview.json"
    policy_path = tmp_path / "policy.json"
    preview_path.write_text(
        json.dumps(
            {
                "yzt_create_preview": {
                    "template_name": "微小每付7R男",
                    "accounts": [{"advertiser_id": "target-1"}],
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    policy_path.write_text(
        json.dumps(
            {
                "create_phase2_template_slot_prep": {
                    "product_template_catalog": {
                        "product": "勇者突进",
                        "platform": "WECHAT_GAME",
                    }
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    module = _load_script("run_create_phase2_yzt_account_pool_check")

    exit_code = module.run_from_args(
        [
            "--config",
            str(runtime_path),
            "--preview-config",
            str(preview_path),
            "--policy",
            str(policy_path),
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["workflow"] == "create_phase2_yzt_account_pool_check"
    assert output["status"] == "passed"
    assert output["summary"]["found_account_count"] == 1
    assert output["summary"]["ready_for_dry_chain"] is True
    assert output["execution_enabled"] is False
    assert output["external_api_calls"] == 0

def test_create_phase2_yzt_material_pool_check_reports_capacity(tmp_path: Path):
    from roibang_v2.workflows.create_phase2_yzt_material_pool_check import (
        run_create_phase2_yzt_material_pool_check_request,
    )

    db_path = tmp_path / "roibang.sqlite3"
    _seed_create_db(db_path)

    result = run_create_phase2_yzt_material_pool_check_request(
        {
            "create_phase2_yzt_material_pool_check": {
                "preview_config": {
                    "template_name": "微小每付7R男",
                    "owner": "郭靖",
                    "target_date": "2026-05-09",
                    "batch_generated_at": "2026-05-09T14:10:00+08:00",
                    "source_advertiser_id": "source-1",
                    "organization_id": "org-1",
                    "pool_key": "pool-yzt-wx-7r",
                    "defaults": {"daily_budget": 300, "project_count": 1, "units_per_project": 1},
                    "roi_coefficient": 0.41,
                    "material_requirements": {
                        "material_type": "video",
                        "materials_per_unit": 2,
                        "dedupe_scope": "request",
                    },
                    "accounts": [{"advertiser_id": "target-1"}],
                },
                "policy": {
                    "create_strategy_plan": {
                        "candidate_filters": {"allowed_review_statuses": ["APPROVED"]},
                    },
                    "create_phase2_template_slot_prep": {
                        "product_template_catalog": {
                            "product": "勇者突进",
                            "platform": "WECHAT_GAME",
                            "script_scope": "勇者突进微信小游戏专用",
                            "templates": [
                                {
                                    "template_key": "wx_7r_male",
                                    "project_template_name": "微小每付7R男",
                                    **_wx_unit_template_fields(),
                                    "roi_goal": {"frontend_label": "ROI系数", "required": True},
                                    "gender": {"value": "1", "label": "男"},
                                    "age": {"value": [], "label": "不限"},
                                }
                            ],
                        }
                    },
                },
            }
        },
        db_path=db_path,
        runs_dir=tmp_path / "runs",
    )

    artifact = json.loads(Path(result["artifact_path"]).read_text(encoding="utf-8"))
    assert result["ok"] is True
    assert result["workflow"] == "create_phase2_yzt_material_pool_check"
    assert result["phase"] == "phase2_preparation"
    assert result["execution_enabled"] is False
    assert result["external_api_calls"] == 0
    assert result["status"] == "passed"
    assert result["summary"] == {
        "product": "勇者突进",
        "source_advertiser_id": "source-1",
        "required_material_count": 2,
        "usable_material_count": 4,
        "missing_material_count": 0,
        "ready_for_dry_chain": True,
    }
    assert result["source_material_account"] == {
        "material_type": "video",
        "materials_per_unit": 2,
        "dedupe_scope": "request",
        "candidate_filter_statuses": ["APPROVED"],
    }
    assert result["violations"] == []
    assert result["human_next_steps"] == ["源素材账户素材数量够用；下一步可以跑完整预演。"]
    assert result["actions"] == []
    assert artifact["summary"] == result["summary"]

def test_create_phase2_yzt_material_pool_check_blocks_short_pool(tmp_path: Path):
    from roibang_v2.workflows.create_phase2_yzt_material_pool_check import build_create_phase2_yzt_material_pool_check

    db_path = tmp_path / "roibang.sqlite3"
    _seed_create_db(db_path)

    result = build_create_phase2_yzt_material_pool_check(
        preview_config={
            "template_name": "微小每付7R男",
            "owner": "郭靖",
            "target_date": "2026-05-09",
            "batch_generated_at": "2026-05-09T14:10:00+08:00",
            "source_advertiser_id": "source-1",
            "organization_id": "org-1",
            "pool_key": "pool-yzt-wx-7r",
            "defaults": {"daily_budget": 300, "project_count": 2, "units_per_project": 2},
            "roi_coefficient": 0.41,
            "material_requirements": {
                "material_type": "video",
                "materials_per_unit": 2,
                "dedupe_scope": "request",
            },
            "accounts": [{"advertiser_id": "target-1"}],
        },
        policy={
            "create_strategy_plan": {"candidate_filters": {"allowed_review_statuses": ["APPROVED"]}},
            "create_phase2_template_slot_prep": {
                "product_template_catalog": {
                    "product": "勇者突进",
                    "platform": "WECHAT_GAME",
                    "script_scope": "勇者突进微信小游戏专用",
                    "templates": [
                        {
                            "template_key": "wx_7r_male",
                            "project_template_name": "微小每付7R男",
                            **_wx_unit_template_fields(),
                            "roi_goal": {"frontend_label": "ROI系数", "required": True},
                            "gender": {"value": "1", "label": "男"},
                            "age": {"value": [], "label": "不限"},
                        }
                    ],
                }
            },
        },
        db_path=db_path,
    )

    assert result["ok"] is False
    assert result["status"] == "needs_source_material_account_sync"
    assert result["summary"]["required_material_count"] == 8
    assert result["summary"]["usable_material_count"] == 4
    assert result["summary"]["missing_material_count"] == 4
    assert result["violations"] == ["源素材账户可用素材 4 个，不够本次预演需要的 8 个，缺 4 个"]
    assert result["human_next_steps"] == ["先同步源素材账户，或减少本次项目数、单元数、每单元素材数。"]

def test_create_phase2_yzt_material_pool_check_treats_platform_status_3_as_approved(tmp_path: Path):
    from roibang_v2.workflows.create_phase2_yzt_material_pool_check import build_create_phase2_yzt_material_pool_check

    db_path = tmp_path / "roibang.sqlite3"
    _seed_create_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE product_source_materials SET review_status = '3'")

    result = build_create_phase2_yzt_material_pool_check(
        preview_config={
            "template_name": "微小每付7R男",
            "owner": "郭靖",
            "target_date": "2026-05-09",
            "batch_generated_at": "2026-05-09T14:10:00+08:00",
            "source_advertiser_id": "source-1",
            "organization_id": "org-1",
            "pool_key": "pool-yzt-wx-7r",
            "defaults": {"daily_budget": 300, "project_count": 1, "units_per_project": 1},
            "roi_coefficient": 0.41,
            "material_requirements": {
                "material_type": "video",
                "materials_per_unit": 2,
                "dedupe_scope": "request",
            },
            "accounts": [{"advertiser_id": "target-1"}],
        },
        policy={
            "create_strategy_plan": {"candidate_filters": {"allowed_review_statuses": ["APPROVED"]}},
            "create_phase2_template_slot_prep": {
                "product_template_catalog": {
                    "product": "勇者突进",
                    "platform": "WECHAT_GAME",
                    "script_scope": "勇者突进微信小游戏专用",
                    "templates": [
                        {
                            "template_key": "wx_7r_male",
                            "project_template_name": "微小每付7R男",
                            **_wx_unit_template_fields(),
                            "roi_goal": {"frontend_label": "ROI系数", "required": True},
                            "gender": {"value": "1", "label": "男"},
                            "age": {"value": [], "label": "不限"},
                        }
                    ],
                }
            },
        },
        db_path=db_path,
    )

    assert result["ok"] is True
    assert result["summary"]["usable_material_count"] == 4
    assert result["violations"] == []

def test_create_phase2_yzt_material_pool_check_cli_uses_manual_config(tmp_path: Path, capsys):
    db_path = tmp_path / "roibang.sqlite3"
    _seed_create_db(db_path)
    runtime_path = _runtime_config(tmp_path, db_path)
    preview_path = tmp_path / "preview.json"
    policy_path = tmp_path / "policy.json"
    preview_path.write_text(
        json.dumps(
            {
                "yzt_create_preview": {
                    "template_name": "微小每付7R男",
                    "owner": "郭靖",
                    "target_date": "2026-05-09",
                    "batch_generated_at": "2026-05-09T14:10:00+08:00",
                    "source_advertiser_id": "source-1",
                    "organization_id": "org-1",
                    "pool_key": "pool-yzt-wx-7r",
                    "defaults": {"daily_budget": 300, "project_count": 1, "units_per_project": 1},
                    "roi_coefficient": 0.41,
                    "material_requirements": {
                        "material_type": "video",
                        "materials_per_unit": 2,
                        "dedupe_scope": "request",
                    },
                    "accounts": [{"advertiser_id": "target-1"}],
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    policy_path.write_text(
        json.dumps(
            {
                "create_strategy_plan": {"candidate_filters": {"allowed_review_statuses": ["APPROVED"]}},
                "create_phase2_template_slot_prep": {
                    "product_template_catalog": {
                        "product": "勇者突进",
                        "platform": "WECHAT_GAME",
                        "script_scope": "勇者突进微信小游戏专用",
                        "templates": [
                            {
                                "template_key": "wx_7r_male",
                                "project_template_name": "微小每付7R男",
                                **_wx_unit_template_fields(),
                                "roi_goal": {"frontend_label": "ROI系数", "required": True},
                                "gender": {"value": "1", "label": "男"},
                                "age": {"value": [], "label": "不限"},
                            }
                        ],
                    }
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    module = _load_script("run_create_phase2_yzt_material_pool_check")

    exit_code = module.run_from_args(
        [
            "--config",
            str(runtime_path),
            "--preview-config",
            str(preview_path),
            "--policy",
            str(policy_path),
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["workflow"] == "create_phase2_yzt_material_pool_check"
    assert output["status"] == "passed"
    assert output["summary"]["ready_for_dry_chain"] is True
    assert output["summary"]["usable_material_count"] == 4
    assert output["execution_enabled"] is False
    assert output["external_api_calls"] == 0

def test_create_phase2_yzt_preparation_check_runs_all_local_checks(tmp_path: Path):
    from roibang_v2.workflows.create_phase2_yzt_preparation_check import (
        run_create_phase2_yzt_preparation_check_request,
    )

    db_path = tmp_path / "roibang.sqlite3"
    _seed_create_db(db_path)

    result = run_create_phase2_yzt_preparation_check_request(
        {
            "create_phase2_yzt_preparation_check": {
                "preview_config": {
                    "template_name": "微小每付7R男",
                    "owner": "郭靖",
                    "target_date": "2026-05-09",
                    "batch_generated_at": "2026-05-09T14:10:00+08:00",
                    "source_advertiser_id": "source-1",
                    "organization_id": "org-1",
                    "pool_key": "pool-yzt-wx-7r",
                    "defaults": {"daily_budget": 300, "project_count": 1, "units_per_project": 1},
                    "roi_coefficient": 0.41,
                    "material_requirements": {
                        "material_type": "video",
                        "materials_per_unit": 2,
                        "dedupe_scope": "request",
                    },
                    "accounts": [{"advertiser_id": "target-1"}],
                },
                "policy": {
                    "create_preflight": {"min_daily_budget": 100, "max_daily_budget": 1000},
                    "create_strategy_plan": {
                        "candidate_filters": {"allowed_review_statuses": ["APPROVED"]},
                    },
                    "create_phase2_template_slot_prep": {
                        "product_template_catalog": {
                            "product": "勇者突进",
                            "platform": "WECHAT_GAME",
                            "script_scope": "勇者突进微信小游戏专用",
                            "templates": [
                                {
                                    "template_key": "wx_7r_male",
                                    "project_template_name": "微小每付7R男",
                                    **_wx_unit_template_fields(),
                                    "roi_goal": {"frontend_label": "ROI系数", "required": True},
                                    "gender": {"value": "1", "label": "男"},
                                    "age": {"value": [], "label": "不限"},
                                }
                            ],
                        }
                    },
                },
            }
        },
        db_path=db_path,
        runs_dir=tmp_path / "runs",
    )

    artifact = json.loads(Path(result["artifact_path"]).read_text(encoding="utf-8"))
    assert result["ok"] is True
    assert result["workflow"] == "create_phase2_yzt_preparation_check"
    assert result["phase"] == "phase2_preparation"
    assert result["execution_enabled"] is False
    assert result["external_api_calls"] == 0
    assert result["status"] == "passed"
    assert result["summary"] == {
        "check_count": 3,
        "passed_check_count": 3,
        "failed_check_count": 0,
        "ready_for_dry_chain": True,
    }
    assert result["check_steps"] == [
        {"step": "config_check", "workflow": "create_phase2_yzt_config_check", "ok": True, "status": "passed"},
        {
            "step": "account_pool_check",
            "workflow": "create_phase2_yzt_account_pool_check",
            "ok": True,
            "status": "passed",
        },
        {
            "step": "material_pool_check",
            "workflow": "create_phase2_yzt_material_pool_check",
            "ok": True,
            "status": "passed",
        },
    ]
    assert result["violations"] == []
    assert result["human_next_steps"] == ["准备检查都通过；下一步可以跑完整预演。"]
    assert result["operator_guide"] == {
        "status": "ready_for_dry_chain",
        "title": "准备检查已通过",
        "ordered_steps": [
            "运行完整预演命令。",
            "检查完整预演产物里的项目名、账户、素材数量。",
        ],
        "next_command": "PYTHONPATH=src python3 scripts/run_create_phase2_yzt_dry_chain.py --config configs/runtime.example.json --preview-config configs/create/yzt-wx-mini-game.preview.example.json --policy policies/create-policy.example.json",
    }
    assert result["actions"] == []
    assert artifact["summary"] == result["summary"]

def test_create_phase2_yzt_preparation_check_collects_blockers(tmp_path: Path):
    from roibang_v2.workflows.create_phase2_yzt_preparation_check import (
        run_create_phase2_yzt_preparation_check_request,
    )

    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)

    result = run_create_phase2_yzt_preparation_check_request(
        {
            "create_phase2_yzt_preparation_check": {
                "preview_config": {
                    "template_name": "微小每付7R男",
                    "owner": "郭靖",
                    "target_date": "2026-05-09",
                    "batch_generated_at": "2026-05-09T14:10:00+08:00",
                    "defaults": {"daily_budget": 1000, "project_count": 1, "units_per_project": 1},
                    "roi_coefficient": 0.41,
                    "accounts": [{"advertiser_id": "target-advertiser-id"}],
                },
                "policy": {
                    "create_preflight": {"min_daily_budget": 100, "max_daily_budget": 1000},
                    "create_strategy_plan": {
                        "candidate_filters": {"allowed_review_statuses": ["APPROVED"]},
                    },
                    "create_phase2_template_slot_prep": {
                        "product_template_catalog": {
                            "product": "勇者突进",
                            "platform": "WECHAT_GAME",
                            "script_scope": "勇者突进微信小游戏专用",
                            "templates": [
                                {
                                    "template_key": "wx_7r_male",
                                    "project_template_name": "微小每付7R男",
                                    **_wx_unit_template_fields(),
                                    "roi_goal": {"frontend_label": "ROI系数", "required": True},
                                    "gender": {"value": "1", "label": "男"},
                                    "age": {"value": [], "label": "不限"},
                                }
                            ],
                        }
                    },
                },
            }
        },
        db_path=db_path,
        runs_dir=tmp_path / "runs",
    )

    assert result["ok"] is False
    assert result["status"] == "needs_fix"
    assert result["summary"] == {
        "check_count": 3,
        "passed_check_count": 0,
        "failed_check_count": 3,
        "ready_for_dry_chain": False,
    }
    assert result["violations"] == [
        "accounts[0].advertiser_id 是占位账户，请换成真实账户ID",
        "账户 target-advertiser-id 不在本地账户池：勇者突进/WECHAT_GAME",
        "源素材账户可用素材 0 个，不够本次预演需要的 2 个，缺 2 个",
    ]
    assert result["human_next_steps"] == [
        "把 target-advertiser-id 这种占位账户换成真实账户ID。",
        "先同步账户池，或把配置里的账户ID改成本地账户池已有账户。",
        "先同步源素材账户，或减少本次项目数、单元数、每单元素材数。",
    ]
    assert result["operator_guide"] == {
        "status": "needs_fix",
        "title": "当前不能进入完整预演",
        "ordered_steps": [
            "把 target-advertiser-id 这种占位账户换成真实账户ID。",
            "先同步账户池，或把配置里的账户ID改成本地账户池已有账户。",
            "先同步源素材账户，或减少本次项目数、单元数、每单元素材数。",
            "修完后重新运行一键准备检查。",
        ],
        "next_command": "PYTHONPATH=src python3 scripts/run_create_phase2_yzt_preparation_check.py --config configs/runtime.example.json --preview-config configs/create/yzt-wx-mini-game.preview.example.json --policy policies/create-policy.example.json",
    }

def test_create_phase2_yzt_preparation_check_cli_uses_manual_config(tmp_path: Path, capsys):
    db_path = tmp_path / "roibang.sqlite3"
    _seed_create_db(db_path)
    runtime_path = _runtime_config(tmp_path, db_path)
    preview_path = tmp_path / "preview.json"
    policy_path = tmp_path / "policy.json"
    preview_path.write_text(
        json.dumps(
            {
                "yzt_create_preview": {
                    "template_name": "微小每付7R男",
                    "owner": "郭靖",
                    "target_date": "2026-05-09",
                    "batch_generated_at": "2026-05-09T14:10:00+08:00",
                    "source_advertiser_id": "source-1",
                    "organization_id": "org-1",
                    "pool_key": "pool-yzt-wx-7r",
                    "defaults": {"daily_budget": 300, "project_count": 1, "units_per_project": 1},
                    "roi_coefficient": 0.41,
                    "material_requirements": {
                        "material_type": "video",
                        "materials_per_unit": 2,
                        "dedupe_scope": "request",
                    },
                    "accounts": [{"advertiser_id": "target-1"}],
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    policy_path.write_text(
        json.dumps(
            {
                "create_preflight": {"min_daily_budget": 100, "max_daily_budget": 1000},
                "create_strategy_plan": {"candidate_filters": {"allowed_review_statuses": ["APPROVED"]}},
                "create_phase2_template_slot_prep": {
                    "product_template_catalog": {
                        "product": "勇者突进",
                        "platform": "WECHAT_GAME",
                        "script_scope": "勇者突进微信小游戏专用",
                        "templates": [
                            {
                                "template_key": "wx_7r_male",
                                "project_template_name": "微小每付7R男",
                                **_wx_unit_template_fields(),
                                "roi_goal": {"frontend_label": "ROI系数", "required": True},
                                "gender": {"value": "1", "label": "男"},
                                "age": {"value": [], "label": "不限"},
                            }
                        ],
                    }
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    module = _load_script("run_create_phase2_yzt_preparation_check")

    exit_code = module.run_from_args(
        [
            "--config",
            str(runtime_path),
            "--preview-config",
            str(preview_path),
            "--policy",
            str(policy_path),
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["workflow"] == "create_phase2_yzt_preparation_check"
    assert output["status"] == "passed"
    assert output["summary"]["ready_for_dry_chain"] is True
    assert output["check_steps"][-1]["step"] == "material_pool_check"
    assert output["operator_guide"]["status"] == "ready_for_dry_chain"
    assert "run_create_phase2_yzt_dry_chain.py" in output["operator_guide"]["next_command"]
    assert str(preview_path) in output["operator_guide"]["next_command"]
    assert output["execution_enabled"] is False
    assert output["external_api_calls"] == 0

def test_run_create_phase2_template_slot_prep_request_writes_artifact(tmp_path: Path):
    result = run_create_phase2_template_slot_prep_request(
        {
            "create_phase2_template_slot_prep": {
                "create_request": _create_request()["create_request"],
                "policy": {
                    "create_preflight": {
                        "required_field_defaults": ["landing_type"],
                    }
                },
            }
        },
        runs_dir=tmp_path / "runs",
    )

    artifact = json.loads(Path(result["artifact_path"]).read_text(encoding="utf-8"))
    assert result["workflow"] == "create_phase2_template_slot_prep"
    assert result["summary"]["slot_count"] == 12
    assert artifact["phase"] == "phase2_preparation"
    assert artifact["execution_enabled"] is False
    assert artifact["external_api_calls"] == 0
    assert artifact["actions"] == []

def test_create_phase2_template_slot_prep_cli_uses_request_and_policy_config(tmp_path: Path, capsys):
    db_path = tmp_path / "roibang.sqlite3"
    runtime_path = _runtime_config(tmp_path, db_path)
    module = _load_script("run_create_phase2_template_slot_prep")

    exit_code = module.run_from_args(
        [
            "--config",
            str(runtime_path),
            "--request",
            "configs/requests/example.create-request.json",
            "--policy",
            "policies/create-policy.example.json",
        ]
    )

    output = json.loads(capsys.readouterr().out)
    artifact = json.loads(Path(output["artifact_path"]).read_text(encoding="utf-8"))
    assert exit_code == 0
    assert output["workflow"] == "create_phase2_template_slot_prep"
    assert output["status"] == "needs_review"
    assert artifact["phase"] == "phase2_preparation"
    assert artifact["summary"]["slot_count"] == 12
    assert artifact["execution_enabled"] is False
    assert artifact["external_api_calls"] == 0
    assert artifact["actions"] == []

def test_create_phase2_template_confirmation_pack_records_pending_user_decisions(tmp_path: Path):
    template_prep = build_create_phase2_template_slot_prep(
        create_request=_create_request()["create_request"],
        policy={
            "create_strategy_plan": {
                "project_naming": {
                    "template": "{target_date_mmdd}_{owner}_{product}_{project_template_name}_{batch_code}_{index}",
                    "index_width": 2,
                    "invalid_char_replacement": "_",
                }
            },
            "create_preflight": {
                "required_field_defaults": ["landing_type", "pricing", "inventory_type"],
                "min_daily_budget": 100,
                "max_daily_budget": 1000,
                "project_name_pattern": "^\\d{4}_.+_.+_.+_B[0-9A-F]{8}_\\d{2}$",
            },
        },
    )

    result = build_create_phase2_template_confirmation_pack(
        create_phase2_template_slot_prep_artifact=template_prep
    )

    assert result["ok"] is True
    assert result["workflow"] == "create_phase2_template_confirmation_pack"
    assert result["phase"] == "phase2_preparation"
    assert result["execution_enabled"] is False
    assert result["external_api_calls"] == 0
    assert result["required_user_input_now"] is True
    assert result["status"] == "needs_user_confirmation"
    assert result["summary"] == {
        "source_workflow": "create_phase2_template_slot_prep",
        "confirmation_item_count": 12,
        "pending_confirmation_count": 12,
        "confirmed_count": 0,
        "changed_count": 0,
        "ready_for_live_payload_development": False,
        "ready_for_live_execute": False,
    }
    assert result["confirmation_contract"] == {
        "review_only": True,
        "writes_policy": False,
        "execution_enabled": False,
        "external_api_calls": 0,
        "create_execute_hard_block_required": True,
    }
    assert result["confirmation_records"][0] == {
        "item_no": 1,
        "section": "项目",
        "field": "项目命名规则",
        "current_value": "{target_date_mmdd}_{owner}_{product}_{project_template_name}_{batch_code}_{index}",
        "source": "策略配置",
        "suggested_action": "建议保留当前值",
        "question": "项目的项目命名规则是否确认使用当前值？",
        "confirmation_status": "pending",
        "confirmed_value": "",
        "user_note": "",
    }
    assert result["confirmation_records"][-1]["field"] == "素材选择"
    assert result["confirmation_records"][-1]["confirmation_status"] == "pending"
    assert result["violations"] == []
    assert result["actions"] == []

def test_run_create_phase2_template_confirmation_pack_request_writes_artifact(tmp_path: Path):
    template_prep = build_create_phase2_template_slot_prep(
        create_request=_create_request()["create_request"],
        policy={},
    )

    result = run_create_phase2_template_confirmation_pack_request(
        {
            "create_phase2_template_confirmation_pack": {
                "create_phase2_template_slot_prep_artifact": template_prep,
            }
        },
        runs_dir=tmp_path / "runs",
    )

    artifact = json.loads(Path(result["artifact_path"]).read_text(encoding="utf-8"))
    assert result["workflow"] == "create_phase2_template_confirmation_pack"
    assert result["required_user_input_now"] is True
    assert artifact["phase"] == "phase2_preparation"
    assert artifact["execution_enabled"] is False
    assert artifact["external_api_calls"] == 0
    assert artifact["actions"] == []

def test_create_phase2_template_confirmation_pack_cli_uses_latest_template_prep(tmp_path: Path, capsys):
    db_path = tmp_path / "roibang.sqlite3"
    runtime_path = _runtime_config(tmp_path, db_path)
    runs_dir = tmp_path / "runs"
    template_prep = build_create_phase2_template_slot_prep(
        create_request=_create_request()["create_request"],
        policy={},
    )
    path = runs_dir / "create_phase2_template_slot_prep" / "20260509T000000Z.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(template_prep, ensure_ascii=False), encoding="utf-8")
    module = _load_script("run_create_phase2_template_confirmation_pack")

    exit_code = module.run_from_args(["--config", str(runtime_path)])

    output = json.loads(capsys.readouterr().out)
    artifact = json.loads(Path(output["artifact_path"]).read_text(encoding="utf-8"))
    assert exit_code == 0
    assert output["workflow"] == "create_phase2_template_confirmation_pack"
    assert output["status"] == "needs_user_confirmation"
    assert artifact["required_user_input_now"] is True
    assert artifact["summary"]["confirmation_item_count"] == 12
    assert artifact["actions"] == []

def test_create_phase2_project_naming_prep_compares_current_rule_with_old_reference():
    result = build_create_phase2_project_naming_prep(
        create_request=_create_request()["create_request"],
        policy={
            "create_strategy_plan": {
                "project_naming": {
                    "template": "{target_date_mmdd}_{owner}_{product}_{project_template_name}_{batch_code}_{index}",
                    "index_width": 2,
                    "invalid_char_replacement": "_",
                }
            },
            "create_preflight": {
                "max_project_name_length": 80,
                "project_name_pattern": "^\\d{4}_.+_.+_.+_B[0-9A-F]{8}_\\d{2}$",
                "reject_existing_project_names": True,
            },
        },
    )

    assert result["ok"] is True
    assert result["workflow"] == "create_phase2_project_naming_prep"
    assert result["phase"] == "phase2_preparation"
    assert result["execution_enabled"] is False
    assert result["external_api_calls"] == 0
    assert result["status"] == "needs_review"
    assert result["summary"] == {
        "request_id": "create_req_20260508_yzt_wx_7r",
        "template": "{target_date_mmdd}_{owner}_{product}_{project_template_name}_{batch_code}_{index}",
        "sample_name_count": 1,
        "duplicate_name_count": 0,
        "invalid_name_count": 0,
        "missing_old_reference_component_count": 0,
        "ready_for_live_payload_development": False,
        "ready_for_live_execute": False,
    }
    assert result["phase2_preparation_contract"] == {
        "review_only": True,
        "live_payload_generation_enabled": False,
        "create_execute_hard_block_required": True,
        "next_required_reviews": [
            "project_naming_rules",
            "live_payload_generation",
        ],
    }
    assert result["naming_rule_contract"] == {
        "status": "needs_review",
        "template_source": "policy.create_strategy_plan.project_naming.template",
        "template": "{target_date_mmdd}_{owner}_{product}_{project_template_name}_{batch_code}_{index}",
        "index_width": 2,
        "invalid_char_replacement": "_",
        "max_project_name_length": 80,
        "project_name_pattern": "^\\d{4}_.+_.+_.+_B[0-9A-F]{8}_\\d{2}$",
        "reject_existing_project_names": True,
    }
    assert result["sample_names"] == [
        {
            "advertiser_id": "target-1",
            "project_index": 1,
            "project_name": "0508_郭靖_勇者突进_微小每付7R通投_B80C4C430_01",
            "length": 34,
            "matches_pattern": True,
            "valid": True,
        }
    ]
    assert result["old_project_reference"] == {
        "source": "old_project_memory_and_readme",
        "project_rule": "月日_归属_游戏名_项目模板名_批次码_批内项目序号",
        "example": "0424_郭靖_勇者突进_微小每付男_B163125F3_01",
        "reason_to_review": "old project used a batch code to reduce duplicate names before remote lookup",
    }
    assert result["batch_code_contract"] == {
        "batch_code": "B80C4C430",
        "algorithm": "sha256_first_8_uppercase",
        "generated_at": "2026-05-09T13:30:45+08:00",
        "source_fields": {
            "request_id": "create_req_20260508_yzt_wx_7r",
            "target_date": "2026-05-08",
            "product": "勇者突进",
            "project_type": "WX_PAY_7R_GENERAL",
            "advertiser_ids": ["target-1"],
            "generated_at": "2026-05-09T13:30:45+08:00",
        },
        "freeze_rule": "generate once in plan, then reuse through preflight, dry-run, and execute",
    }
    assert result["unresolved_naming_items"] == []
    assert result["violations"] == []
    assert result["actions"] == []

def test_run_create_phase2_project_naming_prep_request_writes_artifact(tmp_path: Path):
    result = run_create_phase2_project_naming_prep_request(
        {
            "create_phase2_project_naming_prep": {
                "create_request": _create_request()["create_request"],
                "policy": {
                    "create_strategy_plan": {
                        "project_naming": {
                            "template": "{target_date_mmdd}_{owner}_{product}_{project_template_name}_{batch_code}_{index}",
                            "index_width": 2,
                            "invalid_char_replacement": "_",
                        }
                    }
                },
            }
        },
        runs_dir=tmp_path / "runs",
    )

    artifact = json.loads(Path(result["artifact_path"]).read_text(encoding="utf-8"))
    assert result["workflow"] == "create_phase2_project_naming_prep"
    assert result["summary"]["sample_name_count"] == 1
    assert artifact["phase"] == "phase2_preparation"
    assert artifact["execution_enabled"] is False
    assert artifact["external_api_calls"] == 0
    assert artifact["actions"] == []

def test_create_phase2_project_naming_prep_cli_uses_request_and_policy_config(tmp_path: Path, capsys):
    db_path = tmp_path / "roibang.sqlite3"
    runtime_path = _runtime_config(tmp_path, db_path)
    module = _load_script("run_create_phase2_project_naming_prep")

    exit_code = module.run_from_args(
        [
            "--config",
            str(runtime_path),
            "--request",
            "configs/requests/example.create-request.json",
            "--policy",
            "policies/create-policy.example.json",
        ]
    )

    output = json.loads(capsys.readouterr().out)
    artifact = json.loads(Path(output["artifact_path"]).read_text(encoding="utf-8"))
    assert exit_code == 0
    assert output["workflow"] == "create_phase2_project_naming_prep"
    assert output["status"] == "needs_review"
    assert artifact["phase"] == "phase2_preparation"
    assert artifact["summary"]["sample_name_count"] == 1
    assert artifact["execution_enabled"] is False
    assert artifact["external_api_calls"] == 0
    assert artifact["actions"] == []

def test_create_phase2_preparation_summary_combines_review_gaps_without_execute():
    provider = {
        "workflow": "create_phase2_provider_mapping_prep",
        "ok": True,
        "status": "needs_review",
        "phase": "phase2_preparation",
        "execution_enabled": False,
        "external_api_calls": 0,
        "summary": {"unresolved_field_count": 22, "open_question_count": 16},
        "unresolved_mappings": [{"operation": "create_project", "internal_field": "field_defaults.landing_type"}],
        "violations": [],
        "actions": [],
    }
    template = {
        "workflow": "create_phase2_template_slot_prep",
        "ok": True,
        "status": "needs_review",
        "phase": "phase2_preparation",
        "execution_enabled": False,
        "external_api_calls": 0,
        "summary": {"needs_review_slot_count": 12, "missing_value_slot_count": 0},
        "unresolved_slots": [{"operation": "create_project", "slot_key": "project_name_template"}],
        "violations": [],
        "actions": [],
    }
    naming = {
        "workflow": "create_phase2_project_naming_prep",
        "ok": True,
        "status": "needs_review",
        "phase": "phase2_preparation",
        "execution_enabled": False,
        "external_api_calls": 0,
        "summary": {"missing_old_reference_component_count": 2, "duplicate_name_count": 0, "invalid_name_count": 0},
        "unresolved_naming_items": [{"item": "batch_code"}],
        "violations": [],
        "actions": [],
    }

    result = build_create_phase2_preparation_summary(
        create_phase2_provider_mapping_prep_artifact=provider,
        create_phase2_template_slot_prep_artifact=template,
        create_phase2_project_naming_prep_artifact=naming,
    )

    assert result["ok"] is True
    assert result["workflow"] == "create_phase2_preparation_summary"
    assert result["phase"] == "phase2_preparation"
    assert result["execution_enabled"] is False
    assert result["external_api_calls"] == 0
    assert result["status"] == "needs_review"
    assert result["ready_for_live_payload_development"] is False
    assert result["ready_for_live_execute"] is False
    assert result["summary"] == {
        "check_count": 3,
        "passed_check_count": 0,
        "needs_review_check_count": 3,
        "blocking_check_count": 0,
        "unresolved_item_count": 3,
        "ready_for_live_payload_development": False,
        "ready_for_live_execute": False,
    }
    assert result["preparation_checks"] == [
        {
            "check": "provider_field_mapping",
            "workflow": "create_phase2_provider_mapping_prep",
            "artifact_status": "needs_review",
            "ready": False,
            "blocking": False,
            "unresolved_count": 1,
            "reason": "provider field mapping still needs review",
        },
        {
            "check": "template_slots",
            "workflow": "create_phase2_template_slot_prep",
            "artifact_status": "needs_review",
            "ready": False,
            "blocking": False,
            "unresolved_count": 1,
            "reason": "template slots still need review",
        },
        {
            "check": "project_naming",
            "workflow": "create_phase2_project_naming_prep",
            "artifact_status": "needs_review",
            "ready": False,
            "blocking": False,
            "unresolved_count": 1,
            "reason": "project naming still needs review",
        },
    ]
    assert result["phase2_preparation_contract"] == {
        "review_only": True,
        "live_payload_generation_enabled": False,
        "create_execute_hard_block_required": True,
        "real_create_allowed": False,
    }
    assert result["remaining_review_items"] == [
        {"area": "provider_field_mapping", "operation": "create_project", "field": "field_defaults.landing_type"},
        {"area": "template_slots", "operation": "create_project", "slot": "project_name_template"},
        {"area": "project_naming", "item": "batch_code"},
    ]
    assert result["remaining_review_groups"] == [
        {
            "group": "needs_provider_evidence",
            "label": "需要补平台字段依据",
            "item_count": 1,
            "items": [
                {"area": "provider_field_mapping", "operation": "create_project", "field": "field_defaults.landing_type"},
            ],
        },
        {
            "group": "needs_human_decision",
            "label": "需要人工确认规则",
            "item_count": 2,
            "items": [
                {"area": "template_slots", "operation": "create_project", "slot": "project_name_template"},
                {"area": "project_naming", "item": "batch_code"},
            ],
        },
    ]
    assert result["recommended_next_steps"] == [
        "人工确认字段对应关系",
        "人工确认模板默认项",
        "人工确认项目命名是否加入归属和批次码",
        "确认完成后再设计真实请求内容生成",
    ]
    assert result["violations"] == []
    assert result["actions"] == []

def test_run_create_phase2_preparation_summary_request_writes_artifact(tmp_path: Path):
    artifact = {
        "ok": True,
        "status": "needs_review",
        "phase": "phase2_preparation",
        "execution_enabled": False,
        "external_api_calls": 0,
        "summary": {},
        "violations": [],
        "actions": [],
    }
    result = run_create_phase2_preparation_summary_request(
        {
            "create_phase2_preparation_summary": {
                "create_phase2_provider_mapping_prep_artifact": {
                    **artifact,
                    "workflow": "create_phase2_provider_mapping_prep",
                    "unresolved_mappings": [],
                },
                "create_phase2_template_slot_prep_artifact": {
                    **artifact,
                    "workflow": "create_phase2_template_slot_prep",
                    "unresolved_slots": [],
                },
                "create_phase2_project_naming_prep_artifact": {
                    **artifact,
                    "workflow": "create_phase2_project_naming_prep",
                    "unresolved_naming_items": [],
                },
            }
        },
        runs_dir=tmp_path / "runs",
    )

    written = json.loads(Path(result["artifact_path"]).read_text(encoding="utf-8"))
    assert result["workflow"] == "create_phase2_preparation_summary"
    assert result["phase"] == "phase2_preparation"
    assert written["execution_enabled"] is False
    assert written["external_api_calls"] == 0
    assert written["actions"] == []

def test_create_phase2_preparation_summary_cli_uses_latest_artifacts(tmp_path: Path, capsys):
    db_path = tmp_path / "roibang.sqlite3"
    runtime_path = _runtime_config(tmp_path, db_path)
    runs_dir = tmp_path / "runs"
    artifacts = {
        "create_phase2_provider_mapping_prep": {
            "workflow": "create_phase2_provider_mapping_prep",
            "ok": True,
            "status": "needs_review",
            "phase": "phase2_preparation",
            "execution_enabled": False,
            "external_api_calls": 0,
            "summary": {},
            "unresolved_mappings": [],
            "violations": [],
            "actions": [],
        },
        "create_phase2_template_slot_prep": {
            "workflow": "create_phase2_template_slot_prep",
            "ok": True,
            "status": "needs_review",
            "phase": "phase2_preparation",
            "execution_enabled": False,
            "external_api_calls": 0,
            "summary": {},
            "unresolved_slots": [],
            "violations": [],
            "actions": [],
        },
        "create_phase2_project_naming_prep": {
            "workflow": "create_phase2_project_naming_prep",
            "ok": True,
            "status": "needs_review",
            "phase": "phase2_preparation",
            "execution_enabled": False,
            "external_api_calls": 0,
            "summary": {},
            "unresolved_naming_items": [],
            "violations": [],
            "actions": [],
        },
    }
    for workflow, payload in artifacts.items():
        path = runs_dir / workflow / "20260509T000000Z.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    module = _load_script("run_create_phase2_preparation_summary")

    exit_code = module.run_from_args(["--config", str(runtime_path)])

    output = json.loads(capsys.readouterr().out)
    artifact = json.loads(Path(output["artifact_path"]).read_text(encoding="utf-8"))
    assert exit_code == 0
    assert output["workflow"] == "create_phase2_preparation_summary"
    assert output["status"] == "needs_review"
    assert artifact["phase"] == "phase2_preparation"
    assert artifact["execution_enabled"] is False
    assert artifact["external_api_calls"] == 0
    assert artifact["actions"] == []

def test_create_dry_run_records_provider_field_map_check_lineage(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    _seed_create_db(db_path)
    plan = build_create_strategy_plan(request=_create_request()["create_request"], db_path=db_path, policy={})
    preflight = build_create_preflight(create_strategy_plan_artifact=plan, db_path=db_path, policy={})
    policy = {
        "provider_field_map_path": "configs/provider-field-maps/oceanengine.create.phase1.example.json"
    }
    field_map_check = build_create_provider_field_map_check(policy=policy)

    result = build_create_dry_run(
        create_strategy_plan_artifact=plan,
        create_preflight_artifact=preflight,
        create_provider_field_map_check_artifact=field_map_check,
        policy=policy,
    )

    assert result["ok"] is True
    assert result["status"] == "simulated"
    assert result["lineage"]["create_provider_field_map_check"]["workflow"] == "create_provider_field_map_check"
    assert result["lineage"]["create_provider_field_map_check"]["provider"] == "oceanengine"
    assert result["lineage"]["create_provider_field_map_check"]["status"] == "unverified"
    assert result["provider_field_map_digest"] == field_map_check["provider_field_map_digest"]
    assert result["provider_field_map_contract"] == field_map_check["provider_field_map_contract"]
    assert result["provider_readiness_contract"] == field_map_check["provider_readiness_contract"]

def test_create_dry_run_blocks_mismatched_provider_field_map_check(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    _seed_create_db(db_path)
    plan = build_create_strategy_plan(request=_create_request()["create_request"], db_path=db_path, policy={})
    preflight = build_create_preflight(create_strategy_plan_artifact=plan, db_path=db_path, policy={})
    field_map_check = build_create_provider_field_map_check(
        policy={"provider_field_map_path": "configs/provider-field-maps/oceanengine.create.phase1.example.json"}
    )
    field_map_check["provider_field_map_contract"]["missing_provider_field_count"] = 0

    result = build_create_dry_run(
        create_strategy_plan_artifact=plan,
        create_preflight_artifact=preflight,
        create_provider_field_map_check_artifact=field_map_check,
        policy={"provider_field_map_path": "configs/provider-field-maps/oceanengine.create.phase1.example.json"},
    )

    assert result["ok"] is False
    assert result["status"] == "blocked"
    assert "provider field map check contract must match dry-run field map contract" in result["violations"]
    assert result["candidate_tasks"] == []
    assert result["actions"] == []

def test_create_dry_run_blocks_mismatched_provider_field_map_digest(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    _seed_create_db(db_path)
    plan = build_create_strategy_plan(request=_create_request()["create_request"], db_path=db_path, policy={})
    preflight = build_create_preflight(create_strategy_plan_artifact=plan, db_path=db_path, policy={})
    field_map_check = build_create_provider_field_map_check(
        policy={"provider_field_map_path": "configs/provider-field-maps/oceanengine.create.phase1.example.json"}
    )
    field_map_check["provider_field_map_digest"]["value"] = "0" * 64

    result = build_create_dry_run(
        create_strategy_plan_artifact=plan,
        create_preflight_artifact=preflight,
        create_provider_field_map_check_artifact=field_map_check,
        policy={"provider_field_map_path": "configs/provider-field-maps/oceanengine.create.phase1.example.json"},
    )

    assert result["ok"] is False
    assert result["status"] == "blocked"
    assert "provider field map check digest must match dry-run field map digest" in result["violations"]
    assert result["candidate_tasks"] == []
    assert result["actions"] == []

def test_create_dry_run_blocks_when_payload_required_fields_are_missing(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    _seed_create_db(db_path)
    plan = build_create_strategy_plan(request=_create_request()["create_request"], db_path=db_path, policy={})
    preflight = build_create_preflight(create_strategy_plan_artifact=plan, db_path=db_path, policy={})
    project = plan["strategy"]["projects"][0]
    project["project_name"] = ""
    project["units"][0]["unit_key"] = ""
    project["units"][0]["materials"][0]["material_id"] = ""

    result = build_create_dry_run(
        create_strategy_plan_artifact=plan,
        create_preflight_artifact=preflight,
        policy={},
    )

    assert result["ok"] is False
    assert result["status"] == "blocked"
    assert result["candidate_tasks"] == []
    assert result["payload_contract"]["status"] == "failed"
    assert "create_project project target-1-p001 missing project_name" in result["violations"]
    assert "create_unit unit target-1-p001-u01 missing unit_key" in result["violations"]
    assert "bind_material unit target-1-p001-u01 missing material_id" in result["violations"]

def test_create_dry_run_blocks_duplicate_idempotency_keys(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    _seed_create_db(db_path)
    request = _create_request()["create_request"]
    request["target_accounts"][0]["project_count"] = 2
    request["target_accounts"][0]["units_per_project"] = 1
    request["material_requirements"]["materials_per_unit"] = 1
    plan = build_create_strategy_plan(request=request, db_path=db_path, policy={})
    preflight = build_create_preflight(create_strategy_plan_artifact=plan, db_path=db_path, policy={})
    plan["strategy"]["projects"][1]["project_key"] = plan["strategy"]["projects"][0]["project_key"]

    result = build_create_dry_run(
        create_strategy_plan_artifact=plan,
        create_preflight_artifact=preflight,
        policy={},
    )

    assert result["ok"] is False
    assert result["status"] == "blocked"
    assert result["candidate_tasks"] == []
    assert result["idempotency_contract"]["status"] == "failed"
    assert result["idempotency_contract"]["duplicate_keys"]
    assert "duplicate idempotency key for create_project" in result["violations"]

def test_run_create_dry_run_request_records_idempotency_ledger_in_sqlite(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    _seed_create_db(db_path)
    plan = build_create_strategy_plan(request=_create_request()["create_request"], db_path=db_path, policy={})
    preflight = build_create_preflight(create_strategy_plan_artifact=plan, db_path=db_path, policy={})

    result = run_create_dry_run_request(
        {
            "create_dry_run": {
                "create_strategy_plan_artifact": plan,
                "create_preflight_artifact": preflight,
                "policy": {},
            }
        },
        runs_dir=tmp_path / "runs",
        db_path=db_path,
    )

    assert result["idempotency_ledger"] == {
        "status": "recorded",
        "recorded_key_count": 7,
        "existing_key_count": 0,
    }
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT scope, plan_id, request_id, target_date, advertiser_id, status, execution_enabled
            FROM create_idempotency_keys
            ORDER BY scope, idempotency_key
            """
        ).fetchall()

    assert len(rows) == 7
    assert {row[0] for row in rows} == {"bind_material", "create_project", "create_unit"}
    assert {row[1] for row in rows} == {"create_plan_create_req_20260508_yzt_wx_7r"}
    assert {row[2] for row in rows} == {"create_req_20260508_yzt_wx_7r"}
    assert {row[3] for row in rows} == {"2026-05-08"}
    assert {row[4] for row in rows} == {"target-1"}
    assert {row[5] for row in rows} == {"planned"}
    assert {row[6] for row in rows} == {0}

    second = run_create_dry_run_request(
        {
            "create_dry_run": {
                "create_strategy_plan_artifact": plan,
                "create_preflight_artifact": preflight,
                "policy": {},
            }
        },
        runs_dir=tmp_path / "runs",
        db_path=db_path,
    )

    assert second["idempotency_ledger"] == {
        "status": "recorded",
        "recorded_key_count": 7,
        "existing_key_count": 7,
    }

def test_create_provider_id_ledger_records_and_resolves_lookup_placeholders(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)

    project_record = record_create_provider_id(
        db_path=db_path,
        entity_type="project",
        local_key="target-1-p001",
        provider_id="project_123",
        plan_id="plan-1",
        request_id="request-1",
        advertiser_id="target-1",
        source_workflow="unit_test",
    )
    unit_record = record_create_provider_id(
        db_path=db_path,
        entity_type="promotion",
        local_key="target-1-p001-u01",
        provider_id="promotion_456",
        plan_id="plan-1",
        request_id="request-1",
        advertiser_id="target-1",
        parent_local_key="target-1-p001",
        source_workflow="unit_test",
    )

    resolved = resolve_create_lookup_placeholders(
        db_path=db_path,
        plan_id="plan-1",
        request_id="request-1",
        payload={
            "project_id": "<lookup:target-1-p001>",
            "promotion_id": "<lookup:target-1-p001-u01>",
            "material_id": "m-high",
        },
    )

    assert project_record["status"] == "recorded"
    assert unit_record["status"] == "recorded"
    assert resolved == {
        "status": "resolved",
        "lookup_count": 2,
        "resolved_count": 2,
        "unresolved_count": 0,
        "unresolved_placeholders": [],
        "resolved_payload": {
            "project_id": "project_123",
            "promotion_id": "promotion_456",
            "material_id": "m-high",
        },
        "execution_enabled": False,
        "external_api_calls": 0,
        "actions": [],
    }

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT entity_type, local_key, provider_id, parent_local_key, status, execution_enabled
            FROM create_provider_id_ledger
            ORDER BY entity_type, local_key
            """
        ).fetchall()

    assert rows == [
        ("project", "target-1-p001", "project_123", "", "active", 0),
        ("promotion", "target-1-p001-u01", "promotion_456", "target-1-p001", "active", 0),
    ]

def test_create_provider_id_ledger_blocks_unresolved_lookup_placeholders(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)

    result = resolve_create_lookup_placeholders(
        db_path=db_path,
        payload={
            "project_id": "<lookup:target-1-p001>",
            "promotion_id": "<lookup:target-1-p001-u01>",
        },
    )

    assert result == {
        "status": "blocked",
        "lookup_count": 2,
        "resolved_count": 0,
        "unresolved_count": 2,
        "unresolved_placeholders": [
            {"field": "project_id", "placeholder": "<lookup:target-1-p001>", "local_key": "target-1-p001"},
            {"field": "promotion_id", "placeholder": "<lookup:target-1-p001-u01>", "local_key": "target-1-p001-u01"},
        ],
        "resolved_payload": {
            "project_id": "<lookup:target-1-p001>",
            "promotion_id": "<lookup:target-1-p001-u01>",
        },
        "execution_enabled": False,
        "external_api_calls": 0,
        "actions": [],
    }

def test_create_provider_id_ledger_blocks_conflicting_provider_ids(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)

    first = record_create_provider_id(
        db_path=db_path,
        entity_type="project",
        local_key="target-1-p001",
        provider_id="project_123",
        source_workflow="unit_test",
    )
    conflict = record_create_provider_id(
        db_path=db_path,
        entity_type="project",
        local_key="target-1-p001",
        provider_id="project_999",
        source_workflow="unit_test",
    )

    assert first["status"] == "recorded"
    assert conflict == {
        "status": "conflict",
        "entity_type": "project",
        "local_key": "target-1-p001",
        "existing_provider_id": "project_123",
        "provider_id": "project_999",
        "execution_enabled": False,
        "external_api_calls": 0,
        "actions": [],
    }

    resolved = resolve_create_lookup_placeholders(
        db_path=db_path,
        payload={"project_id": "<lookup:target-1-p001>"},
    )

    assert resolved["resolved_payload"]["project_id"] == "project_123"

def test_create_dry_run_blocks_when_preflight_failed(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    _seed_create_db(db_path)
    plan = build_create_strategy_plan(request=_create_request()["create_request"], db_path=db_path, policy={})
    preflight = build_create_preflight(create_strategy_plan_artifact=plan, db_path=db_path, policy={})
    preflight["status"] = "failed"
    preflight["ok"] = False
    preflight["violations"] = ["manual block"]

    result = build_create_dry_run(
        create_strategy_plan_artifact=plan,
        create_preflight_artifact=preflight,
        policy={},
    )

    assert result["ok"] is False
    assert result["status"] == "blocked"
    assert result["candidate_tasks"] == []
    assert "create preflight must pass before dry-run" in result["violations"]

def test_create_execute_cli_accepts_disabled_live_template_and_still_blocks(tmp_path: Path, capsys):
    db_path = tmp_path / "roibang.sqlite3"
    _seed_create_db(db_path)
    runs_dir = tmp_path / "runs"
    runtime_path = _runtime_config(tmp_path, db_path)
    plan = build_create_strategy_plan(request=_create_request()["create_request"], db_path=db_path, policy={})
    preflight = build_create_preflight(create_strategy_plan_artifact=plan, db_path=db_path, policy={})
    dry_run = build_create_dry_run(create_strategy_plan_artifact=plan, create_preflight_artifact=preflight, policy={})
    dry_run_path = runs_dir / "create_dry_run" / "manual.json"
    dry_run_path.parent.mkdir(parents=True)
    dry_run_path.write_text(json.dumps(dry_run, ensure_ascii=False), encoding="utf-8")
    module = _load_script("run_create_execute")

    exit_code = module.run_from_args(
        [
            "--config",
            str(runtime_path),
            "--request",
            "configs/create-execute.openapi-http.disabled.example.json",
            "--create-dry-run-artifact",
            str(dry_run_path),
        ]
    )

    output = json.loads(capsys.readouterr().out)
    artifact = json.loads(Path(output["artifact_path"]).read_text(encoding="utf-8"))
    assert exit_code == 0
    assert output["status"] == "blocked"
    assert artifact["executed_task_count"] == 0
    assert artifact["payload_schema"]["mode"] == "schema_only"
    assert artifact["payload_schema"]["live_payload_generation_enabled"] is False
    assert artifact["execution_plan"]["live_api_payloads"] == []
    assert artifact["audit"]["enabled"] is False
    assert artifact["audit"]["path"] == "data/runs/create_execute/audit/openapi-http-disabled"
