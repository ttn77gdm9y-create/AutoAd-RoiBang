from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from roibang_v2.config import load_json
from roibang_v2.runs import write_run_artifact
from roibang_v2.workflows.create_strategy_plan import build_create_strategy_plan

MODE_ALIASES = {
    "7r通投历史放量": "wx_7r_general_scale",
    "7r通投近期放量": "wx_7r_general_recent_scale",
    "7r通投测新": "wx_7r_general_test_new",
    "7r通投低转化复测": "wx_7r_general_retest",
    "7r通投无转化复测": "wx_7r_general_no_conversion_retest",
    "7r男历史放量": "wx_7r_male_scale",
    "7r男近期放量": "wx_7r_male_recent_scale",
    "7r男测新": "wx_7r_male_test_new",
    "7r男低转化复测": "wx_7r_male_retest",
    "7r男无转化复测": "wx_7r_male_no_conversion_retest",
    "每付通投历史放量": "wx_pay_general_scale",
    "每付通投近期放量": "wx_pay_general_recent_scale",
    "每付通投测新": "wx_pay_general_test_new",
    "每付通投低转化复测": "wx_pay_general_retest",
    "每付通投无转化复测": "wx_pay_general_no_conversion_retest",
    "每付男历史放量": "wx_pay_male_scale",
    "每付男近期放量": "wx_pay_male_recent_scale",
    "每付男测新": "wx_pay_male_test_new",
    "每付男低转化复测": "wx_pay_male_retest",
    "每付男无转化复测": "wx_pay_male_no_conversion_retest",
}

AMBIGUOUS_MODE_ALIASES = {
    "7r放量": "7R 放量需要指定通投或男，并指定历史/近期，例如 7R 通投历史放量 / 7R 通投近期放量",
    "7r通投放量": "7R 通投放量需要指定历史/近期，例如 7R 通投历史放量 / 7R 通投近期放量",
    "7r男放量": "7R 男放量需要指定历史/近期，例如 7R 男历史放量 / 7R 男近期放量",
    "7r测新": "7R 测新需要指定通投或男，例如 7R 通投测新 / 7R 男测新",
    "7r复测": "7R 复测需要指定通投或男，并指定低转化/无转化，例如 7R 通投低转化复测 / 7R 通投无转化复测",
    "7r通投复测": "7R 通投复测需要指定低转化/无转化，例如 7R 通投低转化复测 / 7R 通投无转化复测",
    "7r男复测": "7R 男复测需要指定低转化/无转化，例如 7R 男低转化复测 / 7R 男无转化复测",
    "每付放量": "每付放量需要指定通投或男，并指定历史/近期，例如 每付通投历史放量 / 每付通投近期放量",
    "每付通投放量": "每付通投放量需要指定历史/近期，例如 每付通投历史放量 / 每付通投近期放量",
    "每付男放量": "每付男放量需要指定历史/近期，例如 每付男历史放量 / 每付男近期放量",
    "每付测新": "每付测新需要指定通投或男，例如 每付通投测新 / 每付男测新",
    "每付复测": "每付复测需要指定通投或男，并指定低转化/无转化，例如 每付通投低转化复测 / 每付通投无转化复测",
    "每付通投复测": "每付通投复测需要指定低转化/无转化，例如 每付通投低转化复测 / 每付通投无转化复测",
    "每付男复测": "每付男复测需要指定低转化/无转化，例如 每付男低转化复测 / 每付男无转化复测",
}


def _cfg(request: dict[str, Any]) -> dict[str, Any]:
    value = request.get("create_mode")
    return dict(value) if isinstance(value, dict) else dict(request)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _compact_mode_alias(value: str) -> str:
    return re.sub(r"[\s_\-]+", "", value).lower()


def resolve_mode_key(value: str) -> str:
    mode_key = _text(value)
    if not mode_key:
        return ""
    compact = _compact_mode_alias(mode_key)
    if compact in AMBIGUOUS_MODE_ALIASES:
        raise ValueError(AMBIGUOUS_MODE_ALIASES[compact])
    return MODE_ALIASES.get(compact, mode_key)


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _float(value: Any, default: float = 0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _template(template_catalog: dict[str, Any], template_key: str) -> dict[str, Any]:
    templates = template_catalog.get("templates") if isinstance(template_catalog.get("templates"), dict) else {}
    value = templates.get(template_key)
    result = dict(value) if isinstance(value, dict) else {}
    effective_touch_url = _text(template_catalog.get("effective_touch_url"))
    if effective_touch_url and not _text(result.get("effective_touch_url")):
        result["effective_touch_url"] = effective_touch_url
    return result


def _template_name(mode_config: dict[str, Any], template: dict[str, Any]) -> str:
    base = (
        _text(mode_config.get("template_name"))
        or _text(template.get("project_template_name"))
        or _text(mode_config.get("template_key"))
    )
    suffix = _text(mode_config.get("template_name_suffix"))
    if suffix and suffix not in base:
        return f"{base}{suffix}"
    return base


def _defaults(mode_config: dict[str, Any]) -> dict[str, Any]:
    value = mode_config.get("defaults")
    return dict(value) if isinstance(value, dict) else {}


def _field_defaults(mode_config: dict[str, Any], template: dict[str, Any]) -> dict[str, Any]:
    fixed = template.get("project_fixed") if isinstance(template.get("project_fixed"), dict) else {}
    defaults = _defaults(mode_config)
    result = {
        "landing_type": _text(fixed.get("landing_type")) or "MICRO_GAME",
        "marketing_goal": _text(fixed.get("marketing_goal")) or "VIDEO_AND_IMAGE",
        "ad_type": _text(fixed.get("ad_type")) or "ALL",
        "delivery_mode": _text(fixed.get("delivery_mode")) or "PROCEDURAL",
        "micro_promotion_type": _text(fixed.get("micro_promotion_type") or template.get("micro_promotion_type")) or "WECHAT_GAME",
        "micro_app_instance_id": template.get("micro_app_instance_id"),
        "aigc_dynamic_creative_switch": "ON",
        "external_action": _text(fixed.get("external_action")) or "AD_CONVERT_TYPE_PAY",
        "deep_external_action": _text(fixed.get("deep_external_action")),
        "inventory_catalog": "UNIVERSAL_SMART",
        "pricing": _text(fixed.get("pricing")) or "PRICING_OCPM",
        "inventory_type": "INVENTORY_FEED",
        "action_track_url": _text(mode_config.get("effective_touch_url")) or _text(template.get("effective_touch_url")),
        "schedule_type": "SCHEDULE_FROM_NOW",
        "deep_bid_type": _text(fixed.get("deep_bid_type")) or "BID_PER_ACTION",
        "bid_type": _text(fixed.get("bid_type")) or "CUSTOM",
        "budget_mode": _text(fixed.get("budget_mode")) or "BUDGET_MODE_DAY",
        "cpa_bid": _float(defaults.get("cpa_bid"), 0),
        "district": "NONE",
        "gender": _text(fixed.get("audience_gender")) or "NONE",
        "audience_platform": [],
    }
    roi = defaults.get("roi_coefficient")
    if roi not in (None, ""):
        result["roi_goal"] = _float(roi)
    return {key: value for key, value in result.items() if value not in ("", None)}


def _template_parameters(mode_config: dict[str, Any], template: dict[str, Any]) -> dict[str, Any]:
    result = dict(template)
    result.pop("project_fixed", None)
    result.pop("effective_touch_url", None)
    fixed_cover = mode_config.get("fixed_cover") if isinstance(mode_config.get("fixed_cover"), dict) else {}
    if _text(fixed_cover.get("mode")) == "template_fixed" and template.get("fixed_video_cover_id"):
        result["fixed_video_cover_id"] = template.get("fixed_video_cover_id")
    unit_creative_selection = (
        mode_config.get("unit_creative_selection")
        if isinstance(mode_config.get("unit_creative_selection"), dict)
        else {}
    )
    if unit_creative_selection:
        result["unit_creative_selection"] = dict(unit_creative_selection)
    return result


def _target_accounts(cfg: dict[str, Any], defaults: dict[str, Any]) -> list[dict[str, Any]]:
    raw = cfg.get("target_accounts")
    rows = raw if isinstance(raw, list) else []
    project_override = cfg.get("projects_per_account")
    result: list[dict[str, Any]] = []
    for row in rows:
        account = row if isinstance(row, dict) else {"advertiser_id": row}
        advertiser_id = _text(account.get("advertiser_id") or account.get("account_id"))
        if not advertiser_id:
            continue
        result.append(
            {
                "advertiser_id": advertiser_id,
                "project_count": _int(project_override, _int(account.get("project_count"), _int(defaults.get("project_count"), 1))),
                "units_per_project": _int(account.get("units_per_project"), _int(defaults.get("units_per_project"), 1)),
                "daily_budget": _int(account.get("daily_budget"), _int(defaults.get("daily_budget"), 0)),
            }
        )
    return result


def _material_requirements(mode_config: dict[str, Any]) -> dict[str, Any]:
    value = mode_config.get("material_requirements")
    requirements = dict(value) if isinstance(value, dict) else {}
    requirements.setdefault("material_type", "video")
    requirements.setdefault("materials_per_unit", 1)
    requirements.setdefault("dedupe_scope", "request")
    if requirements.get("allow_reuse_across_accounts") is None:
        requirements["allow_reuse_across_accounts"] = str(requirements.get("on_insufficient") or "") == "allow_reuse"
    return requirements


def _material_selection(mode_config: dict[str, Any]) -> dict[str, Any]:
    value = mode_config.get("material_selection")
    selection = dict(value) if isinstance(value, dict) else {}
    selection_type = _text(selection.get("selection_type")) or "high_spend"
    selection.setdefault("source_scope", "source_material_account")
    selection.setdefault("min_stat_cost", 1000 if selection_type == "high_spend" else 0)
    selection.setdefault("sort_by", "create_time_desc" if selection_type == "test_new" else "stat_cost_desc")
    selection.setdefault("random_shuffle", True)
    selection.setdefault("exclude_recent_used", False)
    selection.setdefault("exclude_recent_used_days", 0)
    return selection


def _mode_config_path(cfg: dict[str, Any]) -> Path:
    if _text(cfg.get("mode_config_path")):
        return Path(_text(cfg.get("mode_config_path")))
    mode_key = resolve_mode_key(_text(cfg.get("mode_key") or cfg.get("mode")))
    if not mode_key:
        raise ValueError("create_mode requires mode_key or mode_config_path")
    mode_dir = Path(_text(cfg.get("mode_config_dir")) or "configs/create-modes")
    direct = mode_dir / f"{mode_key}.json"
    if direct.exists():
        return direct
    return mode_dir / f"{mode_key}.example.json"


def load_create_mode_config(cfg: dict[str, Any]) -> dict[str, Any]:
    mode_config = load_json(_mode_config_path(cfg))
    if not _text(mode_config.get("mode_key")):
        raise ValueError("create mode config requires mode_key")
    if not _text(mode_config.get("template_key")):
        raise ValueError("create mode config requires template_key")
    return mode_config


def build_create_mode_request(
    request: dict[str, Any],
    *,
    mode_config: dict[str, Any],
    template_catalog: dict[str, Any],
) -> dict[str, Any]:
    cfg = _cfg(request)
    defaults = _defaults(mode_config)
    template_key = _text(mode_config.get("template_key"))
    template = _template(template_catalog, template_key)
    mode_key = _text(mode_config.get("mode_key"))
    target_date = _text(cfg.get("target_date"))
    batch_generated_at = _text(cfg.get("batch_generated_at")) or _now_iso()
    request_id = _text(cfg.get("request_id")) or f"{mode_key}-{target_date or 'date'}"
    return {
        "request_id": request_id,
        "plan_id": _text(cfg.get("plan_id")) or f"create-plan-{request_id}",
        "target_date": target_date,
        "product": _text(mode_config.get("product")) or "勇者突进",
        "platform": _text(mode_config.get("platform")) or "WECHAT_GAME",
        "project_type": _template_name(mode_config, template),
        "template_key": template_key,
        "source_advertiser_id": _text(mode_config.get("source_advertiser_id")),
        "organization_id": _text(mode_config.get("organization_id")),
        "pool_key": _text(mode_config.get("pool_key")) or f"{mode_key}-source-materials",
        "owner": _text(cfg.get("owner") or mode_config.get("owner")),
        "project_template_name": _template_name(mode_config, template),
        "batch_generated_at": batch_generated_at,
        "target_accounts": _target_accounts(cfg, defaults),
        "material_requirements": _material_requirements(mode_config),
        "material_selection": _material_selection(mode_config),
        "field_defaults": _field_defaults(mode_config, template),
        "project_name_template": _text(
            (mode_config.get("naming") if isinstance(mode_config.get("naming"), dict) else {}).get("project_name_template")
        )
        or "{target_date_mmdd}_{owner}_{product}_{project_template_name}_{batch_code}_{index}",
        "initial_status": dict(mode_config.get("initial_status") if isinstance(mode_config.get("initial_status"), dict) else {}),
        "constraints": {
            "phase": "create_mode",
            "execution_enabled": False,
            "allow_real_create": False,
        },
        "template_parameters": _template_parameters(mode_config, template),
    }


def run_create_mode_request(
    request: dict[str, Any],
    *,
    db_path: str | Path,
    runs_dir: str | Path,
    policy: dict[str, Any],
    template_catalog_path: str | Path = "configs/create-templates/wx-mini-game.json",
) -> dict[str, Any]:
    cfg = _cfg(request)
    mode_config = load_create_mode_config(cfg)
    template_catalog = load_json(template_catalog_path)
    create_request = build_create_mode_request(
        cfg,
        mode_config=mode_config,
        template_catalog=template_catalog,
    )
    plan = build_create_strategy_plan(
        request={"create_request": create_request},
        db_path=db_path,
        policy=policy.get("create_strategy_plan") if isinstance(policy.get("create_strategy_plan"), dict) else policy,
    )
    payload = {
        "ok": plan["ok"],
        "workflow": "create_mode",
        "phase": "phase1",
        "status": "planned",
        "execution_enabled": False,
        "external_api_calls": 0,
        "mode_key": mode_config["mode_key"],
        "summary": {
            **plan["summary"],
            "mode_key": mode_config["mode_key"],
            "display_name": _text(mode_config.get("display_name")),
        },
        "blocking_reasons": plan.get("violations", []),
        "create_request": create_request,
        "create_strategy_plan": plan,
    }
    artifact = write_run_artifact(runs_dir, "create_mode", payload)
    return {**payload, "artifact_path": str(artifact)}
