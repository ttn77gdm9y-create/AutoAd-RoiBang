from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from roibang_v2.runs import write_run_artifact
from roibang_v2.workflows.create_phase2_yzt_dry_chain import run_create_phase2_yzt_dry_chain_request
from roibang_v2.workflows.create_phase2_yzt_preparation_check import build_create_phase2_yzt_preparation_check


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
            "复核通过后再生成 approve 批准记录；approve 仍不是执行开关。",
        ]
    rows: list[str] = []
    rows.extend(str(item) for item in preparation.get("violations") or [])
    rows.extend(str(item) for item in dry_chain.get("violations") or [])
    rows.extend(str(item) for item in scope_guard.get("violations") or [])
    return rows or ["修复首单本地链路失败项后重新运行固定脚本。"]


def build_create_first_live_local_chain(
    *,
    preview_config: dict[str, Any],
    policy: dict[str, Any],
    db_path: str | Path,
    runs_dir: str | Path,
    preview_config_path: str,
) -> dict[str, Any]:
    first_live_preview_config = derive_first_live_preview_config(preview_config=preview_config, policy=policy)
    preparation = build_create_phase2_yzt_preparation_check(
        preview_config=first_live_preview_config,
        policy=policy,
        db_path=db_path,
        preview_config_path=preview_config_path,
    )
    dry_chain: dict[str, Any] = {}
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
    scope_guard = _scope_guard(dry_chain=dry_chain, policy=policy)
    ok = bool(preparation.get("ok")) and bool(dry_chain.get("ok")) and bool(scope_guard.get("ok"))
    payload = {
        "ok": ok,
        "workflow": "create_first_live_local_chain",
        "phase": "phase2_preparation",
        "execution_enabled": False,
        "external_api_calls": 0,
        "status": "ready_for_approval_chain" if ok else "blocked",
        "summary": {
            "selected_account_count": len(_accounts(first_live_preview_config)),
            "project_count": int(scope_guard.get("project_count") or 0),
            "unit_count": int(scope_guard.get("unit_count") or 0),
            "material_count": int(scope_guard.get("material_count") or 0),
            "ready_for_approval_chain": ok,
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
        ],
        "artifacts": {
            "dry_chain": str(dry_chain.get("artifact_path") or ""),
        },
        "preparation_check": preparation,
        "dry_chain": dry_chain,
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
        policy=cfg.get("policy") if isinstance(cfg.get("policy"), dict) else {},
        db_path=db_path,
        runs_dir=runs_dir,
        preview_config_path=str(cfg.get("preview_config_path") or "configs/create/yzt-wx-mini-game.preview.example.json"),
    )
    artifact_path = write_run_artifact(runs_dir, "create_first_live_local_chain", payload)
    return {**payload, "artifact_path": str(artifact_path)}
