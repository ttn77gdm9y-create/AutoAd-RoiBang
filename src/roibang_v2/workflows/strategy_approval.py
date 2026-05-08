from __future__ import annotations

from pathlib import Path
from typing import Any

from roibang_v2.runs import write_run_artifact
from roibang_v2.workflows.strategy_lineage import artifact_ref, assert_same_plan, lineage_ref, require_ref_fields


def _approval_config(request: dict[str, Any]) -> dict[str, Any]:
    value = request.get("strategy_approval")
    return dict(value) if isinstance(value, dict) else dict(request)


def _policy_limit(policy: dict[str, Any], key: str, default: int) -> int:
    try:
        value = int(policy.get(key) or default)
    except ValueError:
        value = default
    return max(value, 0)


def _summary(dry_run: dict[str, Any]) -> dict[str, int | str]:
    summary = dry_run.get("summary") if isinstance(dry_run.get("summary"), dict) else {}
    return {
        "plan_id": str(summary.get("plan_id") or ""),
        "target_date": str(summary.get("target_date") or ""),
        "candidate_task_count": int(summary.get("candidate_task_count") or 0),
        "target_account_count": int(summary.get("target_account_count") or 0),
        "material_count": int(summary.get("material_count") or 0),
        "violation_count": int(summary.get("violation_count") or 0),
    }


def _violations(dry_run: dict[str, Any], policy: dict[str, Any]) -> list[str]:
    violations: list[str] = []
    dry_run_ref = artifact_ref(workflow="strategy_dry_run", artifact=dry_run)
    violations.extend(require_ref_fields("strategy dry-run", dry_run_ref))
    dry_run_plan_ref = lineage_ref(dry_run, "strategy_plan")
    violations.extend(require_ref_fields("strategy plan", dry_run_plan_ref))
    if dry_run_plan_ref:
        violations.extend(
            assert_same_plan(
                left_name="strategy dry-run",
                left=dry_run_ref,
                right_name="strategy plan",
                right=dry_run_plan_ref,
            )
        )
    dry_run_preflight_ref = lineage_ref(dry_run, "strategy_preflight")
    violations.extend(require_ref_fields("strategy preflight", dry_run_preflight_ref))
    if dry_run_preflight_ref:
        violations.extend(
            assert_same_plan(
                left_name="strategy dry-run",
                left=dry_run_ref,
                right_name="strategy preflight",
                right=dry_run_preflight_ref,
            )
        )
    if str(dry_run.get("status") or "") != "simulated" or not bool(dry_run.get("ok", True)):
        violations.append("strategy dry-run must be simulated before approval")
    if bool(dry_run.get("execution_enabled", False)):
        violations.append("strategy dry-run execution_enabled must be false")
    if int(dry_run.get("external_api_calls") or 0) != 0:
        violations.append("strategy dry-run external_api_calls must be 0")
    if bool(dry_run.get("approved_for_execute", False)):
        violations.append("strategy dry-run must not already be approved for execute")
    if dry_run.get("actions"):
        violations.append("strategy dry-run actions must be empty in phase1")
    summary = _summary(dry_run)
    if int(summary["material_count"]) > _policy_limit(policy, "max_materials_per_approval", 50):
        violations.append("approval material count exceeds policy limit")
    if int(summary["target_account_count"]) > _policy_limit(policy, "max_target_accounts_per_approval", 20):
        violations.append("approval target account count exceeds policy limit")
    for task in dry_run.get("candidate_tasks") or []:
        if not isinstance(task, dict):
            continue
        if bool(task.get("executable", False)):
            violations.append("approval candidate tasks must not be executable in phase1")
        if task.get("live_api_payloads"):
            violations.append("approval candidate tasks must not contain live_api_payloads in phase1")
    violations.extend(str(item) for item in dry_run.get("violations") or [])
    return violations


def build_strategy_approval(
    *,
    strategy_dry_run_artifact: dict[str, Any],
    policy: dict[str, Any],
) -> dict[str, Any]:
    violations = _violations(strategy_dry_run_artifact, policy)
    summary = _summary(strategy_dry_run_artifact)
    if violations:
        status = "blocked"
        policy_decision = "reject"
    elif bool(policy.get("auto_approve_phase1", False)):
        status = "recorded"
        policy_decision = "would_approve"
    else:
        status = "recorded"
        policy_decision = "record_only"
    return {
        "ok": not violations,
        "workflow": "strategy_approval",
        "phase": "phase1",
        "execution_enabled": False,
        "external_api_calls": 0,
        "status": status,
        "approval_mode": "phase1_record_only",
        "policy_decision": policy_decision,
        "approved": False,
        "execute_allowed": False,
        "approved_for_execute": False,
        "summary": summary,
        "lineage": {
            "strategy_dry_run": artifact_ref(workflow="strategy_dry_run", artifact=strategy_dry_run_artifact),
            "strategy_plan": lineage_ref(strategy_dry_run_artifact, "strategy_plan"),
            "strategy_preflight": lineage_ref(strategy_dry_run_artifact, "strategy_preflight"),
        },
        "policy": {
            "auto_approve_phase1": bool(policy.get("auto_approve_phase1", False)),
            "max_materials_per_approval": _policy_limit(policy, "max_materials_per_approval", 50),
            "max_target_accounts_per_approval": _policy_limit(policy, "max_target_accounts_per_approval", 20),
        },
        "violations": violations,
        "actions": [],
    }


def run_strategy_approval_request(
    request: dict[str, Any],
    *,
    runs_dir: str | Path,
) -> dict[str, Any]:
    cfg = _approval_config(request)
    strategy_dry_run_artifact = cfg.get("strategy_dry_run_artifact")
    if not isinstance(strategy_dry_run_artifact, dict):
        raise ValueError("strategy approval requires strategy_dry_run_artifact")
    policy = cfg.get("policy") if isinstance(cfg.get("policy"), dict) else {}
    payload = build_strategy_approval(strategy_dry_run_artifact=strategy_dry_run_artifact, policy=policy)
    dry_run_path = cfg.get("strategy_dry_run_artifact_path")
    if str(dry_run_path or "").strip():
        payload["lineage"]["strategy_dry_run"]["artifact_path"] = str(dry_run_path)
    artifact_path = write_run_artifact(runs_dir, "strategy_approval", payload)
    return {**payload, "artifact_path": str(artifact_path)}
