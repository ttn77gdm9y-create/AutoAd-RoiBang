from __future__ import annotations

from pathlib import Path
from typing import Any

from roibang_v2.runs import write_run_artifact
from roibang_v2.workflows.strategy_lineage import artifact_ref, plan_payload


def _preflight_config(request: dict[str, Any]) -> dict[str, Any]:
    value = request.get("strategy_preflight")
    return dict(value) if isinstance(value, dict) else dict(request)


def _recommendations(plan: dict[str, Any]) -> list[dict[str, Any]]:
    strategy = plan.get("strategy") if isinstance(plan.get("strategy"), dict) else {}
    rows = strategy.get("recommendations") if isinstance(strategy.get("recommendations"), list) else []
    return [row for row in rows if isinstance(row, dict)]


def _list_value(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _validate_plan_shape(plan: dict[str, Any]) -> list[str]:
    violations: list[str] = []
    if str(plan.get("phase") or "") != "phase1":
        violations.append("strategy plan phase must be phase1")
    if bool(plan.get("execution_enabled", False)):
        violations.append("strategy plan execution_enabled must be false")
    if int(plan.get("external_api_calls") or 0) != 0:
        violations.append("strategy plan external_api_calls must be 0")
    if _list_value(plan.get("actions")):
        violations.append("strategy plan actions must be empty in phase1")

    dry_run = plan.get("dry_run") if isinstance(plan.get("dry_run"), dict) else {}
    if _list_value(dry_run.get("payloads")):
        violations.append("dry_run payloads must be empty in phase1")
    approval = plan.get("approval") if isinstance(plan.get("approval"), dict) else {}
    if str(approval.get("status") or "") != "disabled_in_phase1":
        violations.append("approval must be disabled in phase1")
    execute = plan.get("execute") if isinstance(plan.get("execute"), dict) else {}
    if str(execute.get("status") or "") != "disabled_in_phase1":
        violations.append("execute must be disabled in phase1")
    return violations


def _validate_material_provision_recommendation(recommendation: dict[str, Any]) -> list[str]:
    violations: list[str] = []
    if str(recommendation.get("allowed_phase1_output") or "") != "material_provision_plan_only":
        violations.append("material provision recommendation must be plan-only")
    for key in ("product", "source_advertiser_id", "target_advertiser_id"):
        if not str(recommendation.get(key) or "").strip():
            violations.append(f"material provision recommendation missing {key}")
    missing_material_ids = [str(item).strip() for item in _list_value(recommendation.get("missing_material_ids")) if str(item).strip()]
    if not missing_material_ids:
        violations.append("material provision recommendation missing material ids")
    return violations


def build_strategy_preflight(strategy_plan_artifact: dict[str, Any]) -> dict[str, Any]:
    plan = plan_payload(strategy_plan_artifact)
    recommendations = _recommendations(plan)
    material_recommendations = [
        item for item in recommendations if item.get("recommendation_type") == "plan_material_provision"
    ]
    violations = _validate_plan_shape(plan)
    for recommendation in material_recommendations:
        violations.extend(_validate_material_provision_recommendation(recommendation))

    status = "passed" if not violations else "failed"
    return {
        "ok": not violations,
        "workflow": "strategy_preflight",
        "phase": "phase1",
        "execution_enabled": False,
        "external_api_calls": 0,
        "status": status,
        "summary": {
            "plan_id": str(plan.get("plan_id") or ""),
            "target_date": str(plan.get("target_date") or ""),
            "recommendation_count": len(recommendations),
            "material_provision_recommendation_count": len(material_recommendations),
            "violation_count": len(violations),
        },
        "lineage": {
            "strategy_plan": artifact_ref(workflow="strategy_plan", artifact=strategy_plan_artifact),
        },
        "checks": [
            "validate_phase1_plan_only",
            "validate_no_live_actions",
            "validate_no_dry_run_payloads",
            "validate_material_provision_recommendations",
        ],
        "violations": violations,
        "approved_for_execute": False,
        "actions": [],
    }


def run_strategy_preflight_request(
    request: dict[str, Any],
    *,
    runs_dir: str | Path,
) -> dict[str, Any]:
    cfg = _preflight_config(request)
    artifact = cfg.get("strategy_plan_artifact")
    if not isinstance(artifact, dict):
        raise ValueError("strategy preflight requires strategy_plan_artifact")
    payload = build_strategy_preflight(artifact)
    source_path = cfg.get("strategy_plan_artifact_path")
    if str(source_path or "").strip():
        payload["lineage"]["strategy_plan"]["artifact_path"] = str(source_path)
    artifact_path = write_run_artifact(runs_dir, "strategy_preflight", payload)
    return {**payload, "artifact_path": str(artifact_path)}
