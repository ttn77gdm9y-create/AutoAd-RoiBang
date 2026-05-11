from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from roibang_v2.runs import write_run_artifact

_INVALID_PROJECT_NAME_CHARS = re.compile(r'[\\/:*?"<>|\r\n\t]+')


def _preview_config(value: dict[str, Any]) -> dict[str, Any]:
    cfg = value.get("yzt_create_preview")
    return dict(cfg) if isinstance(cfg, dict) else dict(value)


def _create_strategy_plan_policy(policy: dict[str, Any]) -> dict[str, Any]:
    value = policy.get("create_strategy_plan")
    return dict(value) if isinstance(value, dict) else {}


def _template_prep_policy(policy: dict[str, Any]) -> dict[str, Any]:
    value = policy.get("create_phase2_template_slot_prep")
    return dict(value) if isinstance(value, dict) else {}


def _product_template_catalog(policy: dict[str, Any]) -> dict[str, Any]:
    value = _template_prep_policy(policy).get("product_template_catalog")
    return dict(value) if isinstance(value, dict) else {}


def _templates(policy: dict[str, Any]) -> list[dict[str, Any]]:
    rows = _product_template_catalog(policy).get("templates")
    return [dict(row) for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _selected_template(config: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    template_name = str(config.get("template_name") or "").strip()
    for template in _templates(policy):
        if str(template.get("project_template_name") or "") == template_name:
            return template
        if str(template.get("template_key") or "") == template_name:
            return template
    return {}


def _accounts(config: dict[str, Any]) -> list[dict[str, Any]]:
    rows = config.get("accounts")
    return [dict(row) for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _defaults(config: dict[str, Any]) -> dict[str, Any]:
    value = config.get("defaults")
    return dict(value) if isinstance(value, dict) else {}


def _int_value(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _target_date_mmdd(config: dict[str, Any]) -> str:
    compact = re.sub(r"\D+", "", str(config.get("target_date") or ""))
    return compact[4:8] if len(compact) >= 8 else compact


def _project_naming_policy(policy: dict[str, Any]) -> dict[str, Any]:
    value = _create_strategy_plan_policy(policy).get("project_naming")
    return dict(value) if isinstance(value, dict) else {}


def _batch_code_source(config: dict[str, Any], *, product: str, template_name: str) -> dict[str, Any]:
    return {
        "request_id": str(config.get("request_id") or "yzt_create_preview"),
        "target_date": str(config.get("target_date") or ""),
        "product": product,
        "project_template_name": template_name,
        "advertiser_ids": [
            str(account.get("advertiser_id") or "")
            for account in _accounts(config)
            if str(account.get("advertiser_id") or "")
        ],
        "generated_at": str(config.get("batch_generated_at") or ""),
    }


def _request_id(config: dict[str, Any]) -> str:
    value = str(config.get("request_id") or "").strip()
    if value:
        return value
    compact = re.sub(r"\D+", "", str(config.get("target_date") or ""))
    return f"create_req_{compact}_yzt_preview" if compact else "create_req_yzt_preview"


def _batch_code(source_fields: dict[str, Any]) -> str:
    canonical = json.dumps(source_fields, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "B" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:8].upper()


def _normalize_project_name(name: str, *, replacement: str) -> str:
    normalized = _INVALID_PROJECT_NAME_CHARS.sub(replacement, name)
    normalized = re.sub(r"\s+", replacement, normalized)
    if replacement:
        normalized = re.sub(f"{re.escape(replacement)}+", replacement, normalized)
        normalized = normalized.strip(replacement)
    return normalized.strip()


def _project_name(
    *,
    config: dict[str, Any],
    policy: dict[str, Any],
    product: str,
    template_name: str,
    advertiser_id: str,
    project_index: int,
    batch_code: str,
) -> str:
    naming = _project_naming_policy(policy)
    template = str(naming.get("template") or "{target_date_mmdd}_{owner}_{product}_{project_template_name}_{batch_code}_{index}")
    index_width = max(_int_value(naming.get("index_width"), 2), 1)
    replacement = str(naming.get("invalid_char_replacement") or "_")
    values = {
        "target_date_mmdd": _target_date_mmdd(config),
        "owner": str(config.get("owner") or ""),
        "product": product,
        "project_template_name": template_name,
        "batch_code": batch_code,
        "index": f"{project_index:0{index_width}d}",
        "advertiser_id": advertiser_id,
    }
    try:
        raw_name = template.format(**values)
    except KeyError:
        raw_name = "{target_date_mmdd}_{owner}_{product}_{project_template_name}_{batch_code}_{index}".format(**values)
    return _normalize_project_name(raw_name, replacement=replacement)


def _requires_roi(template: dict[str, Any]) -> bool:
    roi = template.get("roi_goal")
    return bool(roi.get("required")) if isinstance(roi, dict) else False


def _label(template: dict[str, Any], key: str) -> str:
    value = template.get(key)
    return str(value.get("label") or "") if isinstance(value, dict) else ""


def _project_type(template_name: str) -> str:
    return "WX_PAY_7R" if "7R" in template_name.upper() else "WX_PAY"


def _pool_key(config: dict[str, Any], template_name: str) -> str:
    value = str(config.get("pool_key") or "").strip()
    if value:
        return value
    return "yzt_wx_7r_all_history" if "7R" in template_name.upper() else "yzt_wx_pay_all_history"


def _material_requirements(config: dict[str, Any]) -> dict[str, Any]:
    value = config.get("material_requirements")
    if isinstance(value, dict):
        return {
            "material_type": str(value.get("material_type") or "video"),
            "materials_per_unit": max(_int_value(value.get("materials_per_unit"), 2), 0),
            "dedupe_scope": str(value.get("dedupe_scope") or "request"),
        }
    return {"material_type": "video", "materials_per_unit": 2, "dedupe_scope": "request"}


def _field_defaults(config: dict[str, Any]) -> dict[str, Any]:
    value = config.get("field_defaults")
    if isinstance(value, dict):
        return dict(value)
    return {
        "landing_type": "MICRO_GAME",
        "pricing": "PRICING_OCPM",
        "inventory_type": "INVENTORY_FEED",
    }


def _project_name_template(policy: dict[str, Any]) -> str:
    naming = _project_naming_policy(policy)
    return str(naming.get("template") or "{target_date_mmdd}_{owner}_{product}_{project_template_name}_{batch_code}_{index}")


def _standard_target_accounts(config: dict[str, Any]) -> list[dict[str, Any]]:
    defaults = _defaults(config)
    rows: list[dict[str, Any]] = []
    for account in _accounts(config):
        rows.append(
            {
                "advertiser_id": str(account.get("advertiser_id") or ""),
                "project_count": max(_int_value(account.get("project_count"), _int_value(defaults.get("project_count"), 1)), 0),
                "units_per_project": max(
                    _int_value(account.get("units_per_project"), _int_value(defaults.get("units_per_project"), 1)),
                    0,
                ),
                "daily_budget": _int_value(account.get("daily_budget"), _int_value(defaults.get("daily_budget", config.get("daily_budget")), 0)),
            }
        )
    return rows


def _standard_create_request(
    *,
    config: dict[str, Any],
    policy: dict[str, Any],
    product: str,
    platform: str,
    template_name: str,
    selected_template: dict[str, Any],
    batch_code: str,
) -> dict[str, Any]:
    return {
        "request_id": _request_id(config),
        "target_date": str(config.get("target_date") or ""),
        "product": product,
        "platform": platform,
        "project_type": _project_type(template_name),
        "source_advertiser_id": str(config.get("source_advertiser_id") or "source-advertiser-id"),
        "organization_id": str(config.get("organization_id") or ""),
        "pool_key": _pool_key(config, template_name),
        "owner": str(config.get("owner") or ""),
        "project_template_name": template_name,
        "batch_generated_at": str(config.get("batch_generated_at") or ""),
        "batch_code": batch_code,
        "target_accounts": _standard_target_accounts(config),
        "material_requirements": _material_requirements(config),
        "field_defaults": _field_defaults(config),
        "project_name_template": _project_name_template(policy),
        "constraints": {
            "phase": "phase1",
            "execution_enabled": False,
            "allow_real_create": False,
        },
        "template_parameters": {
            "template_name": template_name,
            "roi_coefficient": _float_or_none(config.get("roi_coefficient")) if _requires_roi(selected_template) else None,
            "gender": _label(selected_template, "gender"),
            "age": _label(selected_template, "age"),
            "effective_touch_url": "<fixed-in-yzt-script>",
        },
    }


def _summary(
    *,
    product: str,
    platform: str,
    template_name: str,
    accounts: list[dict[str, Any]],
    preview_projects: list[dict[str, Any]],
    requires_roi: bool,
    preview_checks: list[dict[str, Any]],
) -> dict[str, Any]:
    failed_checks = [check for check in preview_checks if str(check.get("status") or "") != "passed"]
    return {
        "product": product,
        "platform": platform,
        "launch_mode": "create_only",
        "template_name": template_name,
        "target_account_count": len(accounts),
        "preview_project_count": len(preview_projects),
        "requires_roi_coefficient": requires_roi,
        "preview_check_count": len(preview_checks),
        "failed_preview_check_count": len(failed_checks),
        "ready_for_live_execute": False,
    }


def _violations(config: dict[str, Any], selected_template: dict[str, Any], *, requires_roi: bool) -> list[str]:
    violations: list[str] = []
    if not selected_template:
        violations.append("template_name is not in product_template_catalog")
    if not _accounts(config):
        violations.append("accounts must contain at least one advertiser_id")
    if requires_roi and _float_or_none(config.get("roi_coefficient")) is None:
        violations.append("roi_coefficient is required for 7R templates")
    if _int_value(_defaults(config).get("daily_budget", config.get("daily_budget")), 0) <= 0:
        violations.append("daily_budget must be greater than 0")
    return violations


def _config_contract() -> dict[str, Any]:
    return {
        "editable_fields": [
            "template_name",
            "owner",
            "target_date",
            "batch_generated_at",
            "defaults.daily_budget",
            "defaults.project_count",
            "roi_coefficient",
            "accounts[].advertiser_id",
            "accounts[].project_count",
            "accounts[].daily_budget",
        ],
        "fixed_fields": [
            "product",
            "platform",
            "effective_touch_url",
            "marketing_scene",
            "optimize_goal",
            "age",
        ],
        "real_create_allowed": False,
    }


def _manual_config_contract() -> dict[str, Any]:
    return {
        "human_editable_fields": [
            {"field": "template_name", "meaning": "选择模板，比如微小每付7R男、微小每付通投"},
            {"field": "owner", "meaning": "归属，用在项目名里"},
            {"field": "target_date", "meaning": "投放日期，用在项目名里"},
            {"field": "batch_generated_at", "meaning": "批次生成时间，用来生成批次码"},
            {"field": "defaults.daily_budget", "meaning": "默认日预算"},
            {"field": "defaults.project_count", "meaning": "每个账户默认建几个项目"},
            {"field": "defaults.units_per_project", "meaning": "每个项目默认建几个单元"},
            {"field": "roi_coefficient", "meaning": "ROI系数，只有7R模板需要填"},
            {"field": "accounts[].advertiser_id", "meaning": "目标账户"},
            {"field": "accounts[].project_count", "meaning": "单个账户覆盖项目数量，可不填"},
            {"field": "accounts[].daily_budget", "meaning": "单个账户覆盖预算，可不填"},
        ],
        "script_fixed_fields": [
            "product",
            "platform",
            "source_advertiser_id",
            "pool_key",
            "material_requirements",
            "field_defaults",
            "effective_touch_url",
            "marketing_scene",
            "optimize_goal",
            "age",
        ],
        "real_create_allowed": False,
    }


def _preview_checks(
    *,
    config: dict[str, Any],
    selected_template: dict[str, Any],
    template_name: str,
    preview_projects: list[dict[str, Any]],
    requires_roi: bool,
) -> list[dict[str, Any]]:
    accounts = _accounts(config)
    project_names = [str(project.get("project_name") or "") for project in preview_projects]
    budgets = [_int_value(project.get("daily_budget"), 0) for project in preview_projects]
    checks: list[dict[str, Any]] = [
        {
            "check": "runtime_safety",
            "status": "passed",
            "message": "execution is disabled and no external API calls are planned",
        },
        {
            "check": "template_known",
            "status": "passed" if selected_template else "failed",
            "template_name": template_name,
        },
        {
            "check": "target_accounts",
            "status": "passed" if accounts else "failed",
            "account_count": len(accounts),
        },
        {
            "check": "daily_budget",
            "status": "passed" if budgets and all(budget > 0 for budget in budgets) else "failed",
            "message": "all preview projects have positive daily budget",
        },
        {
            "check": "roi_coefficient",
            "status": "passed" if (not requires_roi or _float_or_none(config.get("roi_coefficient")) is not None) else "failed",
            "message": "ROI系数已填写" if requires_roi else "当前模板不需要ROI系数",
        },
        {
            "check": "project_names_unique",
            "status": "passed" if len(project_names) == len(set(project_names)) else "failed",
            "project_name_count": len(project_names),
        },
        {
            "check": "effective_touch_url_fixed",
            "status": "passed",
            "message": "有效触点由勇者突进脚本固定",
        },
    ]
    return checks


def _preview_projects(
    *,
    config: dict[str, Any],
    policy: dict[str, Any],
    product: str,
    selected_template: dict[str, Any],
    batch_code: str,
) -> list[dict[str, Any]]:
    template_name = str(selected_template.get("project_template_name") or "")
    roi_coefficient = _float_or_none(config.get("roi_coefficient")) if _requires_roi(selected_template) else None
    defaults = _defaults(config)
    projects: list[dict[str, Any]] = []
    global_project_index = 0
    for account in _accounts(config):
        advertiser_id = str(account.get("advertiser_id") or "")
        project_count = max(_int_value(account.get("project_count"), _int_value(defaults.get("project_count"), 1)), 0)
        daily_budget = _int_value(account.get("daily_budget"), _int_value(defaults.get("daily_budget", config.get("daily_budget")), 0))
        for project_index in range(1, project_count + 1):
            global_project_index += 1
            projects.append(
                {
                    "advertiser_id": advertiser_id,
                    "project_index": global_project_index,
                    "project_name": _project_name(
                        config=config,
                        policy=policy,
                        product=product,
                        template_name=template_name,
                        advertiser_id=advertiser_id,
                        project_index=global_project_index,
                        batch_code=batch_code,
                    ),
                    "project_template_name": template_name,
                    "owner": str(config.get("owner") or ""),
                    "daily_budget": daily_budget,
                    "roi_coefficient": roi_coefficient,
                    "gender": _label(selected_template, "gender"),
                    "age": _label(selected_template, "age"),
                    "effective_touch_url": "<fixed-in-yzt-script>",
                }
            )
    return projects


def build_create_phase2_yzt_create_preview(
    *,
    preview_config: dict[str, Any],
    policy: dict[str, Any],
) -> dict[str, Any]:
    config = _preview_config(preview_config)
    catalog = _product_template_catalog(policy)
    product = str(catalog.get("product") or "勇者突进")
    platform = str(catalog.get("platform") or "WECHAT_GAME")
    template = _selected_template(config, policy)
    template_name = str(template.get("project_template_name") or config.get("template_name") or "")
    requires_roi = _requires_roi(template)
    batch_code = _batch_code(_batch_code_source(config, product=product, template_name=template_name))
    preview_projects = _preview_projects(
        config=config,
        policy=policy,
        product=product,
        selected_template=template,
        batch_code=batch_code,
    ) if template else []
    preview_checks = _preview_checks(
        config=config,
        selected_template=template,
        template_name=template_name,
        preview_projects=preview_projects,
        requires_roi=requires_roi,
    )
    standard_create_request = _standard_create_request(
        config=config,
        policy=policy,
        product=product,
        platform=platform,
        template_name=template_name,
        selected_template=template,
        batch_code=batch_code,
    )
    violations = _violations(config, template, requires_roi=requires_roi)
    violations.extend(
        f"preview check failed: {check.get('check')}"
        for check in preview_checks
        if str(check.get("status") or "") != "passed" and f"preview check failed: {check.get('check')}" not in violations
    )
    return {
        "ok": not violations,
        "workflow": "create_phase2_yzt_create_preview",
        "phase": "phase2_preparation",
        "execution_enabled": False,
        "external_api_calls": 0,
        "status": "ready_for_review" if not violations else "blocked",
        "summary": _summary(
            product=product,
            platform=platform,
            template_name=template_name,
            accounts=_accounts(config),
            preview_projects=preview_projects,
            requires_roi=requires_roi,
            preview_checks=preview_checks,
        ),
        "config_contract": _config_contract(),
        "manual_config_contract": _manual_config_contract(),
        "fixed_script_fields": {
            "product": product,
            "platform": platform,
            "script_scope": str(catalog.get("script_scope") or "勇者突进微信小游戏专用"),
            "effective_touch_url_source": "fixed_in_yzt_script",
            "marketing_scene": "短视频+图文",
            "optimize_goal": "付费",
            "age": "不限",
        },
        "selected_template": template,
        "batch_code": {
            "value": batch_code,
            "source_fields": _batch_code_source(config, product=product, template_name=template_name),
        },
        "preview_projects": preview_projects,
        "standard_create_request": standard_create_request,
        "chain_handoff": {
            "standard_create_request_ready": not violations,
            "next_safe_chain_steps": [
                "create_request",
                "create_strategy_plan",
                "create_preflight",
                "create_dry_run",
            ],
            "execute_allowed": False,
        },
        "manual_run": {
            "script": "scripts/run_create_phase2_yzt_create_preview.py",
            "config": "configs/create/yzt-wx-mini-game.preview.example.json",
            "command": "PYTHONPATH=src python3 scripts/run_create_phase2_yzt_create_preview.py --config configs/runtime.example.json --preview-config configs/create/yzt-wx-mini-game.preview.example.json --policy policies/strategy.example.json",
        },
        "preview_checks": preview_checks,
        "violations": violations,
        "actions": [],
    }


def run_create_phase2_yzt_create_preview_request(
    request: dict[str, Any],
    *,
    runs_dir: str | Path,
) -> dict[str, Any]:
    cfg = request.get("create_phase2_yzt_create_preview")
    cfg = dict(cfg) if isinstance(cfg, dict) else {}
    payload = build_create_phase2_yzt_create_preview(
        preview_config=cfg.get("preview_config") if isinstance(cfg.get("preview_config"), dict) else {},
        policy=cfg.get("policy") if isinstance(cfg.get("policy"), dict) else {},
    )
    artifact_path = write_run_artifact(runs_dir, "create_phase2_yzt_create_preview", payload)
    return {**payload, "artifact_path": str(artifact_path)}
