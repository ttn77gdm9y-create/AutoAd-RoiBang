from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from roibang_v2.runs import write_run_artifact
from roibang_v2.workflows.create_first_live_local_chain import run_create_first_live_local_chain_request
from roibang_v2.workflows.create_plan_contract import validate_create_plan


def _rows(value: Any) -> list[dict[str, Any]]:
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def _text(value: Any) -> str:
    return str(value or "").strip()


def _int_value(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _float_value(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _strategy_payload(strategy: dict[str, Any]) -> dict[str, Any]:
    value = strategy.get("strategy")
    return dict(value) if isinstance(value, dict) else dict(strategy)


def _defaults(strategy: dict[str, Any]) -> dict[str, Any]:
    value = strategy.get("defaults")
    return dict(value) if isinstance(value, dict) else {}


def _material_policy(strategy: dict[str, Any], group: dict[str, Any]) -> dict[str, Any]:
    defaults = _defaults(strategy)
    policy = strategy.get("material_policy")
    result = dict(policy) if isinstance(policy, dict) else {}
    group_policy = group.get("material_policy")
    if isinstance(group_policy, dict):
        result.update(group_policy)
    if "materials_per_unit" not in result:
        result["materials_per_unit"] = defaults.get("materials_per_unit", 4)
    if "dedupe_scope" not in result:
        result["dedupe_scope"] = defaults.get("dedupe_scope", "request")
    if "material_type" not in result:
        result["material_type"] = defaults.get("material_type", "video")
    return result


def _plan_groups(strategy: dict[str, Any]) -> list[dict[str, Any]]:
    groups = _rows(strategy.get("plan_groups"))
    if groups:
        return groups
    group = {
        "plan_id": strategy.get("plan_id"),
        "template_key": strategy.get("template_key"),
        "template_name": strategy.get("template_name"),
        "roi_coefficient": strategy.get("roi_coefficient"),
        "cpa_bid": strategy.get("cpa_bid"),
        "target_accounts": strategy.get("target_accounts", strategy.get("accounts")),
        "materials": strategy.get("materials"),
    }
    return [group]


def _accounts(strategy: dict[str, Any], group: dict[str, Any]) -> list[dict[str, Any]]:
    rows = _rows(group.get("target_accounts"))
    if not rows:
        rows = _rows(group.get("accounts"))
    if not rows:
        rows = _rows(strategy.get("target_accounts"))
    if not rows:
        rows = _rows(strategy.get("accounts"))
    return rows


def _materials(strategy: dict[str, Any], group: dict[str, Any]) -> list[dict[str, Any]]:
    rows = _rows(group.get("materials"))
    return rows if rows else _rows(strategy.get("materials"))


def _template(template_catalog: dict[str, Any] | None, template_key: str) -> dict[str, Any]:
    catalog = template_catalog or {}
    templates = catalog.get("templates")
    if isinstance(templates, dict):
        value = templates.get(template_key)
        return dict(value) if isinstance(value, dict) else {}
    return {}


def _requires_roi(template_key: str, template: dict[str, Any]) -> bool:
    if "requires_roi_goal" in template:
        return bool(template.get("requires_roi_goal"))
    return "_7r_" in template_key or template_key.startswith("wx_7r")


def _template_name(template_key: str, group: dict[str, Any], template: dict[str, Any]) -> str:
    return (
        _text(group.get("template_name"))
        or _text(template.get("project_template_name"))
        or _text(template.get("template_name"))
        or template_key
    )


def _required_units(accounts: list[dict[str, Any]]) -> int:
    total = 0
    for account in accounts:
        project_count = max(_int_value(account.get("project_count"), 0), 0)
        unit_count = max(_int_value(account.get("unit_count_per_project", account.get("units_per_project")), 0), 0)
        total += project_count * unit_count
    return total


def _normalize_material(row: dict[str, Any]) -> dict[str, Any]:
    material_id = _text(row.get("source_material_id") or row.get("material_id"))
    video_id = _text(row.get("source_video_id") or row.get("video_id"))
    result = {
        "source_material_id": material_id,
        "source_video_id": video_id,
    }
    for key in ["name", "material_type", "review_status", "stat_cost", "score"]:
        if row.get(key) not in (None, ""):
            result[key] = row.get(key)
    return result


def _normalize_accounts(accounts: list[dict[str, Any]], defaults: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for account in accounts:
        rows.append(
            {
                "advertiser_id": _text(account.get("advertiser_id") or account.get("account_id")),
                "project_count": _int_value(account.get("project_count"), _int_value(defaults.get("project_count"), 1)),
                "unit_count_per_project": _int_value(
                    account.get("unit_count_per_project", account.get("units_per_project")),
                    _int_value(defaults.get("unit_count_per_project", defaults.get("units_per_project")), 1),
                ),
                "daily_budget": _int_value(account.get("daily_budget"), _int_value(defaults.get("daily_budget"), 0)),
            }
        )
    return rows


def _group_cpa_bid(strategy: dict[str, Any], group: dict[str, Any]) -> int:
    defaults = _defaults(strategy)
    return _int_value(group.get("cpa_bid", strategy.get("cpa_bid", defaults.get("cpa_bid"))), 0)


def _plan_id(strategy_id: str, group: dict[str, Any], template_key: str, index: int) -> str:
    explicit = _text(group.get("plan_id"))
    if explicit:
        return explicit
    base = strategy_id or _text(group.get("run_id")) or "strategy"
    return f"{base}-{template_key}-{index:02d}"


def _file_safe_plan_id(plan_id: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in plan_id).strip("-") or "create-plan"


def _build_create_plan(
    *,
    strategy: dict[str, Any],
    group: dict[str, Any],
    template_catalog: dict[str, Any] | None,
    group_index: int,
    material_cursor: int,
) -> tuple[dict[str, Any], int, list[str]]:
    violations: list[str] = []
    defaults = _defaults(strategy)
    strategy_id = _text(strategy.get("strategy_id") or strategy.get("run_id"))
    template_key = _text(group.get("template_key") or strategy.get("template_key"))
    template = _template(template_catalog, template_key)
    requires_roi = _requires_roi(template_key, template)
    roi_coefficient = _float_value(group.get("roi_coefficient", strategy.get("roi_coefficient")))
    accounts = _normalize_accounts(_accounts(strategy, group), defaults)
    material_policy = _material_policy(strategy, group)
    materials_per_unit = max(_int_value(material_policy.get("materials_per_unit"), 4), 0)
    dedupe_scope = _text(material_policy.get("dedupe_scope")) or "request"
    needed_materials = _required_units(accounts) * materials_per_unit
    material_rows = _materials(strategy, group)
    if _rows(group.get("materials")):
        start = 0
    elif dedupe_scope == "request":
        start = material_cursor
    else:
        start = 0
    selected_materials = material_rows[start : start + needed_materials] if needed_materials else []
    next_cursor = material_cursor + needed_materials if not _rows(group.get("materials")) and dedupe_scope == "request" else material_cursor

    if not template_key:
        violations.append(f"plan_groups[{group_index}].template_key is required")
    if requires_roi and roi_coefficient is None:
        violations.append(f"plan_groups[{group_index}].roi_coefficient is required for 7R templates")
    if not requires_roi and roi_coefficient is not None:
        violations.append(f"plan_groups[{group_index}].roi_coefficient is only allowed for 7R templates")
    if not accounts:
        violations.append(f"plan_groups[{group_index}].target_accounts requires at least one item")
    if materials_per_unit <= 0:
        violations.append(f"plan_groups[{group_index}].materials_per_unit must be positive")

    plan = {
        "plan_id": _plan_id(strategy_id, group, template_key, group_index + 1),
        "product": _text(strategy.get("product")),
        "platform": _text(strategy.get("platform")),
        "template_key": template_key,
        "template_name": _template_name(template_key, group, template),
        "owner": _text(strategy.get("operator") or strategy.get("owner")),
        "target_date": _text(strategy.get("target_date")),
        "batch_generated_at": _text(strategy.get("batch_generated_at")),
        "launch_mode": _text(strategy.get("launch_mode")) or "create_only",
        "cpa_bid": _group_cpa_bid(strategy, group),
        "organization_id": _text(strategy.get("organization_id")),
        "pool_key": _text(group.get("pool_key") or strategy.get("pool_key")),
        "source_advertiser_id": _text(group.get("source_advertiser_id") or strategy.get("source_advertiser_id")),
        "target_accounts": accounts,
        "material_requirements": {
            "material_type": _text(material_policy.get("material_type")) or "video",
            "materials_per_unit": materials_per_unit,
            "dedupe_scope": dedupe_scope,
        },
        "materials": [_normalize_material(row) for row in selected_materials],
        "reason": _text(group.get("reason") or strategy.get("reason"))
        or f"AI strategy {strategy_id} generated create_plan for {template_key}",
    }
    if requires_roi and roi_coefficient is not None:
        plan["roi_coefficient"] = roi_coefficient
    return plan, next_cursor, violations


def _material_shortage_violations(strategy: dict[str, Any], groups: list[dict[str, Any]]) -> list[str]:
    defaults = _defaults(strategy)
    total_needed = 0
    dedupe_scope = "request"
    for group in groups:
        material_policy = _material_policy(strategy, group)
        dedupe_scope = _text(material_policy.get("dedupe_scope")) or dedupe_scope
        if dedupe_scope != "request" or _rows(group.get("materials")):
            continue
        accounts = _normalize_accounts(_accounts(strategy, group), defaults)
        total_needed += _required_units(accounts) * max(_int_value(material_policy.get("materials_per_unit"), 4), 0)
    if dedupe_scope == "request" and total_needed and len(_rows(strategy.get("materials"))) < total_needed:
        return [f"materials has {len(_rows(strategy.get('materials')))} items, expected at least {total_needed} for dedupe_scope=request"]
    return []


def _summary(create_plans: list[dict[str, Any]], violations: list[str]) -> dict[str, Any]:
    accounts = [account for plan in create_plans for account in _rows(plan.get("target_accounts"))]
    project_count = sum(_int_value(account.get("project_count"), 0) for account in accounts)
    unit_count = sum(
        _int_value(account.get("project_count"), 0) * _int_value(account.get("unit_count_per_project"), 0)
        for account in accounts
    )
    return {
        "create_plan_count": len(create_plans),
        "target_account_count": len(accounts),
        "project_count": project_count,
        "unit_count": unit_count,
        "material_count": sum(len(_rows(plan.get("materials"))) for plan in create_plans),
        "violation_count": len(violations),
    }


def build_create_plans_from_strategy(
    strategy: dict[str, Any],
    *,
    template_catalog: dict[str, Any] | None = None,
    policy: dict[str, Any] | None = None,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    payload = _strategy_payload(strategy)
    groups = _plan_groups(payload)
    create_plans: list[dict[str, Any]] = []
    violations: list[str] = []
    material_cursor = 0
    for index, group in enumerate(groups):
        plan, material_cursor, group_violations = _build_create_plan(
            strategy=payload,
            group=group,
            template_catalog=template_catalog,
            group_index=index,
            material_cursor=material_cursor,
        )
        create_plans.append(plan)
        violations.extend(group_violations)
    violations.extend(_material_shortage_violations(payload, groups))
    if policy:
        for plan in create_plans:
            validation = validate_create_plan(plan, policy=policy, db_path=db_path)
            violations.extend(f"{plan.get('plan_id')}: {item}" for item in validation.get("violations") or [])
    return {
        "ok": not violations,
        "workflow": "create_plan_from_strategy",
        "phase": "phase2_preparation",
        "execution_enabled": False,
        "external_api_calls": 0,
        "status": "created" if not violations else "blocked",
        "strategy_id": _text(payload.get("strategy_id") or payload.get("run_id")),
        "summary": _summary(create_plans, violations),
        "create_plans": create_plans,
        "violations": violations,
        "actions": [],
    }


def write_create_plan_files(create_plans: list[dict[str, Any]], output_dir: str | Path) -> list[str]:
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    paths: list[str] = []
    for plan in create_plans:
        plan_id = _file_safe_plan_id(_text(plan.get("plan_id")))
        path = target / f"{plan_id}.local.json"
        path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        paths.append(str(path))
    return paths


def _live_execute_commands(
    *,
    create_plans: list[dict[str, Any]],
    plan_file_paths: list[str],
    local_chain_results: list[dict[str, Any]],
) -> list[dict[str, str]]:
    by_plan_id = {
        str(row.get("plan_id") or ""): row
        for row in local_chain_results
        if str(row.get("status") or "") == "ready_for_execute_script"
    }
    commands: list[dict[str, str]] = []
    for index, plan in enumerate(create_plans):
        plan_id = _text(plan.get("plan_id"))
        chain = by_plan_id.get(plan_id)
        if not chain:
            continue
        artifacts = chain.get("artifacts") if isinstance(chain.get("artifacts"), dict) else {}
        create_execute_artifact = _text(artifacts.get("create_execute"))
        if not create_execute_artifact:
            continue
        plan_path = plan_file_paths[index] if index < len(plan_file_paths) else ""
        if not plan_path:
            continue
        command = (
            "PYTHONPATH=src python3 scripts/run_create_live_execute_once.py "
            "--config configs/runtime.create-live.local.json "
            "--policy policies/create-live-execute.local.json "
            f"--plan {plan_path} "
            f"--create-execute-artifact {create_execute_artifact}"
        )
        commands.append(
            {
                "plan_id": plan_id,
                "plan_path": plan_path,
                "create_execute_artifact": create_execute_artifact,
                "command": command,
            }
        )
    return commands


def run_create_plan_from_strategy_request(
    request: dict[str, Any],
    *,
    runs_dir: str | Path,
    template_catalog: dict[str, Any] | None = None,
    policy: dict[str, Any] | None = None,
    db_path: str | Path | None = None,
    output_dir: str | Path | None = None,
    run_local_chain: bool = False,
) -> dict[str, Any]:
    result = build_create_plans_from_strategy(
        request,
        template_catalog=template_catalog,
        policy=policy,
        db_path=db_path,
    )
    plan_file_paths: list[str] = []
    if result["ok"] and output_dir:
        plan_file_paths = write_create_plan_files(result["create_plans"], output_dir)
    local_chain_results: list[dict[str, Any]] = []
    if result["ok"] and run_local_chain:
        for plan in result["create_plans"]:
            local_chain = run_create_first_live_local_chain_request(
                {
                    "create_first_live_local_chain": {
                        "create_plan": plan,
                        "preview_config_path": str(output_dir or "strategy.json"),
                        "policy": policy or {},
                    }
                },
                db_path=db_path or "",
                runs_dir=runs_dir,
            )
            local_chain_results.append(
                {
                    "ok": bool(local_chain.get("ok")),
                    "workflow": str(local_chain.get("workflow") or ""),
                    "status": str(local_chain.get("status") or ""),
                    "plan_id": str(plan.get("plan_id") or ""),
                    "summary": dict(local_chain.get("summary")) if isinstance(local_chain.get("summary"), dict) else {},
                    "artifacts": dict(local_chain.get("artifacts")) if isinstance(local_chain.get("artifacts"), dict) else {},
                    "artifact_path": str(local_chain.get("artifact_path") or ""),
                    "violations": [str(item) for item in local_chain.get("violations") or []],
                }
            )
    live_execute_commands = _live_execute_commands(
        create_plans=result["create_plans"],
        plan_file_paths=plan_file_paths,
        local_chain_results=local_chain_results,
    )
    payload = {
        **result,
        "summary": {
            **result["summary"],
            "ready_for_execute_script_count": sum(
                1 for row in local_chain_results if str(row.get("status") or "") == "ready_for_execute_script"
            ),
            "live_execute_command_count": len(live_execute_commands),
        },
        "plan_file_paths": plan_file_paths,
        "local_chain_results": local_chain_results,
        "live_execute_commands": live_execute_commands,
    }
    if local_chain_results and not all(bool(row.get("ok")) for row in local_chain_results):
        payload["ok"] = False
        payload["status"] = "blocked"
        payload["violations"] = [
            f"{row.get('plan_id')}: {item}"
            for row in local_chain_results
            for item in row.get("violations") or []
        ]
    artifact_path = write_run_artifact(runs_dir, "create_plan_from_strategy", payload)
    return {**payload, "artifact_path": str(artifact_path)}
