from __future__ import annotations

from pathlib import Path
from typing import Any

from roibang_v2.runs import write_run_artifact
from roibang_v2.workflows.strategy_lineage import artifact_ref, assert_same_plan, lineage_ref, plan_payload, require_ref_fields


def _dry_run_config(request: dict[str, Any]) -> dict[str, Any]:
    value = request.get("strategy_dry_run")
    return dict(value) if isinstance(value, dict) else dict(request)


def _recommendations(plan: dict[str, Any]) -> list[dict[str, Any]]:
    strategy = plan.get("strategy") if isinstance(plan.get("strategy"), dict) else {}
    rows = strategy.get("recommendations") if isinstance(strategy.get("recommendations"), list) else []
    return [row for row in rows if isinstance(row, dict)]


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _candidate_tasks(plan: dict[str, Any]) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    for recommendation in _recommendations(plan):
        if recommendation.get("recommendation_type") != "plan_material_provision":
            continue
        material_ids = _string_list(recommendation.get("missing_material_ids"))
        if not material_ids:
            continue
        tasks.append(
            {
                "task_type": "material_provision_candidate",
                "product": str(recommendation.get("product") or ""),
                "source_advertiser_id": str(recommendation.get("source_advertiser_id") or ""),
                "target_advertiser_id": str(recommendation.get("target_advertiser_id") or ""),
                "material_ids": material_ids,
                "executable": False,
                "live_api_payloads": [],
                "allowed_phase1_output": "dry_run_only",
            }
        )
    return tasks


def _policy_limit(policy: dict[str, Any], key: str, default: int) -> int:
    try:
        value = int(policy.get(key) or default)
    except ValueError:
        value = default
    return max(value, 0)


def _violations(
    *,
    plan_ref: dict[str, Any],
    preflight: dict[str, Any],
    tasks: list[dict[str, Any]],
    policy: dict[str, Any],
) -> list[str]:
    violations: list[str] = []
    preflight_ref = artifact_ref(workflow="strategy_preflight", artifact=preflight)
    preflight_plan_ref = lineage_ref(preflight, "strategy_plan") or artifact_ref(
        workflow="strategy_preflight",
        artifact=preflight,
    )
    violations.extend(require_ref_fields("strategy plan", plan_ref))
    violations.extend(require_ref_fields("strategy preflight", preflight_ref))
    violations.extend(require_ref_fields("strategy preflight", preflight_plan_ref))
    violations.extend(
        assert_same_plan(
            left_name="strategy plan",
            left=plan_ref,
            right_name="strategy preflight",
            right=preflight_ref,
        )
    )
    violations.extend(
        assert_same_plan(
            left_name="strategy plan",
            left=plan_ref,
            right_name="strategy preflight",
            right=preflight_plan_ref,
        )
    )
    preflight_ok = bool(preflight.get("ok", True))
    if str(preflight.get("status") or "") != "passed" or not preflight_ok:
        violations.append("strategy preflight must pass before dry-run")
    if bool(preflight.get("approved_for_execute", False)):
        violations.append("strategy preflight must not approve execution in phase1")
    target_accounts = {task["target_advertiser_id"] for task in tasks if task.get("target_advertiser_id")}
    material_ids = {material_id for task in tasks for material_id in task.get("material_ids", [])}
    max_materials = _policy_limit(policy, "max_materials_per_dry_run", 50)
    max_targets = _policy_limit(policy, "max_target_accounts_per_dry_run", 20)
    if len(material_ids) > max_materials:
        violations.append("dry-run material count exceeds policy limit")
    if len(target_accounts) > max_targets:
        violations.append("dry-run target account count exceeds policy limit")
    for task in tasks:
        if bool(task.get("executable", False)):
            violations.append("dry-run candidate tasks must not be executable in phase1")
        if task.get("live_api_payloads"):
            violations.append("dry-run live_api_payloads must be empty in phase1")
    return violations


def build_strategy_dry_run(
    *,
    strategy_plan_artifact: dict[str, Any],
    strategy_preflight_artifact: dict[str, Any],
    policy: dict[str, Any],
) -> dict[str, Any]:
    plan = plan_payload(strategy_plan_artifact)
    tasks = _candidate_tasks(plan)
    plan_ref = artifact_ref(workflow="strategy_plan", artifact=strategy_plan_artifact)
    preflight_ref = artifact_ref(workflow="strategy_preflight", artifact=strategy_preflight_artifact)
    target_accounts = {task["target_advertiser_id"] for task in tasks if task.get("target_advertiser_id")}
    material_ids = {material_id for task in tasks for material_id in task.get("material_ids", [])}
    violations = _violations(plan_ref=plan_ref, preflight=strategy_preflight_artifact, tasks=tasks, policy=policy)
    status = "simulated" if not violations else "blocked"
    return {
        "ok": not violations,
        "workflow": "strategy_dry_run",
        "phase": "phase1",
        "execution_enabled": False,
        "external_api_calls": 0,
        "status": status,
        "summary": {
            "plan_id": str(plan.get("plan_id") or ""),
            "target_date": str(plan.get("target_date") or ""),
            "candidate_task_count": len(tasks) if not violations else 0,
            "target_account_count": len(target_accounts) if not violations else 0,
            "material_count": len(material_ids) if not violations else 0,
            "violation_count": len(violations),
        },
        "lineage": {
            "strategy_plan": plan_ref,
            "strategy_preflight": preflight_ref,
        },
        "policy": {
            "max_materials_per_dry_run": _policy_limit(policy, "max_materials_per_dry_run", 50),
            "max_target_accounts_per_dry_run": _policy_limit(policy, "max_target_accounts_per_dry_run", 20),
        },
        "candidate_tasks": tasks if not violations else [],
        "violations": violations,
        "approved_for_execute": False,
        "actions": [],
    }


def run_strategy_dry_run_request(
    request: dict[str, Any],
    *,
    runs_dir: str | Path,
) -> dict[str, Any]:
    cfg = _dry_run_config(request)
    strategy_plan_artifact = cfg.get("strategy_plan_artifact")
    strategy_preflight_artifact = cfg.get("strategy_preflight_artifact")
    if not isinstance(strategy_plan_artifact, dict):
        raise ValueError("strategy dry-run requires strategy_plan_artifact")
    if not isinstance(strategy_preflight_artifact, dict):
        raise ValueError("strategy dry-run requires strategy_preflight_artifact")
    policy = cfg.get("policy") if isinstance(cfg.get("policy"), dict) else {}
    payload = build_strategy_dry_run(
        strategy_plan_artifact=strategy_plan_artifact,
        strategy_preflight_artifact=strategy_preflight_artifact,
        policy=policy,
    )
    plan_path = cfg.get("strategy_plan_artifact_path")
    if str(plan_path or "").strip():
        payload["lineage"]["strategy_plan"]["artifact_path"] = str(plan_path)
    preflight_path = cfg.get("strategy_preflight_artifact_path")
    if str(preflight_path or "").strip():
        payload["lineage"]["strategy_preflight"]["artifact_path"] = str(preflight_path)
    artifact_path = write_run_artifact(runs_dir, "strategy_dry_run", payload)
    return {**payload, "artifact_path": str(artifact_path)}
