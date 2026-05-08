from __future__ import annotations

from pathlib import Path
from typing import Any

from roibang_v2.runs import write_run_artifact


def _scaffold_config(request: dict[str, Any]) -> dict[str, Any]:
    value = request.get("create_live_payload_adapter_scaffold")
    return dict(value) if isinstance(value, dict) else dict(request)


def _create_execute_policy(policy: dict[str, Any]) -> dict[str, Any]:
    value = policy.get("create_execute")
    return dict(value) if isinstance(value, dict) else {}


def _payload_schema_policy(policy: dict[str, Any]) -> dict[str, Any]:
    value = _create_execute_policy(policy).get("payload_schema")
    return dict(value) if isinstance(value, dict) else {}


def _provider_adapter(dry_run: dict[str, Any]) -> dict[str, Any]:
    value = dry_run.get("provider_adapter")
    return dict(value) if isinstance(value, dict) else {}


def _provider(dry_run: dict[str, Any]) -> str:
    return str(_provider_adapter(dry_run).get("provider") or "oceanengine")


def _field_mapping_version(dry_run: dict[str, Any]) -> str:
    return str(_provider_adapter(dry_run).get("field_mapping_version") or "")


def _provider_payload_drafts(dry_run: dict[str, Any]) -> list[dict[str, Any]]:
    rows = dry_run.get("provider_payload_drafts")
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _provider_payload_draft_digest(dry_run: dict[str, Any]) -> dict[str, Any]:
    digest = dry_run.get("provider_payload_draft_digest")
    if isinstance(digest, dict):
        return {
            "algorithm": str(digest.get("algorithm") or ""),
            "value": str(digest.get("value") or ""),
            "provider_payload_draft_count": int(digest.get("provider_payload_draft_count") or 0),
        }
    return {
        "algorithm": "sha256",
        "value": "",
        "provider_payload_draft_count": len(_provider_payload_drafts(dry_run)),
    }


def _phase_gate_allows_development(phase_gate: dict[str, Any]) -> bool:
    return bool(phase_gate.get("live_execute_development_allowed", False))


def _phase_gate_allows_live_execute(phase_gate: dict[str, Any]) -> bool:
    return bool(phase_gate.get("live_execute_allowed", False))


def _policy_generation_enabled(policy: dict[str, Any]) -> bool:
    return bool(_payload_schema_policy(policy).get("live_payload_generation_enabled", False))


def _violations(phase_gate: dict[str, Any], policy: dict[str, Any]) -> list[str]:
    violations: list[str] = []
    if str(policy.get("phase") or "phase1") == "phase1" and _policy_generation_enabled(policy):
        violations.append("phase1 policy must keep live payload generation disabled")
    if _phase_gate_allows_live_execute(phase_gate):
        violations.append("phase gate must not allow live execute for adapter scaffold")
    return violations


def _adapter_interface(dry_run: dict[str, Any]) -> dict[str, Any]:
    return {
        "provider": _provider(dry_run),
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


def _safety_contract(phase_gate: dict[str, Any], *, violations: list[str]) -> dict[str, Any]:
    return {
        "status": "blocked" if violations or not _phase_gate_allows_development(phase_gate) else "development_allowed",
        "phase_gate_allows_development": _phase_gate_allows_development(phase_gate),
        "phase_gate_allows_live_execute": _phase_gate_allows_live_execute(phase_gate),
        "live_payload_generation_enabled": False,
        "live_payload_count_zero": True,
        "executable_payload_count_zero": True,
        "external_api_calls_zero": True,
    }


def _blocking_reasons(phase_gate: dict[str, Any], violations: list[str]) -> list[str]:
    if violations:
        return violations
    if not _phase_gate_allows_development(phase_gate):
        return ["live execute phase gate has not opened development"]
    return []


def build_create_live_payload_adapter_scaffold(
    *,
    create_dry_run_artifact: dict[str, Any],
    create_live_execute_phase_gate_artifact: dict[str, Any],
    policy: dict[str, Any],
) -> dict[str, Any]:
    violations = _violations(create_live_execute_phase_gate_artifact, policy)
    drafts = _provider_payload_drafts(create_dry_run_artifact)
    live_payloads: list[dict[str, Any]] = []
    executable_payloads: list[dict[str, Any]] = []
    safety = _safety_contract(create_live_execute_phase_gate_artifact, violations=violations)
    return {
        "ok": not violations,
        "workflow": "create_live_payload_adapter_scaffold",
        "phase": "phase1",
        "execution_enabled": False,
        "external_api_calls": 0,
        "status": str(safety["status"]),
        "live_payload_generation_enabled": False,
        "live_payloads": live_payloads,
        "executable_payloads": executable_payloads,
        "summary": {
            "provider": _provider(create_dry_run_artifact),
            "field_mapping_version": _field_mapping_version(create_dry_run_artifact),
            "provider_payload_draft_count": len(drafts),
            "live_payload_count": len(live_payloads),
            "executable_payload_count": len(executable_payloads),
            "phase_gate_status": str(create_live_execute_phase_gate_artifact.get("status") or ""),
        },
        "adapter_interface": _adapter_interface(create_dry_run_artifact),
        "safety_contract": safety,
        "provider_payload_draft_digest": _provider_payload_draft_digest(create_dry_run_artifact),
        "blocking_reasons": _blocking_reasons(create_live_execute_phase_gate_artifact, violations),
        "violations": violations,
        "actions": [],
    }


def run_create_live_payload_adapter_scaffold_request(
    request: dict[str, Any],
    *,
    runs_dir: str | Path,
) -> dict[str, Any]:
    cfg = _scaffold_config(request)
    dry_run = cfg.get("create_dry_run_artifact")
    phase_gate = cfg.get("create_live_execute_phase_gate_artifact")
    if not isinstance(dry_run, dict):
        raise ValueError("create live payload adapter scaffold requires create_dry_run_artifact")
    if not isinstance(phase_gate, dict):
        raise ValueError("create live payload adapter scaffold requires create_live_execute_phase_gate_artifact")
    policy = cfg.get("policy") if isinstance(cfg.get("policy"), dict) else {}
    payload = build_create_live_payload_adapter_scaffold(
        create_dry_run_artifact=dry_run,
        create_live_execute_phase_gate_artifact=phase_gate,
        policy=policy,
    )
    artifact_path = write_run_artifact(runs_dir, "create_live_payload_adapter_scaffold", payload)
    return {**payload, "artifact_path": str(artifact_path)}
