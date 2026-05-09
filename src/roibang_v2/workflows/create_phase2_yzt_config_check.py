from __future__ import annotations

from pathlib import Path
from typing import Any

from roibang_v2.runs import write_run_artifact
from roibang_v2.workflows.create_phase2_yzt_create_preview import _manual_config_contract


def _check_config(request: dict[str, Any]) -> dict[str, Any]:
    value = request.get("create_phase2_yzt_config_check")
    return dict(value) if isinstance(value, dict) else dict(request)


def _template_catalog(policy: dict[str, Any]) -> dict[str, Any]:
    prep = policy.get("create_phase2_template_slot_prep")
    prep = prep if isinstance(prep, dict) else {}
    catalog = prep.get("product_template_catalog")
    return dict(catalog) if isinstance(catalog, dict) else {}


def _templates(policy: dict[str, Any]) -> list[dict[str, Any]]:
    rows = _template_catalog(policy).get("templates")
    return [dict(row) for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _selected_template(preview_config: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    template_name = str(preview_config.get("template_name") or "").strip()
    for template in _templates(policy):
        if str(template.get("project_template_name") or "") == template_name:
            return template
        if str(template.get("template_key") or "") == template_name:
            return template
    return {}


def _accounts(preview_config: dict[str, Any]) -> list[dict[str, Any]]:
    rows = preview_config.get("accounts")
    return [dict(row) for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _is_placeholder_advertiser_id(value: str) -> bool:
    normalized = value.strip().lower()
    return (
        normalized.startswith("target-advertiser-id")
        or normalized in {"advertiser-id", "example-advertiser-id", "placeholder-advertiser-id"}
        or "placeholder" in normalized
    )


def _placeholder_account_count(preview_config: dict[str, Any]) -> int:
    return sum(
        1
        for account in _accounts(preview_config)
        if _is_placeholder_advertiser_id(str(account.get("advertiser_id") or ""))
    )


def _defaults(preview_config: dict[str, Any]) -> dict[str, Any]:
    value = preview_config.get("defaults")
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


def _preflight_policy(policy: dict[str, Any]) -> dict[str, Any]:
    value = policy.get("create_preflight")
    return dict(value) if isinstance(value, dict) else {}


def _requires_roi(template: dict[str, Any]) -> bool:
    roi = template.get("roi_goal")
    return bool(roi.get("required")) if isinstance(roi, dict) else False


def _violations(*, preview_config: dict[str, Any], policy: dict[str, Any]) -> list[str]:
    violations: list[str] = []
    template_name = str(preview_config.get("template_name") or "").strip()
    selected_template = _selected_template(preview_config, policy)
    if not template_name:
        violations.append("模板名不能为空")
    elif not selected_template:
        violations.append(f"模板 {template_name} 不在勇者突进模板列表里")

    accounts = _accounts(preview_config)
    if not accounts:
        violations.append("账户列表不能为空")
    for index, account in enumerate(accounts):
        advertiser_id = str(account.get("advertiser_id") or "").strip()
        if not advertiser_id:
            violations.append(f"accounts[{index}].advertiser_id 不能为空")
        elif _is_placeholder_advertiser_id(advertiser_id):
            violations.append(f"accounts[{index}].advertiser_id 是占位账户，请换成真实账户ID")

    defaults = _defaults(preview_config)
    preflight = _preflight_policy(policy)
    min_budget = _int_value(preflight.get("min_daily_budget"), 0)
    max_budget = _int_value(preflight.get("max_daily_budget"), 0)
    default_budget = _int_value(defaults.get("daily_budget", preview_config.get("daily_budget")), 0)
    if min_budget and default_budget < min_budget:
        violations.append(f"默认日预算 {default_budget} 低于策略下限 {min_budget}")
    if max_budget and default_budget > max_budget:
        violations.append(f"默认日预算 {default_budget} 超过策略上限 {max_budget}")

    if _int_value(defaults.get("project_count"), 0) <= 0:
        violations.append("默认项目数必须大于0")
    if _int_value(defaults.get("units_per_project"), 0) <= 0:
        violations.append("默认单元数必须大于0")

    if selected_template and _requires_roi(selected_template) and _float_or_none(preview_config.get("roi_coefficient")) is None:
        violations.append(f"{template_name} 需要填写ROI系数")
    return violations


def _human_next_steps(violations: list[str], *, policy: dict[str, Any]) -> list[str]:
    joined = "\n".join(violations)
    preflight = _preflight_policy(policy)
    min_budget = _int_value(preflight.get("min_daily_budget"), 0)
    max_budget = _int_value(preflight.get("max_daily_budget"), 0)
    steps: list[str] = []
    if "advertiser_id 不能为空" in joined or "账户列表不能为空" in joined:
        steps.append("补齐账户ID。")
    if "占位账户" in joined:
        steps.append("把 target-advertiser-id 这种占位账户换成真实账户ID。")
    if "默认日预算" in joined:
        steps.append(f"把默认预算改到 {min_budget} 到 {max_budget} 之间，或调整策略预算范围。")
    if "默认项目数" in joined:
        steps.append("把默认项目数改成大于0。")
    if "默认单元数" in joined:
        steps.append("把默认单元数改成大于0。")
    if "ROI系数" in joined:
        steps.append("填写ROI系数，或改用不需要ROI系数的模板。")
    if "模板" in joined and "不在勇者突进模板列表里" in joined:
        steps.append("把模板名改成策略里已有的勇者突进模板。")
    return steps or ["配置可以进入预览；下一步运行勇者突进创建预览。"]


def build_create_phase2_yzt_config_check(
    *,
    preview_config: dict[str, Any],
    policy: dict[str, Any],
) -> dict[str, Any]:
    violations = _violations(preview_config=preview_config, policy=policy)
    ok = not violations
    return {
        "ok": ok,
        "workflow": "create_phase2_yzt_config_check",
        "phase": "phase2_preparation",
        "execution_enabled": False,
        "external_api_calls": 0,
        "status": "passed" if ok else "needs_fix",
        "summary": {
            "template_name": str(preview_config.get("template_name") or ""),
            "account_count": len(_accounts(preview_config)),
            "placeholder_account_count": _placeholder_account_count(preview_config),
            "violation_count": len(violations),
            "ready_for_preview": ok,
        },
        "manual_config_contract": _manual_config_contract(),
        "violations": violations,
        "human_next_steps": _human_next_steps(violations, policy=policy),
        "actions": [],
    }


def run_create_phase2_yzt_config_check_request(
    request: dict[str, Any],
    *,
    runs_dir: str | Path,
) -> dict[str, Any]:
    cfg = _check_config(request)
    payload = build_create_phase2_yzt_config_check(
        preview_config=cfg.get("preview_config") if isinstance(cfg.get("preview_config"), dict) else {},
        policy=cfg.get("policy") if isinstance(cfg.get("policy"), dict) else {},
    )
    artifact_path = write_run_artifact(runs_dir, "create_phase2_yzt_config_check", payload)
    return {**payload, "artifact_path": str(artifact_path)}
