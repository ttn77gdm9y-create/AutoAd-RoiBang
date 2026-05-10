import importlib.util
import json
import re
import sqlite3
from pathlib import Path

from roibang_v2.db.bootstrap import bootstrap_database
from roibang_v2.workflows.create_approval import build_create_approval, run_create_approval_request
from roibang_v2.workflows.create_chain_manifest import build_create_chain_manifest, run_create_chain_manifest_request
from roibang_v2.workflows.create_chain_replay import build_create_chain_replay, run_create_chain_replay_request
from roibang_v2.workflows.create_dry_run import build_create_dry_run, run_create_dry_run_request
from roibang_v2.workflows.create_execute import build_create_execute, run_create_execute_request
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
from roibang_v2.workflows.create_readiness_matrix import (
    build_create_readiness_matrix,
    run_create_readiness_matrix_request,
)
from roibang_v2.workflows.create_live_execute_phase_gate import (
    build_create_live_execute_phase_gate,
    run_create_live_execute_phase_gate_request,
)
from roibang_v2.workflows.create_live_payload_adapter_scaffold import (
    build_create_live_payload_adapter_scaffold,
    run_create_live_payload_adapter_scaffold_request,
)
from roibang_v2.workflows.create_adapter_review_pack import (
    build_create_adapter_review_pack,
    run_create_adapter_review_pack_request,
)
from roibang_v2.workflows.create_chain_index import (
    build_create_chain_index,
    run_create_chain_index_request,
)
from roibang_v2.workflows.create_chain_final_report import (
    build_create_chain_final_report,
    run_create_chain_final_report_request,
)
from roibang_v2.workflows.create_phase1_acceptance_checklist import (
    build_create_phase1_acceptance_checklist,
    run_create_phase1_acceptance_checklist_request,
)
from roibang_v2.workflows.create_phase1_baseline_freeze import (
    build_create_phase1_baseline_freeze,
    run_create_phase1_baseline_freeze_request,
)
from roibang_v2.workflows.create_provider_readiness import provider_readiness_contract
from roibang_v2.workflows.create_plan_snapshot import build_create_plan_snapshot, run_create_plan_snapshot_request
from roibang_v2.workflows.create_preflight import build_create_preflight, run_create_preflight_request
from roibang_v2.workflows.create_request import run_create_request
from roibang_v2.workflows.create_strategy_plan import build_create_strategy_plan, run_create_strategy_plan_request


def _load_script(name: str):
    script_path = Path(f"scripts/{name}.py")
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
                INSERT INTO product_source_material_candidates (
                  pool_key, product, source_advertiser_id, organization_id,
                  window_key, period_start, period_end, rank,
                  material_id, material_type, source_video_id, name,
                  review_status, stat_cost, score, source, synced_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "pool-yzt-wx-7r",
                    "勇者突进",
                    "source-1",
                    "org-1",
                    "all_history",
                    "2026-02-10",
                    "2026-05-07",
                    rank,
                    material_id,
                    "video",
                    f"source-video-{rank}",
                    f"素材{rank}",
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
            "project_name_template": "{target_date_mmdd}_{owner}_{product}_{project_template_name}_{batch_code}_{index}",
            "constraints": {
                "phase": "phase1",
                "execution_enabled": False,
                "allow_real_create": False,
            },
        }
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
        "candidate_pool_size": 4,
        "violation_count": 0,
    }
    units = plan["strategy"]["projects"][0]["units"]
    assert [item["material_id"] for item in units[0]["materials"]] == ["m-high", "m-mid"]
    assert [item["material_id"] for item in units[1]["materials"]] == ["m-low", "m-extra"]
    assert plan["actions"] == []
    assert plan["live_api_payloads"] == []


def test_create_strategy_plan_fails_closed_when_request_deduped_materials_are_insufficient(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    _seed_create_db(db_path)
    request = _create_request()["create_request"]
    request["target_accounts"][0]["units_per_project"] = 3

    plan = build_create_strategy_plan(request=request, db_path=db_path, policy={})

    assert plan["ok"] is False
    assert plan["summary"]["planned_unit_count"] == 3
    assert plan["summary"]["planned_material_count"] == 4
    assert plan["summary"]["candidate_pool_size"] == 4
    assert plan["summary"]["violation_count"] == 1
    assert plan["violations"] == [
        "candidate pool has 4 usable materials, expected 6 for dedupe_scope=request"
    ]


def test_create_strategy_plan_filters_candidates_by_policy_thresholds(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    _seed_create_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            UPDATE product_source_material_candidates
            SET review_status = ?, score = ?, stat_cost = ?
            WHERE pool_key = ? AND material_id = ?
            """,
            ("REJECTED", 900, 900, "pool-yzt-wx-7r", "m-high"),
        )
        conn.execute(
            """
            UPDATE product_source_material_candidates
            SET score = ?, stat_cost = ?
            WHERE pool_key = ? AND material_id = ?
            """,
            (20, 20, "pool-yzt-wx-7r", "m-extra"),
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
    assert plan["summary"]["candidate_pool_size"] == 2
    assert [item["material_id"] for item in units[0]["materials"]] == ["m-mid", "m-low"]
    assert units[1]["materials"] == []
    assert plan["violations"] == [
        "candidate pool has 2 usable materials, expected 4 for dedupe_scope=request"
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
    assert plan["summary"]["candidate_pool_size"] == 3
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
    assert result["approved_for_execute"] is False
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
    assert result["approved_for_execute"] is False


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
    assert "material not-in-candidate-pool is not in candidate pool pool-yzt-wx-7r" in result["violations"]
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
            "project_type": "WX_PAY_7R_GENERAL",
            "daily_budget": 300.0,
            "field_defaults": {
                "landing_type": "MICRO_GAME",
                "pricing": "PRICING_CPA",
                "inventory_type": "UNION",
            },
        },
    }
    assert task["redacted_payload_drafts"][1]["operation"] == "create_unit"
    assert task["redacted_payload_drafts"][1]["payload"]["unit_key"] == "target-1-p001-u01"
    assert task["redacted_payload_drafts"][3]["operation"] == "bind_material"
    assert task["redacted_payload_drafts"][3]["payload"]["material_id"] == "m-high"
    assert result["payload_schema"]["version"] == "phase1.create_payload.v1"
    assert result["payload_schema"]["mode"] == "schema_only"
    assert result["payload_schema"]["execution_enabled"] is False
    assert result["payload_schema"]["external_api_enabled"] is False
    assert result["payload_schema"]["live_payload_generation_enabled"] is False
    assert result["payload_schema"]["endpoints"] == {
        "create_project": "",
        "create_unit": "",
        "bind_material": "",
    }
    assert result["payload_schema"]["required_fields"]["create_project"] == [
        "advertiser_id",
        "project_name",
        "project_type",
        "daily_budget",
        "field_defaults",
    ]
    assert result["payload_schema"]["required_fields"]["create_unit"] == [
        "advertiser_id",
        "project_key",
        "project_id",
        "unit_key",
        "promotion_name",
        "field_defaults",
    ]
    assert result["payload_schema"]["required_fields"]["bind_material"] == [
        "advertiser_id",
        "project_key",
        "project_id",
        "unit_key",
        "promotion_id",
        "material_id",
        "source_video_id",
    ]
    assert result["payload_contract"] == {
        "status": "passed",
        "schema_version": "phase1.create_payload.v1",
        "checked_project_count": 1,
        "checked_unit_count": 2,
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
        "draft_count": 7,
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
        "draft_count": 7,
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
        "operation_count": 3,
        "field_count": 18,
        "verified_field_count": 0,
        "unverified_field_count": 18,
        "missing_provider_field_count": 18,
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
    assert result["provider_payload_draft_digest"]["provider_payload_draft_count"] == 7
    assert result["redacted_payload_drafts"][0]["operation"] == "create_project"
    assert result["redacted_payload_drafts"][0]["payload"]["project_key"] == "target-1-p001"
    assert result["redacted_payload_drafts"][0]["payload"]["materials"] == "<redacted:4 material ids>"
    assert result["approved_for_execute"] is False
    assert result["actions"] == []


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
                            "provider_field": "landing_type",
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
                            "internal_field": "field_defaults",
                            "provider_field": "project_fields",
                            "purpose": "project and unit default fields",
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
                            "internal_field": "field_defaults",
                            "provider_field": "promotion_fields",
                            "purpose": "project and unit default fields",
                            "verified": True,
                            "required": True,
                            "source": "unit_test",
                        },
                    ],
                    "bind_material": [
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
                            "internal_field": "promotion_id",
                            "provider_field": "promotion_id",
                            "purpose": "provider promotion id lookup placeholder",
                            "verified": True,
                            "required": True,
                            "source": "unit_test",
                        },
                        {
                            "internal_field": "material_id",
                            "provider_field": "material_id",
                            "purpose": "source material identity",
                            "verified": True,
                            "required": True,
                            "source": "unit_test",
                        },
                        {
                            "internal_field": "source_video_id",
                            "provider_field": "source_video_id",
                            "purpose": "source video identity",
                            "verified": True,
                            "required": True,
                            "source": "unit_test",
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
        "status": "verified",
        "provider": "oceanengine",
        "mapping_verified": True,
        "operation_count": 3,
        "field_count": 18,
        "verified_field_count": 18,
        "unverified_field_count": 0,
        "missing_provider_field_count": 0,
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
        "status": "ready",
        "ready_for_live_execute": True,
        "provider": "oceanengine",
        "checks": {
            "provider_adapter_mapping_verified": True,
            "provider_field_map_verified": True,
            "provider_payloads_fully_mapped": True,
            "payload_drafts_non_executable": True,
            "live_payload_count_zero": True,
        },
        "blocking_reasons": [],
    }
    assert result["execution_enabled"] is False
    assert result["external_api_calls"] == 0
    assert result["provider_payload_drafts"][0]["mapping_verified"] is True
    assert result["provider_payload_drafts"][0]["field_mapping_applied"] is True
    assert result["provider_payload_drafts"][0]["payload"]["advertiser_id"] == "target-1"
    assert result["provider_payload_drafts"][0]["payload"]["name"] == "0508_郭靖_勇者突进_微小每付7R通投_B80C4C430_01"
    assert result["provider_payload_drafts"][0]["payload"]["landing_type"] == "WX_PAY_7R_GENERAL"
    assert result["provider_payload_drafts"][0]["payload"]["budget"] == 300.0
    assert "project_name" not in result["provider_payload_drafts"][0]["payload"]
    assert "daily_budget" not in result["provider_payload_drafts"][0]["payload"]
    unit_draft = next(draft for draft in result["provider_payload_drafts"] if draft["operation"] == "create_unit")
    assert unit_draft["field_mapping_applied"] is True
    assert unit_draft["payload"]["local_project_key"] == "target-1-p001"
    assert unit_draft["payload"]["project_id"] == "<lookup:target-1-p001>"
    assert unit_draft["payload"]["local_unit_key"] == "target-1-p001-u01"
    assert unit_draft["payload"]["promotion_name"] == "0508_郭靖_勇者突进_微小每付7R通投_B80C4C430_01_U01"
    assert "unit_key" not in unit_draft["payload"]
    material_draft = next(draft for draft in result["provider_payload_drafts"] if draft["operation"] == "bind_material")
    assert material_draft["field_mapping_applied"] is True
    assert material_draft["payload"]["local_project_key"] == "target-1-p001"
    assert material_draft["payload"]["project_id"] == "<lookup:target-1-p001>"
    assert material_draft["payload"]["local_unit_key"] == "target-1-p001-u01"
    assert material_draft["payload"]["promotion_id"] == "<lookup:target-1-p001-u01>"
    assert material_draft["payload"]["material_id"] == "m-high"
    assert material_draft["payload"]["source_video_id"] == "source-video-1"
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
    assert material_draft["payload"]["project_id"] == "<lookup:target-1-p001>"
    assert material_draft["payload"]["promotion_id"] == "<lookup:target-1-p001-u01>"
    assert material_draft["payload"]["source_video_id"] == "source-video-1"
    assert result["payload_contract"]["status"] == "passed"
    assert result["execution_enabled"] is False
    assert result["external_api_calls"] == 0
    assert result["actions"] == []


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
                        "project_type": "WX_PAY_7R_GENERAL",
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
        "operation_count": 3,
        "field_count": 18,
        "verified_field_count": 0,
        "missing_provider_field_count": 18,
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
    assert result["summary"]["field_count"] == 18


def test_create_provider_field_map_check_cli_uses_policy_config(tmp_path: Path, capsys):
    db_path = tmp_path / "roibang.sqlite3"
    runtime_path = _runtime_config(tmp_path, db_path)
    module = _load_script("run_create_provider_field_map_check")

    exit_code = module.run_from_args(["--config", str(runtime_path), "--policy", "policies/strategy.example.json"])

    output = json.loads(capsys.readouterr().out)
    artifact = json.loads(Path(output["artifact_path"]).read_text(encoding="utf-8"))
    assert exit_code == 0
    assert output["status"] == "unverified"
    assert artifact["workflow"] == "create_provider_field_map_check"
    assert artifact["summary"]["field_map_path"] == "configs/provider-field-maps/oceanengine.create.phase1.example.json"
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
        "operation_count": 3,
        "field_count": 18,
        "needs_provider_field_count": 18,
        "needs_verification_count": 18,
        "ready_for_live_execute": False,
    }
    assert result["review_contract"] == {
        "status": "needs_review",
        "field_count": 18,
        "needs_provider_field_count": 18,
        "needs_verification_count": 18,
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
    assert result["summary"]["field_count"] == 18
    assert artifact["workflow"] == "create_field_mapping_review_pack"
    assert artifact["actions"] == []


def test_create_field_mapping_review_pack_cli_uses_policy_config(tmp_path: Path, capsys):
    db_path = tmp_path / "roibang.sqlite3"
    runtime_path = _runtime_config(tmp_path, db_path)
    module = _load_script("run_create_field_mapping_review_pack")

    exit_code = module.run_from_args(["--config", str(runtime_path), "--policy", "policies/strategy.example.json"])

    output = json.loads(capsys.readouterr().out)
    artifact = json.loads(Path(output["artifact_path"]).read_text(encoding="utf-8"))
    assert exit_code == 0
    assert output["workflow"] == "create_field_mapping_review_pack"
    assert output["status"] == "needs_review"
    assert artifact["summary"]["field_map_path"] == "configs/provider-field-maps/oceanengine.create.phase1.example.json"
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
                    "create_project": "/open_api/2/project/create/",
                    "create_unit": "/open_api/2/promotion/create/",
                    "bind_material": "/open_api/2/promotion/material/bind/",
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
        "operation_count": 3,
        "field_count": 18,
        "candidate_provider_field_count": 10,
        "verified_field_count": 0,
        "unresolved_field_count": 18,
        "open_question_count": 12,
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
    assert project_section["endpoint"] == "/open_api/2/project/create/"
    assert project_section["field_source"] == "create_strategy_plan.strategy.projects[]"
    assert project_section["fields"][0] == {
        "internal_field": "advertiser_id",
        "provider_field": "advertiser_id",
        "provider_object": "project_create_request",
        "mapping_kind": "direct",
        "value_source": "create_strategy_plan.strategy.projects[].advertiser_id",
        "evidence_refs": ["oceanengine_openapi_project_create_request"],
        "open_questions": [],
        "review_status": "needs_verification",
    }
    unresolved = [
        item
        for item in result["unresolved_mappings"]
        if item["operation"] == "create_project" and item["internal_field"] == "field_defaults"
    ]
    assert unresolved == [
        {
            "operation": "create_project",
            "internal_field": "field_defaults",
            "review_status": "needs_provider_field",
            "open_questions": [
                "Split field_defaults into explicit project API fields before live payload development."
            ],
        }
    ]
    assert result["provider_field_map_contract"]["status"] == "unverified"
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
    assert result["summary"]["field_count"] == 18
    assert artifact["phase"] == "phase2_preparation"
    assert artifact["execution_enabled"] is False
    assert artifact["external_api_calls"] == 0
    assert artifact["actions"] == []


def test_create_phase2_provider_mapping_prep_cli_uses_policy_config(tmp_path: Path, capsys):
    db_path = tmp_path / "roibang.sqlite3"
    runtime_path = _runtime_config(tmp_path, db_path)
    module = _load_script("run_create_phase2_provider_mapping_prep")

    exit_code = module.run_from_args(["--config", str(runtime_path), "--policy", "policies/strategy.example.json"])

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
        "field_count": 18,
        "catalog_evidence_count": 3,
        "reviewed_evidence_count": 0,
        "ready_field_count": 0,
        "unresolved_field_count": 18,
        "evidence_status_counts": {
            "local_only_needs_confirmation": 4,
            "needs_evidence_review": 10,
            "needs_provider_field": 4,
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
        "evidence_status": "needs_evidence_review",
        "evidence_issues": ["evidence oceanengine_openapi_project_create_request is not reviewed"],
    }
    unresolved_local = [
        item
        for item in result["unresolved_evidence_items"]
        if item["operation"] == "create_unit" and item["internal_field"] == "project_key"
    ]
    assert unresolved_local == [
        {
            "operation": "create_unit",
            "internal_field": "project_key",
            "provider_field": "",
            "evidence_status": "local_only_needs_confirmation",
            "evidence_issues": ["local-only field requires explicit confirmation"],
        }
    ]
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
        "next_command": "PYTHONPATH=src python3 scripts/run_create_provider_evidence_review.py --config configs/runtime.example.json --policy policies/strategy.example.json",
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
    assert result["summary"]["field_count"] == 18
    assert artifact["workflow"] == "create_provider_evidence_review"
    assert artifact["execution_enabled"] is False
    assert artifact["external_api_calls"] == 0
    assert artifact["actions"] == []


def test_create_provider_evidence_review_cli_uses_policy_config(tmp_path: Path, capsys):
    db_path = tmp_path / "roibang.sqlite3"
    runtime_path = _runtime_config(tmp_path, db_path)
    module = _load_script("run_create_provider_evidence_review")

    exit_code = module.run_from_args(["--config", str(runtime_path), "--policy", "policies/strategy.example.json"])

    output = json.loads(capsys.readouterr().out)
    artifact = json.loads(Path(output["artifact_path"]).read_text(encoding="utf-8"))
    assert exit_code == 0
    assert output["workflow"] == "create_provider_evidence_review"
    assert output["status"] == "needs_review"
    assert artifact["phase"] == "phase2_preparation"
    assert artifact["summary"]["evidence_catalog_path"] == "configs/provider-evidence/oceanengine.create.phase2-review.example.json"
    assert output["operator_guide"]["status"] == "needs_review"
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
            "policies/strategy.example.json",
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
        "value_source": "product_source_material_candidates.material_id",
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
        "value_source": "product_source_material_candidates.material_id",
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
        "command": "PYTHONPATH=src python3 scripts/run_create_phase2_yzt_create_preview.py --config configs/runtime.example.json --preview-config configs/create/yzt-wx-mini-game.preview.example.json --policy policies/strategy.example.json",
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
        "message": "有效触点由勇者突进脚本固定",
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
    assert result["approved_for_execute"] is False
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
    assert artifact["approved_for_execute"] is False
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
        "先同步或导入素材候选池，确保素材数量够这次预演使用。",
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
            "message": "有效触点由勇者突进脚本固定",
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
            "policies/strategy.example.json",
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
    policy = json.loads(Path("policies/strategy.example.json").read_text(encoding="utf-8"))

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
        "pool_key": "pool-yzt-wx-7r",
        "source_advertiser_id": "source-1",
        "required_material_count": 2,
        "usable_material_count": 4,
        "missing_material_count": 0,
        "ready_for_dry_chain": True,
    }
    assert result["material_pool"] == {
        "material_type": "video",
        "materials_per_unit": 2,
        "dedupe_scope": "request",
        "candidate_filter_statuses": ["APPROVED"],
    }
    assert result["violations"] == []
    assert result["human_next_steps"] == ["本地素材池数量够用；下一步可以跑完整预演。"]
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
    assert result["status"] == "needs_material_pool_sync"
    assert result["summary"]["required_material_count"] == 8
    assert result["summary"]["usable_material_count"] == 4
    assert result["summary"]["missing_material_count"] == 4
    assert result["violations"] == ["本地素材池可用素材 4 个，不够本次预演需要的 8 个，缺 4 个"]
    assert result["human_next_steps"] == ["先同步或导入素材池，或减少本次项目数、单元数、每单元素材数。"]


def test_create_phase2_yzt_material_pool_check_treats_platform_status_3_as_approved(tmp_path: Path):
    from roibang_v2.workflows.create_phase2_yzt_material_pool_check import build_create_phase2_yzt_material_pool_check

    db_path = tmp_path / "roibang.sqlite3"
    _seed_create_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE product_source_material_candidates SET review_status = '3'")

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
        "next_command": "PYTHONPATH=src python3 scripts/run_create_phase2_yzt_dry_chain.py --config configs/runtime.example.json --preview-config configs/create/yzt-wx-mini-game.preview.example.json --policy policies/strategy.example.json",
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
        "本地素材池可用素材 0 个，不够本次预演需要的 2 个，缺 2 个",
    ]
    assert result["human_next_steps"] == [
        "把 target-advertiser-id 这种占位账户换成真实账户ID。",
        "先同步账户池，或把配置里的账户ID改成本地账户池已有账户。",
        "先同步或导入素材池，或减少本次项目数、单元数、每单元素材数。",
    ]
    assert result["operator_guide"] == {
        "status": "needs_fix",
        "title": "当前不能进入完整预演",
        "ordered_steps": [
            "把 target-advertiser-id 这种占位账户换成真实账户ID。",
            "先同步账户池，或把配置里的账户ID改成本地账户池已有账户。",
            "先同步或导入素材池，或减少本次项目数、单元数、每单元素材数。",
            "修完后重新运行一键准备检查。",
        ],
        "next_command": "PYTHONPATH=src python3 scripts/run_create_phase2_yzt_preparation_check.py --config configs/runtime.example.json --preview-config configs/create/yzt-wx-mini-game.preview.example.json --policy policies/strategy.example.json",
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
            "policies/strategy.example.json",
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
        "freeze_rule": "generate once in plan, then reuse through preflight, dry-run, approval, and execute",
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
            "policies/strategy.example.json",
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
        "summary": {"unresolved_field_count": 18, "open_question_count": 12},
        "unresolved_mappings": [{"operation": "create_project", "internal_field": "field_defaults"}],
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
        {"area": "provider_field_mapping", "operation": "create_project", "field": "field_defaults"},
        {"area": "template_slots", "operation": "create_project", "slot": "project_name_template"},
        {"area": "project_naming", "item": "batch_code"},
    ]
    assert result["remaining_review_groups"] == [
        {
            "group": "needs_provider_evidence",
            "label": "需要补平台字段依据",
            "item_count": 1,
            "items": [
                {"area": "provider_field_mapping", "operation": "create_project", "field": "field_defaults"},
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


def test_create_readiness_matrix_summarizes_blocking_review_gates():
    field_map_check = {
        "workflow": "create_provider_field_map_check",
        "ok": True,
        "status": "unverified",
        "summary": {"field_count": 18, "missing_provider_field_count": 18},
        "provider_readiness_contract": {"ready_for_live_execute": False},
    }
    field_mapping_review_pack = {
        "workflow": "create_field_mapping_review_pack",
        "ok": True,
        "status": "needs_review",
        "summary": {"field_count": 18, "needs_provider_field_count": 18},
    }
    template_slot_review_pack = {
        "workflow": "create_template_slot_review_pack",
        "ok": True,
        "status": "needs_review",
        "summary": {"slot_count": 12, "needs_review_slot_count": 12},
    }
    preflight = {"workflow": "create_preflight", "ok": True, "status": "passed", "summary": {"violation_count": 0}}
    dry_run = {"workflow": "create_dry_run", "ok": True, "status": "simulated", "summary": {"candidate_task_count": 1}}
    replay = {"workflow": "create_chain_replay", "ok": True, "status": "passed", "summary": {"violation_count": 0}}
    manifest = {"workflow": "create_chain_manifest", "ok": True, "status": "ready", "summary": {"artifact_count": 8}}

    result = build_create_readiness_matrix(
        create_provider_field_map_check_artifact=field_map_check,
        create_field_mapping_review_pack_artifact=field_mapping_review_pack,
        create_template_slot_review_pack_artifact=template_slot_review_pack,
        create_preflight_artifact=preflight,
        create_dry_run_artifact=dry_run,
        create_chain_replay_artifact=replay,
        create_chain_manifest_artifact=manifest,
    )

    assert result["ok"] is True
    assert result["workflow"] == "create_readiness_matrix"
    assert result["phase"] == "phase1"
    assert result["execution_enabled"] is False
    assert result["external_api_calls"] == 0
    assert result["status"] == "not_ready"
    assert result["ready_for_live_execute"] is False
    assert result["summary"] == {
        "gate_count": 7,
        "passed_gate_count": 4,
        "blocking_gate_count": 3,
        "ready_for_live_execute": False,
    }
    assert result["readiness_matrix"][0] == {
        "gate": "provider_field_map",
        "workflow": "create_provider_field_map_check",
        "artifact_status": "unverified",
        "ready": False,
        "blocking": True,
        "reason": "provider field map must be verified before live execute",
    }
    assert result["readiness_matrix"][3]["gate"] == "create_preflight"
    assert result["readiness_matrix"][3]["ready"] is True
    assert result["blocking_reasons"] == [
        "provider field map must be verified before live execute",
        "field mapping review pack still needs review",
        "template slot review pack still needs review",
    ]
    assert result["actions"] == []


def test_run_create_readiness_matrix_request_writes_artifact(tmp_path: Path):
    passed = {"ok": True, "status": "passed", "summary": {}}
    result = run_create_readiness_matrix_request(
        {
            "create_readiness_matrix": {
                "create_provider_field_map_check_artifact": {
                    "workflow": "create_provider_field_map_check",
                    "ok": True,
                    "status": "verified",
                    "provider_readiness_contract": {"ready_for_live_execute": True},
                },
                "create_field_mapping_review_pack_artifact": {
                    "workflow": "create_field_mapping_review_pack",
                    "ok": True,
                    "status": "verified",
                    "summary": {},
                },
                "create_template_slot_review_pack_artifact": {
                    "workflow": "create_template_slot_review_pack",
                    "ok": True,
                    "status": "reviewed",
                    "summary": {},
                },
                "create_preflight_artifact": {"workflow": "create_preflight", **passed},
                "create_dry_run_artifact": {"workflow": "create_dry_run", "ok": True, "status": "simulated", "summary": {}},
                "create_chain_replay_artifact": {"workflow": "create_chain_replay", **passed},
                "create_chain_manifest_artifact": {"workflow": "create_chain_manifest", "ok": True, "status": "ready", "summary": {}},
            }
        },
        runs_dir=tmp_path / "runs",
    )

    artifact = json.loads(Path(result["artifact_path"]).read_text(encoding="utf-8"))
    assert result["workflow"] == "create_readiness_matrix"
    assert result["ready_for_live_execute"] is True
    assert artifact["workflow"] == "create_readiness_matrix"
    assert artifact["actions"] == []


def test_create_readiness_matrix_cli_uses_latest_artifacts(tmp_path: Path, capsys):
    db_path = tmp_path / "roibang.sqlite3"
    runtime_path = _runtime_config(tmp_path, db_path)
    runs_dir = tmp_path / "runs"
    artifacts = {
        "create_provider_field_map_check": {
            "workflow": "create_provider_field_map_check",
            "ok": True,
            "status": "unverified",
            "summary": {},
            "provider_readiness_contract": {"ready_for_live_execute": False},
        },
        "create_field_mapping_review_pack": {
            "workflow": "create_field_mapping_review_pack",
            "ok": True,
            "status": "needs_review",
            "summary": {},
        },
        "create_template_slot_review_pack": {
            "workflow": "create_template_slot_review_pack",
            "ok": True,
            "status": "needs_review",
            "summary": {},
        },
        "create_preflight": {"workflow": "create_preflight", "ok": True, "status": "passed", "summary": {}},
        "create_dry_run": {"workflow": "create_dry_run", "ok": True, "status": "simulated", "summary": {}},
        "create_chain_replay": {"workflow": "create_chain_replay", "ok": True, "status": "passed", "summary": {}},
        "create_chain_manifest": {"workflow": "create_chain_manifest", "ok": True, "status": "ready", "summary": {}},
    }
    for workflow, payload in artifacts.items():
        path = runs_dir / workflow / "20260508T000000Z.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    module = _load_script("run_create_readiness_matrix")

    exit_code = module.run_from_args(["--config", str(runtime_path)])

    output = json.loads(capsys.readouterr().out)
    artifact = json.loads(Path(output["artifact_path"]).read_text(encoding="utf-8"))
    assert exit_code == 0
    assert output["workflow"] == "create_readiness_matrix"
    assert output["status"] == "not_ready"
    assert artifact["ready_for_live_execute"] is False
    assert artifact["execution_enabled"] is False
    assert artifact["external_api_calls"] == 0
    assert artifact["actions"] == []


def test_create_live_execute_phase_gate_blocks_phase1_even_when_readiness_is_ready():
    readiness_matrix = {
        "workflow": "create_readiness_matrix",
        "ok": True,
        "status": "ready",
        "ready_for_live_execute": True,
        "summary": {"blocking_gate_count": 0},
        "blocking_reasons": [],
    }

    result = build_create_live_execute_phase_gate(
        create_readiness_matrix_artifact=readiness_matrix,
        policy={
            "phase": "phase1",
            "create_execute": {
                "phase_gate": {
                    "allow_live_execute_development": False,
                    "allow_live_execute": False,
                    "required_next_phase": "phase2",
                }
            },
        },
    )

    assert result["ok"] is True
    assert result["workflow"] == "create_live_execute_phase_gate"
    assert result["phase"] == "phase1"
    assert result["execution_enabled"] is False
    assert result["external_api_calls"] == 0
    assert result["status"] == "blocked"
    assert result["live_execute_development_allowed"] is False
    assert result["live_execute_allowed"] is False
    assert result["summary"] == {
        "current_phase": "phase1",
        "required_next_phase": "phase2",
        "readiness_status": "ready",
        "ready_for_live_execute": True,
        "condition_count": 5,
        "passed_condition_count": 3,
        "blocking_condition_count": 2,
    }
    assert result["phase_gate_conditions"] == [
        {
            "condition": "current_phase_is_not_phase1",
            "passed": False,
            "reason": "current phase is phase1",
        },
        {
            "condition": "readiness_matrix_ready",
            "passed": True,
            "reason": "",
        },
        {
            "condition": "policy_allows_live_execute_development",
            "passed": False,
            "reason": "policy does not allow live execute development",
        },
        {
            "condition": "policy_blocks_live_execute",
            "passed": True,
            "reason": "",
        },
        {
            "condition": "phase1_safety_values_retained",
            "passed": True,
            "reason": "",
        },
    ]
    assert result["blocking_reasons"] == [
        "current phase is phase1",
        "policy does not allow live execute development",
    ]
    assert result["violations"] == []
    assert result["actions"] == []


def test_create_live_execute_phase_gate_rejects_dangerous_phase1_policy_switches():
    readiness_matrix = {
        "workflow": "create_readiness_matrix",
        "ok": True,
        "status": "ready",
        "ready_for_live_execute": True,
        "summary": {"blocking_gate_count": 0},
        "blocking_reasons": [],
    }

    result = build_create_live_execute_phase_gate(
        create_readiness_matrix_artifact=readiness_matrix,
        policy={
            "phase": "phase1",
            "create_execute": {
                "phase_gate": {
                    "allow_live_execute_development": True,
                    "allow_live_execute": True,
                }
            },
        },
    )

    assert result["ok"] is False
    assert result["status"] == "blocked"
    assert result["live_execute_development_allowed"] is False
    assert result["live_execute_allowed"] is False
    assert "phase1 policy must not allow live execute development" in result["violations"]
    assert "phase1 policy must not allow live execute" in result["violations"]
    assert result["actions"] == []


def test_run_create_live_execute_phase_gate_request_writes_artifact(tmp_path: Path):
    result = run_create_live_execute_phase_gate_request(
        {
            "create_live_execute_phase_gate": {
                "create_readiness_matrix_artifact": {
                    "workflow": "create_readiness_matrix",
                    "ok": True,
                    "status": "not_ready",
                    "ready_for_live_execute": False,
                    "summary": {"blocking_gate_count": 3},
                    "blocking_reasons": ["field mapping review pack still needs review"],
                },
                "policy": {"phase": "phase1", "create_execute": {"phase_gate": {}}},
            }
        },
        runs_dir=tmp_path / "runs",
    )

    artifact = json.loads(Path(result["artifact_path"]).read_text(encoding="utf-8"))
    assert result["workflow"] == "create_live_execute_phase_gate"
    assert result["status"] == "blocked"
    assert result["live_execute_development_allowed"] is False
    assert artifact["workflow"] == "create_live_execute_phase_gate"
    assert artifact["actions"] == []


def test_create_live_execute_phase_gate_cli_uses_latest_readiness_matrix(tmp_path: Path, capsys):
    db_path = tmp_path / "roibang.sqlite3"
    runtime_path = _runtime_config(tmp_path, db_path)
    runs_dir = tmp_path / "runs"
    path = runs_dir / "create_readiness_matrix" / "20260508T000000Z.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "workflow": "create_readiness_matrix",
                "ok": True,
                "status": "not_ready",
                "ready_for_live_execute": False,
                "summary": {"blocking_gate_count": 3},
                "blocking_reasons": ["field mapping review pack still needs review"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    module = _load_script("run_create_live_execute_phase_gate")

    exit_code = module.run_from_args(["--config", str(runtime_path), "--policy", "policies/strategy.example.json"])

    output = json.loads(capsys.readouterr().out)
    artifact = json.loads(Path(output["artifact_path"]).read_text(encoding="utf-8"))
    assert exit_code == 0
    assert output["workflow"] == "create_live_execute_phase_gate"
    assert output["status"] == "blocked"
    assert output["live_execute_development_allowed"] is False
    assert artifact["execution_enabled"] is False
    assert artifact["external_api_calls"] == 0
    assert artifact["actions"] == []


def test_create_live_payload_adapter_scaffold_keeps_live_payloads_disabled():
    dry_run = {
        "workflow": "create_dry_run",
        "ok": True,
        "status": "simulated",
        "provider_adapter": {
            "provider": "oceanengine",
            "field_mapping_version": "phase1.oceanengine.create_payload.draft.v1",
            "executable": False,
        },
        "provider_payload_drafts": [
            {
                "operation": "create_project",
                "provider": "oceanengine",
                "executable": False,
                "payload": {"advertiser_id": "target-1"},
            }
        ],
        "provider_payload_draft_digest": {
            "algorithm": "sha256",
            "value": "0" * 64,
            "provider_payload_draft_count": 1,
        },
    }
    phase_gate = {
        "workflow": "create_live_execute_phase_gate",
        "ok": True,
        "status": "blocked",
        "live_execute_development_allowed": False,
        "live_execute_allowed": False,
    }

    result = build_create_live_payload_adapter_scaffold(
        create_dry_run_artifact=dry_run,
        create_live_execute_phase_gate_artifact=phase_gate,
        policy={"phase": "phase1", "create_execute": {"payload_schema": {"live_payload_generation_enabled": False}}},
    )

    assert result["ok"] is True
    assert result["workflow"] == "create_live_payload_adapter_scaffold"
    assert result["phase"] == "phase1"
    assert result["execution_enabled"] is False
    assert result["external_api_calls"] == 0
    assert result["status"] == "blocked"
    assert result["live_payload_generation_enabled"] is False
    assert result["live_payloads"] == []
    assert result["executable_payloads"] == []
    assert result["summary"] == {
        "provider": "oceanengine",
        "field_mapping_version": "phase1.oceanengine.create_payload.draft.v1",
        "provider_payload_draft_count": 1,
        "live_payload_count": 0,
        "executable_payload_count": 0,
        "phase_gate_status": "blocked",
    }
    assert result["adapter_interface"] == {
        "provider": "oceanengine",
        "transport": "disabled_live_payload_adapter_scaffold",
        "input_contract": {
            "source_workflow": "create_dry_run",
            "requires_provider_payload_drafts": True,
            "requires_phase_gate": True,
        },
        "output_contract": {
            "emits_live_payloads": False,
            "emits_executable_payloads": False,
            "calls_external_api": False,
        },
    }
    assert result["safety_contract"] == {
        "status": "blocked",
        "phase_gate_allows_development": False,
        "phase_gate_allows_live_execute": False,
        "live_payload_generation_enabled": False,
        "live_payload_count_zero": True,
        "executable_payload_count_zero": True,
        "external_api_calls_zero": True,
    }
    assert result["provider_payload_draft_digest"] == dry_run["provider_payload_draft_digest"]
    assert result["blocking_reasons"] == ["live execute phase gate has not opened development"]
    assert result["violations"] == []
    assert result["actions"] == []


def test_create_live_payload_adapter_scaffold_rejects_dangerous_generation_policy():
    result = build_create_live_payload_adapter_scaffold(
        create_dry_run_artifact={
            "workflow": "create_dry_run",
            "ok": True,
            "status": "simulated",
            "provider_adapter": {"provider": "oceanengine"},
            "provider_payload_drafts": [],
            "provider_payload_draft_digest": {"algorithm": "sha256", "value": "0" * 64, "provider_payload_draft_count": 0},
        },
        create_live_execute_phase_gate_artifact={
            "workflow": "create_live_execute_phase_gate",
            "ok": True,
            "status": "blocked",
            "live_execute_development_allowed": False,
            "live_execute_allowed": True,
        },
        policy={
            "phase": "phase1",
            "create_execute": {
                "payload_schema": {"live_payload_generation_enabled": True},
            },
        },
    )

    assert result["ok"] is False
    assert result["status"] == "blocked"
    assert result["live_payload_generation_enabled"] is False
    assert "phase1 policy must keep live payload generation disabled" in result["violations"]
    assert "phase gate must not allow live execute for adapter scaffold" in result["violations"]
    assert result["live_payloads"] == []
    assert result["actions"] == []


def test_run_create_live_payload_adapter_scaffold_request_writes_artifact(tmp_path: Path):
    result = run_create_live_payload_adapter_scaffold_request(
        {
            "create_live_payload_adapter_scaffold": {
                "create_dry_run_artifact": {
                    "workflow": "create_dry_run",
                    "ok": True,
                    "status": "simulated",
                    "provider_adapter": {"provider": "oceanengine"},
                    "provider_payload_drafts": [],
                    "provider_payload_draft_digest": {"algorithm": "sha256", "value": "0" * 64, "provider_payload_draft_count": 0},
                },
                "create_live_execute_phase_gate_artifact": {
                    "workflow": "create_live_execute_phase_gate",
                    "ok": True,
                    "status": "blocked",
                    "live_execute_development_allowed": False,
                    "live_execute_allowed": False,
                },
                "policy": {"phase": "phase1"},
            }
        },
        runs_dir=tmp_path / "runs",
    )

    artifact = json.loads(Path(result["artifact_path"]).read_text(encoding="utf-8"))
    assert result["workflow"] == "create_live_payload_adapter_scaffold"
    assert result["live_payloads"] == []
    assert artifact["workflow"] == "create_live_payload_adapter_scaffold"
    assert artifact["actions"] == []


def test_create_live_payload_adapter_scaffold_cli_uses_latest_artifacts(tmp_path: Path, capsys):
    db_path = tmp_path / "roibang.sqlite3"
    runtime_path = _runtime_config(tmp_path, db_path)
    runs_dir = tmp_path / "runs"
    dry_run_path = runs_dir / "create_dry_run" / "20260508T000000Z.json"
    dry_run_path.parent.mkdir(parents=True, exist_ok=True)
    dry_run_path.write_text(
        json.dumps(
            {
                "workflow": "create_dry_run",
                "ok": True,
                "status": "simulated",
                "provider_adapter": {"provider": "oceanengine"},
                "provider_payload_drafts": [],
                "provider_payload_draft_digest": {"algorithm": "sha256", "value": "0" * 64, "provider_payload_draft_count": 0},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    gate_path = runs_dir / "create_live_execute_phase_gate" / "20260508T000000Z.json"
    gate_path.parent.mkdir(parents=True, exist_ok=True)
    gate_path.write_text(
        json.dumps(
            {
                "workflow": "create_live_execute_phase_gate",
                "ok": True,
                "status": "blocked",
                "live_execute_development_allowed": False,
                "live_execute_allowed": False,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    module = _load_script("run_create_live_payload_adapter_scaffold")

    exit_code = module.run_from_args(["--config", str(runtime_path), "--policy", "policies/strategy.example.json"])

    output = json.loads(capsys.readouterr().out)
    artifact = json.loads(Path(output["artifact_path"]).read_text(encoding="utf-8"))
    assert exit_code == 0
    assert output["workflow"] == "create_live_payload_adapter_scaffold"
    assert output["status"] == "blocked"
    assert artifact["live_payload_generation_enabled"] is False
    assert artifact["external_api_calls"] == 0
    assert artifact["actions"] == []


def test_create_adapter_review_pack_summarizes_disabled_adapter_scaffold():
    scaffold = {
        "workflow": "create_live_payload_adapter_scaffold",
        "ok": True,
        "status": "blocked",
        "execution_enabled": False,
        "external_api_calls": 0,
        "live_payload_generation_enabled": False,
        "live_payloads": [],
        "executable_payloads": [],
        "summary": {
            "provider": "oceanengine",
            "field_mapping_version": "phase1.oceanengine.create_payload.draft.v1",
            "provider_payload_draft_count": 1,
            "live_payload_count": 0,
            "executable_payload_count": 0,
            "phase_gate_status": "blocked",
        },
        "adapter_interface": {
            "provider": "oceanengine",
            "transport": "disabled_live_payload_adapter_scaffold",
            "input_contract": {
                "source_workflow": "create_dry_run",
                "requires_provider_payload_drafts": True,
                "requires_phase_gate": True,
            },
            "output_contract": {
                "emits_live_payloads": False,
                "emits_executable_payloads": False,
                "calls_external_api": False,
            },
        },
        "safety_contract": {
            "status": "blocked",
            "phase_gate_allows_development": False,
            "phase_gate_allows_live_execute": False,
            "live_payload_generation_enabled": False,
            "live_payload_count_zero": True,
            "executable_payload_count_zero": True,
            "external_api_calls_zero": True,
        },
        "provider_payload_draft_digest": {
            "algorithm": "sha256",
            "value": "0" * 64,
            "provider_payload_draft_count": 1,
        },
        "blocking_reasons": ["live execute phase gate has not opened development"],
        "violations": [],
        "actions": [],
    }

    result = build_create_adapter_review_pack(create_live_payload_adapter_scaffold_artifact=scaffold)

    assert result["ok"] is True
    assert result["workflow"] == "create_adapter_review_pack"
    assert result["phase"] == "phase1"
    assert result["execution_enabled"] is False
    assert result["external_api_calls"] == 0
    assert result["status"] == "needs_review"
    assert result["required_user_input_now"] is False
    assert result["summary"] == {
        "provider": "oceanengine",
        "field_mapping_version": "phase1.oceanengine.create_payload.draft.v1",
        "adapter_status": "blocked",
        "provider_payload_draft_count": 1,
        "live_payload_count": 0,
        "executable_payload_count": 0,
        "review_item_count": 4,
        "blocking_reason_count": 1,
    }
    assert result["review_contract"] == {
        "status": "needs_review",
        "safe_to_review": True,
        "live_payloads_empty": True,
        "executable_payloads_empty": True,
        "external_api_calls_zero": True,
        "actions_empty": True,
    }
    assert result["review_sections"] == [
        {
            "section": "input_contract",
            "status": "present",
            "items": [
                {"key": "source_workflow", "value": "create_dry_run"},
                {"key": "requires_provider_payload_drafts", "value": True},
                {"key": "requires_phase_gate", "value": True},
            ],
        },
        {
            "section": "output_contract",
            "status": "disabled",
            "items": [
                {"key": "emits_live_payloads", "value": False},
                {"key": "emits_executable_payloads", "value": False},
                {"key": "calls_external_api", "value": False},
            ],
        },
        {
            "section": "safety_contract",
            "status": "blocked",
            "items": [
                {"key": "phase_gate_allows_development", "value": False},
                {"key": "phase_gate_allows_live_execute", "value": False},
                {"key": "live_payload_generation_enabled", "value": False},
            ],
        },
        {
            "section": "blocking_reasons",
            "status": "blocked",
            "items": [{"key": "reason", "value": "live execute phase gate has not opened development"}],
        },
    ]
    assert result["provider_payload_draft_digest"] == scaffold["provider_payload_draft_digest"]
    assert result["actions"] == []


def test_create_adapter_review_pack_rejects_non_empty_live_payloads():
    result = build_create_adapter_review_pack(
        create_live_payload_adapter_scaffold_artifact={
            "workflow": "create_live_payload_adapter_scaffold",
            "ok": True,
            "status": "blocked",
            "execution_enabled": False,
            "external_api_calls": 0,
            "live_payload_generation_enabled": False,
            "live_payloads": [{"payload": {}}],
            "executable_payloads": [],
            "summary": {},
            "adapter_interface": {},
            "safety_contract": {},
            "provider_payload_draft_digest": {"algorithm": "sha256", "value": "0" * 64, "provider_payload_draft_count": 0},
            "blocking_reasons": [],
            "violations": [],
            "actions": [],
        }
    )

    assert result["ok"] is False
    assert result["status"] == "invalid"
    assert result["review_contract"]["live_payloads_empty"] is False
    assert "adapter scaffold live_payloads must be empty" in result["violations"]
    assert result["actions"] == []


def test_run_create_adapter_review_pack_request_writes_artifact(tmp_path: Path):
    result = run_create_adapter_review_pack_request(
        {
            "create_adapter_review_pack": {
                "create_live_payload_adapter_scaffold_artifact": {
                    "workflow": "create_live_payload_adapter_scaffold",
                    "ok": True,
                    "status": "blocked",
                    "execution_enabled": False,
                    "external_api_calls": 0,
                    "live_payload_generation_enabled": False,
                    "live_payloads": [],
                    "executable_payloads": [],
                    "summary": {"provider": "oceanengine"},
                    "adapter_interface": {},
                    "safety_contract": {},
                    "provider_payload_draft_digest": {"algorithm": "sha256", "value": "0" * 64, "provider_payload_draft_count": 0},
                    "blocking_reasons": [],
                    "violations": [],
                    "actions": [],
                }
            }
        },
        runs_dir=tmp_path / "runs",
    )

    artifact = json.loads(Path(result["artifact_path"]).read_text(encoding="utf-8"))
    assert result["workflow"] == "create_adapter_review_pack"
    assert result["required_user_input_now"] is False
    assert artifact["workflow"] == "create_adapter_review_pack"
    assert artifact["actions"] == []


def test_create_adapter_review_pack_cli_uses_latest_scaffold(tmp_path: Path, capsys):
    db_path = tmp_path / "roibang.sqlite3"
    runtime_path = _runtime_config(tmp_path, db_path)
    scaffold_path = tmp_path / "runs" / "create_live_payload_adapter_scaffold" / "20260508T000000Z.json"
    scaffold_path.parent.mkdir(parents=True, exist_ok=True)
    scaffold_path.write_text(
        json.dumps(
            {
                "workflow": "create_live_payload_adapter_scaffold",
                "ok": True,
                "status": "blocked",
                "execution_enabled": False,
                "external_api_calls": 0,
                "live_payload_generation_enabled": False,
                "live_payloads": [],
                "executable_payloads": [],
                "summary": {"provider": "oceanengine"},
                "adapter_interface": {},
                "safety_contract": {},
                "provider_payload_draft_digest": {"algorithm": "sha256", "value": "0" * 64, "provider_payload_draft_count": 0},
                "blocking_reasons": [],
                "violations": [],
                "actions": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    module = _load_script("run_create_adapter_review_pack")

    exit_code = module.run_from_args(["--config", str(runtime_path)])

    output = json.loads(capsys.readouterr().out)
    artifact = json.loads(Path(output["artifact_path"]).read_text(encoding="utf-8"))
    assert exit_code == 0
    assert output["workflow"] == "create_adapter_review_pack"
    assert output["status"] == "needs_review"
    assert artifact["review_contract"]["safe_to_review"] is True
    assert artifact["execution_enabled"] is False
    assert artifact["external_api_calls"] == 0
    assert artifact["actions"] == []


def test_create_chain_index_collects_all_phase1_create_artifacts():
    artifacts = {
        "create_request": {"workflow": "create_request", "ok": True, "status": "", "artifact_path": "/runs/create_request/a.json"},
        "create_strategy_plan": {"workflow": "create_strategy_plan", "ok": True, "status": "", "artifact_path": "/runs/create_strategy_plan/a.json"},
        "create_preflight": {"workflow": "create_preflight", "ok": True, "status": "passed", "artifact_path": "/runs/create_preflight/a.json"},
        "create_provider_field_map_check": {
            "workflow": "create_provider_field_map_check",
            "ok": True,
            "status": "unverified",
            "artifact_path": "/runs/create_provider_field_map_check/a.json",
        },
        "create_field_mapping_review_pack": {
            "workflow": "create_field_mapping_review_pack",
            "ok": True,
            "status": "needs_review",
            "artifact_path": "/runs/create_field_mapping_review_pack/a.json",
        },
        "create_template_slot_review_pack": {
            "workflow": "create_template_slot_review_pack",
            "ok": True,
            "status": "needs_review",
            "artifact_path": "/runs/create_template_slot_review_pack/a.json",
        },
        "create_dry_run": {
            "workflow": "create_dry_run",
            "ok": True,
            "status": "simulated",
            "artifact_path": "/runs/create_dry_run/a.json",
            "provider_payload_draft_digest": {
                "algorithm": "sha256",
                "value": "1" * 64,
                "provider_payload_draft_count": 1,
            },
        },
        "create_approval": {"workflow": "create_approval", "ok": True, "status": "recorded", "artifact_path": "/runs/create_approval/a.json"},
        "create_plan_snapshot": {"workflow": "create_plan_snapshot", "ok": True, "status": "", "artifact_path": "/runs/create_plan_snapshot/a.json"},
        "create_execute": {
            "workflow": "create_execute",
            "ok": True,
            "status": "blocked",
            "artifact_path": "/runs/create_execute/a.json",
            "executed_task_count": 0,
        },
        "create_chain_replay": {"workflow": "create_chain_replay", "ok": True, "status": "passed", "artifact_path": "/runs/create_chain_replay/a.json"},
        "create_chain_manifest": {"workflow": "create_chain_manifest", "ok": True, "status": "ready", "artifact_path": "/runs/create_chain_manifest/a.json"},
        "create_readiness_matrix": {
            "workflow": "create_readiness_matrix",
            "ok": True,
            "status": "not_ready",
            "artifact_path": "/runs/create_readiness_matrix/a.json",
            "ready_for_live_execute": False,
        },
        "create_live_execute_phase_gate": {
            "workflow": "create_live_execute_phase_gate",
            "ok": True,
            "status": "blocked",
            "artifact_path": "/runs/create_live_execute_phase_gate/a.json",
            "live_execute_development_allowed": False,
            "live_execute_allowed": False,
        },
        "create_live_payload_adapter_scaffold": {
            "workflow": "create_live_payload_adapter_scaffold",
            "ok": True,
            "status": "blocked",
            "artifact_path": "/runs/create_live_payload_adapter_scaffold/a.json",
            "live_payload_generation_enabled": False,
            "live_payloads": [],
            "executable_payloads": [],
        },
        "create_adapter_review_pack": {
            "workflow": "create_adapter_review_pack",
            "ok": True,
            "status": "needs_review",
            "artifact_path": "/runs/create_adapter_review_pack/a.json",
            "required_user_input_now": False,
        },
    }

    result = build_create_chain_index(artifacts=artifacts)

    assert result["ok"] is True
    assert result["workflow"] == "create_chain_index"
    assert result["phase"] == "phase1"
    assert result["execution_enabled"] is False
    assert result["external_api_calls"] == 0
    assert result["status"] == "indexed"
    assert result["summary"] == {
        "artifact_count": 16,
        "missing_artifact_count": 0,
        "unsafe_artifact_count": 0,
        "ready_for_live_execute": False,
        "live_execute_allowed": False,
    }
    assert result["artifact_index"][0] == {
        "workflow": "create_request",
        "artifact_path": "/runs/create_request/a.json",
        "ok": True,
        "status": "",
        "execution_enabled": False,
        "external_api_calls": 0,
    }
    assert result["artifact_paths"]["create_adapter_review_pack"] == "/runs/create_adapter_review_pack/a.json"
    assert result["safety_contract"] == {
        "status": "passed",
        "execution_enabled_false": True,
        "external_api_calls_zero": True,
        "actions_empty": True,
        "no_live_execute_allowed": True,
        "no_live_payloads": True,
    }
    assert result["provider_payload_draft_digest"] == artifacts["create_dry_run"]["provider_payload_draft_digest"]
    assert result["violations"] == []
    assert result["actions"] == []


def test_create_chain_index_reports_missing_and_unsafe_artifacts():
    result = build_create_chain_index(
        artifacts={
            "create_request": {
                "workflow": "create_request",
                "ok": True,
                "status": "",
                "artifact_path": "/runs/create_request/a.json",
                "execution_enabled": True,
                "actions": [{"action": "bad"}],
            }
        }
    )

    assert result["ok"] is False
    assert result["status"] == "incomplete"
    assert result["summary"]["missing_artifact_count"] == 15
    assert result["summary"]["unsafe_artifact_count"] == 1
    assert "missing artifact create_strategy_plan" in result["violations"]
    assert "create_request execution_enabled must be false" in result["violations"]
    assert "create_request actions must be empty" in result["violations"]


def test_run_create_chain_index_request_writes_artifact(tmp_path: Path):
    artifacts = {
        workflow: {"workflow": workflow, "ok": True, "status": "ok", "artifact_path": f"/runs/{workflow}/a.json"}
        for workflow in [
            "create_request",
            "create_strategy_plan",
            "create_preflight",
            "create_provider_field_map_check",
            "create_field_mapping_review_pack",
            "create_template_slot_review_pack",
            "create_dry_run",
            "create_approval",
            "create_plan_snapshot",
            "create_execute",
            "create_chain_replay",
            "create_chain_manifest",
            "create_readiness_matrix",
            "create_live_execute_phase_gate",
            "create_live_payload_adapter_scaffold",
            "create_adapter_review_pack",
        ]
    }
    artifacts["create_readiness_matrix"]["ready_for_live_execute"] = False
    artifacts["create_live_execute_phase_gate"]["live_execute_allowed"] = False
    artifacts["create_live_payload_adapter_scaffold"]["live_payloads"] = []
    artifacts["create_live_payload_adapter_scaffold"]["executable_payloads"] = []

    result = run_create_chain_index_request(
        {"create_chain_index": {"artifacts": artifacts}},
        runs_dir=tmp_path / "runs",
    )

    artifact = json.loads(Path(result["artifact_path"]).read_text(encoding="utf-8"))
    assert result["workflow"] == "create_chain_index"
    assert artifact["workflow"] == "create_chain_index"
    assert artifact["actions"] == []


def test_create_chain_index_cli_uses_latest_artifacts(tmp_path: Path, capsys):
    db_path = tmp_path / "roibang.sqlite3"
    runtime_path = _runtime_config(tmp_path, db_path)
    runs_dir = tmp_path / "runs"
    workflows = [
        "create_request",
        "create_strategy_plan",
        "create_preflight",
        "create_provider_field_map_check",
        "create_field_mapping_review_pack",
        "create_template_slot_review_pack",
        "create_dry_run",
        "create_approval",
        "create_plan_snapshot",
        "create_execute",
        "create_chain_replay",
        "create_chain_manifest",
        "create_readiness_matrix",
        "create_live_execute_phase_gate",
        "create_live_payload_adapter_scaffold",
        "create_adapter_review_pack",
    ]
    for workflow in workflows:
        payload = {"workflow": workflow, "ok": True, "status": "ok"}
        if workflow == "create_readiness_matrix":
            payload["ready_for_live_execute"] = False
        if workflow == "create_live_execute_phase_gate":
            payload["live_execute_allowed"] = False
        if workflow == "create_live_payload_adapter_scaffold":
            payload["live_payloads"] = []
            payload["executable_payloads"] = []
        path = runs_dir / workflow / "20260508T000000Z.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    module = _load_script("run_create_chain_index")

    exit_code = module.run_from_args(["--config", str(runtime_path)])

    output = json.loads(capsys.readouterr().out)
    artifact = json.loads(Path(output["artifact_path"]).read_text(encoding="utf-8"))
    assert exit_code == 0
    assert output["workflow"] == "create_chain_index"
    assert output["status"] == "indexed"
    assert artifact["summary"]["artifact_count"] == 16
    assert artifact["execution_enabled"] is False
    assert artifact["external_api_calls"] == 0
    assert artifact["actions"] == []


def test_create_chain_final_report_summarizes_index_and_blockers_for_humans():
    chain_index = {
        "workflow": "create_chain_index",
        "ok": True,
        "status": "indexed",
        "summary": {
            "artifact_count": 16,
            "missing_artifact_count": 0,
            "unsafe_artifact_count": 0,
            "ready_for_live_execute": False,
            "live_execute_allowed": False,
        },
        "safety_contract": {
            "status": "passed",
            "execution_enabled_false": True,
            "external_api_calls_zero": True,
            "actions_empty": True,
            "no_live_execute_allowed": True,
            "no_live_payloads": True,
        },
        "violations": [],
    }
    readiness_matrix = {
        "workflow": "create_readiness_matrix",
        "ok": True,
        "status": "not_ready",
        "ready_for_live_execute": False,
        "summary": {"gate_count": 7, "passed_gate_count": 4, "blocking_gate_count": 3},
        "blocking_reasons": [
            "provider field map must be verified before live execute",
            "field mapping review pack still needs review",
            "template slot review pack still needs review",
        ],
    }
    phase_gate = {
        "workflow": "create_live_execute_phase_gate",
        "ok": True,
        "status": "blocked",
        "live_execute_development_allowed": False,
        "live_execute_allowed": False,
        "blocking_reasons": ["current phase is phase1"],
    }
    adapter_review = {
        "workflow": "create_adapter_review_pack",
        "ok": True,
        "status": "needs_review",
        "required_user_input_now": False,
        "summary": {
            "provider": "oceanengine",
            "adapter_status": "blocked",
            "live_payload_count": 0,
            "executable_payload_count": 0,
        },
        "review_contract": {"safe_to_review": True},
    }

    result = build_create_chain_final_report(
        create_chain_index_artifact=chain_index,
        create_readiness_matrix_artifact=readiness_matrix,
        create_live_execute_phase_gate_artifact=phase_gate,
        create_adapter_review_pack_artifact=adapter_review,
    )

    assert result["ok"] is True
    assert result["workflow"] == "create_chain_final_report"
    assert result["phase"] == "phase1"
    assert result["execution_enabled"] is False
    assert result["external_api_calls"] == 0
    assert result["status"] == "reported"
    assert result["overall_status"] == "not_ready_for_live_create"
    assert result["business_summary"] == (
        "创建链路本地产物已索引完成，Phase 1 仍保持真实创建阻断；"
        "当前主要卡点是字段映射、模板槽位和阶段闸门。"
    )
    assert result["summary"] == {
        "artifact_count": 16,
        "missing_artifact_count": 0,
        "unsafe_artifact_count": 0,
        "ready_for_live_execute": False,
        "live_execute_development_allowed": False,
        "live_execute_allowed": False,
        "blocking_reason_count": 4,
    }
    assert result["completed_sections"] == [
        "创建请求到本地预演链路已成型",
        "字段映射审阅包和模板槽位审阅包已生成",
        "链路回放、清单、索引和安全契约已覆盖",
        "真实执行和真实请求体仍保持硬阻断",
    ]
    assert result["pending_confirmations"] == [
        "确认 provider field map（渠道字段映射）",
        "确认 template slots（固定模板槽位）",
        "确认是否进入 Phase 2（真实创建开发阶段）",
    ]
    assert result["blocking_reasons"] == [
        "provider field map must be verified before live execute",
        "field mapping review pack still needs review",
        "template slot review pack still needs review",
        "current phase is phase1",
    ]
    assert result["recommended_next_steps"] == [
        "保持 create_execute 硬阻断",
        "审阅字段映射和模板槽位",
        "准备后续由你确认是否参考老项目成熟模板",
    ]
    assert result["actions"] == []


def test_create_chain_final_report_rejects_unsafe_index():
    result = build_create_chain_final_report(
        create_chain_index_artifact={
            "workflow": "create_chain_index",
            "ok": False,
            "status": "incomplete",
            "summary": {"artifact_count": 1, "missing_artifact_count": 15, "unsafe_artifact_count": 1},
            "safety_contract": {"status": "failed"},
            "violations": ["create_request execution_enabled must be false"],
        },
        create_readiness_matrix_artifact={
            "workflow": "create_readiness_matrix",
            "ok": True,
            "status": "not_ready",
            "ready_for_live_execute": False,
            "blocking_reasons": [],
        },
        create_live_execute_phase_gate_artifact={
            "workflow": "create_live_execute_phase_gate",
            "ok": True,
            "status": "blocked",
            "live_execute_development_allowed": False,
            "live_execute_allowed": False,
            "blocking_reasons": [],
        },
        create_adapter_review_pack_artifact={
            "workflow": "create_adapter_review_pack",
            "ok": True,
            "status": "needs_review",
            "required_user_input_now": False,
            "summary": {},
            "review_contract": {"safe_to_review": True},
        },
    )

    assert result["ok"] is False
    assert result["overall_status"] == "invalid_chain_artifacts"
    assert result["summary"]["unsafe_artifact_count"] == 1
    assert "create_request execution_enabled must be false" in result["violations"]
    assert result["actions"] == []


def test_run_create_chain_final_report_request_writes_artifact(tmp_path: Path):
    result = run_create_chain_final_report_request(
        {
            "create_chain_final_report": {
                "create_chain_index_artifact": {
                    "workflow": "create_chain_index",
                    "ok": True,
                    "status": "indexed",
                    "summary": {"artifact_count": 16, "missing_artifact_count": 0, "unsafe_artifact_count": 0},
                    "safety_contract": {"status": "passed"},
                    "violations": [],
                },
                "create_readiness_matrix_artifact": {
                    "workflow": "create_readiness_matrix",
                    "ok": True,
                    "status": "not_ready",
                    "ready_for_live_execute": False,
                    "blocking_reasons": [],
                },
                "create_live_execute_phase_gate_artifact": {
                    "workflow": "create_live_execute_phase_gate",
                    "ok": True,
                    "status": "blocked",
                    "live_execute_development_allowed": False,
                    "live_execute_allowed": False,
                    "blocking_reasons": ["current phase is phase1"],
                },
                "create_adapter_review_pack_artifact": {
                    "workflow": "create_adapter_review_pack",
                    "ok": True,
                    "status": "needs_review",
                    "required_user_input_now": False,
                    "summary": {},
                    "review_contract": {"safe_to_review": True},
                },
            }
        },
        runs_dir=tmp_path / "runs",
    )

    artifact = json.loads(Path(result["artifact_path"]).read_text(encoding="utf-8"))
    assert result["workflow"] == "create_chain_final_report"
    assert artifact["workflow"] == "create_chain_final_report"
    assert artifact["actions"] == []


def test_create_chain_final_report_cli_uses_latest_artifacts(tmp_path: Path, capsys):
    db_path = tmp_path / "roibang.sqlite3"
    runtime_path = _runtime_config(tmp_path, db_path)
    runs_dir = tmp_path / "runs"
    artifacts = {
        "create_chain_index": {
            "workflow": "create_chain_index",
            "ok": True,
            "status": "indexed",
            "summary": {"artifact_count": 16, "missing_artifact_count": 0, "unsafe_artifact_count": 0},
            "safety_contract": {"status": "passed"},
            "violations": [],
        },
        "create_readiness_matrix": {
            "workflow": "create_readiness_matrix",
            "ok": True,
            "status": "not_ready",
            "ready_for_live_execute": False,
            "blocking_reasons": ["provider field map must be verified before live execute"],
        },
        "create_live_execute_phase_gate": {
            "workflow": "create_live_execute_phase_gate",
            "ok": True,
            "status": "blocked",
            "live_execute_development_allowed": False,
            "live_execute_allowed": False,
            "blocking_reasons": ["current phase is phase1"],
        },
        "create_adapter_review_pack": {
            "workflow": "create_adapter_review_pack",
            "ok": True,
            "status": "needs_review",
            "required_user_input_now": False,
            "summary": {},
            "review_contract": {"safe_to_review": True},
        },
    }
    for workflow, payload in artifacts.items():
        path = runs_dir / workflow / "20260508T000000Z.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    module = _load_script("run_create_chain_final_report")

    exit_code = module.run_from_args(["--config", str(runtime_path)])

    output = json.loads(capsys.readouterr().out)
    artifact = json.loads(Path(output["artifact_path"]).read_text(encoding="utf-8"))
    assert exit_code == 0
    assert output["workflow"] == "create_chain_final_report"
    assert output["overall_status"] == "not_ready_for_live_create"
    assert artifact["execution_enabled"] is False
    assert artifact["external_api_calls"] == 0
    assert artifact["actions"] == []


def test_create_phase1_acceptance_checklist_accepts_safe_blocked_chain():
    final_report = {
        "workflow": "create_chain_final_report",
        "ok": True,
        "status": "reported",
        "overall_status": "not_ready_for_live_create",
        "required_user_input_now": False,
        "summary": {
            "artifact_count": 16,
            "missing_artifact_count": 0,
            "unsafe_artifact_count": 0,
            "ready_for_live_execute": False,
            "live_execute_development_allowed": False,
            "live_execute_allowed": False,
            "blocking_reason_count": 4,
        },
        "blocking_reasons": ["current phase is phase1"],
        "violations": [],
    }
    chain_index = {
        "workflow": "create_chain_index",
        "ok": True,
        "status": "indexed",
        "summary": {
            "artifact_count": 16,
            "missing_artifact_count": 0,
            "unsafe_artifact_count": 0,
            "ready_for_live_execute": False,
            "live_execute_allowed": False,
        },
        "safety_contract": {
            "status": "passed",
            "execution_enabled_false": True,
            "external_api_calls_zero": True,
            "actions_empty": True,
            "no_live_execute_allowed": True,
            "no_live_payloads": True,
        },
        "violations": [],
    }

    result = build_create_phase1_acceptance_checklist(
        create_chain_final_report_artifact=final_report,
        create_chain_index_artifact=chain_index,
    )

    assert result["ok"] is True
    assert result["workflow"] == "create_phase1_acceptance_checklist"
    assert result["phase"] == "phase1"
    assert result["execution_enabled"] is False
    assert result["external_api_calls"] == 0
    assert result["status"] == "accepted_with_phase1_blockers"
    assert result["phase1_acceptance_status"] == "accepted"
    assert result["summary"] == {
        "check_count": 6,
        "accepted_check_count": 6,
        "blocking_check_count": 0,
        "phase1_real_create_blocked": True,
        "ready_for_phase2_review": True,
    }
    assert result["checklist"][0] == {
        "check_id": "create_chain_complete",
        "label": "创建链路本地产物完整",
        "accepted": True,
        "evidence": "artifact_count=16, missing_artifact_count=0",
    }
    assert result["accepted_items"] == [
        "创建链路本地产物完整",
        "创建链路安全契约通过",
        "最终报告已生成",
        "真实创建保持阻断",
        "当前不要求人工临场输入",
        "Phase 1 可作为安全前半段收尾",
    ]
    assert result["blocking_items"] == []
    assert result["recommended_next_steps"] == [
        "冻结 Phase 1 创建链路安全基线",
        "由你决定是否进入 Phase 2 字段和模板确认",
        "继续保持真实创建执行脚本硬阻断",
    ]
    assert result["required_user_input_now"] is False
    assert result["actions"] == []


def test_create_phase1_acceptance_checklist_rejects_unsafe_final_report():
    result = build_create_phase1_acceptance_checklist(
        create_chain_final_report_artifact={
            "workflow": "create_chain_final_report",
            "ok": False,
            "status": "reported",
            "overall_status": "unsafe_live_execute_allowed",
            "required_user_input_now": False,
            "summary": {
                "artifact_count": 16,
                "missing_artifact_count": 0,
                "unsafe_artifact_count": 0,
                "live_execute_allowed": True,
            },
            "blocking_reasons": [],
            "violations": ["live execute unexpectedly allowed"],
        },
        create_chain_index_artifact={
            "workflow": "create_chain_index",
            "ok": True,
            "status": "indexed",
            "summary": {"artifact_count": 16, "missing_artifact_count": 0, "unsafe_artifact_count": 0},
            "safety_contract": {"status": "passed"},
            "violations": [],
        },
    )

    assert result["ok"] is False
    assert result["status"] == "blocked"
    assert result["phase1_acceptance_status"] == "blocked"
    assert "最终报告已生成" in result["accepted_items"]
    assert "真实创建保持阻断" in result["blocking_items"]
    assert "live execute unexpectedly allowed" in result["violations"]
    assert result["actions"] == []


def test_run_create_phase1_acceptance_checklist_request_writes_artifact(tmp_path: Path):
    result = run_create_phase1_acceptance_checklist_request(
        {
            "create_phase1_acceptance_checklist": {
                "create_chain_final_report_artifact": {
                    "workflow": "create_chain_final_report",
                    "ok": True,
                    "status": "reported",
                    "overall_status": "not_ready_for_live_create",
                    "required_user_input_now": False,
                    "summary": {
                        "artifact_count": 16,
                        "missing_artifact_count": 0,
                        "unsafe_artifact_count": 0,
                        "live_execute_allowed": False,
                    },
                    "blocking_reasons": ["current phase is phase1"],
                    "violations": [],
                },
                "create_chain_index_artifact": {
                    "workflow": "create_chain_index",
                    "ok": True,
                    "status": "indexed",
                    "summary": {"artifact_count": 16, "missing_artifact_count": 0, "unsafe_artifact_count": 0},
                    "safety_contract": {
                        "status": "passed",
                        "execution_enabled_false": True,
                        "external_api_calls_zero": True,
                        "actions_empty": True,
                        "no_live_execute_allowed": True,
                        "no_live_payloads": True,
                    },
                    "violations": [],
                },
            }
        },
        runs_dir=tmp_path / "runs",
    )

    artifact = json.loads(Path(result["artifact_path"]).read_text(encoding="utf-8"))
    assert result["workflow"] == "create_phase1_acceptance_checklist"
    assert artifact["workflow"] == "create_phase1_acceptance_checklist"
    assert artifact["actions"] == []


def test_create_phase1_acceptance_checklist_cli_uses_latest_artifacts(tmp_path: Path, capsys):
    db_path = tmp_path / "roibang.sqlite3"
    runtime_path = _runtime_config(tmp_path, db_path)
    runs_dir = tmp_path / "runs"
    artifacts = {
        "create_chain_final_report": {
            "workflow": "create_chain_final_report",
            "ok": True,
            "status": "reported",
            "overall_status": "not_ready_for_live_create",
            "required_user_input_now": False,
            "summary": {
                "artifact_count": 16,
                "missing_artifact_count": 0,
                "unsafe_artifact_count": 0,
                "live_execute_allowed": False,
            },
            "blocking_reasons": ["current phase is phase1"],
            "violations": [],
        },
        "create_chain_index": {
            "workflow": "create_chain_index",
            "ok": True,
            "status": "indexed",
            "summary": {"artifact_count": 16, "missing_artifact_count": 0, "unsafe_artifact_count": 0},
            "safety_contract": {
                "status": "passed",
                "execution_enabled_false": True,
                "external_api_calls_zero": True,
                "actions_empty": True,
                "no_live_execute_allowed": True,
                "no_live_payloads": True,
            },
            "violations": [],
        },
    }
    for workflow, payload in artifacts.items():
        path = runs_dir / workflow / "20260508T000000Z.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    module = _load_script("run_create_phase1_acceptance_checklist")

    exit_code = module.run_from_args(["--config", str(runtime_path)])

    output = json.loads(capsys.readouterr().out)
    artifact = json.loads(Path(output["artifact_path"]).read_text(encoding="utf-8"))
    assert exit_code == 0
    assert output["workflow"] == "create_phase1_acceptance_checklist"
    assert output["phase1_acceptance_status"] == "accepted"
    assert artifact["execution_enabled"] is False
    assert artifact["external_api_calls"] == 0
    assert artifact["actions"] == []


def test_create_phase1_baseline_freeze_records_accepted_safe_baseline():
    acceptance = {
        "workflow": "create_phase1_acceptance_checklist",
        "ok": True,
        "status": "accepted_with_phase1_blockers",
        "phase1_acceptance_status": "accepted",
        "summary": {
            "check_count": 6,
            "accepted_check_count": 6,
            "blocking_check_count": 0,
            "phase1_real_create_blocked": True,
            "ready_for_phase2_review": True,
        },
        "accepted_items": ["创建链路本地产物完整", "真实创建保持阻断"],
        "blocking_items": [],
        "violations": [],
        "artifact_path": "/runs/create_phase1_acceptance_checklist/a.json",
    }
    final_report = {
        "workflow": "create_chain_final_report",
        "ok": True,
        "status": "reported",
        "overall_status": "not_ready_for_live_create",
        "summary": {
            "artifact_count": 16,
            "missing_artifact_count": 0,
            "unsafe_artifact_count": 0,
            "live_execute_allowed": False,
        },
        "blocking_reasons": ["current phase is phase1"],
        "artifact_path": "/runs/create_chain_final_report/a.json",
    }
    chain_index = {
        "workflow": "create_chain_index",
        "ok": True,
        "status": "indexed",
        "summary": {"artifact_count": 16, "missing_artifact_count": 0, "unsafe_artifact_count": 0},
        "safety_contract": {
            "status": "passed",
            "execution_enabled_false": True,
            "external_api_calls_zero": True,
            "actions_empty": True,
            "no_live_execute_allowed": True,
            "no_live_payloads": True,
        },
        "artifact_paths": {"create_request": "/runs/create_request/a.json"},
        "artifact_path": "/runs/create_chain_index/a.json",
    }

    result = build_create_phase1_baseline_freeze(
        create_phase1_acceptance_checklist_artifact=acceptance,
        create_chain_final_report_artifact=final_report,
        create_chain_index_artifact=chain_index,
    )

    assert result["ok"] is True
    assert result["workflow"] == "create_phase1_baseline_freeze"
    assert result["phase"] == "phase1"
    assert result["execution_enabled"] is False
    assert result["external_api_calls"] == 0
    assert result["status"] == "frozen"
    assert result["phase1_baseline_status"] == "frozen"
    assert result["baseline_id"] == "phase1-create-safe-baseline-v1"
    assert re.fullmatch(r"[0-9a-f]{64}", result["baseline_digest"]["value"])
    assert result["summary"] == {
        "accepted": True,
        "artifact_count": 16,
        "accepted_check_count": 6,
        "blocking_check_count": 0,
        "real_create_blocked": True,
        "ready_for_phase2_review": True,
    }
    assert result["freeze_contract"] == {
        "status": "frozen",
        "acceptance_required": True,
        "acceptance_status": "accepted",
        "execution_enabled_false": True,
        "external_api_calls_zero": True,
        "actions_empty": True,
        "no_live_execute_allowed": True,
        "no_live_payloads": True,
    }
    assert result["frozen_workflows"] == [
        "create_phase1_acceptance_checklist",
        "create_chain_final_report",
        "create_chain_index",
    ]
    assert result["source_artifact_paths"] == {
        "create_phase1_acceptance_checklist": "/runs/create_phase1_acceptance_checklist/a.json",
        "create_chain_final_report": "/runs/create_chain_final_report/a.json",
        "create_chain_index": "/runs/create_chain_index/a.json",
    }
    assert result["recommended_next_steps"] == [
        "保留 Phase 1 安全基线产物",
        "进入 Phase 2 前先确认字段映射和模板槽位",
        "真实创建执行仍保持关闭",
    ]
    assert result["actions"] == []


def test_create_phase1_baseline_freeze_blocks_unaccepted_checklist():
    result = build_create_phase1_baseline_freeze(
        create_phase1_acceptance_checklist_artifact={
            "workflow": "create_phase1_acceptance_checklist",
            "ok": False,
            "status": "blocked",
            "phase1_acceptance_status": "blocked",
            "summary": {"blocking_check_count": 1, "phase1_real_create_blocked": False},
            "blocking_items": ["真实创建保持阻断"],
            "violations": ["live execute unexpectedly allowed"],
        },
        create_chain_final_report_artifact={
            "workflow": "create_chain_final_report",
            "ok": False,
            "status": "reported",
            "overall_status": "unsafe_live_execute_allowed",
            "summary": {"artifact_count": 16, "live_execute_allowed": True},
        },
        create_chain_index_artifact={
            "workflow": "create_chain_index",
            "ok": True,
            "status": "indexed",
            "summary": {"artifact_count": 16},
            "safety_contract": {"status": "passed"},
        },
    )

    assert result["ok"] is False
    assert result["status"] == "blocked"
    assert result["phase1_baseline_status"] == "blocked"
    assert result["freeze_contract"]["status"] == "blocked"
    assert result["blocking_reasons"] == ["真实创建保持阻断"]
    assert "live execute unexpectedly allowed" in result["violations"]
    assert result["actions"] == []


def test_run_create_phase1_baseline_freeze_request_writes_artifact(tmp_path: Path):
    result = run_create_phase1_baseline_freeze_request(
        {
            "create_phase1_baseline_freeze": {
                "create_phase1_acceptance_checklist_artifact": {
                    "workflow": "create_phase1_acceptance_checklist",
                    "ok": True,
                    "status": "accepted_with_phase1_blockers",
                    "phase1_acceptance_status": "accepted",
                    "summary": {
                        "check_count": 6,
                        "accepted_check_count": 6,
                        "blocking_check_count": 0,
                        "phase1_real_create_blocked": True,
                        "ready_for_phase2_review": True,
                    },
                    "accepted_items": [],
                    "blocking_items": [],
                    "violations": [],
                },
                "create_chain_final_report_artifact": {
                    "workflow": "create_chain_final_report",
                    "ok": True,
                    "status": "reported",
                    "overall_status": "not_ready_for_live_create",
                    "summary": {"artifact_count": 16, "live_execute_allowed": False},
                    "blocking_reasons": ["current phase is phase1"],
                },
                "create_chain_index_artifact": {
                    "workflow": "create_chain_index",
                    "ok": True,
                    "status": "indexed",
                    "summary": {"artifact_count": 16},
                    "safety_contract": {
                        "status": "passed",
                        "execution_enabled_false": True,
                        "external_api_calls_zero": True,
                        "actions_empty": True,
                        "no_live_execute_allowed": True,
                        "no_live_payloads": True,
                    },
                },
            }
        },
        runs_dir=tmp_path / "runs",
    )

    artifact = json.loads(Path(result["artifact_path"]).read_text(encoding="utf-8"))
    assert result["workflow"] == "create_phase1_baseline_freeze"
    assert artifact["workflow"] == "create_phase1_baseline_freeze"
    assert artifact["actions"] == []


def test_create_phase1_baseline_freeze_cli_uses_latest_artifacts(tmp_path: Path, capsys):
    db_path = tmp_path / "roibang.sqlite3"
    runtime_path = _runtime_config(tmp_path, db_path)
    runs_dir = tmp_path / "runs"
    artifacts = {
        "create_phase1_acceptance_checklist": {
            "workflow": "create_phase1_acceptance_checklist",
            "ok": True,
            "status": "accepted_with_phase1_blockers",
            "phase1_acceptance_status": "accepted",
            "summary": {
                "check_count": 6,
                "accepted_check_count": 6,
                "blocking_check_count": 0,
                "phase1_real_create_blocked": True,
                "ready_for_phase2_review": True,
            },
            "accepted_items": [],
            "blocking_items": [],
            "violations": [],
        },
        "create_chain_final_report": {
            "workflow": "create_chain_final_report",
            "ok": True,
            "status": "reported",
            "overall_status": "not_ready_for_live_create",
            "summary": {"artifact_count": 16, "live_execute_allowed": False},
            "blocking_reasons": ["current phase is phase1"],
        },
        "create_chain_index": {
            "workflow": "create_chain_index",
            "ok": True,
            "status": "indexed",
            "summary": {"artifact_count": 16},
            "safety_contract": {
                "status": "passed",
                "execution_enabled_false": True,
                "external_api_calls_zero": True,
                "actions_empty": True,
                "no_live_execute_allowed": True,
                "no_live_payloads": True,
            },
        },
    }
    for workflow, payload in artifacts.items():
        path = runs_dir / workflow / "20260509T000000Z.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    module = _load_script("run_create_phase1_baseline_freeze")

    exit_code = module.run_from_args(["--config", str(runtime_path)])

    output = json.loads(capsys.readouterr().out)
    artifact = json.loads(Path(output["artifact_path"]).read_text(encoding="utf-8"))
    assert exit_code == 0
    assert output["workflow"] == "create_phase1_baseline_freeze"
    assert output["phase1_baseline_status"] == "frozen"
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


def test_provider_field_map_check_lineage_propagates_after_dry_run(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    _seed_create_db(db_path)
    plan = build_create_strategy_plan(request=_create_request()["create_request"], db_path=db_path, policy={})
    preflight = build_create_preflight(create_strategy_plan_artifact=plan, db_path=db_path, policy={})
    policy = {"provider_field_map_path": "configs/provider-field-maps/oceanengine.create.phase1.example.json"}
    field_map_check = build_create_provider_field_map_check(policy=policy)
    dry_run = build_create_dry_run(
        create_strategy_plan_artifact=plan,
        create_preflight_artifact=preflight,
        create_provider_field_map_check_artifact=field_map_check,
        policy=policy,
    )
    approval = build_create_approval(create_dry_run_artifact=dry_run, policy={"auto_approve_phase1": True})
    snapshot = build_create_plan_snapshot(
        create_strategy_plan_artifact=plan,
        create_preflight_artifact=preflight,
        create_dry_run_artifact=dry_run,
        create_approval_artifact=approval,
    )
    execute = build_create_execute(create_approval_artifact=approval, policy={})

    expected = dry_run["lineage"]["create_provider_field_map_check"]
    assert approval["lineage"]["create_provider_field_map_check"] == expected
    assert snapshot["lineage"]["create_provider_field_map_check"] == expected
    assert execute["lineage"]["create_provider_field_map_check"] == expected
    assert approval["provider_field_map_digest"] == dry_run["provider_field_map_digest"]
    assert snapshot["provider_field_map_digest"] == dry_run["provider_field_map_digest"]
    assert execute["provider_field_map_digest"] == dry_run["provider_field_map_digest"]


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


def test_create_approval_records_automatic_policy_review_but_disallows_execute_in_phase1(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    _seed_create_db(db_path)
    plan = build_create_strategy_plan(request=_create_request()["create_request"], db_path=db_path, policy={})
    preflight = build_create_preflight(create_strategy_plan_artifact=plan, db_path=db_path, policy={})
    dry_run = build_create_dry_run(
        create_strategy_plan_artifact=plan,
        create_preflight_artifact=preflight,
        policy={},
    )

    result = build_create_approval(
        create_dry_run_artifact=dry_run,
        policy={"auto_approve_phase1": True, "max_projects_per_approval": 5, "max_units_per_approval": 10},
    )

    assert result["ok"] is True
    assert result["workflow"] == "create_approval"
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
        "plan_id": "create_plan_create_req_20260508_yzt_wx_7r",
        "request_id": "create_req_20260508_yzt_wx_7r",
        "target_date": "2026-05-08",
        "project_count": 1,
        "unit_count": 2,
        "material_count": 4,
        "violation_count": 0,
    }
    assert result["lineage"]["create_dry_run"]["plan_id"] == "create_plan_create_req_20260508_yzt_wx_7r"
    assert result["lineage"]["create_strategy_plan"]["plan_id"] == "create_plan_create_req_20260508_yzt_wx_7r"
    assert result["candidate_task_digest"]["algorithm"] == "sha256"
    assert re.fullmatch(r"[0-9a-f]{64}", result["candidate_task_digest"]["value"])
    assert result["candidate_task_digest"]["candidate_task_count"] == 1
    assert result["provider_field_map_digest"] == dry_run["provider_field_map_digest"]
    assert result["provider_payload_draft_digest"] == dry_run["provider_payload_draft_digest"]
    assert result["provider_readiness_contract"] == dry_run["provider_readiness_contract"]


def test_create_approval_blocks_failed_dry_run_and_policy_limit(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    _seed_create_db(db_path)
    plan = build_create_strategy_plan(request=_create_request()["create_request"], db_path=db_path, policy={})
    preflight = build_create_preflight(create_strategy_plan_artifact=plan, db_path=db_path, policy={})
    dry_run = build_create_dry_run(
        create_strategy_plan_artifact=plan,
        create_preflight_artifact=preflight,
        policy={"max_units_per_dry_run": 1},
    )

    result = build_create_approval(
        create_dry_run_artifact=dry_run,
        policy={"max_units_per_approval": 1},
    )

    assert result["ok"] is False
    assert result["status"] == "blocked"
    assert result["policy_decision"] == "reject"
    assert result["execute_allowed"] is False
    assert "create dry-run must be simulated before approval" in result["violations"]
    assert "dry-run unit count exceeds policy limit" in result["violations"]


def test_create_execute_plan_carries_provider_id_ledger_gate(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    _seed_create_db(db_path)
    plan = build_create_strategy_plan(request=_create_request()["create_request"], db_path=db_path, policy={})
    preflight = build_create_preflight(create_strategy_plan_artifact=plan, db_path=db_path, policy={})
    dry_run = build_create_dry_run(create_strategy_plan_artifact=plan, create_preflight_artifact=preflight, policy={})
    approval = build_create_approval(create_dry_run_artifact=dry_run, policy={"auto_approve_phase1": True})

    result = build_create_execute(create_approval_artifact=approval, policy={})

    assert dry_run["provider_id_ledger_requirements"]["status"] == "planned"
    assert dry_run["provider_id_ledger_requirements"]["produced_by_create_project"] == [
        {"entity_type": "project", "local_key": "target-1-p001", "provider_id_source": "create_project_response"}
    ]
    assert dry_run["provider_id_ledger_requirements"]["produced_by_create_unit"] == [
        {
            "entity_type": "promotion",
            "local_key": "target-1-p001-u01",
            "parent_local_key": "target-1-p001",
            "provider_id_source": "create_unit_response",
        },
        {
            "entity_type": "promotion",
            "local_key": "target-1-p001-u02",
            "parent_local_key": "target-1-p001",
            "provider_id_source": "create_unit_response",
        },
    ]
    assert dry_run["provider_id_ledger_requirements"]["required_before_create_unit"] == [
        {"field": "project_id", "entity_type": "project", "local_key": "target-1-p001", "placeholder": "<lookup:target-1-p001>"}
    ]
    assert dry_run["provider_id_ledger_requirements"]["required_before_bind_material"] == [
        {"field": "project_id", "entity_type": "project", "local_key": "target-1-p001", "placeholder": "<lookup:target-1-p001>"},
        {
            "field": "promotion_id",
            "entity_type": "promotion",
            "local_key": "target-1-p001-u01",
            "placeholder": "<lookup:target-1-p001-u01>",
        },
        {
            "field": "promotion_id",
            "entity_type": "promotion",
            "local_key": "target-1-p001-u02",
            "placeholder": "<lookup:target-1-p001-u02>",
        },
    ]
    assert approval["provider_id_ledger_requirements"] == dry_run["provider_id_ledger_requirements"]
    assert result["provider_id_ledger_gate"] == {
        "status": "hard_blocked_phase1",
        "ready_for_live_execute": False,
        "required_before_create_unit_count": 1,
        "required_before_bind_material_count": 3,
        "execution_enabled": False,
        "external_api_calls": 0,
        "actions": [],
    }
    assert result["execution_plan"]["provider_id_ledger_gate"] == result["provider_id_ledger_gate"]
    assert result["execution_plan"]["steps"][1]["requires_provider_id_ledger"] == {
        "status": "required",
        "required_count": 1,
    }
    assert result["execution_plan"]["steps"][2]["requires_provider_id_ledger"] == {
        "status": "required",
        "required_count": 3,
    }


def test_create_execute_resolves_provider_payload_drafts_from_id_ledger(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    _seed_create_db(db_path)
    plan = build_create_strategy_plan(request=_create_request()["create_request"], db_path=db_path, policy={})
    preflight = build_create_preflight(create_strategy_plan_artifact=plan, db_path=db_path, policy={})
    dry_run = build_create_dry_run(create_strategy_plan_artifact=plan, create_preflight_artifact=preflight, policy={})
    approval = build_create_approval(create_dry_run_artifact=dry_run, policy={"auto_approve_phase1": True})
    record_create_provider_id(
        db_path=db_path,
        entity_type="project",
        local_key="target-1-p001",
        provider_id="project_123",
        source_workflow="unit_test",
    )
    record_create_provider_id(
        db_path=db_path,
        entity_type="promotion",
        local_key="target-1-p001-u01",
        provider_id="promotion_456",
        source_workflow="unit_test",
    )
    record_create_provider_id(
        db_path=db_path,
        entity_type="promotion",
        local_key="target-1-p001-u02",
        provider_id="promotion_789",
        source_workflow="unit_test",
    )

    result = build_create_execute(create_approval_artifact=approval, policy={}, db_path=db_path)

    assert approval["provider_payload_drafts"] == dry_run["provider_payload_drafts"]
    assert result["provider_payload_resolution"] == {
        "status": "resolved",
        "draft_count": 7,
        "lookup_count": 10,
        "resolved_count": 10,
        "unresolved_count": 0,
        "unresolved_placeholders": [],
        "execution_enabled": False,
        "external_api_calls": 0,
        "actions": [],
    }
    assert result["resolved_payload_contract"] == {
        "status": "passed",
        "checked_draft_count": 7,
        "unresolved_lookup_count": 0,
        "executable_draft_count": 0,
        "live_payload_count": 0,
        "violation_count": 0,
        "violations": [],
        "execution_enabled": False,
        "external_api_calls": 0,
        "actions": [],
    }
    assert result["execute_review_summary"] == {
        "status": "ready_for_manual_review",
        "plain_language": "真实创建仍然硬阻断；7 个平台 payload 草稿已完成本地 ID 解析，可人工复核字段，但不会执行真实创建。",
        "checks": {
            "execute_hard_blocked": True,
            "external_api_calls_zero": True,
            "provider_payload_resolution": "resolved",
            "resolved_payload_contract": "passed",
            "provider_id_ledger_gate": "hard_blocked_phase1",
        },
        "counts": {
            "project_count": 1,
            "unit_count": 2,
            "material_count": 4,
            "resolved_draft_count": 7,
            "unresolved_lookup_count": 0,
        },
        "human_next_steps": [
            "人工复核 resolved_provider_payload_drafts 的账户、项目ID、单元ID、预算和素材。",
            "继续保持 create_execute 硬阻断，等待单独批准的真实执行阶段。",
        ],
        "execution_enabled": False,
        "external_api_calls": 0,
        "actions": [],
    }
    assert result["execution_plan"]["live_api_payloads"] == []
    assert result["resolved_provider_payload_drafts"]
    assert {draft["executable"] for draft in result["resolved_provider_payload_drafts"]} == {False}
    unit_draft = next(draft for draft in result["resolved_provider_payload_drafts"] if draft["operation"] == "create_unit")
    assert unit_draft["payload"]["project_id"] == "project_123"
    material_drafts = [
        draft for draft in result["resolved_provider_payload_drafts"] if draft["operation"] == "bind_material"
    ]
    assert material_drafts[0]["payload"]["project_id"] == "project_123"
    assert material_drafts[0]["payload"]["promotion_id"] == "promotion_456"
    assert material_drafts[2]["payload"]["promotion_id"] == "promotion_789"
    assert result["execution_enabled"] is False
    assert result["external_api_calls"] == 0
    assert result["actions"] == []


def test_create_execute_resolved_payload_contract_blocks_unresolved_lookups(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    _seed_create_db(db_path)
    plan = build_create_strategy_plan(request=_create_request()["create_request"], db_path=db_path, policy={})
    preflight = build_create_preflight(create_strategy_plan_artifact=plan, db_path=db_path, policy={})
    dry_run = build_create_dry_run(create_strategy_plan_artifact=plan, create_preflight_artifact=preflight, policy={})
    approval = build_create_approval(create_dry_run_artifact=dry_run, policy={"auto_approve_phase1": True})

    result = build_create_execute(create_approval_artifact=approval, policy={}, db_path=db_path)

    assert result["provider_payload_resolution"]["status"] == "blocked"
    assert result["resolved_payload_contract"] == {
        "status": "blocked",
        "checked_draft_count": 7,
        "unresolved_lookup_count": 10,
        "executable_draft_count": 0,
        "live_payload_count": 0,
        "violation_count": 1,
        "violations": ["resolved provider payload drafts must not contain lookup placeholders"],
        "execution_enabled": False,
        "external_api_calls": 0,
        "actions": [],
    }
    assert result["execute_review_summary"] == {
        "status": "blocked_missing_provider_ids",
        "plain_language": "真实创建仍然硬阻断；已解析草稿仍有 10 个 lookup 占位未解析，需要先登记平台返回的 project_id/promotion_id。",
        "checks": {
            "execute_hard_blocked": True,
            "external_api_calls_zero": True,
            "provider_payload_resolution": "blocked",
            "resolved_payload_contract": "blocked",
            "provider_id_ledger_gate": "hard_blocked_phase1",
        },
        "counts": {
            "project_count": 1,
            "unit_count": 2,
            "material_count": 4,
            "resolved_draft_count": 7,
            "unresolved_lookup_count": 10,
        },
        "human_next_steps": [
            "先确认项目和单元真实创建返回的 project_id/promotion_id 已写入本地 ID 台账。",
            "重新运行 create_execute，只复核 resolved_payload_contract，不执行真实创建。",
        ],
        "execution_enabled": False,
        "external_api_calls": 0,
        "actions": [],
    }
    assert result["execution_plan"]["live_api_payloads"] == []
    assert result["execution_enabled"] is False
    assert result["external_api_calls"] == 0
    assert result["actions"] == []


def test_create_execute_is_hard_blocked_in_phase1_even_after_recorded_approval(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    _seed_create_db(db_path)
    plan = build_create_strategy_plan(request=_create_request()["create_request"], db_path=db_path, policy={})
    preflight = build_create_preflight(create_strategy_plan_artifact=plan, db_path=db_path, policy={})
    dry_run = build_create_dry_run(create_strategy_plan_artifact=plan, create_preflight_artifact=preflight, policy={})
    approval = build_create_approval(create_dry_run_artifact=dry_run, policy={"auto_approve_phase1": True})

    result = build_create_execute(create_approval_artifact=approval, policy={})

    assert result["ok"] is True
    assert result["workflow"] == "create_execute"
    assert result["phase"] == "phase1"
    assert result["execution_enabled"] is False
    assert result["external_api_calls"] == 0
    assert result["status"] == "blocked"
    assert result["reason"] == "phase1_execute_disabled"
    assert result["summary"] == {
        "plan_id": "create_plan_create_req_20260508_yzt_wx_7r",
        "request_id": "create_req_20260508_yzt_wx_7r",
        "target_date": "2026-05-08",
        "project_count": 1,
        "unit_count": 2,
        "material_count": 4,
        "approval_status": "recorded",
        "policy_decision": "would_approve",
        "execute_allowed": False,
    }
    assert result["lineage"]["create_approval"]["plan_id"] == "create_plan_create_req_20260508_yzt_wx_7r"
    assert result["candidate_task_digest"] == approval["candidate_task_digest"]
    assert result["provider_field_map_digest"] == approval["provider_field_map_digest"]
    assert result["provider_payload_draft_digest"] == approval["provider_payload_draft_digest"]
    assert result["provider_readiness_contract"] == approval["provider_readiness_contract"]
    assert result["provider_readiness_contract"]["ready_for_live_execute"] is False
    assert result["violations"] == []
    assert result["approved_for_execute"] is False
    assert result["executed_task_count"] == 0
    assert result["payload_schema"] == result["execution_plan"]["payload_schema"]
    assert result["execution_plan"] == {
        "mode": "phase1_skeleton_only",
        "steps": [
            {
                "step": "create_project",
                "order": 1,
                "planned_count": 1,
                "status": "blocked_in_phase1",
            },
            {
                "step": "create_unit",
                "order": 2,
                "planned_count": 2,
                "status": "blocked_in_phase1",
                "requires_provider_id_ledger": {
                    "status": "required",
                    "required_count": 1,
                },
            },
            {
                "step": "bind_material",
                "order": 3,
                "planned_count": 4,
                "status": "blocked_in_phase1",
                "requires_provider_id_ledger": {
                    "status": "required",
                    "required_count": 3,
                },
            },
        ],
        "failure_policy": {
            "on_project_create_error": "stop",
            "on_unit_create_error": "stop",
            "on_material_bind_error": "stop",
            "retry_enabled": False,
        },
        "payload_schema": {
            "version": "phase1.create_payload.v1",
            "mode": "schema_only",
            "execution_enabled": False,
            "external_api_enabled": False,
            "live_payload_generation_enabled": False,
            "endpoints": {
                "create_project": "",
                "create_unit": "",
                "bind_material": "",
            },
            "required_fields": {
                "create_project": [
                    "advertiser_id",
                    "project_name",
                    "project_type",
                    "daily_budget",
                    "field_defaults",
                ],
                "create_unit": [
                    "advertiser_id",
                    "project_key",
                    "project_id",
                    "unit_key",
                    "promotion_name",
                    "field_defaults",
                ],
                "bind_material": [
                    "advertiser_id",
                    "project_key",
                    "project_id",
                    "unit_key",
                    "promotion_id",
                    "material_id",
                    "source_video_id",
                ],
            },
            "field_sources": {
                "create_project": "create_strategy_plan.strategy.projects[]",
                "create_unit": "create_strategy_plan.strategy.projects[].units[]",
                "bind_material": "create_strategy_plan.strategy.projects[].units[].materials[]",
            },
        },
        "provider_id_ledger_gate": {
            "status": "hard_blocked_phase1",
            "ready_for_live_execute": False,
            "required_before_create_unit_count": 1,
            "required_before_bind_material_count": 3,
            "execution_enabled": False,
            "external_api_calls": 0,
            "actions": [],
        },
        "live_api_payloads": [],
    }
    assert result["audit"] == {
        "enabled": False,
        "format": "jsonl",
        "path": "data/runs/create_execute/audit",
        "redact_fields": ["Access-Token", "Cookie", "x-csrftoken"],
    }
    assert result["actions"] == []


def test_create_execute_rejects_dangerous_phase1_policy_switches(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    _seed_create_db(db_path)
    plan = build_create_strategy_plan(request=_create_request()["create_request"], db_path=db_path, policy={})
    preflight = build_create_preflight(create_strategy_plan_artifact=plan, db_path=db_path, policy={})
    dry_run = build_create_dry_run(create_strategy_plan_artifact=plan, create_preflight_artifact=preflight, policy={})
    approval = build_create_approval(create_dry_run_artifact=dry_run, policy={"auto_approve_phase1": True})

    result = build_create_execute(
        create_approval_artifact=approval,
        policy={"allow_execute_phase1": True, "allow_live_api_payloads": True},
    )

    assert result["ok"] is False
    assert result["status"] == "blocked"
    assert result["execution_enabled"] is False
    assert result["external_api_calls"] == 0
    assert "create execute policy allow_execute_phase1 must be false in phase1" in result["violations"]
    assert "create execute policy allow_live_api_payloads must be false in phase1" in result["violations"]
    assert result["execution_plan"]["live_api_payloads"] == []
    assert result["actions"] == []


def test_create_execute_rejects_dangerous_live_api_template(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    _seed_create_db(db_path)
    plan = build_create_strategy_plan(request=_create_request()["create_request"], db_path=db_path, policy={})
    preflight = build_create_preflight(create_strategy_plan_artifact=plan, db_path=db_path, policy={})
    dry_run = build_create_dry_run(create_strategy_plan_artifact=plan, create_preflight_artifact=preflight, policy={})
    approval = build_create_approval(create_dry_run_artifact=dry_run, policy={"auto_approve_phase1": True})

    result = build_create_execute(
        create_approval_artifact=approval,
        policy={
            "live_api": {
                "enabled": True,
                "allow_live_api_payloads": True,
            },
            "execution": {
                "status": "execute",
                "execution_enabled": True,
                "external_api_enabled": True,
            },
            "payload_schema": {
                "mode": "live_payloads",
                "live_payload_generation_enabled": True,
            },
        },
    )

    assert result["ok"] is False
    assert "create execute live_api.enabled must be false in phase1" in result["violations"]
    assert "create execute live_api.allow_live_api_payloads must be false in phase1" in result["violations"]
    assert "create execute request execution.status must not be execute in phase1" in result["violations"]
    assert "create execute request execution_enabled must be false in phase1" in result["violations"]
    assert "create execute request external_api_enabled must be false in phase1" in result["violations"]
    assert "create execute payload_schema.live_payload_generation_enabled must be false in phase1" in result["violations"]
    assert result["executed_task_count"] == 0
    assert result["actions"] == []


def test_run_create_approval_and_execute_request_write_artifacts(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    _seed_create_db(db_path)
    plan = build_create_strategy_plan(request=_create_request()["create_request"], db_path=db_path, policy={})
    preflight = build_create_preflight(create_strategy_plan_artifact=plan, db_path=db_path, policy={})
    dry_run = build_create_dry_run(create_strategy_plan_artifact=plan, create_preflight_artifact=preflight, policy={})

    approval = run_create_approval_request(
        {"create_approval": {"create_dry_run_artifact": dry_run, "policy": {"auto_approve_phase1": True}}},
        runs_dir=tmp_path / "runs",
    )
    execute = run_create_execute_request(
        {"create_execute": {"create_approval_artifact": approval}},
        runs_dir=tmp_path / "runs",
    )

    assert Path(approval["artifact_path"]).exists()
    assert Path(execute["artifact_path"]).exists()
    assert approval["execute_allowed"] is False
    assert execute["executed_task_count"] == 0
    assert execute["provider_readiness_contract"]["ready_for_live_execute"] is False


def test_create_execute_cli_accepts_disabled_live_template_and_still_blocks(tmp_path: Path, capsys):
    db_path = tmp_path / "roibang.sqlite3"
    _seed_create_db(db_path)
    runs_dir = tmp_path / "runs"
    runtime_path = _runtime_config(tmp_path, db_path)
    plan = build_create_strategy_plan(request=_create_request()["create_request"], db_path=db_path, policy={})
    preflight = build_create_preflight(create_strategy_plan_artifact=plan, db_path=db_path, policy={})
    dry_run = build_create_dry_run(create_strategy_plan_artifact=plan, create_preflight_artifact=preflight, policy={})
    run_create_approval_request(
        {"create_approval": {"create_dry_run_artifact": dry_run, "policy": {"auto_approve_phase1": True}}},
        runs_dir=runs_dir,
    )
    module = _load_script("run_create_execute")

    exit_code = module.run_from_args(
        [
            "--config",
            str(runtime_path),
            "--request",
            "configs/create-execute.openapi-http.disabled.example.json",
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


def test_create_plan_snapshot_summarizes_plan_for_review(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    _seed_create_db(db_path)
    plan = build_create_strategy_plan(request=_create_request()["create_request"], db_path=db_path, policy={})
    preflight = build_create_preflight(create_strategy_plan_artifact=plan, db_path=db_path, policy={})
    dry_run = build_create_dry_run(create_strategy_plan_artifact=plan, create_preflight_artifact=preflight, policy={})
    approval = build_create_approval(create_dry_run_artifact=dry_run, policy={"auto_approve_phase1": True})

    result = build_create_plan_snapshot(
        create_strategy_plan_artifact=plan,
        create_preflight_artifact=preflight,
        create_dry_run_artifact=dry_run,
        create_approval_artifact=approval,
    )

    assert result["ok"] is True
    assert result["workflow"] == "create_plan_snapshot"
    assert result["phase"] == "phase1"
    assert result["execution_enabled"] is False
    assert result["external_api_calls"] == 0
    assert result["candidate_task_digest"] == approval["candidate_task_digest"]
    assert result["payload_contract"] == dry_run["payload_contract"]
    assert result["payload_draft_contract"] == dry_run["payload_draft_contract"]
    assert result["provider_adapter_contract"] == dry_run["provider_adapter_contract"]
    assert result["provider_field_map_contract"] == dry_run["provider_field_map_contract"]
    assert result["provider_field_map_digest"] == dry_run["provider_field_map_digest"]
    assert result["provider_payload_draft_digest"] == approval["provider_payload_draft_digest"]
    assert result["provider_readiness_contract"] == dry_run["provider_readiness_contract"]
    assert result["idempotency_contract"] == dry_run["idempotency_contract"]
    assert result["idempotency_ledger"] == dry_run["idempotency_ledger"]
    assert result["summary"] == {
        "plan_id": "create_plan_create_req_20260508_yzt_wx_7r",
        "request_id": "create_req_20260508_yzt_wx_7r",
        "target_date": "2026-05-08",
        "account_count": 1,
        "project_count": 1,
        "unit_count": 2,
        "material_count": 4,
        "preflight_status": "passed",
        "dry_run_status": "simulated",
        "approval_status": "recorded",
        "policy_decision": "would_approve",
        "violation_count": 0,
    }
    assert result["accounts"] == [
        {
            "advertiser_id": "target-1",
            "project_count": 1,
            "unit_count": 2,
            "material_count": 4,
            "material_ids": ["m-extra", "m-high", "m-low", "m-mid"],
            "projects": [
                {
                    "project_key": "target-1-p001",
                    "project_name": "0508_郭靖_勇者突进_微小每付7R通投_B80C4C430_01",
                    "idempotency_key": dry_run["candidate_tasks"][0]["idempotency_key"],
                    "unit_count": 2,
                    "material_ids": ["m-extra", "m-high", "m-low", "m-mid"],
                }
            ],
        }
    ]
    assert result["lineage"]["create_strategy_plan"]["plan_id"] == "create_plan_create_req_20260508_yzt_wx_7r"
    assert result["lineage"]["create_preflight"]["plan_id"] == "create_plan_create_req_20260508_yzt_wx_7r"
    assert result["lineage"]["create_dry_run"]["plan_id"] == "create_plan_create_req_20260508_yzt_wx_7r"
    assert result["lineage"]["create_approval"]["plan_id"] == "create_plan_create_req_20260508_yzt_wx_7r"
    assert result["review_notes"] == [
        "phase1 snapshot is review-only",
        "no live API payloads or actions are included",
    ]
    assert result["actions"] == []


def test_run_create_plan_snapshot_request_writes_artifact(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    _seed_create_db(db_path)
    plan = build_create_strategy_plan(request=_create_request()["create_request"], db_path=db_path, policy={})
    preflight = build_create_preflight(create_strategy_plan_artifact=plan, db_path=db_path, policy={})
    dry_run = build_create_dry_run(create_strategy_plan_artifact=plan, create_preflight_artifact=preflight, policy={})
    approval = build_create_approval(create_dry_run_artifact=dry_run, policy={"auto_approve_phase1": True})

    result = run_create_plan_snapshot_request(
        {
            "create_plan_snapshot": {
                "create_strategy_plan_artifact": plan,
                "create_preflight_artifact": preflight,
                "create_dry_run_artifact": dry_run,
                "create_approval_artifact": approval,
            }
        },
        runs_dir=tmp_path / "runs",
    )

    assert Path(result["artifact_path"]).exists()
    assert result["summary"]["project_count"] == 1


def test_create_chain_replay_accepts_consistent_phase1_artifact_chain(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    _seed_create_db(db_path)
    request = run_create_request(_create_request(), db_path=db_path, runs_dir=tmp_path / "runs")
    plan = run_create_strategy_plan_request(
        request,
        db_path=db_path,
        runs_dir=tmp_path / "runs",
        policy={},
        create_request_artifact_path=request["artifact_path"],
    )
    preflight = build_create_preflight(create_strategy_plan_artifact=plan, db_path=db_path, policy={})
    dry_run = build_create_dry_run(create_strategy_plan_artifact=plan, create_preflight_artifact=preflight, policy={})
    approval = build_create_approval(create_dry_run_artifact=dry_run, policy={"auto_approve_phase1": True})
    snapshot = build_create_plan_snapshot(
        create_strategy_plan_artifact=plan,
        create_preflight_artifact=preflight,
        create_dry_run_artifact=dry_run,
        create_approval_artifact=approval,
    )
    execute = build_create_execute(create_approval_artifact=approval, policy={})

    result = build_create_chain_replay(
        create_request_artifact=request,
        create_strategy_plan_artifact=plan,
        create_preflight_artifact=preflight,
        create_dry_run_artifact=dry_run,
        create_approval_artifact=approval,
        create_plan_snapshot_artifact=snapshot,
        create_execute_artifact=execute,
    )

    assert result["ok"] is True
    assert result["workflow"] == "create_chain_replay"
    assert result["phase"] == "phase1"
    assert result["execution_enabled"] is False
    assert result["external_api_calls"] == 0
    assert result["status"] == "passed"
    assert result["summary"] == {
        "plan_id": "create_plan_create_req_20260508_yzt_wx_7r",
        "request_id": "create_req_20260508_yzt_wx_7r",
        "target_date": "2026-05-08",
        "checked_workflow_count": 7,
        "violation_count": 0,
    }
    assert result["lineage"]["create_request"]["workflow"] == "create_request"
    assert result["lineage"]["create_execute"]["workflow"] == "create_execute"
    assert result["digest_consistency"]["candidate_task_digest"]["status"] == "passed"
    assert result["digest_consistency"]["provider_field_map_digest"]["status"] == "passed"
    assert result["digest_consistency"]["provider_payload_draft_digest"]["status"] == "passed"
    assert result["phase1_safety_contract"] == {
        "status": "passed",
        "execution_enabled_false": True,
        "external_api_calls_zero": True,
        "actions_empty": True,
    }
    assert result["violations"] == []
    assert result["actions"] == []


def test_create_chain_replay_blocks_mismatched_provider_payload_draft_digest(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    _seed_create_db(db_path)
    request = run_create_request(_create_request(), db_path=db_path, runs_dir=tmp_path / "runs")
    plan = run_create_strategy_plan_request(
        request,
        db_path=db_path,
        runs_dir=tmp_path / "runs",
        policy={},
        create_request_artifact_path=request["artifact_path"],
    )
    preflight = build_create_preflight(create_strategy_plan_artifact=plan, db_path=db_path, policy={})
    dry_run = build_create_dry_run(create_strategy_plan_artifact=plan, create_preflight_artifact=preflight, policy={})
    approval = build_create_approval(create_dry_run_artifact=dry_run, policy={"auto_approve_phase1": True})
    snapshot = build_create_plan_snapshot(
        create_strategy_plan_artifact=plan,
        create_preflight_artifact=preflight,
        create_dry_run_artifact=dry_run,
        create_approval_artifact=approval,
    )
    execute = build_create_execute(create_approval_artifact=approval, policy={})
    execute["provider_payload_draft_digest"] = {**execute["provider_payload_draft_digest"], "value": "0" * 64}

    result = build_create_chain_replay(
        create_request_artifact=request,
        create_strategy_plan_artifact=plan,
        create_preflight_artifact=preflight,
        create_dry_run_artifact=dry_run,
        create_approval_artifact=approval,
        create_plan_snapshot_artifact=snapshot,
        create_execute_artifact=execute,
    )

    assert result["ok"] is False
    assert result["status"] == "blocked"
    assert result["digest_consistency"]["provider_payload_draft_digest"]["status"] == "failed"
    assert "provider payload draft digest must match across dry-run, approval, snapshot, and execute" in result["violations"]
    assert result["actions"] == []


def test_create_chain_replay_blocks_wrong_artifact_workflow_identity(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    _seed_create_db(db_path)
    request = run_create_request(_create_request(), db_path=db_path, runs_dir=tmp_path / "runs")
    plan = run_create_strategy_plan_request(
        request,
        db_path=db_path,
        runs_dir=tmp_path / "runs",
        policy={},
        create_request_artifact_path=request["artifact_path"],
    )
    preflight = build_create_preflight(create_strategy_plan_artifact=plan, db_path=db_path, policy={})
    dry_run = build_create_dry_run(create_strategy_plan_artifact=plan, create_preflight_artifact=preflight, policy={})
    approval = build_create_approval(create_dry_run_artifact=dry_run, policy={"auto_approve_phase1": True})
    snapshot = build_create_plan_snapshot(
        create_strategy_plan_artifact=plan,
        create_preflight_artifact=preflight,
        create_dry_run_artifact=dry_run,
        create_approval_artifact=approval,
    )
    execute = build_create_execute(create_approval_artifact=approval, policy={})
    execute["workflow"] = "create_plan_snapshot"

    result = build_create_chain_replay(
        create_request_artifact=request,
        create_strategy_plan_artifact=plan,
        create_preflight_artifact=preflight,
        create_dry_run_artifact=dry_run,
        create_approval_artifact=approval,
        create_plan_snapshot_artifact=snapshot,
        create_execute_artifact=execute,
    )

    assert result["ok"] is False
    assert result["status"] == "blocked"
    assert result["artifact_identity_contract"]["status"] == "failed"
    assert "create_execute artifact workflow must be create_execute" in result["violations"]
    assert result["actions"] == []


def test_run_create_chain_replay_request_writes_artifact(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    _seed_create_db(db_path)
    request = run_create_request(_create_request(), db_path=db_path, runs_dir=tmp_path / "runs")
    plan = run_create_strategy_plan_request(
        request,
        db_path=db_path,
        runs_dir=tmp_path / "runs",
        policy={},
        create_request_artifact_path=request["artifact_path"],
    )
    preflight = build_create_preflight(create_strategy_plan_artifact=plan, db_path=db_path, policy={})
    dry_run = build_create_dry_run(create_strategy_plan_artifact=plan, create_preflight_artifact=preflight, policy={})
    approval = build_create_approval(create_dry_run_artifact=dry_run, policy={"auto_approve_phase1": True})
    snapshot = build_create_plan_snapshot(
        create_strategy_plan_artifact=plan,
        create_preflight_artifact=preflight,
        create_dry_run_artifact=dry_run,
        create_approval_artifact=approval,
    )
    execute = build_create_execute(create_approval_artifact=approval, policy={})

    result = run_create_chain_replay_request(
        {
            "create_chain_replay": {
                "create_request_artifact": request,
                "create_strategy_plan_artifact": plan,
                "create_preflight_artifact": preflight,
                "create_dry_run_artifact": dry_run,
                "create_approval_artifact": approval,
                "create_plan_snapshot_artifact": snapshot,
                "create_execute_artifact": execute,
            }
        },
        runs_dir=tmp_path / "runs",
    )

    assert result["workflow"] == "create_chain_replay"
    assert Path(result["artifact_path"]).exists()
    assert result["summary"]["checked_workflow_count"] == 7


def test_create_chain_manifest_is_ready_when_replay_passed(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    _seed_create_db(db_path)
    request = run_create_request(_create_request(), db_path=db_path, runs_dir=tmp_path / "runs")
    plan = run_create_strategy_plan_request(
        request,
        db_path=db_path,
        runs_dir=tmp_path / "runs",
        policy={},
        create_request_artifact_path=request["artifact_path"],
    )
    preflight = run_create_preflight_request(
        {"create_preflight": {"create_strategy_plan_artifact": plan, "policy": {}}},
        db_path=db_path,
        runs_dir=tmp_path / "runs",
    )
    dry_run = run_create_dry_run_request(
        {"create_dry_run": {"create_strategy_plan_artifact": plan, "create_preflight_artifact": preflight, "policy": {}}},
        runs_dir=tmp_path / "runs",
        db_path=db_path,
    )
    approval = run_create_approval_request(
        {"create_approval": {"create_dry_run_artifact": dry_run, "policy": {"auto_approve_phase1": True}}},
        runs_dir=tmp_path / "runs",
    )
    snapshot = run_create_plan_snapshot_request(
        {
            "create_plan_snapshot": {
                "create_strategy_plan_artifact": plan,
                "create_preflight_artifact": preflight,
                "create_dry_run_artifact": dry_run,
                "create_approval_artifact": approval,
            }
        },
        runs_dir=tmp_path / "runs",
    )
    execute = run_create_execute_request(
        {"create_execute": {"create_approval_artifact": approval, "policy": {}}},
        runs_dir=tmp_path / "runs",
    )
    replay = run_create_chain_replay_request(
        {
            "create_chain_replay": {
                "create_request_artifact": request,
                "create_strategy_plan_artifact": plan,
                "create_preflight_artifact": preflight,
                "create_dry_run_artifact": dry_run,
                "create_approval_artifact": approval,
                "create_plan_snapshot_artifact": snapshot,
                "create_execute_artifact": execute,
            }
        },
        runs_dir=tmp_path / "runs",
    )

    result = build_create_chain_manifest(
        create_request_artifact=request,
        create_strategy_plan_artifact=plan,
        create_preflight_artifact=preflight,
        create_dry_run_artifact=dry_run,
        create_approval_artifact=approval,
        create_plan_snapshot_artifact=snapshot,
        create_execute_artifact=execute,
        create_chain_replay_artifact=replay,
    )

    assert result["ok"] is True
    assert result["workflow"] == "create_chain_manifest"
    assert result["phase"] == "phase1"
    assert result["execution_enabled"] is False
    assert result["external_api_calls"] == 0
    assert result["status"] == "ready"
    assert result["summary"] == {
        "plan_id": "create_plan_create_req_20260508_yzt_wx_7r",
        "request_id": "create_req_20260508_yzt_wx_7r",
        "target_date": "2026-05-08",
        "replay_status": "passed",
        "artifact_count": 8,
    }
    assert result["artifact_paths"]["create_request"] == request["artifact_path"]
    assert result["artifact_paths"]["create_chain_replay"] == replay["artifact_path"]
    assert result["candidate_task_digest"] == approval["candidate_task_digest"]
    assert result["provider_field_map_digest"] == dry_run["provider_field_map_digest"]
    assert result["provider_payload_draft_digest"] == dry_run["provider_payload_draft_digest"]
    assert result["phase1_safety_contract"] == replay["phase1_safety_contract"]
    assert result["violations"] == []
    assert result["actions"] == []


def test_create_chain_manifest_is_not_ready_when_replay_blocked(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    _seed_create_db(db_path)
    request = run_create_request(_create_request(), db_path=db_path, runs_dir=tmp_path / "runs")
    plan = run_create_strategy_plan_request(
        request,
        db_path=db_path,
        runs_dir=tmp_path / "runs",
        policy={},
        create_request_artifact_path=request["artifact_path"],
    )
    preflight = build_create_preflight(create_strategy_plan_artifact=plan, db_path=db_path, policy={})
    dry_run = build_create_dry_run(create_strategy_plan_artifact=plan, create_preflight_artifact=preflight, policy={})
    approval = build_create_approval(create_dry_run_artifact=dry_run, policy={"auto_approve_phase1": True})
    snapshot = build_create_plan_snapshot(
        create_strategy_plan_artifact=plan,
        create_preflight_artifact=preflight,
        create_dry_run_artifact=dry_run,
        create_approval_artifact=approval,
    )
    execute = build_create_execute(create_approval_artifact=approval, policy={})
    execute["provider_payload_draft_digest"] = {**execute["provider_payload_draft_digest"], "value": "0" * 64}
    replay = build_create_chain_replay(
        create_request_artifact=request,
        create_strategy_plan_artifact=plan,
        create_preflight_artifact=preflight,
        create_dry_run_artifact=dry_run,
        create_approval_artifact=approval,
        create_plan_snapshot_artifact=snapshot,
        create_execute_artifact=execute,
    )

    result = build_create_chain_manifest(
        create_request_artifact=request,
        create_strategy_plan_artifact=plan,
        create_preflight_artifact=preflight,
        create_dry_run_artifact=dry_run,
        create_approval_artifact=approval,
        create_plan_snapshot_artifact=snapshot,
        create_execute_artifact=execute,
        create_chain_replay_artifact=replay,
    )

    assert result["ok"] is False
    assert result["status"] == "not_ready"
    assert result["summary"]["replay_status"] == "blocked"
    assert "create chain replay must pass before manifest is ready" in result["violations"]
    assert result["actions"] == []


def test_run_create_chain_manifest_request_writes_artifact(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    _seed_create_db(db_path)
    request = run_create_request(_create_request(), db_path=db_path, runs_dir=tmp_path / "runs")
    plan = run_create_strategy_plan_request(
        request,
        db_path=db_path,
        runs_dir=tmp_path / "runs",
        policy={},
        create_request_artifact_path=request["artifact_path"],
    )
    preflight = build_create_preflight(create_strategy_plan_artifact=plan, db_path=db_path, policy={})
    dry_run = build_create_dry_run(create_strategy_plan_artifact=plan, create_preflight_artifact=preflight, policy={})
    approval = build_create_approval(create_dry_run_artifact=dry_run, policy={"auto_approve_phase1": True})
    snapshot = build_create_plan_snapshot(
        create_strategy_plan_artifact=plan,
        create_preflight_artifact=preflight,
        create_dry_run_artifact=dry_run,
        create_approval_artifact=approval,
    )
    execute = build_create_execute(create_approval_artifact=approval, policy={})
    replay = build_create_chain_replay(
        create_request_artifact=request,
        create_strategy_plan_artifact=plan,
        create_preflight_artifact=preflight,
        create_dry_run_artifact=dry_run,
        create_approval_artifact=approval,
        create_plan_snapshot_artifact=snapshot,
        create_execute_artifact=execute,
    )

    result = run_create_chain_manifest_request(
        {
            "create_chain_manifest": {
                "create_request_artifact": request,
                "create_strategy_plan_artifact": plan,
                "create_preflight_artifact": preflight,
                "create_dry_run_artifact": dry_run,
                "create_approval_artifact": approval,
                "create_plan_snapshot_artifact": snapshot,
                "create_execute_artifact": execute,
                "create_chain_replay_artifact": replay,
            }
        },
        runs_dir=tmp_path / "runs",
    )

    assert result["workflow"] == "create_chain_manifest"
    assert Path(result["artifact_path"]).exists()
    assert result["summary"]["artifact_count"] == 8


def test_create_strategy_plan_preflight_and_dry_run_cli_use_latest_artifacts(tmp_path: Path, capsys):
    db_path = tmp_path / "roibang.sqlite3"
    _seed_create_db(db_path)
    runtime_path = _runtime_config(tmp_path, db_path)
    request_result = run_create_request(_create_request(), db_path=db_path, runs_dir=tmp_path / "runs")

    strategy_module = _load_script("run_create_strategy_plan")
    assert strategy_module.run_from_args(["--config", str(runtime_path)]) == 0
    strategy_output = json.loads(capsys.readouterr().out)
    strategy_artifact = Path(strategy_output["artifact_path"])
    assert strategy_artifact.exists()

    preflight_module = _load_script("run_create_preflight")
    assert preflight_module.run_from_args(["--config", str(runtime_path)]) == 0
    preflight_output = json.loads(capsys.readouterr().out)
    assert preflight_output["status"] == "passed"

    field_map_module = _load_script("run_create_provider_field_map_check")
    assert field_map_module.run_from_args(["--config", str(runtime_path)]) == 0
    field_map_output = json.loads(capsys.readouterr().out)
    assert field_map_output["status"] == "unverified"

    dry_run_module = _load_script("run_create_dry_run")
    assert dry_run_module.run_from_args(["--config", str(runtime_path)]) == 0
    dry_run_output = json.loads(capsys.readouterr().out)
    dry_run_artifact = json.loads(Path(dry_run_output["artifact_path"]).read_text(encoding="utf-8"))
    assert dry_run_artifact["status"] == "simulated"
    assert dry_run_artifact["candidate_tasks"][0]["executable"] is False
    assert dry_run_artifact["lineage"]["create_provider_field_map_check"]["artifact_path"] == field_map_output["artifact_path"]
    assert dry_run_artifact["idempotency_ledger"]["status"] == "recorded"
    assert dry_run_artifact["provider_field_map"]["source"] == "phase1_example_config_no_legacy_reference"
    assert dry_run_artifact["provider_readiness_contract"]["ready_for_live_execute"] is False
    assert request_result["summary"]["request_id"] == "create_req_20260508_yzt_wx_7r"

    approval_module = _load_script("run_create_approval")
    assert approval_module.run_from_args(["--config", str(runtime_path)]) == 0
    approval_output = json.loads(capsys.readouterr().out)
    assert approval_output["workflow"] == "create_approval"
    assert approval_output["execute_allowed"] is False

    snapshot_module = _load_script("run_create_plan_snapshot")
    assert snapshot_module.run_from_args(["--config", str(runtime_path)]) == 0
    snapshot_output = json.loads(capsys.readouterr().out)
    snapshot_artifact = json.loads(Path(snapshot_output["artifact_path"]).read_text(encoding="utf-8"))
    assert snapshot_output["workflow"] == "create_plan_snapshot"
    assert snapshot_artifact["summary"]["project_count"] == 1
    assert snapshot_artifact["candidate_task_digest"]["candidate_task_count"] == 1

    execute_module = _load_script("run_create_execute")
    assert execute_module.run_from_args(["--config", str(runtime_path)]) == 0
    execute_output = json.loads(capsys.readouterr().out)
    execute_artifact = json.loads(Path(execute_output["artifact_path"]).read_text(encoding="utf-8"))
    assert execute_output["workflow"] == "create_execute"
    assert execute_output["status"] == "blocked"
    assert execute_artifact["executed_task_count"] == 0


def test_create_chain_fixed_cli_scripts_run_through_replay(tmp_path: Path, capsys):
    db_path = tmp_path / "roibang.sqlite3"
    _seed_create_db(db_path)
    runtime_path = _runtime_config(tmp_path, db_path)
    request_path = tmp_path / "create-request.json"
    request_path.write_text(json.dumps(_create_request(), ensure_ascii=False), encoding="utf-8")

    request_module = _load_script("run_create_request")
    assert request_module.run_from_args(["--config", str(runtime_path), "--request", str(request_path)]) == 0
    request_output = json.loads(capsys.readouterr().out)
    assert Path(request_output["artifact_path"]).exists()

    strategy_module = _load_script("run_create_strategy_plan")
    assert strategy_module.run_from_args(["--config", str(runtime_path)]) == 0
    strategy_output = json.loads(capsys.readouterr().out)
    assert Path(strategy_output["artifact_path"]).exists()

    preflight_module = _load_script("run_create_preflight")
    assert preflight_module.run_from_args(["--config", str(runtime_path)]) == 0
    preflight_output = json.loads(capsys.readouterr().out)
    assert preflight_output["status"] == "passed"

    field_map_module = _load_script("run_create_provider_field_map_check")
    assert field_map_module.run_from_args(["--config", str(runtime_path)]) == 0
    field_map_output = json.loads(capsys.readouterr().out)
    assert field_map_output["status"] == "unverified"

    dry_run_module = _load_script("run_create_dry_run")
    assert dry_run_module.run_from_args(["--config", str(runtime_path)]) == 0
    dry_run_output = json.loads(capsys.readouterr().out)
    assert dry_run_output["status"] == "simulated"

    approval_module = _load_script("run_create_approval")
    assert approval_module.run_from_args(["--config", str(runtime_path)]) == 0
    approval_output = json.loads(capsys.readouterr().out)
    assert approval_output["execute_allowed"] is False

    snapshot_module = _load_script("run_create_plan_snapshot")
    assert snapshot_module.run_from_args(["--config", str(runtime_path)]) == 0
    snapshot_output = json.loads(capsys.readouterr().out)
    assert snapshot_output["workflow"] == "create_plan_snapshot"

    execute_module = _load_script("run_create_execute")
    assert execute_module.run_from_args(["--config", str(runtime_path)]) == 0
    execute_output = json.loads(capsys.readouterr().out)
    assert execute_output["status"] == "blocked"

    replay_module = _load_script("run_create_chain_replay")
    assert replay_module.run_from_args(["--config", str(runtime_path)]) == 0
    replay_output = json.loads(capsys.readouterr().out)
    replay_artifact = json.loads(Path(replay_output["artifact_path"]).read_text(encoding="utf-8"))
    assert replay_output["workflow"] == "create_chain_replay"
    assert replay_output["status"] == "passed"
    assert replay_artifact["phase1_safety_contract"] == {
        "status": "passed",
        "execution_enabled_false": True,
        "external_api_calls_zero": True,
        "actions_empty": True,
    }
    assert replay_artifact["digest_consistency"]["candidate_task_digest"]["status"] == "passed"
    assert replay_artifact["digest_consistency"]["provider_field_map_digest"]["status"] == "passed"
    assert replay_artifact["digest_consistency"]["provider_payload_draft_digest"]["status"] == "passed"
    assert replay_artifact["actions"] == []

    manifest_module = _load_script("run_create_chain_manifest")
    assert manifest_module.run_from_args(["--config", str(runtime_path)]) == 0
    manifest_output = json.loads(capsys.readouterr().out)
    manifest_artifact = json.loads(Path(manifest_output["artifact_path"]).read_text(encoding="utf-8"))
    assert manifest_output["workflow"] == "create_chain_manifest"
    assert manifest_output["status"] == "ready"
    assert manifest_artifact["artifact_paths"]["create_chain_replay"] == replay_output["artifact_path"]
    assert manifest_artifact["provider_payload_draft_digest"] == replay_artifact["digest_consistency"]["provider_payload_draft_digest"]["sources"]["dry_run"]
    assert manifest_artifact["actions"] == []
