import json
import importlib.util
from pathlib import Path

from roibang_v2.workflows.create_live_approval import (
    artifact_digest,
    build_create_live_approval,
    run_create_live_approval_request,
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


def _execute_artifact():
    return {
        "workflow": "create_execute",
        "summary": {"plan_id": "plan-1", "request_id": "req-1", "project_count": 1, "unit_count": 1, "material_count": 2},
        "execution_enabled": False,
        "external_api_calls": 0,
        "resolved_payload_contract": {"unresolved_lookup_count": 0},
    }


def _runbook_artifact():
    return {
        "workflow": "create_first_live_runbook",
        "ok": True,
        "status": "ready_for_human_approval",
        "execution_enabled": False,
        "external_api_calls": 0,
        "scope": {
            "advertiser_id": "target-1",
            "project_count": 1,
            "unit_count": 1,
            "material_count": 2,
            "max_project_count": 1,
            "max_unit_count": 2,
            "max_material_count": 4,
        },
    }


def _scaffold_artifact():
    return {
        "workflow": "create_live_payload_adapter_scaffold",
        "execution_enabled": False,
        "external_api_calls": 0,
        "live_adapter_gate": {"ready_for_live_execute": False},
    }


def _approval_request():
    execute = _execute_artifact()
    runbook = _runbook_artifact()
    scaffold = _scaffold_artifact()
    return {
        "approval_id": "live-approval-001",
        "approved_by": "human-operator",
        "approved_at": "2026-05-10T11:00:00+00:00",
        "expires_at": "2026-05-10T12:00:00+00:00",
        "target_workflow": "create_live_execute_runner",
        "allow_create_http_transport": True,
        "scope": runbook["scope"],
        "approved_artifacts": {
            "create_execute": artifact_digest(execute),
            "create_first_live_runbook": artifact_digest(runbook),
            "create_live_payload_adapter_scaffold": artifact_digest(scaffold),
        },
    }


def test_create_live_approval_validates_scope_and_artifact_digests():
    result = build_create_live_approval(
        approval_request=_approval_request(),
        create_execute_artifact=_execute_artifact(),
        create_first_live_runbook_artifact=_runbook_artifact(),
        create_live_payload_adapter_scaffold_artifact=_scaffold_artifact(),
        now_iso="2026-05-10T11:30:00+00:00",
    )

    assert result["ok"] is True
    assert result["workflow"] == "create_live_approval"
    assert result["status"] == "approved"
    assert result["execution_enabled"] is False
    assert result["external_api_calls"] == 0
    assert result["approval"] == {
        "approved": True,
        "approval_id": "live-approval-001",
        "approved_by": "human-operator",
        "approved_at": "2026-05-10T11:00:00+00:00",
        "expires_at": "2026-05-10T12:00:00+00:00",
        "target_workflow": "create_live_execute_runner",
        "allow_create_http_transport": True,
    }
    assert result["scope"] == _runbook_artifact()["scope"]
    assert result["artifact_digest_contract"]["all_match"] is True
    assert result["runner_policy_fragment"] == {
        "create_live_execute_runner": {
            "allow_create_http_transport": True,
            "human_approval": {
                "approved": True,
                "approval_id": "live-approval-001",
                "approved_by": "human-operator",
            },
        }
    }
    assert result["violations"] == []
    assert result["actions"] == []


def test_create_live_approval_blocks_expired_or_tampered_approval():
    request = _approval_request()
    request["approved_artifacts"]["create_execute"]["value"] = "0" * 64

    result = build_create_live_approval(
        approval_request=request,
        create_execute_artifact=_execute_artifact(),
        create_first_live_runbook_artifact=_runbook_artifact(),
        create_live_payload_adapter_scaffold_artifact=_scaffold_artifact(),
        now_iso="2026-05-10T12:30:00+00:00",
    )

    assert result["ok"] is False
    assert result["status"] == "blocked"
    assert result["approval"]["approved"] is False
    assert "approval has expired" in result["violations"]
    assert "approved create_execute digest does not match current artifact" in result["violations"]
    assert result["runner_policy_fragment"] == {}
    assert result["execution_enabled"] is False
    assert result["external_api_calls"] == 0
    assert result["actions"] == []


def test_run_create_live_approval_request_writes_artifact(tmp_path: Path):
    result = run_create_live_approval_request(
        {
            "create_live_approval": {
                "approval_request": _approval_request(),
                "create_execute_artifact": _execute_artifact(),
                "create_first_live_runbook_artifact": _runbook_artifact(),
                "create_live_payload_adapter_scaffold_artifact": _scaffold_artifact(),
                "now_iso": "2026-05-10T11:30:00+00:00",
            }
        },
        runs_dir=tmp_path / "runs",
    )

    artifact = json.loads(Path(result["artifact_path"]).read_text(encoding="utf-8"))
    assert result["workflow"] == "create_live_approval"
    assert result["status"] == "approved"
    assert artifact["external_api_calls"] == 0
    assert artifact["actions"] == []


def test_create_live_approval_cli_uses_latest_artifacts_and_approval_file(tmp_path: Path, capsys):
    runtime_path = _runtime_config(tmp_path)
    runs_dir = tmp_path / "runs"
    artifacts = {
        "create_execute": _execute_artifact(),
        "create_first_live_runbook": _runbook_artifact(),
        "create_live_payload_adapter_scaffold": _scaffold_artifact(),
    }
    for workflow, artifact in artifacts.items():
        path = runs_dir / workflow / "20260510T000000Z.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(artifact, ensure_ascii=False), encoding="utf-8")
    approval_file = tmp_path / "approval.json"
    approval_file.write_text(json.dumps(_approval_request(), ensure_ascii=False), encoding="utf-8")
    module = _load_script("run_create_live_approval")

    exit_code = module.run_from_args(["--config", str(runtime_path), "--approval-file", str(approval_file)])

    output = json.loads(capsys.readouterr().out)
    artifact = json.loads(Path(output["artifact_path"]).read_text(encoding="utf-8"))
    assert exit_code == 0
    assert output["workflow"] == "create_live_approval"
    assert output["status"] == "approved"
    assert output["execution_enabled"] is False
    assert output["external_api_calls"] == 0
    assert artifact["actions"] == []
