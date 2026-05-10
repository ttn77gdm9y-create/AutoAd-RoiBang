import importlib.util
import json
from pathlib import Path

from roibang_v2.workflows.create_live_execution_pack import (
    build_create_live_execution_pack,
    run_create_live_execution_pack_request,
)


def _load_script(name: str):
    script_path = Path(f"scripts/{name}.py")
    spec = importlib.util.spec_from_file_location(name, script_path)
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
                "phase": "phase2",
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
            "unit_count": 2,
            "material_count": 4,
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
                "payload": {"advertiser_id": "target-1", "project_id": "<lookup:project:target-1-p001>"},
                "executable": False,
                "live_api_payload": False,
            },
            {
                "operation": "create_unit",
                "payload": {"advertiser_id": "target-1", "project_id": "<lookup:project:target-1-p001>"},
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
        ],
        "resolved_payload_contract": {
            "status": "passed",
            "checked_draft_count": 4,
            "unresolved_lookup_count": 0,
            "executable_draft_count": 0,
            "live_payload_count": 0,
        },
    }


def _runbook_artifact() -> dict:
    return {
        "workflow": "create_first_live_runbook",
        "ok": True,
        "status": "ready_for_human_approval",
        "execution_enabled": False,
        "external_api_calls": 0,
        "scope": {
            "advertiser_id": "target-1",
            "project_count": 1,
            "unit_count": 2,
            "material_count": 4,
            "max_project_count": 1,
            "max_unit_count": 2,
            "max_material_count": 4,
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
                "bind_material": "/open_api/2/file/material/bind/",
            },
        },
    }


def _approval_artifact() -> dict:
    return {
        "workflow": "create_live_approval",
        "ok": True,
        "status": "approved",
        "execution_enabled": False,
        "external_api_calls": 0,
        "scope": _runbook_artifact()["scope"],
        "approval": {
            "approved": True,
            "approval_id": "live-approval-001",
            "approved_by": "operator",
            "approved_at": "2026-05-10T11:00:00+00:00",
            "expires_at": "2026-05-10T12:00:00+00:00",
            "target_workflow": "create_live_execute_runner",
            "allow_create_http_transport": True,
        },
    }


def _enabled_policy() -> dict:
    return {
        "create_execute": {
            "live_api": {
                "enabled": True,
                "endpoints": {
                    "create_project": "/open_api/2/project/create/",
                    "create_unit": "/open_api/2/promotion/create/",
                    "bind_material": "/open_api/2/file/material/bind/",
                },
            },
            "payload_schema": {"live_payload_generation_enabled": True},
        },
        "create_live_execute_runner": {
            "allow_create_http_transport": True,
            "human_approval": {
                "approved": True,
                "approval_id": "live-approval-001",
                "approved_by": "operator",
            },
        },
    }


def test_create_live_execution_pack_blocks_when_live_enablement_is_missing():
    result = build_create_live_execution_pack(
        create_execute_artifact=_execute_artifact(),
        create_first_live_runbook_artifact=_runbook_artifact(),
        create_live_payload_adapter_scaffold_artifact=_scaffold_artifact(),
        create_live_approval_artifact=_approval_artifact(),
        policy={},
        runtime={"execution_enabled": False, "external_api_enabled": False},
    )

    assert result["ok"] is False
    assert result["workflow"] == "create_live_execution_pack"
    assert result["status"] == "blocked"
    assert result["execution_enabled"] is False
    assert result["live_execute_enabled"] is False
    assert result["external_api_calls"] == 0
    assert result["final_preflight"]["ready_for_live_execute"] is False
    assert result["final_preflight"]["ready_for_live_enablement"] is True
    assert result["final_preflight"]["checks"]["safe_artifact_boundary"] is True
    assert "runtime.execution_enabled is false" in result["final_preflight"]["blocking_reasons"]
    assert "policy.create_execute.live_api.enabled is false" in result["final_preflight"]["blocking_reasons"]
    assert result["execution_pack"]["payload_counts"] == {
        "create_project": 1,
        "create_unit": 2,
        "bind_material": 1,
        "total": 4,
    }
    assert result["execution_pack"]["approve_contract"] == {
        "approve_is_record_only": True,
        "approve_opens_execution": False,
        "execution_pack_opens_execution": False,
        "requires_separate_human_approval_for_live": True,
    }
    assert result["actions"] == []


def test_create_live_execution_pack_marks_ready_only_when_all_live_gates_are_explicit():
    result = build_create_live_execution_pack(
        create_execute_artifact=_execute_artifact(),
        create_first_live_runbook_artifact=_runbook_artifact(),
        create_live_payload_adapter_scaffold_artifact=_scaffold_artifact(),
        create_live_approval_artifact=_approval_artifact(),
        policy=_enabled_policy(),
        runtime={"execution_enabled": True, "external_api_enabled": True},
    )

    assert result["ok"] is True
    assert result["status"] == "ready_for_live_execute"
    assert result["execution_enabled"] is False
    assert result["live_execute_enabled"] is False
    assert result["external_api_calls"] == 0
    assert result["final_preflight"]["ready_for_live_execute"] is True
    assert result["final_preflight"]["blocking_reasons"] == []
    assert result["execution_pack"]["scope"] == _runbook_artifact()["scope"]
    assert result["execution_pack"]["ordered_operations"] == ["create_project", "create_unit", "bind_material"]
    assert result["execution_pack"]["payloads_by_operation"]["bind_material"][0]["payload"] == {
        "source_advertiser_id": "source-1",
        "target_advertiser_ids": ["target-1"],
        "source_video_ids": ["video-1"],
    }
    assert result["execution_pack"]["transport"] == {
        "mode": "create_http",
        "create_http_transport_allowed": True,
        "external_api_calls_in_pack": 0,
    }


def test_run_create_live_execution_pack_request_writes_artifact(tmp_path: Path):
    result = run_create_live_execution_pack_request(
        {
            "create_live_execution_pack": {
                "create_execute_artifact": _execute_artifact(),
                "create_first_live_runbook_artifact": _runbook_artifact(),
                "create_live_payload_adapter_scaffold_artifact": _scaffold_artifact(),
                "create_live_approval_artifact": _approval_artifact(),
                "policy": _enabled_policy(),
                "runtime": {"execution_enabled": True, "external_api_enabled": True},
            }
        },
        runs_dir=tmp_path / "runs",
    )

    artifact = json.loads(Path(result["artifact_path"]).read_text(encoding="utf-8"))
    assert result["workflow"] == "create_live_execution_pack"
    assert result["status"] == "ready_for_live_execute"
    assert artifact["external_api_calls"] == 0
    assert artifact["actions"] == []


def test_create_live_execution_pack_fixed_script_uses_latest_artifacts(tmp_path: Path, capsys):
    runtime_path = _runtime_config(tmp_path)
    policy_path = tmp_path / "policy.json"
    policy_path.write_text(json.dumps(_enabled_policy(), ensure_ascii=False), encoding="utf-8")
    runs_dir = tmp_path / "runs"
    artifacts = {
        "create_execute": _execute_artifact(),
        "create_first_live_runbook": _runbook_artifact(),
        "create_live_payload_adapter_scaffold": _scaffold_artifact(),
        "create_live_approval": _approval_artifact(),
    }
    for workflow, artifact in artifacts.items():
        path = runs_dir / workflow / "20260510T000000Z.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(artifact, ensure_ascii=False), encoding="utf-8")
    module = _load_script("run_create_live_execution_pack")

    exit_code = module.run_from_args(["--config", str(runtime_path), "--policy", str(policy_path)])

    output = json.loads(capsys.readouterr().out)
    artifact = json.loads(Path(output["artifact_path"]).read_text(encoding="utf-8"))
    assert exit_code == 0
    assert output["workflow"] == "create_live_execution_pack"
    assert output["status"] == "blocked"
    assert output["execution_enabled"] is False
    assert output["external_api_calls"] == 0
    assert output["final_preflight"]["ready_for_live_enablement"] is True
    assert artifact["execution_pack"]["payload_counts"]["total"] == 4
