import importlib.util
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from roibang_v2.db.bootstrap import bootstrap_database
from roibang_v2.workflows.create_material_bind_ledger import (
    material_bind_key_from_payload,
    record_create_material_bind_result,
)
from roibang_v2.workflows.create_provider_id_ledger import record_create_provider_id
from roibang_v2.workflows.create_live_execute_once import (
    _project_delete_payload,
    _target_material_item_for_lookup,
    run_create_live_execute_once_request,
)


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


def test_target_material_lookup_matches_exact_material_id_without_first_row_fallback():
    response = {
        "code": 0,
        "data": {
            "list": [
                {"id": "target-video-a", "material_id": 111},
                {"id": "target-video-b", "material_id": 222},
            ]
        },
    }

    assert _target_material_item_for_lookup(response, {"material_id": "222"})["id"] == "target-video-b"
    assert _target_material_item_for_lookup(response, {"material_id": "333"}) == {}


def test_project_delete_payload_casts_numeric_ids_to_ints():
    assert _project_delete_payload("1856647530917899", "7638636431363719210") == {
        "advertiser_id": 1856647530917899,
        "project_ids": [7638636431363719210],
    }


def test_watch_create_live_progress_cli_prints_current_progress(tmp_path: Path, capsys):
    progress_dir = tmp_path / "progress"
    progress_dir.mkdir()
    (progress_dir / "current.json").write_text(
        json.dumps(
            {
                "operation": "create_unit",
                "status": "running",
                "done": 3,
                "total": 8,
                "external_api_calls": 12,
                "advertiser_id": "target-1",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    script = _load_script("watch_create_live_progress")
    code = script.run_from_args(["--progress-dir", str(progress_dir), "--once"])

    assert code == 0
    output = capsys.readouterr().out
    assert "operation（操作）=create_unit" in output
    assert "progress（进度）=3/8" in output
    assert "external_api_calls（外部接口调用）=12" in output


def test_run_create_live_execute_terminal_wraps_fixed_script_with_progress(tmp_path: Path, capsys):
    runtime_path = _runtime_config(tmp_path)
    _seed_plan_sources(tmp_path / "roibang.sqlite3")
    policy = _policy()
    policy["create_live_execute_once"]["progress"] = {
        "enabled": True,
        "dir": str(tmp_path / "progress"),
        "append_jsonl": True,
        "stderr": False,
    }
    policy_path = tmp_path / "policy.json"
    plan_path = tmp_path / "create-plan.json"
    create_execute_path = tmp_path / "create-execute.json"
    policy_path.write_text(json.dumps(policy, ensure_ascii=False), encoding="utf-8")
    plan_path.write_text(json.dumps(_create_plan(), ensure_ascii=False), encoding="utf-8")
    create_execute_path.write_text(json.dumps(_execute_artifact(), ensure_ascii=False), encoding="utf-8")
    progress_dir = tmp_path / "progress"
    progress_dir.mkdir()
    (progress_dir / "events.jsonl").write_text(
        json.dumps({"operation": "old_run", "status": "completed"}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    script = _load_script("run_create_live_execute_terminal")
    code = script.run_from_args(
        [
            "--config",
            str(runtime_path),
            "--policy",
            str(policy_path),
            "--plan",
            str(plan_path),
            "--create-execute-artifact",
            str(create_execute_path),
            "--interval",
            "0.2",
            "--recent-events",
            "1",
        ]
    )

    output = capsys.readouterr().out
    assert code == 0
    assert "terminal_runner（终端执行器）=started" in output
    assert "terminal_runner（终端执行器）=finished exit_code（退出码）=0" in output
    assert "final_result（最终结果）:" in output
    assert list((tmp_path / "progress").glob("terminal_*.stdout.log"))
    assert list((tmp_path / "progress").glob("terminal_*.stderr.log"))
    events_path = tmp_path / "progress" / "events.jsonl"
    assert not events_path.exists() or "old_run" not in events_path.read_text(encoding="utf-8")


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
                    "create_project": "/open_api/v3.0/project/create/",
                    "create_unit": "/open_api/v3.0/promotion/create/",
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


def _create_strategy_plan(*, plan_id: str = "plan-1") -> dict:
    raw = _create_plan(plan_id=plan_id)
    return {
        "ok": True,
        "workflow": "create_strategy_plan",
        "phase": "phase1",
        "execution_enabled": False,
        "external_api_calls": 0,
        "status": "planned",
        "plan_id": raw["plan_id"],
        "request_id": "req-1",
        "target_date": "2026-05-13",
        "request": {
            **raw,
            "request_id": "req-1",
            "target_date": "2026-05-13",
            "template_parameters": {
                "product_name": "勇者突进",
                "fixed_video_cover_id": "cover-1",
                "title_pool": ["勇者突进测试"],
                "cta_pool": ["立即下载"],
            },
        },
        "strategy": {
            "source_advertiser_id": raw["source_advertiser_id"],
            "projects": [
                {
                    "project_key": "target-1-p001",
                    "advertiser_id": "target-1",
                    "project_index": 1,
                    "project_name": "首单项目",
                    "project_type": "微小每付通投",
                    "daily_budget": 1000,
                    "operation": "ENABLE",
                    "field_defaults": {
                        "landing_type": "MICRO_GAME",
                        "pricing": "PRICING_OCPM",
                        "inventory_type": "INVENTORY_FEED",
                    },
                    "units": [
                        {
                            "unit_key": "target-1-p001-u01",
                            "unit_index": 1,
                            "promotion_name": "首单单元",
                            "operation": "ENABLE",
                            "materials": [
                                {
                                    "material_id": "material-1",
                                    "material_type": "video",
                                    "source_video_id": "video-1",
                                    "name": "Material 1",
                                }
                            ],
                        }
                    ],
                }
            ],
        },
        "summary": {
            "plan_id": raw["plan_id"],
            "request_id": "req-1",
            "target_date": "2026-05-13",
            "planned_project_count": 1,
            "planned_unit_count": 1,
            "planned_material_count": 1,
            "violation_count": 0,
        },
        "violations": [],
        "actions": [],
    }


def _write_token_store(path: Path, *, access: str = "access-secret", refresh: str = "refresh-secret", expires_in: int = 3600) -> None:
    now = datetime(2026, 5, 7, 2, 0, tzinfo=timezone.utc)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "tokens": {
                    "default": {
                        "access_token": access,
                        "refresh_token": refresh,
                        "expires_at": (now + timedelta(seconds=expires_in)).isoformat(),
                        "refresh_token_expires_at": (now + timedelta(days=30)).isoformat(),
                        "updated_at": now.isoformat(),
                    }
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


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


def _write_allowed_accounts(path: Path, rows: list[dict]) -> Path:
    path.write_text(json.dumps({"allowed_target_accounts": rows}, ensure_ascii=False), encoding="utf-8")
    return path


def test_create_live_execute_once_direct_mode_blocks_without_runtime_or_pack(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)

    result = run_create_live_execute_once_request(
        {
            "create_live_execute_once": {
                "create_execute_artifact": _execute_artifact(),
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
    assert "source_execution_pack_status" not in result
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
    assert "source_execution_pack_status" not in result
    assert result["execution_enabled"] is True
    assert result["live_execute_enabled"] is True
    assert result["external_api_calls"] == 3
    assert [call["operation"] for call in calls] == [
        "create_project",
        "lookup_target_material",
        "create_unit",
    ]
    assert result["ordered_steps"][1]["status"] == "skipped_existing_target_material"


def test_lookup_target_material_retries_when_bound_material_is_not_visible_yet(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)
    artifact = _execute_artifact()
    artifact["resolved_provider_payload_drafts"] = [
        draft
        for draft in artifact["resolved_provider_payload_drafts"]
        if draft["operation"] != "bind_material"
    ]
    policy = _policy()
    policy["create_live_execute_once"]["lookup_target_material_visibility_wait"] = {
        "enabled": True,
        "max_retries": 1,
        "sleep_seconds": 0,
    }
    calls: list[dict] = []
    lookup_count = {"value": 0}

    def fake_transport(call: dict) -> dict:
        calls.append(call)
        if call["operation"] == "create_project":
            return {"code": 0, "data": {"project_id": "project-001"}}
        if call["operation"] == "lookup_target_material":
            lookup_count["value"] += 1
            if lookup_count["value"] == 1:
                return {"code": 0, "data": {"list": []}}
            return {
                "code": 0,
                "data": {"list": [{"id": "target-video-001", "material_id": "material-1", "cover_id": "target-cover-001"}]},
            }
        if call["operation"] == "create_unit":
            assert call["payload"]["promotion_materials"]["video_material_list"][0]["video_id"] == "target-video-001"
            return {"code": 0, "data": {"promotion_id": "promotion-001"}}
        raise AssertionError(call["operation"])

    result = run_create_live_execute_once_request(
        {
            "create_live_execute_once": {
                "create_execute_artifact": artifact,
                "policy": policy,
                "runtime": {"execution_enabled": True, "external_api_enabled": True},
            }
        },
        runs_dir=tmp_path / "runs",
        db_path=db_path,
        transport=fake_transport,
    )

    assert result["ok"] is True
    assert lookup_count["value"] == 2
    assert [call["operation"] for call in calls] == [
        "create_project",
        "lookup_target_material",
        "lookup_target_material",
        "create_unit",
    ]


def test_create_live_execute_once_deletes_closed_projects_and_retries_when_project_cap_is_hit(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)
    calls: list[dict] = []
    create_attempts = {"count": 0}

    def fake_transport(call: dict) -> dict:
        calls.append(call)
        if call["operation"] == "create_project":
            create_attempts["count"] += 1
            if create_attempts["count"] == 1:
                return {"code": 40000, "message": "广告主已创建30个项目，请删除部分项目后再试"}
            return {"code": 0, "data": {"project_id": "project-001"}}
        if call["operation"] == "lookup_disabled_projects":
            assert call["payload"]["advertiser_id"] == "target-1"
            return {
                "code": 0,
                "data": {
                    "list": [
                        {"project_id": f"closed-{index:02d}", "project_status": "PROJECT_STATUS_DISABLE"}
                        for index in range(1, 13)
                    ]
                },
            }
        if call["operation"] == "delete_project":
            assert call["payload"]["advertiser_id"] == "target-1"
            return {"code": 0, "data": {"project_ids": call["payload"]["project_ids"]}}
        if call["operation"] == "bind_material":
            return {"code": 0, "data": {"task_id": "bind-001"}}
        if call["operation"] == "lookup_target_material":
            return {"code": 0, "data": {"target_video_id": "target-video-001", "target_video_cover_id": "target-cover-001"}}
        if call["operation"] == "create_unit":
            assert call["payload"]["project_id"] == "project-001"
            return {"code": 0, "data": {"promotion_id": "promotion-001"}}
        raise AssertionError(call["operation"])

    result = run_create_live_execute_once_request(
        {
            "create_live_execute_once": {
                "create_execute_artifact": _execute_artifact(),
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
    assert result["external_api_calls"] == 15
    assert [call["operation"] for call in calls] == [
        "create_project",
        "lookup_disabled_projects",
        *["delete_project"] * 10,
        "create_project",
        "lookup_target_material",
        "create_unit",
    ]
    assert [call["payload"]["project_ids"][0] for call in calls if call["operation"] == "delete_project"] == [
        f"closed-{index:02d}" for index in range(1, 11)
    ]
    assert result["project_cap_cleanup"]["attempted_count"] == 1
    assert result["project_cap_cleanup"]["deleted_count"] == 10
    assert result["project_cap_cleanup"]["records"][0]["status"] == "deleted_and_retried"


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


def test_create_live_execute_once_direct_mode_allows_active_create_payload(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)
    create_execute = json.loads(json.dumps(_execute_artifact(), ensure_ascii=False))
    create_execute["resolved_provider_payload_drafts"][0]["payload"]["status"] = "ACTIVE"

    result = run_create_live_execute_once_request(
        {
            "create_live_execute_once": {
                "create_execute_artifact": create_execute,
                "policy": _policy(),
                "runtime": {"execution_enabled": True, "external_api_enabled": True},
            }
        },
        runs_dir=tmp_path / "runs",
        db_path=db_path,
        transport=lambda _call: {"code": 0},
    )

    assert result["ok"] is False
    assert result["external_api_calls"] > 0
    assert result["blocking_reasons"] == []
    assert "create_project.status must not be ACTIVE during create" not in result["blocking_reasons"]


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
    assert result["external_api_calls"] == 3
    assert result["transport_call_count"] == 3
    assert [call["operation"] for call in calls] == [
        "create_project",
        "lookup_target_material",
        "create_unit",
    ]
    assert result["ordered_steps"] == [
        {"operation": "create_project", "planned_count": 1, "status": "completed", "test_transport_call_count": 1},
        {
            "operation": "bind_material",
            "planned_count": 1,
            "status": "skipped_existing_target_material",
            "test_transport_call_count": 1,
        },
        {
            "operation": "lookup_target_material",
            "planned_count": 1,
            "status": "skipped_existing_provider_id",
            "test_transport_call_count": 0,
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
        ("source-1", '["target-1"]', '["video-1"]', "existing_target_material", "active"),
    ]


def test_create_live_execute_once_returns_failure_artifact_for_transport_error(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)
    calls: list[str] = []

    def fake_transport(call: dict) -> dict:
        calls.append(call["operation"])
        if call["operation"] == "create_project":
            raise RuntimeError("create HTTP request failed with transient network error")
        if call["operation"] == "lookup_existing_project":
            return {"code": 0, "data": {"list": []}}
        raise AssertionError(call["operation"])

    result = run_create_live_execute_once_request(
        {
            "create_live_execute_once": {
                "create_execute_artifact": _execute_artifact(),
                "policy": _policy(),
                "runtime": {"execution_enabled": True, "external_api_enabled": True},
            }
        },
        runs_dir=tmp_path / "runs",
        db_path=db_path,
        transport=fake_transport,
    )

    assert result["ok"] is False
    assert result["status"] == "create_http_failed"
    assert result["external_api_calls"] == 4
    assert calls == ["create_project", "lookup_existing_project", "create_project", "lookup_existing_project"]
    assert result["failure"] == {
        "operation": "create_project",
        "index": 0,
        "message": "create HTTP request failed with transient network error",
        "code": -1,
    }
    assert Path(result["artifact_path"]).exists()


def test_create_live_execute_once_skips_account_after_material_bind_failure_and_continues(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)
    artifact = _execute_artifact()
    artifact["summary"] = {
        **artifact["summary"],
        "project_count": 2,
        "unit_count": 2,
        "material_count": 2,
    }
    artifact["resolved_provider_payload_drafts"] = [
        {
            "operation": "create_project",
            "payload": {"advertiser_id": "target-1", "name": "项目1"},
            "executable": False,
            "live_api_payload": False,
        },
        {
            "operation": "create_project",
            "payload": {"advertiser_id": "target-2", "name": "项目2"},
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
            "operation": "bind_material",
            "payload": {
                "source_advertiser_id": "source-1",
                "target_advertiser_ids": ["target-2"],
                "source_video_ids": ["video-2"],
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
        {
            "operation": "lookup_target_material",
            "payload": {
                "target_advertiser_id": "target-2",
                "source_video_id": "video-2",
                "material_id": "material-2",
            },
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
            "operation": "create_unit",
            "payload": {
                "advertiser_id": "target-2",
                "project_id": "<lookup:target-2-p001>",
                "promotion_materials": {
                    "video_material_list": [
                        {
                            "video_id": "<lookup:target_video:target-2:video-2>",
                            "video_cover_id": "<lookup:target_video_cover:target-2:video-2>",
                        }
                    ]
                },
            },
            "executable": False,
            "live_api_payload": False,
        },
    ]
    artifact["provider_id_ledger_requirements"] = {
        "produced_by_create_project": [
            {"local_key": "target-1-p001", "advertiser_id": "target-1", "parent_local_key": ""},
            {"local_key": "target-2-p001", "advertiser_id": "target-2", "parent_local_key": ""},
        ],
        "produced_by_create_unit": [
            {"local_key": "target-1-p001-u01", "advertiser_id": "target-1", "parent_local_key": "target-1-p001"},
            {"local_key": "target-2-p001-u01", "advertiser_id": "target-2", "parent_local_key": "target-2-p001"},
        ],
        "required_before_create_unit": [
            {"entity_type": "project", "local_key": "target-1-p001"},
            {"entity_type": "project", "local_key": "target-2-p001"},
            {"entity_type": "target_video", "local_key": "target_video:target-1:video-1"},
            {"entity_type": "target_video_cover", "local_key": "target_video_cover:target-1:video-1"},
            {"entity_type": "target_video", "local_key": "target_video:target-2:video-2"},
            {"entity_type": "target_video_cover", "local_key": "target_video_cover:target-2:video-2"},
        ],
        "required_before_bind_material": [
            {"local_key": "target-1-p001-u01"},
            {"local_key": "target-2-p001-u01"},
        ],
    }
    calls: list[dict] = []
    bound_targets: set[str] = set()

    def fake_transport(call: dict) -> dict:
        calls.append(call)
        operation = call["operation"]
        payload = call["payload"]
        if operation == "create_project":
            return {"code": 0, "data": {"project_id": f"project-{payload['advertiser_id']}"}}
        if operation == "bind_material":
            target_id = payload["target_advertiser_ids"][0]
            if target_id == "target-2":
                return {"code": 40000, "message": "部分视频无权限或不存在"}
            bound_targets.add(target_id)
            return {"code": 0, "data": {"task_id": f"bind-{target_id}"}}
        if operation == "lookup_target_material":
            target_id = str(payload.get("target_advertiser_id") or payload.get("advertiser_id") or "")
            if target_id not in bound_targets:
                return {"code": 0, "data": {"list": []}}
            return {
                "code": 0,
                "data": {
                    "list": [
                        {
                            "material_id": "material-1",
                            "video_id": "target-video-1",
                            "video_cover_id": "target-cover-1",
                        }
                    ]
                },
            }
        if operation == "create_unit":
            assert payload["advertiser_id"] == "target-1"
            return {"code": 0, "data": {"promotion_id": "promotion-target-1"}}
        raise AssertionError(operation)

    result = run_create_live_execute_once_request(
        {
            "create_live_execute_once": {
                "create_execute_artifact": artifact,
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
    assert result["skipped_accounts"] == [
        {
            "operation": "bind_material",
            "index": 1,
            "advertiser_id": "target-2",
            "status": "skipped_account_after_live_step_failure",
            "code": 40000,
            "message": "部分视频无权限或不存在",
        },
        {
            "operation": "lookup_target_material",
            "index": 1,
            "advertiser_id": "target-2",
            "status": "skipped_account_after_create_project_failure",
        },
        {
            "operation": "create_unit",
            "index": 1,
            "advertiser_id": "target-2",
            "status": "skipped_account_after_create_project_failure",
        },
    ]
    assert [call["operation"] for call in calls].count("create_unit") == 1


def test_create_live_execute_once_retries_transient_unit_failure_after_batch(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)
    artifact = _execute_artifact()
    artifact["summary"] = {
        **artifact["summary"],
        "project_count": 2,
        "unit_count": 2,
        "material_count": 2,
    }
    artifact["resolved_provider_payload_drafts"] = [
        {
            "operation": "create_project",
            "payload": {"advertiser_id": "target-1", "name": "项目1"},
            "executable": False,
            "live_api_payload": False,
        },
        {
            "operation": "create_project",
            "payload": {"advertiser_id": "target-2", "name": "项目2"},
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
            "operation": "bind_material",
            "payload": {
                "source_advertiser_id": "source-1",
                "target_advertiser_ids": ["target-2"],
                "source_video_ids": ["video-2"],
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
        {
            "operation": "lookup_target_material",
            "payload": {
                "target_advertiser_id": "target-2",
                "source_video_id": "video-2",
                "material_id": "material-2",
            },
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
            "operation": "create_unit",
            "payload": {
                "advertiser_id": "target-2",
                "project_id": "<lookup:target-2-p001>",
                "promotion_materials": {
                    "video_material_list": [
                        {
                            "video_id": "<lookup:target_video:target-2:video-2>",
                            "video_cover_id": "<lookup:target_video_cover:target-2:video-2>",
                        }
                    ]
                },
            },
            "executable": False,
            "live_api_payload": False,
        },
    ]
    artifact["provider_id_ledger_requirements"] = {
        "produced_by_create_project": [
            {"local_key": "target-1-p001", "advertiser_id": "target-1", "parent_local_key": ""},
            {"local_key": "target-2-p001", "advertiser_id": "target-2", "parent_local_key": ""},
        ],
        "produced_by_create_unit": [
            {"local_key": "target-1-p001-u01", "advertiser_id": "target-1", "parent_local_key": "target-1-p001"},
            {"local_key": "target-2-p001-u01", "advertiser_id": "target-2", "parent_local_key": "target-2-p001"},
        ],
        "required_before_create_unit": [
            {"entity_type": "project", "local_key": "target-1-p001"},
            {"entity_type": "project", "local_key": "target-2-p001"},
            {"entity_type": "target_video", "local_key": "target_video:target-1:video-1"},
            {"entity_type": "target_video_cover", "local_key": "target_video_cover:target-1:video-1"},
            {"entity_type": "target_video", "local_key": "target_video:target-2:video-2"},
            {"entity_type": "target_video_cover", "local_key": "target_video_cover:target-2:video-2"},
        ],
        "required_before_bind_material": [
            {"local_key": "target-1-p001-u01"},
            {"local_key": "target-2-p001-u01"},
        ],
    }
    for advertiser_id, source_video_id, video_id, cover_id in [
        ("target-1", "video-1", "target-video-1", "target-cover-1"),
        ("target-2", "video-2", "target-video-2", "target-cover-2"),
    ]:
        record_create_provider_id(
            db_path=db_path,
            entity_type="target_video",
            local_key=f"target_video:{advertiser_id}:{source_video_id}",
            provider_id=video_id,
            source_workflow="create_live_execute_once",
        )
        record_create_provider_id(
            db_path=db_path,
            entity_type="target_video_cover",
            local_key=f"target_video_cover:{advertiser_id}:{source_video_id}",
            provider_id=cover_id,
            source_workflow="create_live_execute_once",
        )
        record_create_material_bind_result(
            db_path=db_path,
            source_advertiser_id="source-1",
            target_advertiser_ids=[advertiser_id],
            source_video_ids=[source_video_id],
            provider_task_id=f"bind-{advertiser_id}",
            plan_id="plan-1",
            request_id="req-1",
            source_workflow="create_live_execute_once",
            response_payload={"code": 0, "data_keys": ["task_id"]},
        )
    calls: list[dict] = []
    unit_attempts: dict[str, int] = {}

    def fake_transport(call: dict) -> dict:
        calls.append(call)
        operation = call["operation"]
        payload = call["payload"]
        if operation == "create_project":
            return {"code": 0, "data": {"project_id": f"project-{payload['advertiser_id']}"}}
        if operation == "create_unit":
            advertiser_id = payload["advertiser_id"]
            unit_attempts[advertiser_id] = unit_attempts.get(advertiser_id, 0) + 1
            if advertiser_id == "target-2" and unit_attempts[advertiser_id] == 1:
                return {"code": 50000, "message": "服务内部错误，请稍后重试"}
            return {"code": 0, "data": {"promotion_id": f"promotion-{advertiser_id}-{unit_attempts[advertiser_id]}"}}
        raise AssertionError(operation)

    result = run_create_live_execute_once_request(
        {
            "create_live_execute_once": {
                "create_execute_artifact": artifact,
                "policy": _policy(),
                "runtime": {"execution_enabled": True, "external_api_enabled": True},
            }
        },
        runs_dir=tmp_path / "runs",
        db_path=db_path,
        transport=fake_transport,
    )

    assert result["ok"] is True
    assert [call["operation"] for call in calls] == [
        "create_project",
        "create_project",
        "create_unit",
        "create_unit",
        "create_unit",
    ]
    assert result["skipped_accounts"] == [
        {
            "operation": "create_unit",
            "index": 1,
            "advertiser_id": "target-2",
            "status": "skipped_account_after_live_step_failure",
            "code": 50000,
            "message": "服务内部错误，请稍后重试",
        }
    ]
    assert result["post_run_retry"]["status"] == "completed"
    assert result["post_run_retry"]["attempted_count"] == 1
    assert result["post_run_retry"]["recovered_count"] == 1
    assert result["external_api_calls"] == 5
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT provider_id, status
            FROM create_provider_id_ledger
            WHERE entity_type = 'promotion' AND local_key = 'target-2-p001-u01'
            """
        ).fetchone()
    assert row == ("promotion-target-2-2", "archived")


def test_create_live_execute_once_retries_create_project_after_lookup_confirms_missing(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)
    calls: list[dict] = []
    create_attempts = {"count": 0}

    def fake_transport(call: dict) -> dict:
        calls.append(call)
        if call["operation"] == "create_project":
            create_attempts["count"] += 1
            if create_attempts["count"] == 1:
                raise RuntimeError("create HTTP request failed with transient network error")
            return {"code": 0, "data": {"project_id": "project-001"}}
        if call["operation"] == "lookup_existing_project":
            assert call["payload"] == {"advertiser_id": "target-1", "name": "首单项目"}
            return {"code": 0, "data": {"list": []}}
        if call["operation"] == "bind_material":
            return {"code": 0, "data": {"task_id": "bind-001"}}
        if call["operation"] == "lookup_target_material":
            return {"code": 0, "data": {"target_video_id": "target-video-001", "target_video_cover_id": "target-cover-001"}}
        if call["operation"] == "create_unit":
            assert call["payload"]["project_id"] == "project-001"
            return {"code": 0, "data": {"promotion_id": "promotion-001"}}
        raise AssertionError(call["operation"])

    result = run_create_live_execute_once_request(
        {
            "create_live_execute_once": {
                "create_execute_artifact": _execute_artifact(),
                "policy": _policy(),
                "runtime": {"execution_enabled": True, "external_api_enabled": True},
            }
        },
        runs_dir=tmp_path / "runs",
        db_path=db_path,
        transport=fake_transport,
    )

    assert result["ok"] is True
    assert [call["operation"] for call in calls] == [
        "create_project",
        "lookup_existing_project",
        "create_project",
        "lookup_target_material",
        "create_unit",
    ]
    assert result["external_api_calls"] == 5


def test_create_live_execute_once_returns_failure_when_recovery_lookup_fails(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)
    calls: list[str] = []

    def fake_transport(call: dict) -> dict:
        calls.append(call["operation"])
        if call["operation"] == "create_project":
            raise RuntimeError("create HTTP request failed with transient network error")
        if call["operation"] == "lookup_existing_project":
            raise RuntimeError("project lookup failed")
        raise AssertionError(call["operation"])

    result = run_create_live_execute_once_request(
        {
            "create_live_execute_once": {
                "create_execute_artifact": _execute_artifact(),
                "policy": _policy(),
                "runtime": {"execution_enabled": True, "external_api_enabled": True},
            }
        },
        runs_dir=tmp_path / "runs",
        db_path=db_path,
        transport=fake_transport,
    )

    assert result["ok"] is False
    assert result["status"] == "create_http_failed"
    assert result["external_api_calls"] == 2
    assert calls == ["create_project", "lookup_existing_project"]
    assert result["failure"] == {
        "operation": "lookup_existing_project",
        "index": 0,
        "message": "project lookup failed",
        "code": -1,
    }


def test_create_live_execute_once_records_existing_unit_after_transient_create_error(tmp_path: Path):
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
            return {"code": 40000, "message": "网络异常"}
        if call["operation"] == "lookup_existing_unit":
            assert call["payload"] == {
                "advertiser_id": "target-1",
                "project_id": "project-001",
                "name": "",
            }
            return {"code": 0, "data": {"list": [{"promotion_id": "promotion-existing", "promotion_name": ""}]}}
        raise AssertionError(call["operation"])

    result = run_create_live_execute_once_request(
        {
            "create_live_execute_once": {
                "create_execute_artifact": _execute_artifact(),
                "policy": _policy(),
                "runtime": {"execution_enabled": True, "external_api_enabled": True},
            }
        },
        runs_dir=tmp_path / "runs",
        db_path=db_path,
        transport=fake_transport,
    )

    assert result["ok"] is True
    assert [call["operation"] for call in calls] == [
        "create_project",
        "lookup_target_material",
        "create_unit",
        "lookup_existing_unit",
    ]
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT provider_id
            FROM create_provider_id_ledger
            WHERE entity_type = 'promotion' AND local_key = 'target-1-p001-u01'
            """
        ).fetchone()
    assert row == ("promotion-existing",)


def test_create_live_execute_once_batches_target_material_lookup_by_account(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)
    create_execute = json.loads(json.dumps(_execute_artifact(), ensure_ascii=False))
    create_execute["resolved_provider_payload_drafts"].append(
        {
            "operation": "lookup_target_material",
            "payload": {
                "target_advertiser_id": "target-1",
                "source_video_id": "video-2",
                "material_id": "material-2",
            },
            "executable": False,
            "live_api_payload": False,
        }
    )
    create_execute["provider_id_ledger_requirements"]["required_before_create_unit"].extend(
        [
            {"entity_type": "target_video", "local_key": "target_video:target-1:video-2"},
            {"entity_type": "target_video_cover", "local_key": "target_video_cover:target-1:video-2"},
        ]
    )
    calls: list[dict] = []

    def fake_transport(call: dict) -> dict:
        calls.append(call)
        if call["operation"] == "create_project":
            return {"code": 0, "data": {"project_id": "project-001"}}
        if call["operation"] == "bind_material":
            return {"code": 0, "data": {"task_id": "bind-001"}}
        if call["operation"] == "lookup_target_material":
            if call["payload"]["material_ids"] == ["material-1"]:
                return {"code": 0, "data": {"list": []}}
            assert call["payload"]["material_ids"] == ["material-1", "material-2"]
            return {
                "code": 0,
                "data": {
                    "list": [
                        {"material_id": "material-1", "id": "target-video-001", "video_cover_id": "target-cover-001"},
                        {"material_id": "material-2", "id": "target-video-002", "video_cover_id": "target-cover-002"},
                    ]
                },
            }
        if call["operation"] == "create_unit":
            return {"code": 0, "data": {"promotion_id": "promotion-001"}}
        raise AssertionError(call["operation"])

    result = run_create_live_execute_once_request(
        {
            "create_live_execute_once": {
                "create_execute_artifact": create_execute,
                "policy": _policy(),
                "runtime": {"execution_enabled": True, "external_api_enabled": True},
            }
        },
        runs_dir=tmp_path / "runs",
        db_path=db_path,
        transport=fake_transport,
    )

    assert result["ok"] is True
    assert [call["operation"] for call in calls] == [
        "create_project",
        "lookup_target_material",
        "bind_material",
        "lookup_target_material",
        "create_unit",
    ]
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT entity_type, local_key, provider_id
            FROM create_provider_id_ledger
            WHERE entity_type IN ('target_video', 'target_video_cover')
            ORDER BY local_key
            """
        ).fetchall()
    assert rows == [
        ("target_video", "target_video:target-1:video-1", "target-video-001"),
        ("target_video", "target_video:target-1:video-2", "target-video-002"),
        ("target_video_cover", "target_video_cover:target-1:video-1", "target-cover-001"),
        ("target_video_cover", "target_video_cover:target-1:video-2", "target-cover-002"),
    ]


def test_create_live_execute_once_resumes_existing_project_in_same_round(tmp_path: Path):
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
            return {"code": 0, "data": {"project_id": "project-new"}}
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
    assert result["external_api_calls"] == 2
    assert [call["operation"] for call in calls] == ["lookup_target_material", "create_unit"]
    assert result["idempotency"]["skipped_existing_provider_id_count"] == 3
    assert result["ordered_steps"][0] == {
        "operation": "create_project",
        "planned_count": 1,
        "status": "skipped_existing_provider_id",
        "test_transport_call_count": 0,
    }
    assert result["ledger_archive"][0]["stage"] == "after_run"

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT entity_type, local_key, provider_id, status
            FROM create_provider_id_ledger
            ORDER BY entity_type, local_key
            """
        ).fetchall()
    assert rows == [
        ("project", "target-1-p001", "project-existing", "archived"),
        ("promotion", "target-1-p001-u01", "promotion-001", "archived"),
        ("target_video", "target_video:target-1:video-1", "target-video-001", "active"),
        ("target_video_cover", "target_video_cover:target-1:video-1", "target-cover-001", "active"),
    ]


def test_create_live_execute_once_ignores_mock_provider_ids_during_live_run(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)
    record_create_provider_id(
        db_path=db_path,
        entity_type="project",
        local_key="target-1-p001",
        provider_id="mock_project_target_1_p001",
        plan_id="old-plan",
        request_id="old-req",
        advertiser_id="target-1",
        source_workflow="create_mock_execute",
    )
    record_create_provider_id(
        db_path=db_path,
        entity_type="promotion",
        local_key="target-1-p001-u01",
        provider_id="mock_promotion_target_1_p001_u01",
        plan_id="old-plan",
        request_id="old-req",
        advertiser_id="target-1",
        parent_local_key="target-1-p001",
        source_workflow="create_mock_execute",
    )
    calls: list[dict] = []

    def fake_transport(call: dict) -> dict:
        calls.append(call)
        if call["operation"] == "create_project":
            return {"code": 0, "data": {"project_id": "project-real"}}
        if call["operation"] == "bind_material":
            return {"code": 0, "data": {"task_id": "bind-001"}}
        if call["operation"] == "lookup_target_material":
            return {"code": 0, "data": {"target_video_id": "target-video-real", "target_video_cover_id": "target-cover-real"}}
        if call["operation"] == "create_unit":
            assert call["payload"]["project_id"] == "project-real"
            return {"code": 0, "data": {"promotion_id": "promotion-real"}}
        raise AssertionError(call["operation"])

    result = run_create_live_execute_once_request(
        {
            "create_live_execute_once": {
                "create_execute_artifact": _execute_artifact(),
                "policy": _policy(),
                "runtime": {"execution_enabled": True, "external_api_enabled": True},
            }
        },
        runs_dir=tmp_path / "runs",
        db_path=db_path,
        transport=fake_transport,
    )

    assert result["ok"] is True
    assert [call["operation"] for call in calls] == [
        "create_project",
        "lookup_target_material",
        "create_unit",
    ]
    assert result["idempotency"]["skipped_existing_provider_id_count"] == 2
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT entity_type, local_key, provider_id, source_workflow
            FROM create_provider_id_ledger
            ORDER BY entity_type, local_key
            """
        ).fetchall()
    assert ("project", "target-1-p001", "project-real", "create_live_execute_once") in rows
    assert ("promotion", "target-1-p001-u01", "promotion-real", "create_live_execute_once") in rows


def test_create_live_execute_once_replaces_invalid_provider_id_record(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)
    record_create_provider_id(
        db_path=db_path,
        entity_type="target_video",
        local_key="target_video:target-1:video-1",
        provider_id="wrong-video-id",
        source_workflow="create_live_execute_once",
    )
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            UPDATE create_provider_id_ledger
            SET status = 'invalid'
            WHERE entity_type = 'target_video'
              AND local_key = 'target_video:target-1:video-1'
            """
        )
    record = record_create_provider_id(
        db_path=db_path,
        entity_type="target_video",
        local_key="target_video:target-1:video-1",
        provider_id="correct-video-id",
        source_workflow="create_live_execute_once",
    )

    assert record["status"] == "recorded"
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT provider_id, status
            FROM create_provider_id_ledger
            WHERE entity_type = 'target_video'
              AND local_key = 'target_video:target-1:video-1'
            """
        ).fetchone()
    assert row == ("correct-video-id", "active")


def test_create_live_execute_once_skips_existing_project_and_unit_in_same_round(tmp_path: Path):
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
        if call["operation"] == "create_project":
            return {"code": 0, "data": {"project_id": "project-new"}}
        if call["operation"] == "create_unit":
            assert call["payload"]["project_id"] == "project-new"
            return {"code": 0, "data": {"promotion_id": "promotion-new"}}
        if call["operation"] == "bind_material":
            return {"code": 0, "data": {"task_id": "bind-001"}}
        if call["operation"] == "lookup_target_material":
            return {"code": 0, "data": {"target_video_id": "target-video-001", "target_video_cover_id": "target-cover-001"}}
        raise AssertionError(call["operation"])

    result = run_create_live_execute_once_request(
        {
            "create_live_execute_once": {
                "create_execute_artifact": _execute_artifact(),
                "policy": _policy(),
                "runtime": {"execution_enabled": True, "external_api_enabled": True},
            }
        },
        runs_dir=tmp_path / "runs",
        db_path=db_path,
        transport=fake_transport,
    )

    assert result["ok"] is True
    assert result["external_api_calls"] == 1
    assert [call["operation"] for call in calls] == ["lookup_target_material"]
    assert result["idempotency"]["skipped_existing_provider_id_count"] == 4
    assert [step["status"] for step in result["ordered_steps"]] == [
        "skipped_existing_provider_id",
        "skipped_existing_target_material",
        "skipped_existing_provider_id",
        "skipped_existing_provider_id",
    ]


def test_create_live_execute_once_does_not_reuse_project_or_unit_from_different_plan(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)
    record_create_provider_id(
        db_path=db_path,
        entity_type="project",
        local_key="target-1-p001",
        provider_id="project-from-old-plan",
        plan_id="old-plan",
        request_id="old-req",
        advertiser_id="target-1",
        source_workflow="create_live_execute_once",
    )
    record_create_provider_id(
        db_path=db_path,
        entity_type="promotion",
        local_key="target-1-p001-u01",
        provider_id="promotion-from-old-plan",
        plan_id="old-plan",
        request_id="old-req",
        advertiser_id="target-1",
        parent_local_key="target-1-p001",
        source_workflow="create_live_execute_once",
    )
    record_create_provider_id(
        db_path=db_path,
        entity_type="target_video",
        local_key="target_video:target-1:video-1",
        provider_id="target-video-from-old-plan",
        plan_id="old-plan",
        request_id="old-req",
        source_workflow="create_live_execute_once",
    )
    record_create_provider_id(
        db_path=db_path,
        entity_type="target_video_cover",
        local_key="target_video_cover:target-1:video-1",
        provider_id="target-cover-from-old-plan",
        plan_id="old-plan",
        request_id="old-req",
        source_workflow="create_live_execute_once",
    )
    calls: list[dict] = []

    def fake_transport(call: dict) -> dict:
        calls.append(call)
        if call["operation"] == "create_project":
            return {"code": 0, "data": {"project_id": "project-new-plan"}}
        if call["operation"] == "create_unit":
            assert call["payload"]["project_id"] == "project-new-plan"
            material = call["payload"]["promotion_materials"]["video_material_list"][0]
            assert material["video_id"] == "target-video-from-old-plan"
            assert material["video_cover_id"] == "target-cover-from-old-plan"
            return {"code": 0, "data": {"promotion_id": "promotion-new-plan"}}
        raise AssertionError(f"{call['operation']} should be skipped by target material ledger")

    result = run_create_live_execute_once_request(
        {
            "create_live_execute_once": {
                "create_execute_artifact": _execute_artifact(),
                "policy": _policy(),
                "runtime": {"execution_enabled": True, "external_api_enabled": True},
            }
        },
        runs_dir=tmp_path / "runs",
        db_path=db_path,
        transport=fake_transport,
    )

    assert result["ok"] is True
    assert [call["operation"] for call in calls] == ["create_project", "create_unit"]
    assert result["idempotency"]["skipped_existing_provider_id_count"] == 2
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT entity_type, local_key, provider_id, plan_id, status
            FROM create_provider_id_ledger
            WHERE entity_type IN ('project', 'promotion')
            ORDER BY entity_type, plan_id, provider_id
            """
        ).fetchall()
    assert rows == [
        ("project", "target-1-p001", "project-from-old-plan", "old-plan", "active"),
        ("project", "target-1-p001", "project-new-plan", "plan-1", "archived"),
        ("promotion", "target-1-p001-u01", "promotion-from-old-plan", "old-plan", "active"),
        ("promotion", "target-1-p001-u01", "promotion-new-plan", "plan-1", "archived"),
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
        if call["operation"] == "create_project":
            return {"code": 0, "data": {"project_id": "project-new"}}
        if call["operation"] == "create_unit":
            assert call["payload"]["project_id"] == "project-existing"
            assert call["payload"]["promotion_materials"]["video_material_list"][0]["video_id"] == "target-video-existing"
            return {"code": 0, "data": {"promotion_id": "promotion-new"}}
        raise AssertionError(f"{call['operation']} must not be called")

    result = run_create_live_execute_once_request(
        {
            "create_live_execute_once": {
                "create_execute_artifact": _execute_artifact(),
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


def test_material_bind_ledger_accepts_provider_payload_field_names():
    assert material_bind_key_from_payload(
        {
            "advertiser_id": "source-1",
            "target_advertiser_ids": ["target-1"],
            "video_ids": ["video-1"],
        }
    ) == material_bind_key_from_payload(
        {
            "source_advertiser_id": "source-1",
            "target_advertiser_ids": ["target-1"],
            "source_video_ids": ["video-1"],
        }
    )


def test_run_create_live_execute_once_request_writes_blocked_artifact(tmp_path: Path):
    result = run_create_live_execute_once_request(
        {
            "create_live_execute_once": {
                "create_execute_artifact": _execute_artifact(),
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


def test_create_live_execute_once_request_rejects_unknown_request_options(tmp_path: Path):
    with pytest.raises(ValueError, match="unexpected options"):
        run_create_live_execute_once_request(
            {
                "create_live_execute_once": {
                    "create_execute_artifact": _execute_artifact(),
                    "extra_pack": {"unexpected": True},
                    "policy": _policy(),
                    "runtime": {"execution_enabled": False, "external_api_enabled": False},
                }
            },
            runs_dir=tmp_path / "runs",
            db_path=tmp_path / "roibang.sqlite3",
        )


def test_create_live_execute_once_fixed_script_keeps_default_runtime_blocked(tmp_path: Path, capsys):
    runtime_path = _runtime_config(tmp_path)
    _seed_plan_sources(tmp_path / "roibang.sqlite3")
    policy_path = tmp_path / "policy.json"
    plan_path = tmp_path / "create-plan.json"
    policy_path.write_text(json.dumps(_policy(), ensure_ascii=False), encoding="utf-8")
    plan_path.write_text(json.dumps(_create_plan(), ensure_ascii=False), encoding="utf-8")
    create_execute_path = tmp_path / "create-execute.json"
    create_execute_path.write_text(json.dumps(_execute_artifact(), ensure_ascii=False), encoding="utf-8")
    module = _load_script("run_create_live_execute_once")

    exit_code = module.run_from_args(
        [
            "--config",
            str(runtime_path),
            "--policy",
            str(policy_path),
            "--plan",
            str(plan_path),
            "--create-execute-artifact",
            str(create_execute_path),
        ]
    )

    output = json.loads(capsys.readouterr().out)
    artifact = json.loads(Path(output["artifact_path"]).read_text(encoding="utf-8"))
    assert exit_code == 0
    assert output["workflow"] == "create_live_execute_once"
    assert output["status"] == "blocked"
    assert output["execution_enabled"] is False
    assert output["live_execute_enabled"] is False
    assert output["external_api_calls"] == 0
    assert output["transport_call_count"] == 0
    assert output["local_config_readiness"]["ready"] is False
    assert "runtime.execution_enabled" in output["local_config_readiness"]["missing"]
    assert "create_http_transport.token_value" in output["local_config_readiness"]["missing"]
    assert "source_execution_pack_status" not in output
    assert artifact["actions"] == []
    assert artifact["local_config_readiness"]["ready"] is False


def test_create_live_execute_once_fixed_script_blocks_missing_token_without_crashing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys,
):
    monkeypatch.delenv("ROIBANG_TEST_ACCESS_TOKEN", raising=False)
    runtime_path = _runtime_config(tmp_path, execution_enabled=True, external_api_enabled=True)
    _seed_plan_sources(tmp_path / "roibang.sqlite3")
    policy = _policy()
    policy["create_live_execute_once"]["create_http_transport"].pop("token_env", None)
    policy_path = tmp_path / "policy.json"
    plan_path = tmp_path / "create-plan.json"
    policy_path.write_text(json.dumps(policy, ensure_ascii=False), encoding="utf-8")
    plan_path.write_text(json.dumps(_create_plan(), ensure_ascii=False), encoding="utf-8")
    create_execute_path = tmp_path / "create-execute.json"
    create_execute_path.write_text(json.dumps(_execute_artifact(), ensure_ascii=False), encoding="utf-8")
    module = _load_script("run_create_live_execute_once")

    exit_code = module.run_from_args(
        [
            "--config",
            str(runtime_path),
            "--policy",
            str(policy_path),
            "--plan",
            str(plan_path),
            "--create-execute-artifact",
            str(create_execute_path),
        ]
    )

    output = json.loads(capsys.readouterr().out)
    artifact = json.loads(Path(output["artifact_path"]).read_text(encoding="utf-8"))
    assert exit_code == 0
    assert output["status"] == "blocked"
    assert output["external_api_calls"] == 0
    assert output["transport_call_count"] == 0
    assert output["local_config_readiness"]["ready"] is False
    assert output["local_config_readiness"]["missing"] == [
        "create_http_transport.token_pointer",
        "create_http_transport.token_value",
    ]
    assert "create_http_transport.token_pointer" in output["blocking_reasons"][0]
    assert artifact["local_config_readiness"] == output["local_config_readiness"]


def test_create_live_execute_once_fixed_script_check_config_only_never_executes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys,
):
    monkeypatch.setenv("ROIBANG_TEST_ACCESS_TOKEN", "secret-token")
    runtime_path = _runtime_config(tmp_path, execution_enabled=True, external_api_enabled=True)
    _seed_plan_sources(tmp_path / "roibang.sqlite3")
    policy_path = tmp_path / "policy.json"
    plan_path = tmp_path / "create-plan.json"
    policy_path.write_text(json.dumps(_policy(), ensure_ascii=False), encoding="utf-8")
    plan_path.write_text(json.dumps(_create_plan(), ensure_ascii=False), encoding="utf-8")
    create_execute_path = tmp_path / "create-execute.json"
    create_execute_path.write_text(json.dumps(_execute_artifact(), ensure_ascii=False), encoding="utf-8")
    module = _load_script("run_create_live_execute_once")

    exit_code = module.run_from_args(
        [
            "--config",
            str(runtime_path),
            "--policy",
            str(policy_path),
            "--plan",
            str(plan_path),
            "--create-execute-artifact",
            str(create_execute_path),
            "--check-config-only",
        ]
    )

    captured = capsys.readouterr().out
    output = json.loads(captured)
    artifact = json.loads(Path(output["artifact_path"]).read_text(encoding="utf-8"))
    assert exit_code == 0
    assert output["ok"] is True
    assert output["status"] == "config_ready"
    assert output["execution_enabled"] is False
    assert output["live_execute_enabled"] is False
    assert output["external_api_calls"] == 0
    assert output["transport_call_count"] == 0
    assert output["local_config_readiness"]["ready"] is True
    assert output["blocking_reasons"] == []
    assert artifact["status"] == "config_ready"
    assert artifact["actions"] == []
    assert "secret-token" not in captured


def test_create_live_execute_once_fixed_script_check_config_only_does_not_require_create_execute_artifact(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys,
):
    monkeypatch.setenv("ROIBANG_TEST_ACCESS_TOKEN", "secret-token")
    runtime_path = _runtime_config(tmp_path, execution_enabled=True, external_api_enabled=True)
    _seed_plan_sources(tmp_path / "roibang.sqlite3")
    policy_path = tmp_path / "policy.json"
    plan_path = tmp_path / "create-plan.json"
    policy_path.write_text(json.dumps(_policy(), ensure_ascii=False), encoding="utf-8")
    plan_path.write_text(json.dumps(_create_plan(), ensure_ascii=False), encoding="utf-8")
    module = _load_script("run_create_live_execute_once")

    exit_code = module.run_from_args(
        [
            "--config",
            str(runtime_path),
            "--policy",
            str(policy_path),
            "--plan",
            str(plan_path),
            "--check-config-only",
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["ok"] is True
    assert output["status"] == "config_ready"
    assert output["external_api_calls"] == 0


def test_create_live_execute_once_fixed_script_can_build_internal_create_execute_from_plan(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    _seed_plan_sources(db_path)
    plan = _create_strategy_plan()
    module = _load_script("run_create_live_execute_once")

    create_execute = module._build_internal_create_execute(
        create_plan=plan,
        policy=_policy(),
        db_path=db_path,
    )

    assert create_execute["ok"] is True
    assert create_execute["summary"]["plan_id"] == "plan-1"
    assert create_execute["summary"]["request_id"] == "req-1"
    assert create_execute["generated_from_create_plan"] is True
    assert create_execute["resolved_provider_payload_drafts"]


def test_create_live_execute_once_fixed_script_keeps_old_plan_project_out_of_current_plan_scope(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    _seed_plan_sources(db_path)
    record_create_provider_id(
        db_path=db_path,
        entity_type="project",
        local_key="target-1-p001",
        provider_id="project-deleted",
        plan_id="old-plan",
        request_id="old-req",
        advertiser_id="target-1",
        source_workflow="create_live_execute_once",
    )
    plan = _create_strategy_plan()
    module = _load_script("run_create_live_execute_once")

    create_execute = module._build_internal_create_execute(
        create_plan=plan,
        policy=_policy(),
        db_path=db_path,
    )

    unit_draft = next(
        item
        for item in create_execute["resolved_provider_payload_drafts"]
        if item["operation"] == "create_unit"
    )
    assert unit_draft["payload"]["project_id"] == "<lookup:target-1-p001>"
    assert create_execute["pre_create_execute_ledger_archive"]["stage"] == "before_internal_create_execute"
    assert create_execute["pre_create_execute_ledger_archive"]["status"] == "plan_scoped_no_archive"
    assert create_execute["pre_create_execute_ledger_archive"]["archived_count"] == 0

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT status
            FROM create_provider_id_ledger
            WHERE entity_type = 'project'
              AND local_key = 'target-1-p001'
              AND provider_id = 'project-deleted'
            """
        ).fetchone()
    assert row == ("active",)


def test_create_live_execute_once_fixed_script_does_not_archive_colliding_local_keys_from_old_plan(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    _seed_plan_sources(db_path)
    record_create_provider_id(
        db_path=db_path,
        entity_type="project",
        local_key="target-1-p001",
        provider_id="project-from-old-plan",
        plan_id="old-plan",
        request_id="old-req",
        advertiser_id="target-1",
        source_workflow="create_live_execute_once",
    )
    record_create_provider_id(
        db_path=db_path,
        entity_type="promotion",
        local_key="target-1-p001-u01",
        provider_id="promotion-from-old-plan",
        plan_id="old-plan",
        request_id="old-req",
        advertiser_id="target-1",
        source_workflow="create_live_execute_once",
    )
    plan = _create_strategy_plan()
    module = _load_script("run_create_live_execute_once")

    create_execute = module._build_internal_create_execute(
        create_plan=plan,
        policy=_policy(),
        db_path=db_path,
    )

    assert create_execute["pre_create_execute_ledger_archive"]["status"] == "plan_scoped_no_archive"
    assert create_execute["pre_create_execute_ledger_archive"]["archived_count"] == 0
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT entity_type, status
            FROM create_provider_id_ledger
            WHERE provider_id IN ('project-from-old-plan', 'promotion-from-old-plan')
            ORDER BY entity_type
            """
        ).fetchall()
    assert rows == [("project", "active"), ("promotion", "active")]


def test_create_live_execute_once_fixed_script_blocks_disallowed_target_account(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys,
):
    monkeypatch.setenv("ROIBANG_TEST_ACCESS_TOKEN", "secret-token")
    runtime_path = _runtime_config(tmp_path, execution_enabled=True, external_api_enabled=True)
    _seed_plan_sources(tmp_path / "roibang.sqlite3")
    allowlist_path = _write_allowed_accounts(
        tmp_path / "allowed-create-accounts.json",
        [
            {
                "account_name": "Other Account",
                "advertiser_id": "target-2",
                "product": "yzt",
                "enable": True,
                "channel": "wx",
            }
        ],
    )
    policy = _policy()
    policy["create_plan"]["require_allowed_target_accounts"] = True
    policy["create_plan"]["allowed_target_accounts_path"] = str(allowlist_path)
    policy_path = tmp_path / "policy.json"
    plan_path = tmp_path / "create-plan.json"
    policy_path.write_text(json.dumps(policy, ensure_ascii=False), encoding="utf-8")
    plan_path.write_text(json.dumps(_create_plan(), ensure_ascii=False), encoding="utf-8")
    create_execute_path = tmp_path / "create-execute.json"
    create_execute_path.write_text(json.dumps(_execute_artifact(), ensure_ascii=False), encoding="utf-8")
    module = _load_script("run_create_live_execute_once")

    exit_code = module.run_from_args(
        [
            "--config",
            str(runtime_path),
            "--policy",
            str(policy_path),
            "--plan",
            str(plan_path),
            "--create-execute-artifact",
            str(create_execute_path),
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["status"] == "blocked"
    assert output["external_api_calls"] == 0
    assert output["transport_call_count"] == 0
    assert "target account not in allowed create account list: target-1" in output["blocking_reasons"]
    assert output["allowed_account_contract"]["missing_allowed_target_accounts"] == ["target-1"]


def test_create_live_execute_once_fixed_script_blocks_expired_token_store_without_leaking_secret(
    tmp_path: Path,
    capsys,
):
    runtime_path = _runtime_config(tmp_path, execution_enabled=True, external_api_enabled=True)
    _seed_plan_sources(tmp_path / "roibang.sqlite3")
    token_store_path = tmp_path / "secrets" / "tokens.json"
    _write_token_store(
        token_store_path,
        access="access-secret",
        refresh="refresh-secret",
        expires_in=-60,
    )
    policy = _policy()
    transport = policy["create_live_execute_once"]["create_http_transport"]
    transport.pop("token_env", None)
    transport["token_store"] = {
        "enabled": True,
        "store_file": str(token_store_path),
        "user_id": "default",
        "auto_refresh": False,
    }
    policy_path = tmp_path / "policy.json"
    plan_path = tmp_path / "create-plan.json"
    policy_path.write_text(json.dumps(policy, ensure_ascii=False), encoding="utf-8")
    plan_path.write_text(json.dumps(_create_plan(), ensure_ascii=False), encoding="utf-8")
    create_execute_path = tmp_path / "create-execute.json"
    create_execute_path.write_text(json.dumps(_execute_artifact(), ensure_ascii=False), encoding="utf-8")
    module = _load_script("run_create_live_execute_once")

    exit_code = module.run_from_args(
        [
            "--config",
            str(runtime_path),
            "--policy",
            str(policy_path),
            "--plan",
            str(plan_path),
            "--create-execute-artifact",
            str(create_execute_path),
        ]
    )

    captured = capsys.readouterr().out
    output = json.loads(captured)
    assert exit_code == 0
    assert output["status"] == "blocked"
    assert output["external_api_calls"] == 0
    assert output["transport_call_count"] == 0
    assert output["local_config_readiness"]["token_pointer"] == "token_store"
    assert output["local_config_readiness"]["token_health"]["status"] == "expired"
    assert output["local_config_readiness"]["missing"] == ["create_http_transport.token_value"]
    assert "access-secret" not in captured
    assert "refresh-secret" not in captured


def test_create_live_execute_once_readiness_blocks_wrong_live_endpoint(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys,
):
    monkeypatch.setenv("ROIBANG_TEST_ACCESS_TOKEN", "secret-token")
    runtime_path = _runtime_config(tmp_path, execution_enabled=True, external_api_enabled=True)
    _seed_plan_sources(tmp_path / "roibang.sqlite3")
    policy = _policy()
    policy["create_execute"]["live_api"]["endpoints"]["bind_material"] = "/wrong/"
    policy_path = tmp_path / "policy.json"
    plan_path = tmp_path / "create-plan.json"
    policy_path.write_text(json.dumps(policy, ensure_ascii=False), encoding="utf-8")
    plan_path.write_text(json.dumps(_create_plan(), ensure_ascii=False), encoding="utf-8")
    create_execute_path = tmp_path / "create-execute.json"
    create_execute_path.write_text(json.dumps(_execute_artifact(), ensure_ascii=False), encoding="utf-8")
    module = _load_script("run_create_live_execute_once")

    exit_code = module.run_from_args(
        [
            "--config",
            str(runtime_path),
            "--policy",
            str(policy_path),
            "--plan",
            str(plan_path),
            "--create-execute-artifact",
            str(create_execute_path),
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["local_config_readiness"]["ready"] is False
    assert output["local_config_readiness"]["missing"] == [
        "create_execute.live_api.endpoints.bind_material"
    ]
    assert output["status"] == "blocked"
    assert output["external_api_calls"] == 0


def test_create_live_execute_once_fixed_script_blocks_plan_mismatch(tmp_path: Path, capsys):
    runtime_path = _runtime_config(tmp_path)
    _seed_plan_sources(tmp_path / "roibang.sqlite3")
    policy_path = tmp_path / "policy.json"
    plan_path = tmp_path / "create-plan.json"
    policy_path.write_text(json.dumps(_policy(), ensure_ascii=False), encoding="utf-8")
    plan_path.write_text(json.dumps(_create_plan(plan_id="different-plan"), ensure_ascii=False), encoding="utf-8")
    create_execute_path = tmp_path / "create-execute.json"
    create_execute_path.write_text(json.dumps(_execute_artifact(), ensure_ascii=False), encoding="utf-8")
    module = _load_script("run_create_live_execute_once")

    exit_code = module.run_from_args(
        [
            "--config",
            str(runtime_path),
            "--policy",
            str(policy_path),
            "--plan",
            str(plan_path),
            "--create-execute-artifact",
            str(create_execute_path),
        ]
    )

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


def test_create_live_execute_once_fixed_script_requires_explicit_plan(tmp_path: Path):
    runtime_path = _runtime_config(tmp_path)
    policy_path = tmp_path / "policy.json"
    policy_path.write_text(json.dumps(_policy(), ensure_ascii=False), encoding="utf-8")
    module = _load_script("run_create_live_execute_once")

    with pytest.raises(SystemExit) as exc:
        module.run_from_args(["--config", str(runtime_path), "--policy", str(policy_path)])

    assert exc.value.code == 2
