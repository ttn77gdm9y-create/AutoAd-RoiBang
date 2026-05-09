from __future__ import annotations

from pathlib import Path
from typing import Any

from roibang_v2.runs import write_run_artifact
from roibang_v2.workflows.create_lineage import create_request_payload


def _prep_config(request: dict[str, Any]) -> dict[str, Any]:
    value = request.get("create_phase2_template_slot_prep")
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


def _int_policy(policy: dict[str, Any], key: str) -> int:
    try:
        return int(_create_preflight_policy(policy).get(key) or 0)
    except (TypeError, ValueError):
        return 0


def _project_name_pattern(policy: dict[str, Any]) -> str:
    return str(_create_preflight_policy(policy).get("project_name_pattern") or "")


def _project_name_template(request: dict[str, Any], policy: dict[str, Any]) -> tuple[str, str]:
    naming = _project_naming(policy)
    if str(naming.get("template") or "").strip():
        return str(naming.get("template") or "").strip(), "policy.create_strategy_plan.project_naming.template"
    return str(request.get("project_name_template") or "").strip(), "create_request.project_name_template"


def _preview(value: Any) -> str:
    if isinstance(value, dict):
        return "<configured-object>" if value else ""
    if isinstance(value, list):
        return "<configured-list>" if value else ""
    if isinstance(value, (int, float)):
        return str(value) if value > 0 else ""
    return str(value or "").strip()


def _slot(
    *,
    slot_key: str,
    value_source: str,
    value_preview: Any,
    value_scope: str,
    required: bool = True,
) -> dict[str, Any]:
    preview = _preview(value_preview)
    configured = bool(preview)
    return {
        "slot_key": slot_key,
        "value_preview": preview,
        "value_source": value_source,
        "value_scope": value_scope,
        "required": required,
        "configured": configured,
        "review_status": "needs_review" if configured else "missing_value",
        "open_questions": [_open_question(value_scope)] if configured else ["Fill this required value before live payload development."],
    }


def _open_question(value_scope: str) -> str:
    if value_scope == "per_target_account":
        return "Confirm each target account can safely use its own value."
    if value_scope == "selected_by_strategy":
        return "Confirm this value is selected by fixed strategy rules, not by live AI judgment."
    return "Confirm this fixed value can be used for real create payloads."


def _confirmation_question(value_scope: str) -> str:
    if value_scope == "per_target_account":
        return "确认每个目标账户可以安全使用各自的值。"
    if value_scope == "selected_by_strategy":
        return "确认这个值由固定脚本规则选择，不由运行中的 AI 临场判断。"
    return "确认这个固定值未来可以用于真实创建模板。"


def _suggested_decision(slot: dict[str, Any]) -> str:
    if str(slot.get("review_status") or "") == "missing_value":
        return "fill_before_live_payload_development"
    value_scope = str(slot.get("value_scope") or "")
    if value_scope == "per_target_account":
        return "keep_per_account_value"
    if value_scope == "selected_by_strategy":
        return "keep_strategy_selection"
    return "keep_current_value"


def _section_label(operation: str) -> str:
    return {
        "create_project": "项目",
        "create_unit": "单元",
        "bind_material": "素材绑定",
    }.get(operation, operation)


def _field_label(slot_key: str) -> str:
    return {
        "project_name_template": "项目命名规则",
        "project_type": "项目类型",
        "daily_budget": "日预算",
        "field_defaults.landing_type": "落地类型",
        "field_defaults.pricing": "计费方式",
        "field_defaults.inventory_type": "流量库存",
        "units_per_project": "每项目单元数",
        "material_type": "素材类型",
        "materials_per_unit": "每单元素材数",
        "material_id": "素材选择",
    }.get(slot_key, slot_key)


def _source_label(value_scope: str) -> str:
    if value_scope == "per_target_account":
        return "每个账户单独填写"
    if value_scope == "selected_by_strategy":
        return "固定脚本规则选择"
    return "策略配置"


def _action_label(value_scope: str) -> str:
    if value_scope == "per_target_account":
        return "建议保留按账户填写"
    if value_scope == "selected_by_strategy":
        return "建议保留固定脚本选择"
    return "建议保留当前值"


def _checklist_question(operation: str, slot_key: str, value_scope: str) -> str:
    section = _section_label(operation)
    field = _field_label(slot_key)
    if value_scope == "per_target_account":
        return f"{section}的{field}是否确认按账户填写？"
    if value_scope == "selected_by_strategy":
        return f"{section}的{field}是否确认由固定脚本选择？"
    return f"{section}的{field}是否确认使用当前值？"


def _field_defaults(request: dict[str, Any]) -> dict[str, Any]:
    value = request.get("field_defaults")
    return dict(value) if isinstance(value, dict) else {}


def _material_requirements(request: dict[str, Any]) -> dict[str, Any]:
    value = request.get("material_requirements")
    return dict(value) if isinstance(value, dict) else {}


def _template_prep_policy(policy: dict[str, Any]) -> dict[str, Any]:
    value = policy.get("create_phase2_template_slot_prep")
    return dict(value) if isinstance(value, dict) else {}


def _product_template_catalog(request: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    value = _template_prep_policy(policy).get("product_template_catalog")
    if isinstance(value, dict):
        return dict(value)
    return {
        "product": str(request.get("product") or ""),
        "platform": str(request.get("platform") or ""),
        "templates": [],
    }


def _review_matrix(request: dict[str, Any], policy: dict[str, Any]) -> list[dict[str, Any]]:
    defaults = _field_defaults(request)
    requirements = _material_requirements(request)
    template, template_source = _project_name_template(request, policy)
    return [
        {
            "operation": "create_project",
            "description": "project-level fixed template slots",
            "slots": [
                _slot(
                    slot_key="project_name_template",
                    value_source=template_source,
                    value_preview=template,
                    value_scope="fixed_template",
                ),
                _slot(
                    slot_key="project_type",
                    value_source="create_request.project_type",
                    value_preview=request.get("project_type"),
                    value_scope="fixed_template",
                ),
                _slot(
                    slot_key="daily_budget",
                    value_source="create_request.target_accounts[].daily_budget",
                    value_preview="<per-target-account>",
                    value_scope="per_target_account",
                ),
                _slot(
                    slot_key="field_defaults.landing_type",
                    value_source="create_request.field_defaults.landing_type",
                    value_preview=defaults.get("landing_type"),
                    value_scope="fixed_template",
                ),
                _slot(
                    slot_key="field_defaults.pricing",
                    value_source="create_request.field_defaults.pricing",
                    value_preview=defaults.get("pricing"),
                    value_scope="fixed_template",
                ),
                _slot(
                    slot_key="field_defaults.inventory_type",
                    value_source="create_request.field_defaults.inventory_type",
                    value_preview=defaults.get("inventory_type"),
                    value_scope="fixed_template",
                ),
            ],
        },
        {
            "operation": "create_unit",
            "description": "unit-level fixed template slots",
            "slots": [
                _slot(
                    slot_key="units_per_project",
                    value_source="create_request.target_accounts[].units_per_project",
                    value_preview="<per-target-account>",
                    value_scope="per_target_account",
                ),
                _slot(
                    slot_key="field_defaults.landing_type",
                    value_source="create_request.field_defaults.landing_type",
                    value_preview=defaults.get("landing_type"),
                    value_scope="fixed_template",
                ),
                _slot(
                    slot_key="field_defaults.pricing",
                    value_source="create_request.field_defaults.pricing",
                    value_preview=defaults.get("pricing"),
                    value_scope="fixed_template",
                ),
            ],
        },
        {
            "operation": "bind_material",
            "description": "material-binding fixed template slots",
            "slots": [
                _slot(
                    slot_key="material_type",
                    value_source="create_request.material_requirements.material_type",
                    value_preview=requirements.get("material_type"),
                    value_scope="fixed_template",
                ),
                _slot(
                    slot_key="materials_per_unit",
                    value_source="create_request.material_requirements.materials_per_unit",
                    value_preview=requirements.get("materials_per_unit"),
                    value_scope="fixed_template",
                ),
                _slot(
                    slot_key="material_id",
                    value_source="product_source_material_candidates.material_id",
                    value_preview="<selected-by-create-strategy-plan>",
                    value_scope="selected_by_strategy",
                ),
            ],
        },
    ]


def _slots(matrix: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        slot
        for section in matrix
        for slot in (section.get("slots") if isinstance(section.get("slots"), list) else [])
        if isinstance(slot, dict)
    ]


def _confirmation_item(operation: str, slot: dict[str, Any]) -> dict[str, Any]:
    value_scope = str(slot.get("value_scope") or "")
    return {
        "operation": operation,
        "slot_key": str(slot.get("slot_key") or ""),
        "value_preview": str(slot.get("value_preview") or ""),
        "value_source": str(slot.get("value_source") or ""),
        "review_status": str(slot.get("review_status") or ""),
        "confirmation_question": _confirmation_question(value_scope),
    }


def _template_confirmation_groups(matrix: list[dict[str, Any]]) -> list[dict[str, Any]]:
    group_order = [
        ("fixed_template", "fixed_template_defaults", "固定模板默认项"),
        ("per_target_account", "per_target_account_values", "按账户填写项"),
        ("selected_by_strategy", "strategy_selected_values", "由固定策略选择项"),
    ]
    items_by_scope = {scope: [] for scope, _, _ in group_order}
    for section in matrix:
        operation = str(section.get("operation") or "")
        for slot in section.get("slots") if isinstance(section.get("slots"), list) else []:
            if not isinstance(slot, dict):
                continue
            value_scope = str(slot.get("value_scope") or "")
            if value_scope in items_by_scope:
                items_by_scope[value_scope].append(_confirmation_item(operation, slot))
    groups: list[dict[str, Any]] = []
    for scope, group, label in group_order:
        items = items_by_scope[scope]
        if items:
            groups.append(
                {
                    "group": group,
                    "label": label,
                    "item_count": len(items),
                    "items": items,
                }
            )
    return groups


def _template_confirmation_draft(matrix: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for section in matrix:
        operation = str(section.get("operation") or "")
        for slot in section.get("slots") if isinstance(section.get("slots"), list) else []:
            if not isinstance(slot, dict):
                continue
            value_scope = str(slot.get("value_scope") or "")
            rows.append(
                {
                    "operation": operation,
                    "slot_key": str(slot.get("slot_key") or ""),
                    "current_value": str(slot.get("value_preview") or ""),
                    "value_source": str(slot.get("value_source") or ""),
                    "value_scope": value_scope,
                    "decision_status": "pending_confirmation",
                    "suggested_decision": _suggested_decision(slot),
                    "confirmation_question": _confirmation_question(value_scope),
                }
            )
    return rows


def _template_confirmation_checklist(matrix: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for section in matrix:
        operation = str(section.get("operation") or "")
        for slot in section.get("slots") if isinstance(section.get("slots"), list) else []:
            if not isinstance(slot, dict):
                continue
            value_scope = str(slot.get("value_scope") or "")
            slot_key = str(slot.get("slot_key") or "")
            rows.append(
                {
                    "item_no": len(rows) + 1,
                    "section": _section_label(operation),
                    "field": _field_label(slot_key),
                    "current_value": str(slot.get("value_preview") or ""),
                    "source": _source_label(value_scope),
                    "suggested_action": _action_label(value_scope),
                    "needs_user_confirmation": True,
                    "question": _checklist_question(operation, slot_key, value_scope),
                }
            )
    return rows


def _template_slot_contract(matrix: list[dict[str, Any]], policy: dict[str, Any]) -> dict[str, Any]:
    slots = _slots(matrix)
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
        "daily_budget_bounds": {
            "min": _int_policy(policy, "min_daily_budget"),
            "max": _int_policy(policy, "max_daily_budget"),
        },
        "project_name_pattern": _project_name_pattern(policy),
    }


def _summary(
    request: dict[str, Any],
    contract: dict[str, Any],
    confirmation_groups: list[dict[str, Any]],
    confirmation_draft: list[dict[str, Any]],
    confirmation_checklist: list[dict[str, Any]],
    product_template_catalog: dict[str, Any],
) -> dict[str, Any]:
    product_templates = product_template_catalog.get("templates")
    return {
        "request_id": str(request.get("request_id") or ""),
        "product": str(request.get("product") or ""),
        "platform": str(request.get("platform") or ""),
        "project_type": str(request.get("project_type") or ""),
        "slot_count": int(contract.get("slot_count") or 0),
        "configured_slot_count": int(contract.get("configured_slot_count") or 0),
        "missing_value_slot_count": int(contract.get("missing_value_slot_count") or 0),
        "needs_review_slot_count": int(contract.get("needs_review_slot_count") or 0),
        "confirmation_group_count": len(confirmation_groups),
        "confirmation_draft_item_count": len(confirmation_draft),
        "confirmation_checklist_item_count": len(confirmation_checklist),
        "product_template_count": len(product_templates) if isinstance(product_templates, list) else 0,
        "ready_for_live_payload_development": False,
        "ready_for_live_execute": False,
    }


def _phase2_contract() -> dict[str, Any]:
    return {
        "review_only": True,
        "live_payload_generation_enabled": False,
        "create_execute_hard_block_required": True,
        "next_required_reviews": [
            "template_slots",
            "project_naming_rules",
            "live_payload_generation",
        ],
    }


def _unresolved_slots(matrix: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for section in matrix:
        operation = str(section.get("operation") or "")
        for slot in section.get("slots") if isinstance(section.get("slots"), list) else []:
            if not isinstance(slot, dict):
                continue
            if str(slot.get("review_status") or "") == "verified":
                continue
            rows.append(
                {
                    "operation": operation,
                    "slot_key": str(slot.get("slot_key") or ""),
                    "review_status": str(slot.get("review_status") or ""),
                    "open_questions": list(slot.get("open_questions") or []),
                }
            )
    return rows


def build_create_phase2_template_slot_prep(
    *,
    create_request: dict[str, Any],
    policy: dict[str, Any],
) -> dict[str, Any]:
    request = _create_request(create_request)
    matrix = _review_matrix(request, policy)
    confirmation_groups = _template_confirmation_groups(matrix)
    confirmation_draft = _template_confirmation_draft(matrix)
    confirmation_checklist = _template_confirmation_checklist(matrix)
    product_template_catalog = _product_template_catalog(request, policy)
    contract = _template_slot_contract(matrix, policy)
    missing_count = int(contract.get("missing_value_slot_count") or 0)
    return {
        "ok": missing_count == 0,
        "workflow": "create_phase2_template_slot_prep",
        "phase": "phase2_preparation",
        "execution_enabled": False,
        "external_api_calls": 0,
        "status": str(contract.get("status") or "needs_review"),
        "summary": _summary(
            request,
            contract,
            confirmation_groups,
            confirmation_draft,
            confirmation_checklist,
            product_template_catalog,
        ),
        "phase2_preparation_contract": _phase2_contract(),
        "template_slot_contract": contract,
        "product_template_catalog": product_template_catalog,
        "template_confirmation_groups": confirmation_groups,
        "template_confirmation_draft": confirmation_draft,
        "template_confirmation_checklist": confirmation_checklist,
        "review_matrix": matrix,
        "unresolved_slots": _unresolved_slots(matrix),
        "violations": [] if missing_count == 0 else ["required template slots are missing values"],
        "actions": [],
    }


def run_create_phase2_template_slot_prep_request(
    request: dict[str, Any],
    *,
    runs_dir: str | Path,
) -> dict[str, Any]:
    cfg = _prep_config(request)
    create_request = cfg.get("create_request") if isinstance(cfg.get("create_request"), dict) else {}
    policy = cfg.get("policy") if isinstance(cfg.get("policy"), dict) else {}
    payload = build_create_phase2_template_slot_prep(create_request=create_request, policy=policy)
    artifact_path = write_run_artifact(runs_dir, "create_phase2_template_slot_prep", payload)
    return {**payload, "artifact_path": str(artifact_path)}
