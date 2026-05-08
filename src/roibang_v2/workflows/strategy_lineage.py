from __future__ import annotations

from pathlib import Path
from typing import Any


def plan_payload(strategy_plan_artifact: dict[str, Any]) -> dict[str, Any]:
    plan = strategy_plan_artifact.get("plan")
    return plan if isinstance(plan, dict) else strategy_plan_artifact


def artifact_ref(
    *,
    workflow: str,
    artifact: dict[str, Any],
    artifact_path: str | Path | None = None,
) -> dict[str, str]:
    summary = artifact.get("summary") if isinstance(artifact.get("summary"), dict) else {}
    if workflow == "strategy_plan":
        plan = plan_payload(artifact)
        plan_id = str(plan.get("plan_id") or "")
        target_date = str(plan.get("target_date") or artifact.get("target_date") or "")
    else:
        plan_id = str(summary.get("plan_id") or artifact.get("plan_id") or "")
        target_date = str(summary.get("target_date") or artifact.get("target_date") or "")
    return {
        "workflow": workflow,
        "artifact_path": str(artifact_path or ""),
        "plan_id": plan_id,
        "target_date": target_date,
    }


def lineage_ref(
    artifact: dict[str, Any],
    key: str,
) -> dict[str, Any]:
    lineage = artifact.get("lineage") if isinstance(artifact.get("lineage"), dict) else {}
    value = lineage.get(key)
    return value if isinstance(value, dict) else {}


def assert_same_plan(
    *,
    left_name: str,
    left: dict[str, Any],
    right_name: str,
    right: dict[str, Any],
) -> list[str]:
    violations: list[str] = []
    left_plan_id = str(left.get("plan_id") or "")
    right_plan_id = str(right.get("plan_id") or "")
    if left_plan_id and right_plan_id and left_plan_id != right_plan_id:
        violations.append(f"{left_name} plan_id must match {right_name} plan_id")

    left_target_date = str(left.get("target_date") or "")
    right_target_date = str(right.get("target_date") or "")
    if left_target_date and right_target_date and left_target_date != right_target_date:
        violations.append(f"{left_name} target_date must match {right_name} target_date")
    return violations


def require_ref_fields(name: str, ref: dict[str, Any]) -> list[str]:
    violations: list[str] = []
    if not ref:
        return [f"{name} lineage reference is required"]
    for field in ("plan_id", "target_date"):
        if not str(ref.get(field) or "").strip():
            violations.append(f"{name} {field} is required")
    return violations
