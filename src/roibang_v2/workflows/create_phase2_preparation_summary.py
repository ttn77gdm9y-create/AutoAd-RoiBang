from __future__ import annotations

from pathlib import Path
from typing import Any

from roibang_v2.runs import write_run_artifact


def _summary_config(request: dict[str, Any]) -> dict[str, Any]:
    value = request.get("create_phase2_preparation_summary")
    return dict(value) if isinstance(value, dict) else dict(request)


def _artifact_status(artifact: dict[str, Any]) -> str:
    return str(artifact.get("status") or "")


def _artifact_ok(artifact: dict[str, Any]) -> bool:
    return bool(artifact.get("ok", False))


def _safe_artifact(artifact: dict[str, Any], workflow: str) -> list[str]:
    violations: list[str] = []
    if str(artifact.get("workflow") or "") != workflow:
        violations.append(f"{workflow} artifact workflow mismatch")
    if str(artifact.get("phase") or "") != "phase2_preparation":
        violations.append(f"{workflow} artifact phase must be phase2_preparation")
    if bool(artifact.get("execution_enabled", False)):
        violations.append(f"{workflow} artifact execution_enabled must be false")
    if int(artifact.get("external_api_calls") or 0) != 0:
        violations.append(f"{workflow} artifact external_api_calls must be 0")
    if artifact.get("actions"):
        violations.append(f"{workflow} artifact actions must be empty")
    violations.extend(str(item) for item in artifact.get("violations") or [])
    return violations


def _row(
    *,
    check: str,
    workflow: str,
    artifact: dict[str, Any],
    unresolved_count: int,
    reason: str,
) -> dict[str, Any]:
    blocking = not _artifact_ok(artifact) or _artifact_status(artifact) in {"blocked", "invalid", "incomplete"}
    ready = _artifact_ok(artifact) and _artifact_status(artifact) in {"reviewed", "verified"} and unresolved_count == 0
    return {
        "check": check,
        "workflow": workflow,
        "artifact_status": _artifact_status(artifact),
        "ready": ready,
        "blocking": blocking,
        "unresolved_count": unresolved_count,
        "reason": "" if ready else reason,
    }


def _provider_items(artifact: dict[str, Any]) -> list[dict[str, Any]]:
    rows = artifact.get("unresolved_mappings") if isinstance(artifact.get("unresolved_mappings"), list) else []
    return [
        {
            "area": "provider_field_mapping",
            "operation": str(item.get("operation") or ""),
            "field": str(item.get("internal_field") or ""),
        }
        for item in rows
        if isinstance(item, dict)
    ]


def _template_items(artifact: dict[str, Any]) -> list[dict[str, Any]]:
    rows = artifact.get("unresolved_slots") if isinstance(artifact.get("unresolved_slots"), list) else []
    return [
        {
            "area": "template_slots",
            "operation": str(item.get("operation") or ""),
            "slot": str(item.get("slot_key") or ""),
        }
        for item in rows
        if isinstance(item, dict)
    ]


def _naming_items(artifact: dict[str, Any]) -> list[dict[str, Any]]:
    rows = artifact.get("unresolved_naming_items") if isinstance(artifact.get("unresolved_naming_items"), list) else []
    return [
        {
            "area": "project_naming",
            "item": str(item.get("item") or ""),
        }
        for item in rows
        if isinstance(item, dict)
    ]


def _remaining_review_groups(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    provider_items = [item for item in items if str(item.get("area") or "") == "provider_field_mapping"]
    human_items = [
        item
        for item in items
        if str(item.get("area") or "") in {"template_slots", "project_naming"}
    ]
    groups: list[dict[str, Any]] = []
    if provider_items:
        groups.append(
            {
                "group": "needs_provider_evidence",
                "label": "需要补平台字段依据",
                "item_count": len(provider_items),
                "items": provider_items,
            }
        )
    if human_items:
        groups.append(
            {
                "group": "needs_human_decision",
                "label": "需要人工确认规则",
                "item_count": len(human_items),
                "items": human_items,
            }
        )
    return groups


def _phase2_contract() -> dict[str, Any]:
    return {
        "review_only": True,
        "live_payload_generation_enabled": False,
        "create_execute_hard_block_required": True,
        "real_create_allowed": False,
    }


def _recommended_next_steps(items: list[dict[str, Any]]) -> list[str]:
    areas = {str(item.get("area") or "") for item in items}
    steps: list[str] = []
    if "provider_field_mapping" in areas:
        steps.append("人工确认字段对应关系")
    if "template_slots" in areas:
        steps.append("人工确认模板默认项")
    if "project_naming" in areas:
        steps.append("人工确认项目命名是否加入归属和批次码")
    steps.append("确认完成后再设计真实请求内容生成")
    return steps


def _summary(rows: list[dict[str, Any]], items: list[dict[str, Any]]) -> dict[str, Any]:
    blocking_count = sum(1 for row in rows if bool(row.get("blocking", False)))
    ready_count = sum(1 for row in rows if bool(row.get("ready", False)))
    return {
        "check_count": len(rows),
        "passed_check_count": ready_count,
        "needs_review_check_count": len(rows) - ready_count - blocking_count,
        "blocking_check_count": blocking_count,
        "unresolved_item_count": len(items),
        "ready_for_live_payload_development": False,
        "ready_for_live_execute": False,
    }


def build_create_phase2_preparation_summary(
    *,
    create_phase2_provider_mapping_prep_artifact: dict[str, Any],
    create_phase2_template_slot_prep_artifact: dict[str, Any],
    create_phase2_project_naming_prep_artifact: dict[str, Any],
) -> dict[str, Any]:
    provider_items = _provider_items(create_phase2_provider_mapping_prep_artifact)
    template_items = _template_items(create_phase2_template_slot_prep_artifact)
    naming_items = _naming_items(create_phase2_project_naming_prep_artifact)
    items = provider_items + template_items + naming_items
    rows = [
        _row(
            check="provider_field_mapping",
            workflow="create_phase2_provider_mapping_prep",
            artifact=create_phase2_provider_mapping_prep_artifact,
            unresolved_count=len(provider_items),
            reason="provider field mapping still needs review",
        ),
        _row(
            check="template_slots",
            workflow="create_phase2_template_slot_prep",
            artifact=create_phase2_template_slot_prep_artifact,
            unresolved_count=len(template_items),
            reason="template slots still need review",
        ),
        _row(
            check="project_naming",
            workflow="create_phase2_project_naming_prep",
            artifact=create_phase2_project_naming_prep_artifact,
            unresolved_count=len(naming_items),
            reason="project naming still needs review",
        ),
    ]
    violations: list[str] = []
    violations.extend(_safe_artifact(create_phase2_provider_mapping_prep_artifact, "create_phase2_provider_mapping_prep"))
    violations.extend(_safe_artifact(create_phase2_template_slot_prep_artifact, "create_phase2_template_slot_prep"))
    violations.extend(_safe_artifact(create_phase2_project_naming_prep_artifact, "create_phase2_project_naming_prep"))
    blocking_rows = [row for row in rows if bool(row.get("blocking", False))]
    status = "blocked" if blocking_rows or violations else "needs_review"
    return {
        "ok": not violations,
        "workflow": "create_phase2_preparation_summary",
        "phase": "phase2_preparation",
        "execution_enabled": False,
        "external_api_calls": 0,
        "status": status,
        "ready_for_live_payload_development": False,
        "ready_for_live_execute": False,
        "summary": _summary(rows, items),
        "phase2_preparation_contract": _phase2_contract(),
        "preparation_checks": rows,
        "remaining_review_items": items,
        "remaining_review_groups": _remaining_review_groups(items),
        "recommended_next_steps": _recommended_next_steps(items),
        "violations": violations,
        "actions": [],
    }


def run_create_phase2_preparation_summary_request(
    request: dict[str, Any],
    *,
    runs_dir: str | Path,
) -> dict[str, Any]:
    cfg = _summary_config(request)
    provider = cfg.get("create_phase2_provider_mapping_prep_artifact")
    template = cfg.get("create_phase2_template_slot_prep_artifact")
    naming = cfg.get("create_phase2_project_naming_prep_artifact")
    if not isinstance(provider, dict):
        raise ValueError("phase2 preparation summary requires provider mapping prep artifact")
    if not isinstance(template, dict):
        raise ValueError("phase2 preparation summary requires template slot prep artifact")
    if not isinstance(naming, dict):
        raise ValueError("phase2 preparation summary requires project naming prep artifact")
    payload = build_create_phase2_preparation_summary(
        create_phase2_provider_mapping_prep_artifact=provider,
        create_phase2_template_slot_prep_artifact=template,
        create_phase2_project_naming_prep_artifact=naming,
    )
    artifact_path = write_run_artifact(runs_dir, "create_phase2_preparation_summary", payload)
    return {**payload, "artifact_path": str(artifact_path)}
