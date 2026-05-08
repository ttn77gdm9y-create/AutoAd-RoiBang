from __future__ import annotations

from pathlib import Path
from typing import Any

from roibang_v2.runs import write_run_artifact
from roibang_v2.workflows.strategy_lineage import artifact_ref, assert_same_plan, lineage_ref, require_ref_fields


def _execute_config(request: dict[str, Any]) -> dict[str, Any]:
    value = request.get("strategy_execute")
    return dict(value) if isinstance(value, dict) else dict(request)


def _summary(approval: dict[str, Any]) -> dict[str, Any]:
    summary = approval.get("summary") if isinstance(approval.get("summary"), dict) else {}
    return {
        "plan_id": str(summary.get("plan_id") or ""),
        "target_date": str(summary.get("target_date") or ""),
        "candidate_task_count": int(summary.get("candidate_task_count") or 0),
        "target_account_count": int(summary.get("target_account_count") or 0),
        "material_count": int(summary.get("material_count") or 0),
        "approval_status": str(approval.get("status") or ""),
        "policy_decision": str(approval.get("policy_decision") or ""),
        "execute_allowed": bool(approval.get("execute_allowed", False)),
    }


def _violations(approval: dict[str, Any]) -> list[str]:
    violations: list[str] = []
    approval_ref = artifact_ref(workflow="strategy_approval", artifact=approval)
    violations.extend(require_ref_fields("strategy approval", approval_ref))
    dry_run_ref = lineage_ref(approval, "strategy_dry_run")
    violations.extend(require_ref_fields("strategy dry-run", dry_run_ref))
    if dry_run_ref:
        violations.extend(
            assert_same_plan(
                left_name="strategy approval",
                left=approval_ref,
                right_name="strategy dry-run",
                right=dry_run_ref,
            )
        )
    plan_ref = lineage_ref(approval, "strategy_plan")
    violations.extend(require_ref_fields("strategy plan", plan_ref))
    if plan_ref:
        violations.extend(
            assert_same_plan(
                left_name="strategy approval",
                left=approval_ref,
                right_name="strategy plan",
                right=plan_ref,
            )
        )
    if str(approval.get("status") or "") != "recorded" or not bool(approval.get("ok", True)):
        violations.append("strategy approval must be recorded before execute")
    if bool(approval.get("execution_enabled", False)):
        violations.append("strategy approval execution_enabled must be false")
    if int(approval.get("external_api_calls") or 0) != 0:
        violations.append("strategy approval external_api_calls must be 0")
    if bool(approval.get("execute_allowed", False)):
        violations.append("strategy approval execute_allowed must be false in phase1")
    if bool(approval.get("approved_for_execute", False)):
        violations.append("strategy approval approved_for_execute must be false in phase1")
    if approval.get("actions"):
        violations.append("strategy approval actions must be empty in phase1")
    violations.extend(str(item) for item in approval.get("violations") or [])
    return violations


def build_strategy_execute(
    *,
    strategy_approval_artifact: dict[str, Any],
    policy: dict[str, Any],
) -> dict[str, Any]:
    del policy
    violations = _violations(strategy_approval_artifact)
    return {
        "ok": not violations,
        "workflow": "strategy_execute",
        "phase": "phase1",
        "execution_enabled": False,
        "external_api_calls": 0,
        "status": "blocked",
        "reason": "phase1_execute_disabled",
        "summary": _summary(strategy_approval_artifact),
        "lineage": {
            "strategy_approval": artifact_ref(workflow="strategy_approval", artifact=strategy_approval_artifact),
            "strategy_dry_run": lineage_ref(strategy_approval_artifact, "strategy_dry_run"),
            "strategy_plan": lineage_ref(strategy_approval_artifact, "strategy_plan"),
            "strategy_preflight": lineage_ref(strategy_approval_artifact, "strategy_preflight"),
        },
        "violations": violations,
        "approved_for_execute": False,
        "executed_task_count": 0,
        "actions": [],
    }


def run_strategy_execute_request(
    request: dict[str, Any],
    *,
    runs_dir: str | Path,
) -> dict[str, Any]:
    cfg = _execute_config(request)
    strategy_approval_artifact = cfg.get("strategy_approval_artifact")
    if not isinstance(strategy_approval_artifact, dict):
        raise ValueError("strategy execute requires strategy_approval_artifact")
    policy = cfg.get("policy") if isinstance(cfg.get("policy"), dict) else {}
    payload = build_strategy_execute(strategy_approval_artifact=strategy_approval_artifact, policy=policy)
    approval_path = cfg.get("strategy_approval_artifact_path")
    if str(approval_path or "").strip():
        payload["lineage"]["strategy_approval"]["artifact_path"] = str(approval_path)
    artifact_path = write_run_artifact(runs_dir, "strategy_execute", payload)
    return {**payload, "artifact_path": str(artifact_path)}
