from pathlib import Path

import pytest

from roibang_v2.scheduler.jobs import load_job_registry, validate_job_registry


def test_scheduler_registry_has_no_ai_execution_prompts():
    registry = load_job_registry(Path("configs/scheduler/roibang-v2.jobs.example.json"))

    result = validate_job_registry(registry)

    assert result == {
        "ok": True,
        "jobs": 31,
        "enabled_jobs": 9,
        "disabled_jobs": 22,
        "violations": [],
    }


def test_scheduler_registry_includes_disabled_fixed_create_chain_jobs():
    registry = load_job_registry(Path("configs/scheduler/roibang-v2.jobs.example.json"))
    jobs = {job["id"]: job for job in registry["jobs"]}

    expected = {
        "roibang-create-request": ("create_request", "scripts/run_create_request.py"),
        "roibang-create-strategy-plan": ("create_strategy_plan", "scripts/run_create_strategy_plan.py"),
        "roibang-create-preflight": ("create_preflight", "scripts/run_create_preflight.py"),
        "roibang-create-provider-field-map-check": (
            "create_provider_field_map_check",
            "scripts/run_create_provider_field_map_check.py",
        ),
        "roibang-create-field-mapping-review-pack": (
            "create_field_mapping_review_pack",
            "scripts/run_create_field_mapping_review_pack.py",
        ),
        "roibang-create-template-slot-review-pack": (
            "create_template_slot_review_pack",
            "scripts/run_create_template_slot_review_pack.py",
        ),
        "roibang-create-dry-run": ("create_dry_run", "scripts/run_create_dry_run.py"),
        "roibang-create-approval": ("create_approval", "scripts/run_create_approval.py"),
        "roibang-create-plan-snapshot": ("create_plan_snapshot", "scripts/run_create_plan_snapshot.py"),
        "roibang-create-execute": ("create_execute", "scripts/run_create_execute.py"),
        "roibang-create-chain-replay": ("create_chain_replay", "scripts/run_create_chain_replay.py"),
        "roibang-create-chain-manifest": ("create_chain_manifest", "scripts/run_create_chain_manifest.py"),
        "roibang-create-readiness-matrix": ("create_readiness_matrix", "scripts/run_create_readiness_matrix.py"),
        "roibang-create-live-execute-phase-gate": (
            "create_live_execute_phase_gate",
            "scripts/run_create_live_execute_phase_gate.py",
        ),
        "roibang-create-live-payload-adapter-scaffold": (
            "create_live_payload_adapter_scaffold",
            "scripts/run_create_live_payload_adapter_scaffold.py",
        ),
        "roibang-create-adapter-review-pack": (
            "create_adapter_review_pack",
            "scripts/run_create_adapter_review_pack.py",
        ),
        "roibang-create-chain-index": ("create_chain_index", "scripts/run_create_chain_index.py"),
        "roibang-create-chain-final-report": (
            "create_chain_final_report",
            "scripts/run_create_chain_final_report.py",
        ),
        "roibang-create-phase1-acceptance-checklist": (
            "create_phase1_acceptance_checklist",
            "scripts/run_create_phase1_acceptance_checklist.py",
        ),
        "roibang-create-phase1-baseline-freeze": (
            "create_phase1_baseline_freeze",
            "scripts/run_create_phase1_baseline_freeze.py",
        ),
    }
    for job_id, (workflow, script_path) in expected.items():
        job = jobs[job_id]
        assert job["enabled"] is False
        assert job["script"]["path"] == script_path
        assert "prompt" not in job
        assert job["result_contract"]["workflow"] == workflow
        assert job["result_contract"]["artifact_dir"] == f"data/runs/{workflow}"


def test_scheduler_registry_phase1_contracts_pin_safe_execution_values():
    registry = load_job_registry(Path("configs/scheduler/roibang-v2.jobs.example.json"))

    for job in registry["jobs"]:
        contract = job["result_contract"]
        assert contract["must_equal"]["execution_enabled"] is False
        assert contract["must_equal"]["external_api_calls"] == 0

    jobs = {job["id"]: job for job in registry["jobs"]}
    for job_id in [
        "roibang-strategy-preflight",
        "roibang-strategy-dry-run",
        "roibang-strategy-approval",
        "roibang-strategy-execute",
        "roibang-create-request",
        "roibang-create-preflight",
        "roibang-create-provider-field-map-check",
        "roibang-create-field-mapping-review-pack",
        "roibang-create-template-slot-review-pack",
        "roibang-create-dry-run",
        "roibang-create-approval",
        "roibang-create-plan-snapshot",
        "roibang-create-execute",
        "roibang-create-chain-replay",
        "roibang-create-chain-manifest",
        "roibang-create-readiness-matrix",
        "roibang-create-live-execute-phase-gate",
        "roibang-create-live-payload-adapter-scaffold",
        "roibang-create-adapter-review-pack",
        "roibang-create-chain-index",
        "roibang-create-chain-final-report",
        "roibang-create-phase1-acceptance-checklist",
        "roibang-create-phase1-baseline-freeze",
    ]:
        assert "actions" in jobs[job_id]["result_contract"]["must_be_empty"]
    assert "payload_schema" in jobs["roibang-create-dry-run"]["result_contract"]["must_include"]
    assert "payload_contract" in jobs["roibang-create-dry-run"]["result_contract"]["must_include"]
    assert "payload_draft_contract" in jobs["roibang-create-dry-run"]["result_contract"]["must_include"]
    assert "redacted_payload_drafts" in jobs["roibang-create-dry-run"]["result_contract"]["must_include"]
    assert "provider_adapter" in jobs["roibang-create-dry-run"]["result_contract"]["must_include"]
    assert "provider_field_map_contract" in jobs["roibang-create-provider-field-map-check"]["result_contract"]["must_include"]
    assert "provider_field_map_digest" in jobs["roibang-create-provider-field-map-check"]["result_contract"]["must_include"]
    assert "provider_readiness_contract" in jobs["roibang-create-provider-field-map-check"]["result_contract"]["must_include"]
    assert "missing_required_fields" in jobs["roibang-create-provider-field-map-check"]["result_contract"]["must_include"]
    assert "duplicate_internal_fields" in jobs["roibang-create-provider-field-map-check"]["result_contract"]["must_include"]
    assert "unknown_internal_fields" in jobs["roibang-create-provider-field-map-check"]["result_contract"]["must_include"]
    assert "required_user_input_now" in jobs["roibang-create-field-mapping-review-pack"]["result_contract"]["must_include"]
    assert "review_contract" in jobs["roibang-create-field-mapping-review-pack"]["result_contract"]["must_include"]
    assert "review_sections" in jobs["roibang-create-field-mapping-review-pack"]["result_contract"]["must_include"]
    assert jobs["roibang-create-field-mapping-review-pack"]["result_contract"]["must_equal"]["required_user_input_now"] is False
    assert "template_contract" in jobs["roibang-create-template-slot-review-pack"]["result_contract"]["must_include"]
    assert "review_sections" in jobs["roibang-create-template-slot-review-pack"]["result_contract"]["must_include"]
    assert jobs["roibang-create-template-slot-review-pack"]["result_contract"]["must_equal"]["required_user_input_now"] is False
    assert "provider_adapter_contract" in jobs["roibang-create-dry-run"]["result_contract"]["must_include"]
    assert "provider_field_map" in jobs["roibang-create-dry-run"]["result_contract"]["must_include"]
    assert "provider_field_map_contract" in jobs["roibang-create-dry-run"]["result_contract"]["must_include"]
    assert "provider_field_map_digest" in jobs["roibang-create-dry-run"]["result_contract"]["must_include"]
    assert "provider_readiness_contract" in jobs["roibang-create-dry-run"]["result_contract"]["must_include"]
    assert "provider_payload_drafts" in jobs["roibang-create-dry-run"]["result_contract"]["must_include"]
    assert "idempotency_contract" in jobs["roibang-create-dry-run"]["result_contract"]["must_include"]
    assert "idempotency_ledger" in jobs["roibang-create-dry-run"]["result_contract"]["must_include"]
    assert "provider_field_map_digest" in jobs["roibang-create-approval"]["result_contract"]["must_include"]
    assert "payload_contract" in jobs["roibang-create-plan-snapshot"]["result_contract"]["must_include"]
    assert "payload_draft_contract" in jobs["roibang-create-plan-snapshot"]["result_contract"]["must_include"]
    assert "provider_adapter_contract" in jobs["roibang-create-plan-snapshot"]["result_contract"]["must_include"]
    assert "provider_field_map_contract" in jobs["roibang-create-plan-snapshot"]["result_contract"]["must_include"]
    assert "provider_field_map_digest" in jobs["roibang-create-plan-snapshot"]["result_contract"]["must_include"]
    assert "provider_readiness_contract" in jobs["roibang-create-plan-snapshot"]["result_contract"]["must_include"]
    assert "idempotency_contract" in jobs["roibang-create-plan-snapshot"]["result_contract"]["must_include"]
    assert "idempotency_ledger" in jobs["roibang-create-plan-snapshot"]["result_contract"]["must_include"]
    assert "provider_readiness_contract" in jobs["roibang-create-approval"]["result_contract"]["must_include"]
    assert "payload_schema" in jobs["roibang-create-execute"]["result_contract"]["must_include"]
    assert "provider_field_map_digest" in jobs["roibang-create-execute"]["result_contract"]["must_include"]
    assert "provider_readiness_contract" in jobs["roibang-create-execute"]["result_contract"]["must_include"]
    assert "digest_consistency" in jobs["roibang-create-chain-replay"]["result_contract"]["must_include"]
    assert "artifact_identity_contract" in jobs["roibang-create-chain-replay"]["result_contract"]["must_include"]
    assert "phase1_safety_contract" in jobs["roibang-create-chain-replay"]["result_contract"]["must_include"]
    assert "artifact_paths" in jobs["roibang-create-chain-manifest"]["result_contract"]["must_include"]
    assert "provider_payload_draft_digest" in jobs["roibang-create-chain-manifest"]["result_contract"]["must_include"]
    assert "phase1_safety_contract" in jobs["roibang-create-chain-manifest"]["result_contract"]["must_include"]
    assert "ready_for_live_execute" in jobs["roibang-create-readiness-matrix"]["result_contract"]["must_include"]
    assert "readiness_matrix" in jobs["roibang-create-readiness-matrix"]["result_contract"]["must_include"]
    assert "blocking_reasons" in jobs["roibang-create-readiness-matrix"]["result_contract"]["must_include"]
    assert "live_execute_development_allowed" in jobs["roibang-create-live-execute-phase-gate"]["result_contract"]["must_include"]
    assert "live_execute_allowed" in jobs["roibang-create-live-execute-phase-gate"]["result_contract"]["must_include"]
    assert "phase_gate_conditions" in jobs["roibang-create-live-execute-phase-gate"]["result_contract"]["must_include"]
    assert jobs["roibang-create-live-execute-phase-gate"]["result_contract"]["must_equal"]["live_execute_development_allowed"] is False
    assert jobs["roibang-create-live-execute-phase-gate"]["result_contract"]["must_equal"]["live_execute_allowed"] is False
    assert "adapter_interface" in jobs["roibang-create-live-payload-adapter-scaffold"]["result_contract"]["must_include"]
    assert "safety_contract" in jobs["roibang-create-live-payload-adapter-scaffold"]["result_contract"]["must_include"]
    assert "live_payloads" in jobs["roibang-create-live-payload-adapter-scaffold"]["result_contract"]["must_be_empty"]
    assert "executable_payloads" in jobs["roibang-create-live-payload-adapter-scaffold"]["result_contract"]["must_be_empty"]
    assert jobs["roibang-create-live-payload-adapter-scaffold"]["result_contract"]["must_equal"]["live_payload_generation_enabled"] is False
    assert "review_contract" in jobs["roibang-create-adapter-review-pack"]["result_contract"]["must_include"]
    assert "review_sections" in jobs["roibang-create-adapter-review-pack"]["result_contract"]["must_include"]
    assert jobs["roibang-create-adapter-review-pack"]["result_contract"]["must_equal"]["required_user_input_now"] is False
    assert "artifact_index" in jobs["roibang-create-chain-index"]["result_contract"]["must_include"]
    assert "artifact_paths" in jobs["roibang-create-chain-index"]["result_contract"]["must_include"]
    assert "safety_contract" in jobs["roibang-create-chain-index"]["result_contract"]["must_include"]
    assert "overall_status" in jobs["roibang-create-chain-final-report"]["result_contract"]["must_include"]
    assert "business_summary" in jobs["roibang-create-chain-final-report"]["result_contract"]["must_include"]
    assert "recommended_next_steps" in jobs["roibang-create-chain-final-report"]["result_contract"]["must_include"]
    assert jobs["roibang-create-chain-final-report"]["result_contract"]["must_equal"]["required_user_input_now"] is False
    assert "phase1_acceptance_status" in jobs[
        "roibang-create-phase1-acceptance-checklist"
    ]["result_contract"]["must_include"]
    assert "checklist" in jobs["roibang-create-phase1-acceptance-checklist"]["result_contract"]["must_include"]
    assert "blocking_items" in jobs[
        "roibang-create-phase1-acceptance-checklist"
    ]["result_contract"]["must_include"]
    assert jobs[
        "roibang-create-phase1-acceptance-checklist"
    ]["result_contract"]["must_equal"]["required_user_input_now"] is False
    assert "phase1_baseline_status" in jobs[
        "roibang-create-phase1-baseline-freeze"
    ]["result_contract"]["must_include"]
    assert "baseline_id" in jobs["roibang-create-phase1-baseline-freeze"]["result_contract"]["must_include"]
    assert "baseline_digest" in jobs["roibang-create-phase1-baseline-freeze"]["result_contract"]["must_include"]
    assert "freeze_contract" in jobs["roibang-create-phase1-baseline-freeze"]["result_contract"]["must_include"]
    assert jobs[
        "roibang-create-phase1-baseline-freeze"
    ]["result_contract"]["must_equal"]["required_user_input_now"] is False


def test_scheduler_registry_rejects_prompt_driven_jobs():
    registry = {
        "jobs": [
            {
                "id": "bad-ai-command",
                "name": "Bad AI command",
                "schedule": {"type": "cron", "expr": "0 1 * * *", "tz": "Asia/Shanghai"},
                "prompt": "调用 bash 工具运行创建脚本",
                "delivery": {"channel": "feishu-roi"},
            }
        ]
    }

    with pytest.raises(ValueError, match="prompt"):
        validate_job_registry(registry)


def test_live_mutation_jobs_must_have_policy_and_result_contract():
    registry = {
        "jobs": [
            {
                "id": "bad-live-job",
                "name": "Bad live job",
                "category": "live_mutation",
                "enabled": True,
                "schedule": {"type": "cron", "expr": "0 1 * * *", "tz": "Asia/Shanghai"},
                "script": {"path": "scripts/jobs/bad.py", "mode": "foreground"},
                "delivery": {"channel": "feishu-roi"},
            }
        ]
    }

    with pytest.raises(ValueError, match="policy"):
        validate_job_registry(registry)
