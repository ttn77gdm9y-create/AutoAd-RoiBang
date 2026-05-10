from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


PLACEHOLDER_IDS = {
    "target-advertiser-id",
    "target-advertiser-id-2",
    "source-advertiser-id",
    "material-id",
    "video-id",
}


def _rows(value: Any) -> list[dict[str, Any]]:
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def _text(value: Any) -> str:
    return str(value or "").strip()


def _int_value(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _float_value(value: Any, default: float = 0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _policy_section(policy: dict[str, Any]) -> dict[str, Any]:
    value = policy.get("create_plan")
    if isinstance(value, dict):
        return dict(value)
    fallback = policy.get("create_strategy_plan")
    result = dict(fallback) if isinstance(fallback, dict) else {}
    preflight = policy.get("create_preflight")
    if isinstance(preflight, dict):
        if "min_daily_budget" not in result:
            result["min_daily_budget"] = preflight.get("min_daily_budget")
        if "max_daily_budget" not in result:
            result["max_daily_budget"] = preflight.get("max_daily_budget")
    return result


def _limit(policy: dict[str, Any], key: str, default: int) -> int:
    return max(_int_value(_policy_section(policy).get(key), default), 0)


def _budget_limit(policy: dict[str, Any], key: str, default: float) -> float:
    return max(_float_value(_policy_section(policy).get(key), default), 0)


def _contains_placeholder(value: Any) -> bool:
    text = _text(value)
    return text in PLACEHOLDER_IDS or text.endswith(".example.json")


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ? LIMIT 1",
        (table,),
    ).fetchone()
    return row is not None


def _first_existing_table(conn: sqlite3.Connection, names: list[str]) -> str:
    for name in names:
        if _table_exists(conn, name):
            return name
    return ""


def _account_exists(conn: sqlite3.Connection, advertiser_id: str) -> bool:
    table = _first_existing_table(conn, ["account_pool", "accounts"])
    if not table:
        return False
    row = conn.execute(
        f"SELECT 1 FROM {table} WHERE advertiser_id = ? LIMIT 1",
        (advertiser_id,),
    ).fetchone()
    return row is not None


def _material_exists(conn: sqlite3.Connection, *, plan: dict[str, Any], material: dict[str, Any]) -> bool:
    product = _text(plan.get("product"))
    source_advertiser_id = _text(plan.get("source_advertiser_id"))
    material_id = _text(material.get("source_material_id") or material.get("material_id"))
    source_video_id = _text(material.get("source_video_id") or material.get("video_id"))
    if _table_exists(conn, "product_source_materials"):
        row = conn.execute(
            """
            SELECT 1
            FROM product_source_materials
            WHERE product = ?
              AND source_advertiser_id = ?
              AND material_id = ?
              AND (? = '' OR video_id = ?)
            LIMIT 1
            """,
            (product, source_advertiser_id, material_id, source_video_id, source_video_id),
        ).fetchone()
        if row is not None:
            return True
    for table in ["materials", "material_profiles"]:
        if not _table_exists(conn, table):
            continue
        row = conn.execute(
            f"SELECT 1 FROM {table} WHERE material_id = ? LIMIT 1",
            (material_id,),
        ).fetchone()
        if row is not None:
            return True
    return False


def _field_violations(plan: dict[str, Any], policy: dict[str, Any]) -> list[str]:
    violations: list[str] = []
    required_text_fields = ["plan_id", "product", "platform", "source_advertiser_id", "reason"]
    for field in required_text_fields:
        if not _text(plan.get(field)):
            violations.append(f"{field} is required")
        elif _contains_placeholder(plan.get(field)):
            violations.append(f"{field} contains placeholder id")

    accounts = _rows(plan.get("target_accounts"))
    materials = _rows(plan.get("materials"))
    if not accounts:
        violations.append("target_accounts requires at least one item")
    if not materials:
        violations.append("materials requires at least one item")

    max_accounts = _limit(policy, "max_target_accounts", 20)
    max_projects = _limit(policy, "max_projects_per_account", 10)
    max_units = _limit(policy, "max_units_per_project", 20)
    max_materials = _limit(policy, "max_materials", 50)
    min_budget = _budget_limit(policy, "min_daily_budget", 0)
    max_budget = _budget_limit(policy, "max_daily_budget", 100000000)
    if len(accounts) > max_accounts:
        violations.append("target_accounts exceeds max_target_accounts")
    if len(materials) > max_materials:
        violations.append("materials exceeds max_materials")

    for index, account in enumerate(accounts):
        prefix = f"target_accounts[{index}]"
        advertiser_id = _text(account.get("advertiser_id"))
        project_count = _int_value(account.get("project_count"), 0)
        unit_count = _int_value(account.get("unit_count_per_project", account.get("units_per_project")), 0)
        daily_budget = _float_value(account.get("daily_budget"), 0)
        if not advertiser_id:
            violations.append(f"{prefix}.advertiser_id is required")
        elif _contains_placeholder(advertiser_id):
            violations.append(f"{prefix}.advertiser_id contains placeholder id")
        if project_count <= 0:
            violations.append(f"{prefix}.project_count must be positive")
        elif project_count > max_projects:
            violations.append(f"{prefix}.project_count exceeds max_projects_per_account")
        if unit_count <= 0:
            violations.append(f"{prefix}.unit_count_per_project must be positive")
        elif unit_count > max_units:
            violations.append(f"{prefix}.unit_count_per_project exceeds max_units_per_project")
        if daily_budget < min_budget:
            violations.append(f"{prefix}.daily_budget below min_daily_budget")
        if daily_budget > max_budget:
            violations.append(f"{prefix}.daily_budget exceeds max_daily_budget")

    for index, material in enumerate(materials):
        prefix = f"materials[{index}]"
        material_id = _text(material.get("source_material_id") or material.get("material_id"))
        video_id = _text(material.get("source_video_id") or material.get("video_id"))
        if not material_id:
            violations.append(f"{prefix}.source_material_id is required")
        elif _contains_placeholder(material_id):
            violations.append(f"{prefix}.source_material_id contains placeholder id")
        if not video_id:
            violations.append(f"{prefix}.source_video_id is required")
        elif _contains_placeholder(video_id):
            violations.append(f"{prefix}.source_video_id contains placeholder id")
    return violations


def _summary(plan: dict[str, Any]) -> dict[str, Any]:
    accounts = _rows(plan.get("target_accounts"))
    materials = _rows(plan.get("materials"))
    project_count = sum(_int_value(row.get("project_count"), 0) for row in accounts)
    unit_count = sum(
        _int_value(row.get("project_count"), 0)
        * _int_value(row.get("unit_count_per_project", row.get("units_per_project")), 0)
        for row in accounts
    )
    return {
        "plan_id": _text(plan.get("plan_id")),
        "target_account_count": len(accounts),
        "project_count": project_count,
        "unit_count": unit_count,
        "material_count": len(materials),
    }


def _source_contract(plan: dict[str, Any], *, db_path: str | Path | None) -> dict[str, Any]:
    if db_path is None:
        return {
            "checked": False,
            "target_accounts_in_sqlite": False,
            "materials_in_sqlite": False,
            "missing_target_accounts": [],
            "missing_materials": [],
        }
    path = Path(db_path)
    if not path.exists():
        return {
            "checked": False,
            "target_accounts_in_sqlite": False,
            "materials_in_sqlite": False,
            "missing_target_accounts": [],
            "missing_materials": [],
            "reason": "database_not_found",
        }
    missing_accounts: list[str] = []
    missing_materials: list[str] = []
    with sqlite3.connect(path) as conn:
        for account in _rows(plan.get("target_accounts")):
            advertiser_id = _text(account.get("advertiser_id"))
            if advertiser_id and not _account_exists(conn, advertiser_id):
                missing_accounts.append(advertiser_id)
        for material in _rows(plan.get("materials")):
            material_id = _text(material.get("source_material_id") or material.get("material_id"))
            if material_id and not _material_exists(conn, plan=plan, material=material):
                missing_materials.append(material_id)
    return {
        "checked": True,
        "target_accounts_in_sqlite": not missing_accounts,
        "materials_in_sqlite": not missing_materials,
        "missing_target_accounts": missing_accounts,
        "missing_materials": missing_materials,
    }


def validate_create_plan(
    plan: dict[str, Any],
    *,
    policy: dict[str, Any] | None = None,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    policy = policy or {}
    violations = _field_violations(plan, policy)
    source_contract = _source_contract(plan, db_path=db_path)
    for advertiser_id in source_contract.get("missing_target_accounts") or []:
        violations.append(f"target account not found in SQLite: {advertiser_id}")
    for material_id in source_contract.get("missing_materials") or []:
        violations.append(f"source material not found in SQLite: {material_id}")
    ok = not violations
    return {
        "ok": ok,
        "workflow": "create_plan_validate",
        "phase": "phase2_preparation",
        "execution_enabled": False,
        "external_api_calls": 0,
        "status": "passed" if ok else "blocked",
        "summary": _summary(plan),
        "source_contract": source_contract,
        "violations": violations,
        "actions": [],
    }
