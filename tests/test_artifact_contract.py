import importlib.util
import json
from pathlib import Path

from roibang_v2.artifacts.contract import validate_artifact_contract
from roibang_v2.scheduler.jobs import load_job_registry


def _load_validate_script():
    script_path = Path("scripts/validate_run_artifact.py")
    spec = importlib.util.spec_from_file_location("validate_run_artifact", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _write_json(path: Path, payload: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_validate_artifact_contract_accepts_matching_result_json(tmp_path):
    registry = load_job_registry(Path("configs/scheduler/roibang-v2.jobs.example.json"))
    artifact = tmp_path / "material_sync.json"
    _write_json(
        artifact,
        {
            "ok": True,
            "workflow": "material_sync",
            "execution_enabled": False,
            "external_api_calls": 0,
            "plan": {"status": "sufficient"},
        },
    )

    result = validate_artifact_contract(registry, job_id="roibang-material-sync", artifact_path=artifact)

    assert result["ok"] is True
    assert result["job_id"] == "roibang-material-sync"
    assert result["workflow"] == "material_sync"
    assert result["missing_fields"] == []
    assert result["violations"] == []


def test_validate_artifact_contract_rejects_missing_required_fields(tmp_path):
    registry = load_job_registry(Path("configs/scheduler/roibang-v2.jobs.example.json"))
    artifact = tmp_path / "material_sync.json"
    _write_json(
        artifact,
        {
            "ok": True,
            "workflow": "material_sync",
            "execution_enabled": False,
            "external_api_calls": 0,
        },
    )

    result = validate_artifact_contract(registry, job_id="roibang-material-sync", artifact_path=artifact)

    assert result["ok"] is False
    assert result["missing_fields"] == ["plan"]
    assert "missing required fields: plan" in result["violations"]


def test_validate_artifact_contract_rejects_workflow_mismatch(tmp_path):
    registry = load_job_registry(Path("configs/scheduler/roibang-v2.jobs.example.json"))
    artifact = tmp_path / "wrong_workflow.json"
    _write_json(
        artifact,
        {
            "ok": True,
            "workflow": "daily_learning",
            "execution_enabled": False,
            "external_api_calls": 0,
            "plan": {},
        },
    )

    result = validate_artifact_contract(registry, job_id="roibang-material-sync", artifact_path=artifact)

    assert result["ok"] is False
    assert "workflow mismatch: expected material_sync, got daily_learning" in result["violations"]


def test_validate_artifact_contract_rejects_phase1_safety_value_violations(tmp_path):
    registry = {
        "jobs": [
            {
                "id": "create-execute",
                "name": "Create execute",
                "enabled": True,
                "schedule": {"type": "cron", "expr": "0 9 * * *", "tz": "Asia/Shanghai"},
                "script": {"path": "scripts/run_create_execute.py", "mode": "foreground"},
                "policy": {},
                "result_contract": {
                    "workflow": "create_execute",
                    "artifact_dir": "runs/create_execute",
                    "must_include": ["ok", "workflow", "execution_enabled", "external_api_calls", "actions"],
                    "must_equal": {
                        "execution_enabled": False,
                        "external_api_calls": 0
                    },
                    "must_be_empty": ["actions"],
                },
            }
        ]
    }
    artifact = tmp_path / "unsafe.json"
    _write_json(
        artifact,
        {
            "ok": True,
            "workflow": "create_execute",
            "execution_enabled": True,
            "external_api_calls": 1,
            "actions": [{"action": "create_project"}],
        },
    )

    result = validate_artifact_contract(registry, job_id="create-execute", artifact_path=artifact)

    assert result["ok"] is False
    assert "field execution_enabled must equal False, got True" in result["violations"]
    assert "field external_api_calls must equal 0, got 1" in result["violations"]
    assert "field actions must be empty" in result["violations"]


def test_validate_artifact_contract_can_find_latest_artifact(tmp_path):
    registry = {
        "jobs": [
            {
                "id": "daily",
                "name": "Daily",
                "enabled": True,
                "schedule": {"type": "cron", "expr": "0 9 * * *", "tz": "Asia/Shanghai"},
                "script": {"path": "scripts/run_daily_learning.py", "mode": "foreground"},
                "policy": {},
                "result_contract": {
                    "workflow": "daily_learning",
                    "artifact_dir": "runs/daily_learning",
                    "must_include": ["ok", "workflow", "summary"],
                },
            }
        ]
    }
    _write_json(tmp_path / "runs" / "daily_learning" / "20260101T000000Z.json", {"workflow": "old"})
    latest = tmp_path / "runs" / "daily_learning" / "20260102T000000Z.json"
    _write_json(latest, {"ok": True, "workflow": "daily_learning", "summary": {}})

    result = validate_artifact_contract(registry, job_id="daily", repo_root=tmp_path)

    assert result["ok"] is True
    assert result["artifact_path"] == str(latest)


def test_validate_artifact_contract_accepts_create_approval_and_execute_outputs(tmp_path):
    registry = load_job_registry(Path("configs/scheduler/roibang-v2.jobs.example.json"))
    approval = tmp_path / "create_approval.json"
    snapshot = tmp_path / "create_plan_snapshot.json"
    execute = tmp_path / "create_execute.json"
    replay = tmp_path / "create_chain_replay.json"
    manifest = tmp_path / "create_chain_manifest.json"
    field_map_check = tmp_path / "create_provider_field_map_check.json"
    review_pack = tmp_path / "create_field_mapping_review_pack.json"
    phase2_mapping_prep = tmp_path / "create_phase2_provider_mapping_prep.json"
    template_pack = tmp_path / "create_template_slot_review_pack.json"
    readiness_matrix = tmp_path / "create_readiness_matrix.json"
    phase_gate = tmp_path / "create_live_execute_phase_gate.json"
    adapter_scaffold = tmp_path / "create_live_payload_adapter_scaffold.json"
    adapter_review = tmp_path / "create_adapter_review_pack.json"
    chain_index = tmp_path / "create_chain_index.json"
    final_report = tmp_path / "create_chain_final_report.json"
    acceptance_checklist = tmp_path / "create_phase1_acceptance_checklist.json"
    baseline_freeze = tmp_path / "create_phase1_baseline_freeze.json"
    _write_json(
        approval,
        {
            "ok": True,
            "workflow": "create_approval",
            "phase": "phase1",
            "execution_enabled": False,
            "external_api_calls": 0,
            "status": "recorded",
            "policy_decision": "would_approve",
            "execute_allowed": False,
            "summary": {},
            "lineage": {},
            "candidate_task_digest": {
                "algorithm": "sha256",
                "value": "0" * 64,
                "candidate_task_count": 0,
            },
            "provider_field_map_digest": {
                "algorithm": "sha256",
                "value": "0" * 64,
            },
            "provider_payload_draft_digest": {
                "algorithm": "sha256",
                "value": "0" * 64,
                "provider_payload_draft_count": 0,
            },
            "provider_readiness_contract": {
                "status": "not_ready",
                "ready_for_live_execute": False,
                "provider": "oceanengine",
                "checks": {},
                "blocking_reasons": [],
            },
            "violations": [],
            "actions": [],
        },
    )
    _write_json(
        snapshot,
        {
            "ok": True,
            "workflow": "create_plan_snapshot",
            "phase": "phase1",
            "execution_enabled": False,
            "external_api_calls": 0,
            "summary": {},
            "lineage": {},
            "candidate_task_digest": {
                "algorithm": "sha256",
                "value": "0" * 64,
                "candidate_task_count": 0,
            },
            "payload_contract": {"status": "passed", "missing_fields": []},
            "payload_draft_contract": {
                "status": "passed",
                "draft_count": 0,
                "live_payload_count": 0,
                "executable_draft_count": 0,
                "redacted": True,
            },
            "provider_adapter_contract": {
                "status": "draft_unverified",
                "provider": "oceanengine",
                "mapping_verified": False,
                "draft_count": 0,
                "live_payload_count": 0,
                "executable_draft_count": 0,
            },
            "provider_field_map_contract": {
                "status": "unverified",
                "provider": "oceanengine",
                "operation_count": 3,
                "field_count": 0,
                "verified_field_count": 0,
                "unverified_field_count": 0,
                "missing_provider_field_count": 0,
                "missing_required_field_count": 0,
                "missing_required_fields": [],
                "duplicate_internal_field_count": 0,
                "duplicate_internal_fields": [],
                "unknown_internal_field_count": 0,
                "unknown_internal_fields": [],
                "provider_mismatch_count": 0,
                "provider_mismatches": [],
                "field_mapping_version_mismatch_count": 0,
                "field_mapping_version_mismatches": [],
            },
            "provider_field_map_digest": {
                "algorithm": "sha256",
                "value": "0" * 64,
            },
            "provider_payload_draft_digest": {
                "algorithm": "sha256",
                "value": "0" * 64,
                "provider_payload_draft_count": 0,
            },
            "provider_readiness_contract": {
                "status": "not_ready",
                "ready_for_live_execute": False,
                "provider": "oceanengine",
                "checks": {},
                "blocking_reasons": [],
            },
            "idempotency_contract": {"status": "passed", "duplicate_keys": []},
            "idempotency_ledger": {"status": "recorded", "recorded_key_count": 0, "existing_key_count": 0},
            "accounts": [],
            "review_notes": [],
            "violations": [],
            "actions": [],
        },
    )
    _write_json(
        execute,
        {
            "ok": True,
            "workflow": "create_execute",
            "phase": "phase1",
            "execution_enabled": False,
            "external_api_calls": 0,
            "status": "blocked",
            "reason": "phase1_execute_disabled",
            "summary": {},
            "lineage": {},
            "candidate_task_digest": {
                "algorithm": "sha256",
                "value": "0" * 64,
                "candidate_task_count": 0,
            },
            "payload_schema": {"version": "phase1.create_payload.v1", "mode": "schema_only"},
            "execution_plan": {},
            "provider_field_map_digest": {
                "algorithm": "sha256",
                "value": "0" * 64,
            },
            "provider_payload_draft_digest": {
                "algorithm": "sha256",
                "value": "0" * 64,
                "provider_payload_draft_count": 0,
            },
            "provider_readiness_contract": {
                "status": "not_ready",
                "ready_for_live_execute": False,
                "provider": "oceanengine",
                "checks": {},
                "blocking_reasons": [],
            },
            "audit": {},
            "executed_task_count": 0,
            "actions": [],
        },
    )
    _write_json(
        replay,
        {
            "ok": True,
            "workflow": "create_chain_replay",
            "phase": "phase1",
            "execution_enabled": False,
            "external_api_calls": 0,
            "status": "passed",
            "summary": {},
            "lineage": {},
            "digest_consistency": {
                "candidate_task_digest": {"status": "passed", "sources": {}},
                "provider_field_map_digest": {"status": "passed", "sources": {}},
                "provider_payload_draft_digest": {"status": "passed", "sources": {}},
            },
            "artifact_identity_contract": {
                "status": "passed",
                "workflow_checks": {},
                "status_checks": {},
            },
            "phase1_safety_contract": {
                "status": "passed",
                "execution_enabled_false": True,
                "external_api_calls_zero": True,
                "actions_empty": True,
            },
            "violations": [],
            "actions": [],
        },
    )
    _write_json(
        manifest,
        {
            "ok": True,
            "workflow": "create_chain_manifest",
            "phase": "phase1",
            "execution_enabled": False,
            "external_api_calls": 0,
            "status": "ready",
            "summary": {},
            "artifact_paths": {},
            "candidate_task_digest": {
                "algorithm": "sha256",
                "value": "0" * 64,
                "candidate_task_count": 0,
            },
            "provider_field_map_digest": {
                "algorithm": "sha256",
                "value": "0" * 64,
            },
            "provider_payload_draft_digest": {
                "algorithm": "sha256",
                "value": "0" * 64,
                "provider_payload_draft_count": 0,
            },
            "replay_status": "passed",
            "phase1_safety_contract": {
                "status": "passed",
                "execution_enabled_false": True,
                "external_api_calls_zero": True,
                "actions_empty": True,
            },
            "violations": [],
            "actions": [],
        },
    )
    dry_run = tmp_path / "create_dry_run.json"
    _write_json(
        dry_run,
        {
            "ok": True,
            "workflow": "create_dry_run",
            "phase": "phase1",
            "execution_enabled": False,
            "external_api_calls": 0,
            "status": "simulated",
            "summary": {},
            "lineage": {
                "create_provider_field_map_check": {
                    "workflow": "create_provider_field_map_check",
                    "phase": "phase1",
                    "status": "unverified",
                    "provider": "oceanengine",
                    "field_map_path": "configs/provider-field-maps/oceanengine.create.phase1.example.json",
                }
            },
            "payload_schema": {"version": "phase1.create_payload.v1", "mode": "schema_only"},
            "payload_contract": {"status": "passed", "missing_fields": []},
            "payload_draft_contract": {
                "status": "passed",
                "draft_count": 0,
                "live_payload_count": 0,
                "executable_draft_count": 0,
                "redacted": True,
            },
            "redacted_payload_drafts": [],
            "provider_adapter": {
                "status": "draft_unverified",
                "provider": "oceanengine",
                "mapping_verified": False,
                "executable": False,
            },
            "provider_adapter_contract": {
                "status": "draft_unverified",
                "provider": "oceanengine",
                "mapping_verified": False,
                "draft_count": 0,
                "live_payload_count": 0,
                "executable_draft_count": 0,
            },
            "provider_field_map": {
                "provider": "oceanengine",
                "field_mapping_version": "phase1.oceanengine.create_payload.draft.v1",
                "mapping_verified": False,
                "source": "phase1_placeholder_no_legacy_reference",
                "operations": {},
            },
            "provider_field_map_contract": {
                "status": "unverified",
                "provider": "oceanengine",
                "operation_count": 3,
                "field_count": 0,
                "verified_field_count": 0,
                "unverified_field_count": 0,
                "missing_provider_field_count": 0,
                "missing_required_field_count": 0,
                "missing_required_fields": [],
                "duplicate_internal_field_count": 0,
                "duplicate_internal_fields": [],
                "unknown_internal_field_count": 0,
                "unknown_internal_fields": [],
                "provider_mismatch_count": 0,
                "provider_mismatches": [],
                "field_mapping_version_mismatch_count": 0,
                "field_mapping_version_mismatches": [],
            },
            "provider_field_map_digest": {
                "algorithm": "sha256",
                "value": "0" * 64,
            },
            "provider_payload_draft_digest": {
                "algorithm": "sha256",
                "value": "0" * 64,
                "provider_payload_draft_count": 0,
            },
            "provider_readiness_contract": {
                "status": "not_ready",
                "ready_for_live_execute": False,
                "provider": "oceanengine",
                "checks": {},
                "blocking_reasons": [],
            },
            "provider_payload_drafts": [],
            "idempotency_contract": {"status": "passed", "duplicate_keys": []},
            "idempotency_ledger": {"status": "recorded", "recorded_key_count": 0, "existing_key_count": 0},
            "candidate_tasks": [],
            "violations": [],
            "actions": [],
        },
    )
    _write_json(
        field_map_check,
        {
            "ok": True,
            "workflow": "create_provider_field_map_check",
            "phase": "phase1",
            "execution_enabled": False,
            "external_api_calls": 0,
            "status": "unverified",
            "summary": {},
            "provider_field_map_contract": {
                "status": "unverified",
                "provider": "oceanengine",
                "operation_count": 3,
                "field_count": 13,
                "verified_field_count": 0,
                "unverified_field_count": 13,
                "missing_provider_field_count": 13,
                "missing_required_field_count": 0,
                "missing_required_fields": [],
                "duplicate_internal_field_count": 0,
                "duplicate_internal_fields": [],
                "unknown_internal_field_count": 0,
                "unknown_internal_fields": [],
                "provider_mismatch_count": 0,
                "provider_mismatches": [],
                "field_mapping_version_mismatch_count": 0,
                "field_mapping_version_mismatches": [],
            },
            "provider_field_map_digest": {
                "algorithm": "sha256",
                "value": "0" * 64,
            },
            "provider_readiness_contract": {
                "status": "not_ready",
                "ready_for_live_execute": False,
                "provider": "oceanengine",
                "checks": {},
                "blocking_reasons": [],
            },
            "missing_provider_fields": [],
            "missing_required_fields": [],
            "duplicate_internal_fields": [],
            "unknown_internal_fields": [],
            "unverified_fields": [],
            "violations": [],
            "actions": [],
        },
    )
    _write_json(
        review_pack,
        {
            "ok": True,
            "workflow": "create_field_mapping_review_pack",
            "phase": "phase1",
            "execution_enabled": False,
            "external_api_calls": 0,
            "status": "needs_review",
            "required_user_input_now": False,
            "summary": {
                "provider": "oceanengine",
                "field_mapping_version": "phase1.oceanengine.create_payload.draft.v1",
                "field_map_path": "configs/provider-field-maps/oceanengine.create.phase1.example.json",
                "operation_count": 3,
                "field_count": 13,
                "needs_provider_field_count": 13,
                "needs_verification_count": 13,
                "ready_for_live_execute": False,
            },
            "payload_schema": {"version": "phase1.create_payload.v1", "mode": "schema_only"},
            "provider_field_map": {
                "provider": "oceanengine",
                "field_mapping_version": "phase1.oceanengine.create_payload.draft.v1",
                "mapping_verified": False,
                "source": "phase1_example_config_no_legacy_reference",
                "operations": {},
            },
            "provider_field_map_contract": {
                "status": "unverified",
                "provider": "oceanengine",
                "operation_count": 3,
                "field_count": 13,
                "verified_field_count": 0,
                "unverified_field_count": 13,
                "missing_provider_field_count": 13,
                "missing_required_field_count": 0,
                "missing_required_fields": [],
                "duplicate_internal_field_count": 0,
                "duplicate_internal_fields": [],
                "duplicate_provider_field_count": 0,
                "duplicate_provider_fields": [],
                "unknown_internal_field_count": 0,
                "unknown_internal_fields": [],
            },
            "provider_field_map_digest": {
                "algorithm": "sha256",
                "value": "0" * 64,
            },
            "provider_readiness_contract": {
                "status": "not_ready",
                "ready_for_live_execute": False,
                "provider": "oceanengine",
                "checks": {},
                "blocking_reasons": [],
            },
            "review_contract": {
                "status": "needs_review",
                "field_count": 13,
                "needs_provider_field_count": 13,
                "needs_verification_count": 13,
                "verified_field_count": 0,
                "missing_required_field_count": 0,
                "duplicate_internal_field_count": 0,
                "duplicate_provider_field_count": 0,
                "unknown_internal_field_count": 0,
            },
            "review_sections": [],
            "violations": [],
            "actions": [],
        },
    )
    _write_json(
        phase2_mapping_prep,
        {
            "ok": True,
            "workflow": "create_phase2_provider_mapping_prep",
            "phase": "phase2_preparation",
            "execution_enabled": False,
            "external_api_calls": 0,
            "status": "needs_review",
            "summary": {
                "provider": "oceanengine",
                "field_mapping_version": "phase2.oceanengine.create_payload.prep.v1",
                "field_map_path": "configs/provider-field-maps/oceanengine.create.phase2-prep.example.json",
                "operation_count": 3,
                "field_count": 13,
                "candidate_provider_field_count": 10,
                "verified_field_count": 0,
                "unresolved_field_count": 13,
                "open_question_count": 7,
                "ready_for_live_payload_development": False,
                "ready_for_live_execute": False,
            },
            "phase2_preparation_contract": {
                "review_only": True,
                "live_payload_generation_enabled": False,
                "create_execute_hard_block_required": True,
                "next_required_reviews": [],
            },
            "payload_schema": {"version": "phase1.create_payload.v1", "mode": "schema_only"},
            "provider_field_map": {
                "provider": "oceanengine",
                "field_mapping_version": "phase2.oceanengine.create_payload.prep.v1",
                "mapping_verified": False,
                "source": "phase2_preparation_example_no_live_execute",
                "operations": {},
            },
            "provider_field_map_contract": {
                "status": "unverified",
                "provider": "oceanengine",
                "operation_count": 3,
                "field_count": 13,
                "verified_field_count": 0,
                "unverified_field_count": 13,
                "missing_provider_field_count": 3,
                "missing_required_field_count": 0,
                "missing_required_fields": [],
                "duplicate_internal_field_count": 0,
                "duplicate_internal_fields": [],
                "duplicate_provider_field_count": 0,
                "duplicate_provider_fields": [],
                "unknown_internal_field_count": 0,
                "unknown_internal_fields": [],
            },
            "provider_field_map_digest": {
                "algorithm": "sha256",
                "value": "0" * 64,
            },
            "provider_readiness_contract": {
                "status": "not_ready",
                "ready_for_live_execute": False,
                "provider": "oceanengine",
                "checks": {},
                "blocking_reasons": [],
            },
            "review_matrix": [],
            "unresolved_mappings": [],
            "violations": [],
            "actions": [],
        },
    )
    _write_json(
        template_pack,
        {
            "ok": True,
            "workflow": "create_template_slot_review_pack",
            "phase": "phase1",
            "execution_enabled": False,
            "external_api_calls": 0,
            "status": "needs_review",
            "required_user_input_now": False,
            "summary": {
                "request_id": "create_req_20260508_yzt_wx_7r",
                "target_date": "2026-05-08",
                "product": "勇者突进",
                "platform": "WECHAT_GAME",
                "project_type": "WX_PAY_7R_GENERAL",
                "slot_count": 12,
                "configured_slot_count": 12,
                "missing_value_slot_count": 0,
                "needs_review_slot_count": 12,
            },
            "template_contract": {
                "status": "needs_review",
                "slot_count": 12,
                "configured_slot_count": 12,
                "missing_value_slot_count": 0,
                "needs_review_slot_count": 12,
                "required_defaults": ["landing_type", "pricing", "inventory_type"],
            },
            "review_sections": [],
            "violations": [],
            "actions": [],
        },
    )
    _write_json(
        readiness_matrix,
        {
            "ok": True,
            "workflow": "create_readiness_matrix",
            "phase": "phase1",
            "execution_enabled": False,
            "external_api_calls": 0,
            "status": "not_ready",
            "ready_for_live_execute": False,
            "summary": {
                "gate_count": 7,
                "passed_gate_count": 4,
                "blocking_gate_count": 3,
                "ready_for_live_execute": False,
            },
            "readiness_matrix": [],
            "blocking_reasons": [
                "provider field map must be verified before live execute",
                "field mapping review pack still needs review",
                "template slot review pack still needs review",
            ],
            "violations": [],
            "actions": [],
        },
    )
    _write_json(
        phase_gate,
        {
            "ok": True,
            "workflow": "create_live_execute_phase_gate",
            "phase": "phase1",
            "execution_enabled": False,
            "external_api_calls": 0,
            "status": "blocked",
            "live_execute_development_allowed": False,
            "live_execute_allowed": False,
            "summary": {
                "current_phase": "phase1",
                "required_next_phase": "phase2",
                "readiness_status": "not_ready",
                "ready_for_live_execute": False,
                "condition_count": 5,
                "passed_condition_count": 2,
                "blocking_condition_count": 3,
            },
            "phase_gate_conditions": [],
            "readiness_blocking_reasons": [],
            "blocking_reasons": ["current phase is phase1"],
            "violations": [],
            "actions": [],
        },
    )
    _write_json(
        adapter_scaffold,
        {
            "ok": True,
            "workflow": "create_live_payload_adapter_scaffold",
            "phase": "phase1",
            "execution_enabled": False,
            "external_api_calls": 0,
            "status": "blocked",
            "live_payload_generation_enabled": False,
            "live_payloads": [],
            "executable_payloads": [],
            "summary": {
                "provider": "oceanengine",
                "field_mapping_version": "phase1.oceanengine.create_payload.draft.v1",
                "provider_payload_draft_count": 0,
                "live_payload_count": 0,
                "executable_payload_count": 0,
                "phase_gate_status": "blocked",
            },
            "adapter_interface": {
                "provider": "oceanengine",
                "transport": "disabled_live_payload_adapter_scaffold",
                "input_contract": {},
                "output_contract": {},
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
                "provider_payload_draft_count": 0,
            },
            "blocking_reasons": ["live execute phase gate has not opened development"],
            "violations": [],
            "actions": [],
        },
    )
    _write_json(
        adapter_review,
        {
            "ok": True,
            "workflow": "create_adapter_review_pack",
            "phase": "phase1",
            "execution_enabled": False,
            "external_api_calls": 0,
            "status": "needs_review",
            "required_user_input_now": False,
            "summary": {
                "provider": "oceanengine",
                "field_mapping_version": "phase1.oceanengine.create_payload.draft.v1",
                "adapter_status": "blocked",
                "provider_payload_draft_count": 0,
                "live_payload_count": 0,
                "executable_payload_count": 0,
                "review_item_count": 4,
                "blocking_reason_count": 1,
            },
            "review_contract": {
                "status": "needs_review",
                "safe_to_review": True,
                "live_payloads_empty": True,
                "executable_payloads_empty": True,
                "external_api_calls_zero": True,
                "actions_empty": True,
            },
            "review_sections": [],
            "provider_payload_draft_digest": {
                "algorithm": "sha256",
                "value": "0" * 64,
                "provider_payload_draft_count": 0,
            },
            "violations": [],
            "actions": [],
        },
    )
    _write_json(
        chain_index,
        {
            "ok": True,
            "workflow": "create_chain_index",
            "phase": "phase1",
            "execution_enabled": False,
            "external_api_calls": 0,
            "status": "indexed",
            "summary": {
                "artifact_count": 16,
                "missing_artifact_count": 0,
                "unsafe_artifact_count": 0,
                "ready_for_live_execute": False,
                "live_execute_allowed": False,
            },
            "artifact_index": [],
            "artifact_paths": {},
            "safety_contract": {
                "status": "passed",
                "execution_enabled_false": True,
                "external_api_calls_zero": True,
                "actions_empty": True,
                "no_live_execute_allowed": True,
                "no_live_payloads": True,
            },
            "provider_payload_draft_digest": {
                "algorithm": "sha256",
                "value": "0" * 64,
                "provider_payload_draft_count": 0,
            },
            "violations": [],
            "actions": [],
        },
    )
    _write_json(
        final_report,
        {
            "ok": True,
            "workflow": "create_chain_final_report",
            "phase": "phase1",
            "execution_enabled": False,
            "external_api_calls": 0,
            "status": "reported",
            "overall_status": "not_ready_for_live_create",
            "business_summary": "创建链路本地产物已索引完成，Phase 1 仍保持真实创建阻断。",
            "summary": {
                "artifact_count": 16,
                "missing_artifact_count": 0,
                "unsafe_artifact_count": 0,
                "ready_for_live_execute": False,
                "live_execute_development_allowed": False,
                "live_execute_allowed": False,
                "blocking_reason_count": 1,
            },
            "completed_sections": [],
            "pending_confirmations": [],
            "blocking_reasons": ["current phase is phase1"],
            "recommended_next_steps": [],
            "source_workflows": [],
            "adapter_review_status": "needs_review",
            "required_user_input_now": False,
            "violations": [],
            "actions": [],
        },
    )
    _write_json(
        acceptance_checklist,
        {
            "ok": True,
            "workflow": "create_phase1_acceptance_checklist",
            "phase": "phase1",
            "execution_enabled": False,
            "external_api_calls": 0,
            "status": "accepted_with_phase1_blockers",
            "phase1_acceptance_status": "accepted",
            "summary": {
                "check_count": 6,
                "accepted_check_count": 6,
                "blocking_check_count": 0,
                "phase1_real_create_blocked": True,
                "ready_for_phase2_review": True,
            },
            "checklist": [],
            "accepted_items": [],
            "blocking_items": [],
            "recommended_next_steps": [],
            "source_workflows": [],
            "required_user_input_now": False,
            "violations": [],
            "actions": [],
        },
    )
    _write_json(
        baseline_freeze,
        {
            "ok": True,
            "workflow": "create_phase1_baseline_freeze",
            "phase": "phase1",
            "execution_enabled": False,
            "external_api_calls": 0,
            "status": "frozen",
            "phase1_baseline_status": "frozen",
            "baseline_id": "phase1-create-safe-baseline-v1",
            "baseline_digest": {
                "algorithm": "sha256",
                "value": "0" * 64,
            },
            "summary": {
                "accepted": True,
                "artifact_count": 16,
                "accepted_check_count": 6,
                "blocking_check_count": 0,
                "real_create_blocked": True,
                "ready_for_phase2_review": True,
            },
            "freeze_contract": {
                "status": "frozen",
                "acceptance_required": True,
                "acceptance_status": "accepted",
                "execution_enabled_false": True,
                "external_api_calls_zero": True,
                "actions_empty": True,
                "no_live_execute_allowed": True,
                "no_live_payloads": True,
            },
            "frozen_workflows": [],
            "source_artifact_paths": {},
            "blocking_reasons": [],
            "recommended_next_steps": [],
            "required_user_input_now": False,
            "violations": [],
            "actions": [],
        },
    )

    approval_result = validate_artifact_contract(
        registry,
        job_id="roibang-create-approval",
        artifact_path=approval,
    )
    execute_result = validate_artifact_contract(
        registry,
        job_id="roibang-create-execute",
        artifact_path=execute,
    )
    snapshot_result = validate_artifact_contract(
        registry,
        job_id="roibang-create-plan-snapshot",
        artifact_path=snapshot,
    )
    dry_run_result = validate_artifact_contract(
        registry,
        job_id="roibang-create-dry-run",
        artifact_path=dry_run,
    )
    field_map_check_result = validate_artifact_contract(
        registry,
        job_id="roibang-create-provider-field-map-check",
        artifact_path=field_map_check,
    )
    review_pack_result = validate_artifact_contract(
        registry,
        job_id="roibang-create-field-mapping-review-pack",
        artifact_path=review_pack,
    )
    phase2_mapping_prep_result = validate_artifact_contract(
        registry,
        job_id="roibang-create-phase2-provider-mapping-prep",
        artifact_path=phase2_mapping_prep,
    )
    template_pack_result = validate_artifact_contract(
        registry,
        job_id="roibang-create-template-slot-review-pack",
        artifact_path=template_pack,
    )
    replay_result = validate_artifact_contract(
        registry,
        job_id="roibang-create-chain-replay",
        artifact_path=replay,
    )
    manifest_result = validate_artifact_contract(
        registry,
        job_id="roibang-create-chain-manifest",
        artifact_path=manifest,
    )
    readiness_matrix_result = validate_artifact_contract(
        registry,
        job_id="roibang-create-readiness-matrix",
        artifact_path=readiness_matrix,
    )
    phase_gate_result = validate_artifact_contract(
        registry,
        job_id="roibang-create-live-execute-phase-gate",
        artifact_path=phase_gate,
    )
    adapter_scaffold_result = validate_artifact_contract(
        registry,
        job_id="roibang-create-live-payload-adapter-scaffold",
        artifact_path=adapter_scaffold,
    )
    adapter_review_result = validate_artifact_contract(
        registry,
        job_id="roibang-create-adapter-review-pack",
        artifact_path=adapter_review,
    )
    chain_index_result = validate_artifact_contract(
        registry,
        job_id="roibang-create-chain-index",
        artifact_path=chain_index,
    )
    final_report_result = validate_artifact_contract(
        registry,
        job_id="roibang-create-chain-final-report",
        artifact_path=final_report,
    )
    acceptance_checklist_result = validate_artifact_contract(
        registry,
        job_id="roibang-create-phase1-acceptance-checklist",
        artifact_path=acceptance_checklist,
    )
    baseline_freeze_result = validate_artifact_contract(
        registry,
        job_id="roibang-create-phase1-baseline-freeze",
        artifact_path=baseline_freeze,
    )

    assert approval_result["ok"] is True
    assert field_map_check_result["ok"] is True
    assert review_pack_result["ok"] is True
    assert phase2_mapping_prep_result["ok"] is True
    assert template_pack_result["ok"] is True
    assert dry_run_result["ok"] is True
    assert snapshot_result["ok"] is True
    assert execute_result["ok"] is True
    assert replay_result["ok"] is True
    assert manifest_result["ok"] is True
    assert readiness_matrix_result["ok"] is True
    assert phase_gate_result["ok"] is True
    assert adapter_scaffold_result["ok"] is True
    assert adapter_review_result["ok"] is True
    assert chain_index_result["ok"] is True
    assert final_report_result["ok"] is True
    assert acceptance_checklist_result["ok"] is True
    assert baseline_freeze_result["ok"] is True


def test_validate_run_artifact_cli_exits_nonzero_for_bad_contract(tmp_path, capsys):
    module = _load_validate_script()
    artifact = tmp_path / "bad.json"
    _write_json(artifact, {"ok": True, "workflow": "material_sync"})

    exit_code = module.validate_from_args(
        [
            "--registry",
            "configs/scheduler/roibang-v2.jobs.example.json",
            "--job-id",
            "roibang-material-sync",
            "--artifact",
            str(artifact),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert '"ok": false' in captured.out
    assert "missing required fields" in captured.out
