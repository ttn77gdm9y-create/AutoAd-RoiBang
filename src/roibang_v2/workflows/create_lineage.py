from __future__ import annotations

from pathlib import Path
from typing import Any


def create_plan_payload(artifact: dict[str, Any]) -> dict[str, Any]:
    plan = artifact.get("plan")
    return plan if isinstance(plan, dict) else artifact


def create_request_payload(artifact: dict[str, Any]) -> dict[str, Any]:
    request = artifact.get("request")
    return request if isinstance(request, dict) else artifact


def create_ref(
    *,
    workflow: str,
    artifact: dict[str, Any],
    artifact_path: str | Path | None = None,
) -> dict[str, str]:
    summary = artifact.get("summary") if isinstance(artifact.get("summary"), dict) else {}
    if workflow == "create_strategy_plan":
        plan = create_plan_payload(artifact)
        plan_id = str(plan.get("plan_id") or "")
        request_id = str(plan.get("request_id") or "")
        target_date = str(plan.get("target_date") or "")
    elif workflow == "create_request":
        request = create_request_payload(artifact)
        plan_id = ""
        request_id = str(request.get("request_id") or summary.get("request_id") or "")
        target_date = str(request.get("target_date") or summary.get("target_date") or "")
    else:
        plan_id = str(summary.get("plan_id") or artifact.get("plan_id") or "")
        request_id = str(summary.get("request_id") or artifact.get("request_id") or "")
        target_date = str(summary.get("target_date") or artifact.get("target_date") or "")
    return {
        "workflow": workflow,
        "artifact_path": str(artifact_path or ""),
        "plan_id": plan_id,
        "request_id": request_id,
        "target_date": target_date,
    }


def create_lineage_ref(artifact: dict[str, Any], key: str) -> dict[str, Any]:
    lineage = artifact.get("lineage") if isinstance(artifact.get("lineage"), dict) else {}
    value = lineage.get(key)
    return value if isinstance(value, dict) else {}


def assert_same_create_plan(
    *,
    left_name: str,
    left: dict[str, Any],
    right_name: str,
    right: dict[str, Any],
) -> list[str]:
    violations: list[str] = []
    for field in ("plan_id", "request_id", "target_date"):
        left_value = str(left.get(field) or "")
        right_value = str(right.get(field) or "")
        if left_value and right_value and left_value != right_value:
            violations.append(f"{left_name} {field} must match {right_name} {field}")
    return violations


def require_create_ref_fields(name: str, ref: dict[str, Any]) -> list[str]:
    violations: list[str] = []
    if not ref:
        return [f"{name} lineage reference is required"]
    for field in ("plan_id", "request_id", "target_date"):
        if not str(ref.get(field) or "").strip():
            violations.append(f"{name} {field} is required")
    return violations
