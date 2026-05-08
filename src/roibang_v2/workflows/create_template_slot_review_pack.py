from __future__ import annotations

from pathlib import Path
from typing import Any

from roibang_v2.runs import write_run_artifact
from roibang_v2.workflows.create_lineage import create_request_payload


def _review_pack_config(request: dict[str, Any]) -> dict[str, Any]:
    value = request.get("create_template_slot_review_pack")
    return dict(value) if isinstance(value, dict) else dict(request)


def _create_request(value: dict[str, Any]) -> dict[str, Any]:
    if isinstance(value.get("create_request"), dict):
        return create_request_payload(value["create_request"])
    return create_request_payload(value)


def _create_strategy_plan_policy(policy: dict[str, Any]) -> dict[str, Any]:
    value = policy.get("create_strategy_plan")
    return dict(value) if isinstance(value, dict) else {}


def _create_preflight_policy(policy: dict[str, Any]) -> dict[str, Any]:
    value = policy.get("create_preflight")
    return dict(value) if isinstance(value, dict) else {}


def _project_naming(policy: dict[str, Any]) -> dict[str, Any]:
    strategy_policy = _create_strategy_plan_policy(policy)
    value = strategy_policy.get("project_naming")
    return dict(value) if isinstance(value, dict) else {}


def _required_defaults(policy: dict[str, Any]) -> list[str]:
    value = _create_preflight_policy(policy).get("required_field_defaults")
    return [str(item) for item in value if str(item).strip()] if isinstance(value, list) else []


def _slot(
    *,
    slot_key: str,
    source: str,
    value_preview: Any,
    required: bool = True,
) -> dict[str, Any]:
    preview = _preview(value_preview)
    configured = bool(preview)
    return {
        "slot_key": slot_key,
        "source": source,
        "value_preview": preview,
        "required": required,
        "configured": configured,
        "review_status": "needs_review" if configured else "missing_value",
    }


def _preview(value: Any) -> str:
    if isinstance(value, dict):
        return "<configured-object>" if value else ""
    if isinstance(value, list):
        return "<configured-list>" if value else ""
    if isinstance(value, (int, float)):
        return str(value) if value > 0 else ""
    return str(value or "").strip()


def _field_defaults(request: dict[str, Any]) -> dict[str, Any]:
    value = request.get("field_defaults")
    return dict(value) if isinstance(value, dict) else {}


def _material_requirements(request: dict[str, Any]) -> dict[str, Any]:
    value = request.get("material_requirements")
    return dict(value) if isinstance(value, dict) else {}


def _project_name_template(request: dict[str, Any], policy: dict[str, Any]) -> tuple[str, str]:
    naming = _project_naming(policy)
    if str(naming.get("template") or "").strip():
        return str(naming.get("template") or "").strip(), "policy.create_strategy_plan.project_naming.template"
    return str(request.get("project_name_template") or "").strip(), "create_request.project_name_template"


def _review_sections(request: dict[str, Any], policy: dict[str, Any]) -> list[dict[str, Any]]:
    defaults = _field_defaults(request)
    requirements = _material_requirements(request)
    template, template_source = _project_name_template(request, policy)
    return [
        {
            "operation": "create_project",
            "description": "project-level fixed template slots",
            "slots": [
                _slot(slot_key="project_name_template", source=template_source, value_preview=template),
                _slot(slot_key="project_type", source="create_request.project_type", value_preview=request.get("project_type")),
                _slot(slot_key="daily_budget", source="create_request.target_accounts[].daily_budget", value_preview="<per-target-account>"),
                _slot(
                    slot_key="field_defaults.landing_type",
                    source="create_request.field_defaults.landing_type",
                    value_preview=defaults.get("landing_type"),
                ),
                _slot(
                    slot_key="field_defaults.pricing",
                    source="create_request.field_defaults.pricing",
                    value_preview=defaults.get("pricing"),
                ),
                _slot(
                    slot_key="field_defaults.inventory_type",
                    source="create_request.field_defaults.inventory_type",
                    value_preview=defaults.get("inventory_type"),
                ),
            ],
        },
        {
            "operation": "create_unit",
            "description": "unit-level fixed template slots",
            "slots": [
                _slot(slot_key="units_per_project", source="create_request.target_accounts[].units_per_project", value_preview="<per-target-account>"),
                _slot(
                    slot_key="field_defaults.landing_type",
                    source="create_request.field_defaults.landing_type",
                    value_preview=defaults.get("landing_type"),
                ),
                _slot(
                    slot_key="field_defaults.pricing",
                    source="create_request.field_defaults.pricing",
                    value_preview=defaults.get("pricing"),
                ),
            ],
        },
        {
            "operation": "bind_material",
            "description": "material-binding fixed template slots",
            "slots": [
                _slot(
                    slot_key="material_type",
                    source="create_request.material_requirements.material_type",
                    value_preview=requirements.get("material_type"),
                ),
                _slot(
                    slot_key="materials_per_unit",
                    source="create_request.material_requirements.materials_per_unit",
                    value_preview=requirements.get("materials_per_unit"),
                ),
                _slot(
                    slot_key="material_id",
                    source="product_source_material_candidates.material_id",
                    value_preview="<selected-by-create-strategy-plan>",
                ),
            ],
        },
    ]


def _slots(sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        slot
        for section in sections
        for slot in section.get("slots", [])
        if isinstance(slot, dict)
    ]


def _template_contract(sections: list[dict[str, Any]], policy: dict[str, Any]) -> dict[str, Any]:
    slots = _slots(sections)
    configured = [slot for slot in slots if bool(slot.get("configured", False))]
    missing = [slot for slot in slots if not bool(slot.get("configured", False)) and bool(slot.get("required", False))]
    needs_review = [slot for slot in slots if str(slot.get("review_status") or "") == "needs_review"]
    return {
        "status": "needs_review" if not missing else "incomplete",
        "slot_count": len(slots),
        "configured_slot_count": len(configured),
        "missing_value_slot_count": len(missing),
        "needs_review_slot_count": len(needs_review),
        "required_defaults": _required_defaults(policy),
    }


def _summary(request: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    return {
        "request_id": str(request.get("request_id") or ""),
        "target_date": str(request.get("target_date") or ""),
        "product": str(request.get("product") or ""),
        "platform": str(request.get("platform") or ""),
        "project_type": str(request.get("project_type") or ""),
        "slot_count": int(contract.get("slot_count") or 0),
        "configured_slot_count": int(contract.get("configured_slot_count") or 0),
        "missing_value_slot_count": int(contract.get("missing_value_slot_count") or 0),
        "needs_review_slot_count": int(contract.get("needs_review_slot_count") or 0),
    }


def build_create_template_slot_review_pack(
    *,
    create_request: dict[str, Any],
    policy: dict[str, Any],
) -> dict[str, Any]:
    request = _create_request(create_request)
    sections = _review_sections(request, policy)
    contract = _template_contract(sections, policy)
    missing_count = int(contract.get("missing_value_slot_count") or 0)
    return {
        "ok": missing_count == 0,
        "workflow": "create_template_slot_review_pack",
        "phase": "phase1",
        "execution_enabled": False,
        "external_api_calls": 0,
        "status": str(contract.get("status") or "needs_review"),
        "required_user_input_now": False,
        "summary": _summary(request, contract),
        "template_contract": contract,
        "review_sections": sections,
        "violations": [] if missing_count == 0 else ["required template slots are missing values"],
        "actions": [],
    }


def run_create_template_slot_review_pack_request(
    request: dict[str, Any],
    *,
    runs_dir: str | Path,
) -> dict[str, Any]:
    cfg = _review_pack_config(request)
    create_request = cfg.get("create_request") if isinstance(cfg.get("create_request"), dict) else {}
    policy = cfg.get("policy") if isinstance(cfg.get("policy"), dict) else {}
    payload = build_create_template_slot_review_pack(create_request=create_request, policy=policy)
    artifact_path = write_run_artifact(runs_dir, "create_template_slot_review_pack", payload)
    return {**payload, "artifact_path": str(artifact_path)}
