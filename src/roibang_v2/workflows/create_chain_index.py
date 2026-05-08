from __future__ import annotations

from pathlib import Path
from typing import Any

from roibang_v2.runs import write_run_artifact


WORKFLOWS = [
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


def _index_config(request: dict[str, Any]) -> dict[str, Any]:
    value = request.get("create_chain_index")
    return dict(value) if isinstance(value, dict) else dict(request)


def _artifact_path(artifact: dict[str, Any]) -> str:
    return str(artifact.get("artifact_path") or "")


def _external_api_calls(artifact: dict[str, Any]) -> int:
    return int(artifact.get("external_api_calls") or 0)


def _execution_enabled(artifact: dict[str, Any]) -> bool:
    return bool(artifact.get("execution_enabled", False))


def _actions_empty(artifact: dict[str, Any]) -> bool:
    return artifact.get("actions") in (None, [], {})


def _artifact_index(artifacts: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for workflow in WORKFLOWS:
        artifact = artifacts.get(workflow)
        if not isinstance(artifact, dict):
            continue
        rows.append(
            {
                "workflow": workflow,
                "artifact_path": _artifact_path(artifact),
                "ok": bool(artifact.get("ok", False)),
                "status": str(artifact.get("status") or ""),
                "execution_enabled": _execution_enabled(artifact),
                "external_api_calls": _external_api_calls(artifact),
            }
        )
    return rows


def _artifact_paths(artifacts: dict[str, dict[str, Any]]) -> dict[str, str]:
    return {
        workflow: _artifact_path(artifact)
        for workflow, artifact in artifacts.items()
        if workflow in WORKFLOWS and isinstance(artifact, dict)
    }


def _provider_payload_draft_digest(artifacts: dict[str, dict[str, Any]]) -> dict[str, Any]:
    dry_run = artifacts.get("create_dry_run") if isinstance(artifacts.get("create_dry_run"), dict) else {}
    digest = dry_run.get("provider_payload_draft_digest") if isinstance(dry_run, dict) else None
    if isinstance(digest, dict):
        return {
            "algorithm": str(digest.get("algorithm") or ""),
            "value": str(digest.get("value") or ""),
            "provider_payload_draft_count": int(digest.get("provider_payload_draft_count") or 0),
        }
    return {"algorithm": "sha256", "value": "", "provider_payload_draft_count": 0}


def _safety_contract(artifacts: dict[str, dict[str, Any]]) -> dict[str, Any]:
    present = [artifact for workflow, artifact in artifacts.items() if workflow in WORKFLOWS and isinstance(artifact, dict)]
    execution_enabled_false = all(not _execution_enabled(artifact) for artifact in present)
    external_api_calls_zero = all(_external_api_calls(artifact) == 0 for artifact in present)
    actions_empty = all(_actions_empty(artifact) for artifact in present)
    phase_gate = artifacts.get("create_live_execute_phase_gate")
    no_live_execute_allowed = not (
        isinstance(phase_gate, dict) and bool(phase_gate.get("live_execute_allowed", False))
    )
    scaffold = artifacts.get("create_live_payload_adapter_scaffold")
    no_live_payloads = True
    if isinstance(scaffold, dict):
        no_live_payloads = scaffold.get("live_payloads") == [] and scaffold.get("executable_payloads") == []
    passed = (
        execution_enabled_false
        and external_api_calls_zero
        and actions_empty
        and no_live_execute_allowed
        and no_live_payloads
    )
    return {
        "status": "passed" if passed else "failed",
        "execution_enabled_false": execution_enabled_false,
        "external_api_calls_zero": external_api_calls_zero,
        "actions_empty": actions_empty,
        "no_live_execute_allowed": no_live_execute_allowed,
        "no_live_payloads": no_live_payloads,
    }


def _violations(artifacts: dict[str, dict[str, Any]], safety: dict[str, Any]) -> list[str]:
    violations: list[str] = []
    for workflow in WORKFLOWS:
        artifact = artifacts.get(workflow)
        if not isinstance(artifact, dict):
            violations.append(f"missing artifact {workflow}")
            continue
        if _execution_enabled(artifact):
            violations.append(f"{workflow} execution_enabled must be false")
        if _external_api_calls(artifact) != 0:
            violations.append(f"{workflow} external_api_calls must be 0")
        if not _actions_empty(artifact):
            violations.append(f"{workflow} actions must be empty")
    if not bool(safety.get("no_live_execute_allowed", False)):
        violations.append("live execute must not be allowed")
    if not bool(safety.get("no_live_payloads", False)):
        violations.append("live payloads must be empty")
    return violations


def _summary(artifacts: dict[str, dict[str, Any]], violations: list[str]) -> dict[str, Any]:
    missing = sum(1 for workflow in WORKFLOWS if not isinstance(artifacts.get(workflow), dict))
    unsafe = sum(
        1
        for workflow in WORKFLOWS
        if isinstance(artifacts.get(workflow), dict)
        and (
            _execution_enabled(artifacts[workflow])
            or _external_api_calls(artifacts[workflow]) != 0
            or not _actions_empty(artifacts[workflow])
        )
    )
    readiness = artifacts.get("create_readiness_matrix")
    phase_gate = artifacts.get("create_live_execute_phase_gate")
    return {
        "artifact_count": sum(1 for workflow in WORKFLOWS if isinstance(artifacts.get(workflow), dict)),
        "missing_artifact_count": missing,
        "unsafe_artifact_count": unsafe,
        "ready_for_live_execute": bool(readiness.get("ready_for_live_execute", False)) if isinstance(readiness, dict) else False,
        "live_execute_allowed": bool(phase_gate.get("live_execute_allowed", False)) if isinstance(phase_gate, dict) else False,
    }


def build_create_chain_index(*, artifacts: dict[str, dict[str, Any]]) -> dict[str, Any]:
    normalized = {
        workflow: artifact
        for workflow, artifact in artifacts.items()
        if workflow in WORKFLOWS and isinstance(artifact, dict)
    }
    safety = _safety_contract(normalized)
    violations = _violations(normalized, safety)
    summary = _summary(normalized, violations)
    return {
        "ok": not violations,
        "workflow": "create_chain_index",
        "phase": "phase1",
        "execution_enabled": False,
        "external_api_calls": 0,
        "status": "indexed" if not violations else "incomplete",
        "summary": summary,
        "artifact_index": _artifact_index(normalized),
        "artifact_paths": _artifact_paths(normalized),
        "safety_contract": safety,
        "provider_payload_draft_digest": _provider_payload_draft_digest(normalized),
        "violations": violations,
        "actions": [],
    }


def run_create_chain_index_request(
    request: dict[str, Any],
    *,
    runs_dir: str | Path,
) -> dict[str, Any]:
    cfg = _index_config(request)
    artifacts = cfg.get("artifacts")
    if not isinstance(artifacts, dict):
        raise ValueError("create chain index requires artifacts")
    payload = build_create_chain_index(artifacts=artifacts)
    artifact_path = write_run_artifact(runs_dir, "create_chain_index", payload)
    return {**payload, "artifact_path": str(artifact_path)}
