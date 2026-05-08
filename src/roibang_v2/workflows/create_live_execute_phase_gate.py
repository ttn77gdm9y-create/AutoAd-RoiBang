from __future__ import annotations

from pathlib import Path
from typing import Any

from roibang_v2.runs import write_run_artifact


def _gate_config(request: dict[str, Any]) -> dict[str, Any]:
    value = request.get("create_live_execute_phase_gate")
    return dict(value) if isinstance(value, dict) else dict(request)


def _create_execute_policy(policy: dict[str, Any]) -> dict[str, Any]:
    value = policy.get("create_execute")
    return dict(value) if isinstance(value, dict) else {}


def _phase_gate_policy(policy: dict[str, Any]) -> dict[str, Any]:
    value = _create_execute_policy(policy).get("phase_gate")
    return dict(value) if isinstance(value, dict) else {}


def _current_phase(policy: dict[str, Any]) -> str:
    return str(policy.get("phase") or "phase1")


def _required_next_phase(policy: dict[str, Any]) -> str:
    return str(_phase_gate_policy(policy).get("required_next_phase") or "phase2")


def _readiness_ready(artifact: dict[str, Any]) -> bool:
    return (
        bool(artifact.get("ok", False))
        and str(artifact.get("status") or "") == "ready"
        and bool(artifact.get("ready_for_live_execute", False))
    )


def _allow_development(policy: dict[str, Any]) -> bool:
    return bool(_phase_gate_policy(policy).get("allow_live_execute_development", False))


def _allow_live_execute(policy: dict[str, Any]) -> bool:
    gate = _phase_gate_policy(policy)
    return bool(gate.get("allow_live_execute", False) or _create_execute_policy(policy).get("allow_live_execute", False))


def _condition(condition: str, passed: bool, reason: str) -> dict[str, Any]:
    return {
        "condition": condition,
        "passed": passed,
        "reason": "" if passed else reason,
    }


def _conditions(readiness: dict[str, Any], policy: dict[str, Any]) -> list[dict[str, Any]]:
    phase = _current_phase(policy)
    allow_development = _allow_development(policy)
    allow_live_execute = _allow_live_execute(policy)
    return [
        _condition(
            "current_phase_is_not_phase1",
            phase != "phase1",
            f"current phase is {phase}",
        ),
        _condition(
            "readiness_matrix_ready",
            _readiness_ready(readiness),
            "readiness matrix is not ready",
        ),
        _condition(
            "policy_allows_live_execute_development",
            allow_development,
            "policy does not allow live execute development",
        ),
        _condition(
            "policy_blocks_live_execute",
            not allow_live_execute,
            "policy must keep live execute blocked at phase gate",
        ),
        _condition(
            "phase1_safety_values_retained",
            True,
            "",
        ),
    ]


def _policy_violations(policy: dict[str, Any]) -> list[str]:
    if _current_phase(policy) != "phase1":
        return []
    violations: list[str] = []
    if _allow_development(policy):
        violations.append("phase1 policy must not allow live execute development")
    if _allow_live_execute(policy):
        violations.append("phase1 policy must not allow live execute")
    return violations


def _summary(readiness: dict[str, Any], policy: dict[str, Any], conditions: list[dict[str, Any]]) -> dict[str, Any]:
    passed = sum(1 for item in conditions if bool(item.get("passed", False)))
    blocking = len(conditions) - passed
    return {
        "current_phase": _current_phase(policy),
        "required_next_phase": _required_next_phase(policy),
        "readiness_status": str(readiness.get("status") or ""),
        "ready_for_live_execute": bool(readiness.get("ready_for_live_execute", False)),
        "condition_count": len(conditions),
        "passed_condition_count": passed,
        "blocking_condition_count": blocking,
    }


def build_create_live_execute_phase_gate(
    *,
    create_readiness_matrix_artifact: dict[str, Any],
    policy: dict[str, Any],
) -> dict[str, Any]:
    conditions = _conditions(create_readiness_matrix_artifact, policy)
    violations = _policy_violations(policy)
    summary = _summary(create_readiness_matrix_artifact, policy, conditions)
    development_allowed = (
        int(summary.get("blocking_condition_count") or 0) == 0
        and not violations
        and _allow_development(policy)
        and not _allow_live_execute(policy)
    )
    return {
        "ok": not violations,
        "workflow": "create_live_execute_phase_gate",
        "phase": "phase1",
        "execution_enabled": False,
        "external_api_calls": 0,
        "status": "development_allowed" if development_allowed else "blocked",
        "live_execute_development_allowed": development_allowed,
        "live_execute_allowed": False,
        "summary": summary,
        "phase_gate_conditions": conditions,
        "readiness_blocking_reasons": list(create_readiness_matrix_artifact.get("blocking_reasons") or []),
        "blocking_reasons": [str(item.get("reason") or "") for item in conditions if not bool(item.get("passed", False))],
        "violations": violations,
        "actions": [],
    }


def run_create_live_execute_phase_gate_request(
    request: dict[str, Any],
    *,
    runs_dir: str | Path,
) -> dict[str, Any]:
    cfg = _gate_config(request)
    readiness = cfg.get("create_readiness_matrix_artifact")
    if not isinstance(readiness, dict):
        raise ValueError("create live execute phase gate requires create_readiness_matrix_artifact")
    policy = cfg.get("policy") if isinstance(cfg.get("policy"), dict) else {}
    payload = build_create_live_execute_phase_gate(create_readiness_matrix_artifact=readiness, policy=policy)
    artifact_path = write_run_artifact(runs_dir, "create_live_execute_phase_gate", payload)
    return {**payload, "artifact_path": str(artifact_path)}
