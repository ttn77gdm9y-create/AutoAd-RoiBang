import importlib.util
import json
import sqlite3
from pathlib import Path

from roibang_v2.db.bootstrap import bootstrap_database
from roibang_v2.workflows.create_material_bind_ledger import record_create_material_bind_result
from roibang_v2.workflows.create_provider_id_ledger import record_create_provider_id
from roibang_v2.workflows.create_live_execute_once import run_create_live_execute_once_request


def _load_script(name: str):
    script_path = Path(f"scripts/{name}.py")
    spec = importlib.util.spec_from_file_location(name, script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _runtime_config(tmp_path: Path, *, execution_enabled: bool = False, external_api_enabled: bool = False) -> Path:
    path = tmp_path / "runtime.json"
    path.write_text(
        json.dumps(
            {
                "environment": "test",
                "phase": "phase2",
                "database_path": str(tmp_path / "roibang.sqlite3"),
                "runs_dir": str(tmp_path / "runs"),
                "fixtures_dir": "data/fixtures",
                "external_api_enabled": external_api_enabled,
                "execution_enabled": execution_enabled,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path


def _execute_artifact() -> dict:
    return {
        "workflow": "create_execute",
        "ok": True,
        "phase": "phase1",
        "status": "blocked",
        "execution_enabled": False,
        "external_api_calls": 0,
        "summary": {
            "plan_id": "plan-1",
            "request_id": "req-1",
            "target_date": "2026-05-10",
            "project_count": 1,
            "unit_count": 1,
            "material_count": 1,
        },
        "resolved_provider_payload_drafts": [
            {
                "operation": "create_project",
                "payload": {"advertiser_id": "target-1", "name": "首单项目"},
                "executable": False,
                "live_api_payload": False,
            },
            {
                "operation": "create_unit",
                "payload": {
                    "advertiser_id": "target-1",
                    "project_id": "<lookup:target-1-p001>",
                    "promotion_materials": {
                        "video_material_list": [
                            {
                                "video_id": "<lookup:target_video:target-1:video-1>",
                                "video_cover_id": "<lookup:target_video_cover:target-1:video-1>",
                            }
                        ]
                    },
                },
                "executable": False,
                "live_api_payload": False,
            },
            {
                "operation": "bind_material",
                "payload": {
                    "source_advertiser_id": "source-1",
                    "target_advertiser_ids": ["target-1"],
                    "source_video_ids": ["video-1"],
                },
                "executable": False,
                "live_api_payload": False,
            },
            {
                "operation": "lookup_target_material",
                "payload": {
                    "target_advertiser_id": "target-1",
                    "source_video_id": "video-1",
                    "material_id": "material-1",
                },
                "executable": False,
                "live_api_payload": False,
            },
        ],
        "resolved_payload_contract": {
            "status": "passed",
            "checked_draft_count": 4,
            "unresolved_lookup_count": 0,
            "executable_draft_count": 0,
            "live_payload_count": 0,
        },
        "provider_id_ledger_requirements": {
            "produced_by_create_project": [
                {
                    "local_key": "target-1-p001",
                    "advertiser_id": "target-1",
                    "parent_local_key": "",
                }
            ],
            "produced_by_create_unit": [
                {
                    "local_key": "target-1-p001-u01",
                    "advertiser_id": "target-1",
                    "parent_local_key": "target-1-p001",
                }
            ],
            "required_before_create_unit": [
                {"entity_type": "project", "local_key": "target-1-p001"},
                {"entity_type": "target_video", "local_key": "target_video:target-1:video-1"},
                {"entity_type": "target_video_cover", "local_key": "target_video_cover:target-1:video-1"},
            ],
            "required_before_bind_material": [{"local_key": "target-1-p001-u01"}],
        },
    }


def _scaffold_artifact() -> dict:
    return {
        "workflow": "create_live_payload_adapter_scaffold",
        "execution_enabled": False,
        "external_api_calls": 0,
        "live_adapter_gate": {
            "ready_for_live_execute": True,
            "required_gates": {"phase_gate_allows_live_execute": True},
            "endpoints": {
                "create_project": "/open_api/2/project/create/",
                "create_unit": "/open_api/2/promotion/create/",
                "lookup_target_material": "/open_api/2/file/video/get/",
                "bind_material": "/open_api/2/file/material/bind/",
            },
        },
    }


def _policy() -> dict:
    return {
        "create_plan": {
            "max_target_accounts": 2,
            "max_projects_per_account": 2,
            "max_units_per_project": 2,
            "max_materials": 2,
            "min_daily_budget": 100,
            "max_daily_budget": 1000,
        },
        "create_execute": {
            "live_api": {
                "enabled": True,
                "endpoints": {
                    "create_project": "/open_api/2/project/create/",
                    "create_unit": "/open_api/2/promotion/create/",
                    "lookup_target_material": "/open_api/2/file/video/get/",
                    "bind_material": "/open_api/2/file/material/bind/",
                },
            },
            "payload_schema": {"live_payload_generation_enabled": True},
        },
        "create_live_execute_once": {
            "allow_create_http_transport": True,
            "create_http_transport": {
                "enabled": True,
                "allow_mutation": True,
                "run_id": "manual-live-create-001",
                "operator": "operator",
                "token_env": "ROIBANG_TEST_ACCESS_TOKEN",
            },
        },
    }


def _create_plan(*, plan_id: str = "plan-1") -> dict:
    return {
        "plan_id": plan_id,
        "product": "yzt",
        "platform": "wx-mini-game",
        "launch_mode": "create_only",
        "source_advertiser_id": "source-1",
        "target_accounts": [
            {
                "advertiser_id": "target-1",
                "project_count": 1,
                "unit_count_per_project": 1,
                "daily_budget": 1000,
            }
        ],
        "materials": [{"source_material_id": "material-1", "source_video_id": "video-1"}],
        "reason": "首单链路验证",
    }


def _seed_plan_sources(db_path: Path) -> None:
    bootstrap_database(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO account_pool (
              advertiser_id, account_name, product, platform, historical_spend, source, synced_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("target-1", "Target Account", "yzt", "wx-mini-game", 1000, "test", "2026-05-11T00:00:00Z"),
        )
        conn.execute(
            """
            INSERT INTO product_source_materials (
              product, source_advertiser_id, material_id, video_id, name, source, synced_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("yzt", "source-1", "material-1", "video-1", "Material 1", "test", "2026-05-11T00:00:00Z"),
        )


def test_create_live_execute_once_direct_mode_blocks_without_runtime_or_pack(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)

    result = run_create_live_execute_once_request(
        {
            "create_live_execute_once": {
                "create_execute_artifact": _execute_artifact(),
                "create_live_payload_adapter_scaffold_artifact": _scaffold_artifact(),
                "policy": _policy(),
                "runtime": {"execution_enabled": False, "external_api_enabled": False},
            }
        },
        runs_dir=tmp_path / "runs",
        db_path=db_path,
    )

    assert result["ok"] is False
    assert result["workflow"] == "create_live_execute_once"
    assert result["status"] == "blocked"
    assert result["reason"] == "direct_execute_not_ready"
    assert result["source_execution_pack_status"] == "not_required_direct_create_execute"
    assert result["execution_enabled"] is False
    assert result["live_execute_enabled"] is False
    assert result["external_api_calls"] == 0
    assert result["transport_call_count"] == 0
    assert "runtime.execution_enabled is false" in result["blocking_reasons"]
    assert "runtime.external_api_enabled is false" in result["blocking_reasons"]
    assert result["actions"] == []


def test_create_live_execute_once_direct_mode_requires_verified_field_mapping_when_policy_requires_it(
    tmp_path: Path,
):
    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)
    policy = _policy()
    policy["create_live_execute_once"]["require_provider_field_mapping"] = True

    result = run_create_live_execute_once_request(
        {
            "create_live_execute_once": {
                "create_execute_artifact": _execute_artifact(),
                "create_live_payload_adapter_scaffold_artifact": _scaffold_artifact(),
                "policy": policy,
                "runtime": {"execution_enabled": True, "external_api_enabled": True},
            }
        },
        runs_dir=tmp_path / "runs",
        db_path=db_path,
        transport=lambda _call: {"code": 0},
    )

    assert result["ok"] is False
    assert result["status"] == "blocked"
    assert result["reason"] == "direct_execute_not_ready"
    assert result["external_api_calls"] == 0
    assert (
        "create_execute provider payloads must have verified field mapping before live execute"
        in result["blocking_reasons"]
    )


def test_create_live_execute_once_direct_mode_runs_fixed_sequence_with_transport(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)
    calls: list[dict] = []

    def fake_transport(call: dict) -> dict:
        calls.append(call)
        if call["operation"] == "create_project":
            return {"code": 0, "data": {"project_id": "project-001"}}
        if call["operation"] == "bind_material":
            return {"code": 0, "data": {"task_id": "bind-001"}}
        if call["operation"] == "lookup_target_material":
            return {"code": 0, "data": {"target_video_id": "target-video-001", "target_video_cover_id": "target-cover-001"}}
        if call["operation"] == "create_unit":
            assert call["payload"]["project_id"] == "project-001"
            assert call["payload"]["promotion_materials"]["video_material_list"][0]["video_id"] == "target-video-001"
            return {"code": 0, "data": {"promotion_id": "promotion-001"}}
        raise AssertionError(call["operation"])

    result = run_create_live_execute_once_request(
        {
            "create_live_execute_once": {
                "create_execute_artifact": _execute_artifact(),
                "create_live_payload_adapter_scaffold_artifact": _scaffold_artifact(),
                "policy": _policy(),
                "runtime": {"execution_enabled": True, "external_api_enabled": True},
            }
        },
        runs_dir=tmp_path / "runs",
        db_path=db_path,
        transport=fake_transport,
    )

    assert result["ok"] is True
    assert result["status"] == "create_http_completed"
    assert result["source_execution_pack_status"] == "not_required_direct_create_execute"
    assert result["execution_enabled"] is True
    assert result["live_execute_enabled"] is True
    assert result["external_api_calls"] == 4
    assert [call["operation"] for call in calls] == [
        "create_project",
        "bind_material",
        "lookup_target_material",
        "create_unit",
    ]


def test_create_live_execute_once_direct_mode_allows_chain_resolvable_lookups(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)
    create_execute = json.loads(json.dumps(_execute_artifact(), ensure_ascii=False))
    create_execute["resolved_payload_contract"]["unresolved_lookup_count"] = 3
    calls: list[dict] = []

    def fake_transport(call: dict) -> dict:
        calls.append(call)
        if call["operation"] == "create_project":
            return {"code": 0, "data": {"project_id": "project-001"}}
        if call["operation"] == "bind_material":
            return {"code": 0, "data": {"task_id": "bind-001"}}
        if call["operation"] == "lookup_target_material":
            return {"code": 0, "data": {"target_video_id": "target-video-001", "target_video_cover_id": "target-cover-001"}}
        if call["operation"] == "create_unit":
            return {"code": 0, "data": {"promotion_id": "promotion-001"}}
        raise AssertionError(call["operation"])

    result = run_create_live_execute_once_request(
        {
            "create_live_execute_once": {
                "create_execute_artifact": create_execute,
                "create_live_payload_adapter_scaffold_artifact": _scaffold_artifact(),
                "policy": _policy(),
                "runtime": {"execution_enabled": True, "external_api_enabled": True},
            }
        },
        runs_dir=tmp_path / "runs",
        db_path=db_path,
        transport=fake_transport,
    )

    assert result["ok"] is True
    assert result["status"] == "create_http_completed"
    assert [call["operation"] for call in calls] == [
        "create_project",
        "bind_material",
        "lookup_target_material",
        "create_unit",
    ]


def test_create_live_execute_once_direct_mode_blocks_unproducible_lookup(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)
    create_execute = json.loads(json.dumps(_execute_artifact(), ensure_ascii=False))
    create_execute["resolved_provider_payload_drafts"][0]["payload"]["name"] = "<lookup:not-produced>"

    result = run_create_live_execute_once_request(
        {
            "create_live_execute_once": {
                "create_execute_artifact": create_execute,
                "create_live_payload_adapter_scaffold_artifact": _scaffold_artifact(),
                "policy": _policy(),
                "runtime": {"execution_enabled": True, "external_api_enabled": True},
            }
        },
        runs_dir=tmp_path / "runs",
        db_path=db_path,
        transport=lambda _call: {"code": 0},
    )

    assert result["ok"] is False
    assert result["external_api_calls"] == 0
    assert (
        "create_execute payloads contain lookup placeholders that cannot be produced by this fixed chain"
        in result["blocking_reasons"]
    )


def test_create_live_execute_once_direct_mode_blocks_active_create_payload(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)
    create_execute = json.loads(json.dumps(_execute_artifact(), ensure_ascii=False))
    create_execute["resolved_provider_payload_drafts"][0]["payload"]["status"] = "ACTIVE"

    result = run_create_live_execute_once_request(
        {
            "create_live_execute_once": {
                "create_execute_artifact": create_execute,
                "create_live_payload_adapter_scaffold_artifact": _scaffold_artifact(),
                "policy": _policy(),
                "runtime": {"execution_enabled": True, "external_api_enabled": True},
            }
        },
        runs_dir=tmp_path / "runs",
        db_path=db_path,
        transport=lambda _call: {"code": 0},
    )

    assert result["ok"] is False
    assert result["external_api_calls"] == 0
    assert "create_project.status must not be ACTIVE during create" in result["blocking_reasons"]


def test_create_live_execute_once_runs_create_http_transport_in_order(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)
    calls: list[dict] = []

    def fake_transport(call: dict) -> dict:
        calls.append(call)
        if call["operation"] == "create_project":
            return {"code": 0, "data": {"project_id": "project-001"}}
        if call["operation"] == "create_unit":
            assert call["payload"]["project_id"] == "project-001"
            return {"code": 0, "data": {"promotion_id": "promotion-001"}}
        if call["operation"] == "bind_material":
            return {"code": 0, "data": {"task_id": "bind-001"}}
        if call["operation"] == "lookup_target_material":
            return {"code": 0, "data": {"target_video_id": "target-video-001", "target_video_cover_id": "target-cover-001"}}
        raise AssertionError(call["operation"])

    result = run_create_live_execute_once_request(
        {
            "create_live_execute_once": {
                "create_execute_artifact": _execute_artifact(),
                "create_live_payload_adapter_scaffold_artifact": _scaffold_artifact(),
                "policy": _policy(),
                "runtime": {"execution_enabled": True, "external_api_enabled": True},
            }
        },
        runs_dir=tmp_path / "runs",
        db_path=db_path,
        transport=fake_transport,
    )

    assert result["ok"] is True
    assert result["status"] == "create_http_completed"
    assert result["execution_enabled"] is True
    assert result["live_execute_enabled"] is True
    assert result["external_api_calls"] == 4
    assert result["transport_call_count"] == 4
    assert [call["operation"] for call in calls] == [
        "create_project",
        "bind_material",
        "lookup_target_material",
        "create_unit",
    ]
    assert result["ordered_steps"] == [
        {"operation": "create_project", "planned_count": 1, "status": "completed", "test_transport_call_count": 1},
        {"operation": "bind_material", "planned_count": 1, "status": "completed", "test_transport_call_count": 1},
        {
            "operation": "lookup_target_material",
            "planned_count": 1,
            "status": "completed",
            "test_transport_call_count": 1,
        },
        {"operation": "create_unit", "planned_count": 1, "status": "completed", "test_transport_call_count": 1},
    ]
    assert [row["provider_id"] for row in result["provider_id_records"]] == [
        "project-001",
        "target-video-001",
        "target-cover-001",
        "promotion-001",
    ]

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT entity_type, local_key, provider_id
            FROM create_provider_id_ledger
            ORDER BY entity_type, local_key
            """
        ).fetchall()
    assert rows == [
        ("project", "target-1-p001", "project-001"),
        ("promotion", "target-1-p001-u01", "promotion-001"),
        ("target_video", "target_video:target-1:video-1", "target-video-001"),
        ("target_video_cover", "target_video_cover:target-1:video-1", "target-cover-001"),
    ]
    with sqlite3.connect(db_path) as conn:
        bind_rows = conn.execute(
            """
            SELECT source_advertiser_id, target_advertiser_ids_json, source_video_ids_json, provider_task_id, status
            FROM create_material_bind_ledger
            """
        ).fetchall()
    assert bind_rows == [
        ("source-1", '["target-1"]', '["video-1"]', "bind-001", "active"),
    ]


def test_create_live_execute_once_skips_existing_project_and_resumes_unit(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)
    record_create_provider_id(
        db_path=db_path,
        entity_type="project",
        local_key="target-1-p001",
        provider_id="project-existing",
        plan_id="plan-1",
        request_id="req-1",
        advertiser_id="target-1",
        source_workflow="create_live_execute_once",
    )
    calls: list[dict] = []

    def fake_transport(call: dict) -> dict:
        calls.append(call)
        if call["operation"] == "create_project":
            raise AssertionError("existing project must not be created again")
        if call["operation"] == "create_unit":
            assert call["payload"]["project_id"] == "project-existing"
            return {"code": 0, "data": {"promotion_id": "promotion-001"}}
        if call["operation"] == "bind_material":
            return {"code": 0, "data": {"task_id": "bind-001"}}
        if call["operation"] == "lookup_target_material":
            return {"code": 0, "data": {"target_video_id": "target-video-001", "target_video_cover_id": "target-cover-001"}}
        raise AssertionError(call["operation"])

    result = run_create_live_execute_once_request(
        {
            "create_live_execute_once": {
                "create_execute_artifact": _execute_artifact(),
                "create_live_payload_adapter_scaffold_artifact": _scaffold_artifact(),
                "policy": _policy(),
                "runtime": {"execution_enabled": True, "external_api_enabled": True},
            }
        },
        runs_dir=tmp_path / "runs",
        db_path=db_path,
        transport=fake_transport,
    )

    assert result["ok"] is True
    assert result["status"] == "create_http_completed"
    assert result["external_api_calls"] == 3
    assert [call["operation"] for call in calls] == ["bind_material", "lookup_target_material", "create_unit"]
    assert result["idempotency"]["skipped_existing_provider_id_count"] == 1
    assert result["ordered_steps"][0] == {
        "operation": "create_project",
        "planned_count": 1,
        "status": "skipped_existing_provider_id",
        "test_transport_call_count": 0,
    }

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT entity_type, local_key, provider_id
            FROM create_provider_id_ledger
            ORDER BY entity_type, local_key
            """
        ).fetchall()
    assert rows == [
        ("project", "target-1-p001", "project-existing"),
        ("promotion", "target-1-p001-u01", "promotion-001"),
        ("target_video", "target_video:target-1:video-1", "target-video-001"),
        ("target_video_cover", "target_video_cover:target-1:video-1", "target-cover-001"),
    ]


def test_create_live_execute_once_skips_existing_project_and_unit_then_binds_material(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)
    record_create_provider_id(
        db_path=db_path,
        entity_type="project",
        local_key="target-1-p001",
        provider_id="project-existing",
        plan_id="plan-1",
        request_id="req-1",
        advertiser_id="target-1",
        source_workflow="create_live_execute_once",
    )
    record_create_provider_id(
        db_path=db_path,
        entity_type="promotion",
        local_key="target-1-p001-u01",
        provider_id="promotion-existing",
        plan_id="plan-1",
        request_id="req-1",
        advertiser_id="target-1",
        parent_local_key="target-1-p001",
        source_workflow="create_live_execute_once",
    )
    calls: list[dict] = []

    def fake_transport(call: dict) -> dict:
        calls.append(call)
        if call["operation"] in {"create_project", "create_unit"}:
            raise AssertionError(f"{call['operation']} must not be created again")
        if call["operation"] == "bind_material":
            return {"code": 0, "data": {"task_id": "bind-001"}}
        if call["operation"] == "lookup_target_material":
            return {"code": 0, "data": {"target_video_id": "target-video-001", "target_video_cover_id": "target-cover-001"}}
        raise AssertionError(call["operation"])

    result = run_create_live_execute_once_request(
        {
            "create_live_execute_once": {
                "create_execute_artifact": _execute_artifact(),
                "create_live_payload_adapter_scaffold_artifact": _scaffold_artifact(),
                "policy": _policy(),
                "runtime": {"execution_enabled": True, "external_api_enabled": True},
            }
        },
        runs_dir=tmp_path / "runs",
        db_path=db_path,
        transport=fake_transport,
    )

    assert result["ok"] is True
    assert result["external_api_calls"] == 2
    assert [call["operation"] for call in calls] == ["bind_material", "lookup_target_material"]
    assert result["idempotency"]["skipped_existing_provider_id_count"] == 2
    assert [step["status"] for step in result["ordered_steps"]] == [
        "skipped_existing_provider_id",
        "completed",
        "completed",
        "skipped_existing_provider_id",
    ]


def test_create_live_execute_once_skips_existing_material_bind(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)
    record_create_provider_id(
        db_path=db_path,
        entity_type="project",
        local_key="target-1-p001",
        provider_id="project-existing",
        plan_id="plan-1",
        request_id="req-1",
        advertiser_id="target-1",
        source_workflow="create_live_execute_once",
    )
    record_create_provider_id(
        db_path=db_path,
        entity_type="promotion",
        local_key="target-1-p001-u01",
        provider_id="promotion-existing",
        plan_id="plan-1",
        request_id="req-1",
        advertiser_id="target-1",
        parent_local_key="target-1-p001",
        source_workflow="create_live_execute_once",
    )
    record_create_provider_id(
        db_path=db_path,
        entity_type="target_video",
        local_key="target_video:target-1:video-1",
        provider_id="target-video-existing",
        source_workflow="create_live_execute_once",
    )
    record_create_provider_id(
        db_path=db_path,
        entity_type="target_video_cover",
        local_key="target_video_cover:target-1:video-1",
        provider_id="target-cover-existing",
        source_workflow="create_live_execute_once",
    )
    record_create_material_bind_result(
        db_path=db_path,
        source_advertiser_id="source-1",
        target_advertiser_ids=["target-1"],
        source_video_ids=["video-1"],
        provider_task_id="bind-existing",
        plan_id="plan-1",
        request_id="req-1",
        source_workflow="create_live_execute_once",
        response_payload={"code": 0, "data_keys": ["task_id"]},
    )
    calls: list[dict] = []

    def fake_transport(call: dict) -> dict:
        calls.append(call)
        raise AssertionError(f"{call['operation']} must not be called")

    result = run_create_live_execute_once_request(
        {
            "create_live_execute_once": {
                "create_execute_artifact": _execute_artifact(),
                "create_live_payload_adapter_scaffold_artifact": _scaffold_artifact(),
                "policy": _policy(),
                "runtime": {"execution_enabled": True, "external_api_enabled": True},
            }
        },
        runs_dir=tmp_path / "runs",
        db_path=db_path,
        transport=fake_transport,
    )

    assert result["ok"] is True
    assert result["status"] == "create_http_completed"
    assert result["external_api_calls"] == 0
    assert calls == []
    assert result["idempotency"]["skipped_existing_provider_id_count"] == 4
    assert result["idempotency"]["skipped_existing_material_bind_count"] == 1
    assert [step["status"] for step in result["ordered_steps"]] == [
        "skipped_existing_provider_id",
        "skipped_existing_material_bind",
        "skipped_existing_provider_id",
        "skipped_existing_provider_id",
    ]


def test_run_create_live_execute_once_request_writes_blocked_artifact(tmp_path: Path):
    result = run_create_live_execute_once_request(
        {
            "create_live_execute_once": {
                "create_execute_artifact": _execute_artifact(),
                "create_live_payload_adapter_scaffold_artifact": _scaffold_artifact(),
                "policy": _policy(),
                "runtime": {"execution_enabled": True, "external_api_enabled": True},
            }
        },
        runs_dir=tmp_path / "runs",
        db_path=tmp_path / "roibang.sqlite3",
    )

    artifact = json.loads(Path(result["artifact_path"]).read_text(encoding="utf-8"))
    assert result["workflow"] == "create_live_execute_once"
    assert result["status"] == "blocked"
    assert artifact["external_api_calls"] == 0
    assert artifact["actions"] == []


def test_create_live_execute_once_fixed_script_keeps_default_runtime_blocked(tmp_path: Path, capsys):
    runtime_path = _runtime_config(tmp_path)
    _seed_plan_sources(tmp_path / "roibang.sqlite3")
    policy_path = tmp_path / "policy.json"
    plan_path = tmp_path / "create-plan.json"
    policy_path.write_text(json.dumps(_policy(), ensure_ascii=False), encoding="utf-8")
    plan_path.write_text(json.dumps(_create_plan(), ensure_ascii=False), encoding="utf-8")
    runs_dir = tmp_path / "runs"
    artifacts = {
        "create_execute": _execute_artifact(),
        "create_live_payload_adapter_scaffold": _scaffold_artifact(),
    }
    for workflow, artifact in artifacts.items():
        path = runs_dir / workflow / "20260510T000000Z.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(artifact, ensure_ascii=False), encoding="utf-8")
    module = _load_script("run_create_live_execute_once")

    exit_code = module.run_from_args(["--config", str(runtime_path), "--policy", str(policy_path), "--plan", str(plan_path)])

    output = json.loads(capsys.readouterr().out)
    artifact = json.loads(Path(output["artifact_path"]).read_text(encoding="utf-8"))
    assert exit_code == 0
    assert output["workflow"] == "create_live_execute_once"
    assert output["status"] == "blocked"
    assert output["execution_enabled"] is False
    assert output["live_execute_enabled"] is False
    assert output["external_api_calls"] == 0
    assert output["transport_call_count"] == 0
    assert output["source_execution_pack_status"] == "not_required_direct_create_execute"
    assert artifact["actions"] == []


def test_create_live_execute_once_fixed_script_blocks_plan_mismatch(tmp_path: Path, capsys):
    runtime_path = _runtime_config(tmp_path)
    _seed_plan_sources(tmp_path / "roibang.sqlite3")
    policy_path = tmp_path / "policy.json"
    plan_path = tmp_path / "create-plan.json"
    policy_path.write_text(json.dumps(_policy(), ensure_ascii=False), encoding="utf-8")
    plan_path.write_text(json.dumps(_create_plan(plan_id="different-plan"), ensure_ascii=False), encoding="utf-8")
    runs_dir = tmp_path / "runs"
    path = runs_dir / "create_execute" / "20260510T000000Z.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_execute_artifact(), ensure_ascii=False), encoding="utf-8")
    module = _load_script("run_create_live_execute_once")

    exit_code = module.run_from_args(["--config", str(runtime_path), "--policy", str(policy_path), "--plan", str(plan_path)])

    output = json.loads(capsys.readouterr().out)
    artifact = json.loads(Path(output["artifact_path"]).read_text(encoding="utf-8"))
    assert exit_code == 0
    assert output["workflow"] == "create_live_execute_once"
    assert output["status"] == "blocked"
    assert output["execution_enabled"] is False
    assert output["external_api_calls"] == 0
    assert output["transport_call_count"] == 0
    assert "create_plan.plan_id must match create_execute.summary.plan_id" in output["blocking_reasons"]
    assert artifact["create_plan_validation"]["ok"] is True
    assert artifact["actions"] == []


def test_create_live_execute_once_fixed_script_reports_missing_artifacts_as_blocked(tmp_path: Path, capsys):
    runtime_path = _runtime_config(tmp_path)
    policy_path = tmp_path / "policy.json"
    policy_path.write_text(json.dumps(_policy(), ensure_ascii=False), encoding="utf-8")
    module = _load_script("run_create_live_execute_once")

    exit_code = module.run_from_args(["--config", str(runtime_path), "--policy", str(policy_path)])

    output = json.loads(capsys.readouterr().out)
    artifact = json.loads(Path(output["artifact_path"]).read_text(encoding="utf-8"))
    assert exit_code == 0
    assert output["workflow"] == "create_live_execute_once"
    assert output["status"] == "blocked"
    assert output["execution_enabled"] is False
    assert output["external_api_calls"] == 0
    assert output["transport_call_count"] == 0
    assert "no create_execute artifacts found" in output["blocking_reasons"][0]
    assert artifact["actions"] == []
