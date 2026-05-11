from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from roibang_v2.runs import write_run_artifact
from roibang_v2.config import load_json
from roibang_v2.workflows.create_approval import run_create_approval_request
from roibang_v2.workflows.create_execute import run_create_execute_request
from roibang_v2.workflows.create_phase2_yzt_dry_chain import run_create_phase2_yzt_dry_chain_request
from roibang_v2.workflows.create_phase2_yzt_preparation_check import build_create_phase2_yzt_preparation_check
from roibang_v2.workflows.create_plan_contract import validate_create_plan


def _chain_config(request: dict[str, Any]) -> dict[str, Any]:
    value = request.get("create_first_live_local_chain")
    return dict(value) if isinstance(value, dict) else dict(request)


def _policy_section(policy: dict[str, Any], key: str) -> dict[str, Any]:
    value = policy.get(key)
    return dict(value) if isinstance(value, dict) else {}


def _positive_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(parsed, 0)


def _accounts(preview_config: dict[str, Any]) -> list[dict[str, Any]]:
    rows = preview_config.get("accounts")
    return [dict(row) for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _materials_per_unit(preview_config: dict[str, Any]) -> int:
    requirements = preview_config.get("material_requirements")
    if not isinstance(requirements, dict):
        return 2
    return max(_positive_int(requirements.get("materials_per_unit"), 2), 0)


def _preferred_account(accounts: list[dict[str, Any]], first_live_policy: dict[str, Any]) -> dict[str, Any] | None:
    requested_advertiser_id = str(first_live_policy.get("advertiser_id") or "").strip()
    if requested_advertiser_id:
        for account in accounts:
            if str(account.get("advertiser_id") or "").strip() == requested_advertiser_id:
                return account
    return accounts[0] if accounts else None


def derive_first_live_preview_config(
    *,
    preview_config: dict[str, Any],
    policy: dict[str, Any],
) -> dict[str, Any]:
    config = copy.deepcopy(preview_config)
    defaults = dict(config.get("defaults") if isinstance(config.get("defaults"), dict) else {})
    first_live_policy = _policy_section(policy, "first_live_run")
    max_project_count = _positive_int(first_live_policy.get("max_project_count"), 1) or 1
    max_unit_count = _positive_int(first_live_policy.get("max_unit_count"), 2) or 1
    max_material_count = _positive_int(first_live_policy.get("max_material_count"), 4)
    materials_per_unit = _materials_per_unit(config)
    max_units_by_material = max_material_count // materials_per_unit if materials_per_unit else 0
    allowed_units = max(0, min(max_unit_count, max_units_by_material if max_material_count else max_unit_count))

    defaults["project_count"] = min(_positive_int(defaults.get("project_count"), 1) or 1, max_project_count)
    defaults["units_per_project"] = min(_positive_int(defaults.get("units_per_project"), 1) or 1, allowed_units or 1)

    selected = _preferred_account(_accounts(config), first_live_policy)
    if selected is not None:
        selected["project_count"] = min(_positive_int(selected.get("project_count"), defaults["project_count"]) or 1, max_project_count)
        selected["units_per_project"] = min(
            _positive_int(selected.get("units_per_project"), defaults["units_per_project"]) or 1,
            allowed_units or 1,
        )
        config["accounts"] = [selected]
    else:
        config["accounts"] = []
    config["defaults"] = defaults
    return config


def create_plan_to_preview_config(create_plan: dict[str, Any]) -> dict[str, Any]:
    accounts = []
    plan_accounts = _accounts({"accounts": create_plan.get("target_accounts")})
    for row in plan_accounts:
        accounts.append(
            {
                "advertiser_id": str(row.get("advertiser_id") or ""),
                "project_count": _positive_int(row.get("project_count"), 1) or 1,
                "units_per_project": _positive_int(
                    row.get("unit_count_per_project", row.get("units_per_project")),
                    1,
                )
                or 1,
                "daily_budget": _positive_int(row.get("daily_budget"), 0),
            }
        )
    first_account = accounts[0] if accounts else {}
    materials = _accounts({"accounts": create_plan.get("materials")})
    material_requirements = create_plan.get("material_requirements")
    if not isinstance(material_requirements, dict):
        material_requirements = {
            "material_type": "video",
            "materials_per_unit": max(len(materials), 1),
            "dedupe_scope": "request",
        }
    field_defaults = create_plan.get("field_defaults")
    if not isinstance(field_defaults, dict) or not field_defaults:
        field_defaults = {
            "landing_type": "MICRO_GAME",
            "pricing": "PRICING_OCPM",
            "inventory_type": "INVENTORY_FEED",
        }
    return {
        "template_name": str(create_plan.get("template_name") or "微小每付7R男"),
        "owner": str(create_plan.get("owner") or ""),
        "target_date": str(create_plan.get("target_date") or ""),
        "batch_generated_at": str(create_plan.get("batch_generated_at") or ""),
        "source_advertiser_id": str(create_plan.get("source_advertiser_id") or ""),
        "organization_id": str(create_plan.get("organization_id") or ""),
        "pool_key": str(create_plan.get("pool_key") or ""),
        "defaults": {
            "daily_budget": _positive_int(first_account.get("daily_budget"), 0),
            "project_count": _positive_int(first_account.get("project_count"), 1) or 1,
            "units_per_project": _positive_int(first_account.get("units_per_project"), 1) or 1,
        },
        "roi_coefficient": create_plan.get("roi_coefficient"),
        "accounts": accounts,
        "material_requirements": dict(material_requirements),
        "field_defaults": dict(field_defaults),
        "create_plan": {
            "plan_id": str(create_plan.get("plan_id") or ""),
            "reason": str(create_plan.get("reason") or ""),
            "materials": materials,
        },
    }


def _step(step: str, artifact: dict[str, Any]) -> dict[str, Any]:
    return {
        "step": step,
        "workflow": str(artifact.get("workflow") or ""),
        "ok": bool(artifact.get("ok")),
        "status": str(artifact.get("status") or ""),
    }


def _dry_summary(dry_chain: dict[str, Any]) -> dict[str, Any]:
    value = dry_chain.get("dry_run_summary")
    return dict(value) if isinstance(value, dict) else {}


def _scope_guard(*, dry_chain: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    first_live_policy = _policy_section(policy, "first_live_run")
    max_project_count = _positive_int(first_live_policy.get("max_project_count"), 1) or 1
    max_unit_count = _positive_int(first_live_policy.get("max_unit_count"), 2) or 1
    max_material_count = _positive_int(first_live_policy.get("max_material_count"), 4)
    dry_summary = _dry_summary(dry_chain)
    project_count = _positive_int(dry_summary.get("project_count"), 0)
    unit_count = _positive_int(dry_summary.get("unit_count"), 0)
    material_count = _positive_int(dry_summary.get("material_count"), 0)
    violations: list[str] = []
    if project_count > max_project_count:
        violations.append("首单项目数超过策略上限")
    if unit_count > max_unit_count:
        violations.append("首单单元数超过策略上限")
    if material_count > max_material_count:
        violations.append("首单素材数超过策略上限")
    if project_count <= 0:
        violations.append("首单项目数必须大于 0")
    if unit_count <= 0:
        violations.append("首单单元数必须大于 0")
    return {
        "ok": not violations,
        "project_count": project_count,
        "unit_count": unit_count,
        "material_count": material_count,
        "max_project_count": max_project_count,
        "max_unit_count": max_unit_count,
        "max_material_count": max_material_count,
        "violations": violations,
    }


def _human_next_steps(*, ok: bool, preparation: dict[str, Any], dry_chain: dict[str, Any], scope_guard: dict[str, Any]) -> list[str]:
    if ok:
        return [
            "人工复核首单本地链路产物里的账户、项目名、预算、单元和素材。",
            "复核 create_execute 产物路径；真实执行只把这个产物交给 run_create_live_execute_once.py。",
        ]
    rows: list[str] = []
    rows.extend(str(item) for item in preparation.get("violations") or [])
    rows.extend(str(item) for item in dry_chain.get("violations") or [])
    rows.extend(str(item) for item in scope_guard.get("violations") or [])
    return rows or ["修复首单本地链路失败项后重新运行固定脚本。"]


def _blocked_chain_payload(
    *,
    violations: list[str],
    preview_config: dict[str, Any] | None = None,
    create_plan_validation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "ok": False,
        "workflow": "create_first_live_local_chain",
        "phase": "phase2_preparation",
        "execution_enabled": False,
        "external_api_calls": 0,
        "status": "blocked",
        "summary": {
            "selected_account_count": 0,
            "project_count": 0,
            "unit_count": 0,
            "material_count": 0,
            "ready_for_approval_chain": False,
            "ready_for_live_execute": False,
        },
        "first_live_scope": {
            "max_project_count": 0,
            "max_unit_count": 0,
            "max_material_count": 0,
            "derived_preview_config": preview_config or {},
        },
        "scope_guard": {
            "ok": False,
            "project_count": 0,
            "unit_count": 0,
            "material_count": 0,
            "max_project_count": 0,
            "max_unit_count": 0,
            "max_material_count": 0,
            "violations": violations,
        },
        "chain_steps": [],
        "artifacts": {"dry_chain": "", "dry_run": "", "create_approval": "", "create_execute": ""},
        "preparation_check": {},
        "dry_chain": {},
        "create_plan_validation": create_plan_validation or {},
        "approved_for_execute": False,
        "human_next_steps": violations,
        "violations": violations,
        "actions": [],
    }


def build_create_first_live_local_chain(
    *,
    preview_config: dict[str, Any],
    create_plan: dict[str, Any] | None = None,
    policy: dict[str, Any],
    db_path: str | Path,
    runs_dir: str | Path,
    preview_config_path: str,
) -> dict[str, Any]:
    create_plan_validation: dict[str, Any] | None = None
    if isinstance(create_plan, dict) and create_plan:
        create_plan_validation = validate_create_plan(create_plan, policy=policy, db_path=db_path)
        plan_preview_config = create_plan_to_preview_config(create_plan)
        if not bool(create_plan_validation.get("ok")):
            return _blocked_chain_payload(
                violations=[str(item) for item in create_plan_validation.get("violations") or []],
                preview_config=plan_preview_config,
                create_plan_validation=create_plan_validation,
            )
        preview_config = plan_preview_config
    first_live_preview_config = derive_first_live_preview_config(preview_config=preview_config, policy=policy)
    preparation = build_create_phase2_yzt_preparation_check(
        preview_config=first_live_preview_config,
        policy=policy,
        db_path=db_path,
        preview_config_path=preview_config_path,
    )
    dry_chain: dict[str, Any] = {}
    approval: dict[str, Any] = {}
    execute: dict[str, Any] = {}
    if bool(preparation.get("ok")):
        dry_chain = run_create_phase2_yzt_dry_chain_request(
            {
                "create_phase2_yzt_dry_chain": {
                    "preview_config": first_live_preview_config,
                    "policy": policy,
                }
            },
            db_path=db_path,
            runs_dir=runs_dir,
        )
    if bool(dry_chain.get("ok")) and str(dry_chain.get("artifacts", {}).get("dry_run") or "").strip():
        dry_run_path = str(dry_chain["artifacts"]["dry_run"])
        approval = run_create_approval_request(
            {
                "create_approval": {
                    "create_dry_run_artifact": load_json(dry_run_path),
                    "create_dry_run_artifact_path": dry_run_path,
                    "policy": _policy_section(policy, "create_approval"),
                }
            },
            runs_dir=runs_dir,
        )
    if bool(approval.get("ok")):
        execute = run_create_execute_request(
            {
                "create_execute": {
                    "create_approval_artifact": approval,
                    "create_approval_artifact_path": str(approval.get("artifact_path") or ""),
                    "policy": _policy_section(policy, "create_execute"),
                }
            },
            runs_dir=runs_dir,
            db_path=db_path,
        )
    scope_guard = _scope_guard(dry_chain=dry_chain, policy=policy)
    ok = (
        bool(preparation.get("ok"))
        and bool(dry_chain.get("ok"))
        and bool(approval.get("ok"))
        and bool(execute.get("ok"))
        and bool(scope_guard.get("ok"))
    )
    payload = {
        "ok": ok,
        "workflow": "create_first_live_local_chain",
        "phase": "phase2_preparation",
        "execution_enabled": False,
        "external_api_calls": 0,
        "status": "ready_for_execute_script" if ok else "blocked",
        "summary": {
            "selected_account_count": len(_accounts(first_live_preview_config)),
            "project_count": int(scope_guard.get("project_count") or 0),
            "unit_count": int(scope_guard.get("unit_count") or 0),
            "material_count": int(scope_guard.get("material_count") or 0),
            "ready_for_approval_chain": bool(approval.get("ok")),
            "ready_for_live_execute": False,
        },
        "first_live_scope": {
            "max_project_count": int(scope_guard.get("max_project_count") or 0),
            "max_unit_count": int(scope_guard.get("max_unit_count") or 0),
            "max_material_count": int(scope_guard.get("max_material_count") or 0),
            "derived_preview_config": first_live_preview_config,
        },
        "scope_guard": scope_guard,
        "chain_steps": [
            _step("preparation_check", preparation),
            _step("dry_chain", dry_chain) if dry_chain else {"step": "dry_chain", "workflow": "", "ok": False, "status": "not_run"},
            _step("create_approval", approval) if approval else {"step": "create_approval", "workflow": "", "ok": False, "status": "not_run"},
            _step("create_execute", execute) if execute else {"step": "create_execute", "workflow": "", "ok": False, "status": "not_run"},
        ],
        "artifacts": {
            "dry_chain": str(dry_chain.get("artifact_path") or ""),
            "dry_run": str(dry_chain.get("artifacts", {}).get("dry_run") or "") if dry_chain else "",
            "create_approval": str(approval.get("artifact_path") or ""),
            "create_execute": str(execute.get("artifact_path") or ""),
        },
        "preparation_check": preparation,
        "dry_chain": dry_chain,
        "create_plan_validation": create_plan_validation or {},
        "approved_for_execute": False,
        "human_next_steps": _human_next_steps(ok=ok, preparation=preparation, dry_chain=dry_chain, scope_guard=scope_guard),
        "violations": _human_next_steps(ok=False, preparation=preparation, dry_chain=dry_chain, scope_guard=scope_guard) if not ok else [],
        "actions": [],
    }
    return payload


def run_create_first_live_local_chain_request(
    request: dict[str, Any],
    *,
    db_path: str | Path,
    runs_dir: str | Path,
) -> dict[str, Any]:
    cfg = _chain_config(request)
    payload = build_create_first_live_local_chain(
        preview_config=cfg.get("preview_config") if isinstance(cfg.get("preview_config"), dict) else {},
        create_plan=cfg.get("create_plan") if isinstance(cfg.get("create_plan"), dict) else None,
        policy=cfg.get("policy") if isinstance(cfg.get("policy"), dict) else {},
        db_path=db_path,
        runs_dir=runs_dir,
        preview_config_path=str(cfg.get("preview_config_path") or "configs/create/yzt-wx-mini-game.preview.example.json"),
    )
    artifact_path = write_run_artifact(runs_dir, "create_first_live_local_chain", payload)
    return {**payload, "artifact_path": str(artifact_path)}
