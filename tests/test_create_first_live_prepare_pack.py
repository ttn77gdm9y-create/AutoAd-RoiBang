import importlib.util
import json
from pathlib import Path

from roibang_v2.workflows.create_first_live_prepare_pack import (
    build_create_first_live_prepare_pack,
    run_create_first_live_prepare_pack_request,
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


def _execution_pack_artifact(*, ready_for_live_enablement: bool = True) -> dict:
    checks = {
        "safe_artifact_boundary": True,
        "runtime_execution_enabled": False,
        "runtime_external_api_enabled": False,
        "policy_live_api_enabled": False,
        "policy_live_payload_generation_enabled": False,
        "phase_gate_allows_live_execute": True,
        "runbook_ready_for_human_approval": True,
        "live_approval_artifact_present": True,
        "human_approval_record_present": True,
        "create_http_transport_allowed": False,
        "approval_scope_matches_runbook": True,
        "scope_matches_payload_counts": True,
        "payloads_non_executable": True,
        "live_payload_count_zero": True,
        "no_unresolved_lookup_placeholders": True,
    }
    if not ready_for_live_enablement:
        checks["payloads_non_executable"] = False
    return {
        "workflow": "create_live_execution_pack",
        "ok": False,
        "phase": "phase2_preparation",
        "execution_enabled": False,
        "live_execute_enabled": False,
        "external_api_calls": 0,
        "status": "blocked",
        "final_preflight": {
            "ready_for_live_execute": False,
            "ready_for_live_enablement": ready_for_live_enablement,
            "checks": checks,
            "blocking_reasons": ["runtime.execution_enabled is false"]
            if ready_for_live_enablement
            else ["execution pack payload drafts must not be executable"],
        },
        "execution_pack": {
            "summary": {
                "plan_id": "plan-1",
                "request_id": "req-1",
                "target_date": "2026-05-10",
                "project_count": 1,
                "unit_count": 2,
                "material_count": 4,
            },
            "scope": {
                "advertiser_id": "target-1",
                "project_count": 1,
                "unit_count": 2,
                "material_count": 4,
                "max_project_count": 1,
                "max_unit_count": 2,
                "max_material_count": 4,
            },
            "payload_counts": {
                "create_project": 1,
                "create_unit": 2,
                "bind_material": 1,
                "total": 4,
            },
            "ordered_operations": ["create_project", "create_unit", "bind_material"],
            "transport": {
                "mode": "create_http",
                "create_http_transport_allowed": False,
                "external_api_calls_in_pack": 0,
            },
        },
        "actions": [],
    }


def test_first_live_prepare_pack_marks_local_ready_without_opening_execution():
    result = build_create_first_live_prepare_pack(
        create_live_execution_pack_artifact=_execution_pack_artifact(ready_for_live_enablement=True),
    )

    assert result["ok"] is True
    assert result["workflow"] == "create_first_live_prepare_pack"
    assert result["status"] == "ready_for_human_live_enablement"
    assert result["execution_enabled"] is False
    assert result["live_execute_enabled"] is False
    assert result["external_api_calls"] == 0
    assert result["readiness"] == {
        "local_boundary_ready": True,
        "ready_for_live_execute": False,
        "requires_human_switch_enablement": True,
        "requires_explicit_user_approval": True,
    }
    assert result["payload_review"]["payload_counts"] == {
        "create_project": 1,
        "create_unit": 2,
        "bind_material": 1,
        "total": 4,
    }
    assert result["required_enablement"]["runtime"] == {
        "execution_enabled": True,
        "external_api_enabled": True,
    }
    assert result["fixed_scripts"]["execute_once"] == "scripts/run_create_live_execute_once.py"
    assert result["actions"] == []


def test_first_live_prepare_pack_blocks_when_local_boundary_is_not_ready():
    result = build_create_first_live_prepare_pack(
        create_live_execution_pack_artifact=_execution_pack_artifact(ready_for_live_enablement=False),
    )

    assert result["ok"] is False
    assert result["status"] == "blocked"
    assert result["readiness"]["local_boundary_ready"] is False
    assert "execution pack payload drafts must not be executable" in result["blocking_reasons"]
    assert result["execution_enabled"] is False
    assert result["external_api_calls"] == 0


def test_run_create_first_live_prepare_pack_request_writes_artifact(tmp_path: Path):
    result = run_create_first_live_prepare_pack_request(
        {
            "create_first_live_prepare_pack": {
                "create_live_execution_pack_artifact": _execution_pack_artifact(ready_for_live_enablement=True)
            }
        },
        runs_dir=tmp_path / "runs",
    )

    artifact = json.loads(Path(result["artifact_path"]).read_text(encoding="utf-8"))
    assert result["workflow"] == "create_first_live_prepare_pack"
    assert result["status"] == "ready_for_human_live_enablement"
    assert artifact["external_api_calls"] == 0
    assert artifact["actions"] == []


def test_first_live_prepare_pack_fixed_script_uses_latest_execution_pack(tmp_path: Path, capsys):
    runtime_path = _runtime_config(tmp_path)
    runs_dir = tmp_path / "runs"
    path = runs_dir / "create_live_execution_pack" / "20260510T000000Z.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(_execution_pack_artifact(ready_for_live_enablement=True), ensure_ascii=False),
        encoding="utf-8",
    )
    module = _load_script("run_create_first_live_prepare_pack")

    exit_code = module.run_from_args(["--config", str(runtime_path)])

    output = json.loads(capsys.readouterr().out)
    artifact = json.loads(Path(output["artifact_path"]).read_text(encoding="utf-8"))
    assert exit_code == 0
    assert output["workflow"] == "create_first_live_prepare_pack"
    assert output["status"] == "ready_for_human_live_enablement"
    assert output["execution_enabled"] is False
    assert output["external_api_calls"] == 0
    assert artifact["payload_review"]["payload_counts"]["total"] == 4
