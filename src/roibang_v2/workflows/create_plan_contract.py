from __future__ import annotations

import csv
import json
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


def _bool_value(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    text = _text(value).lower()
    if not text:
        return default
    return text in {"1", "true", "yes", "y", "enabled", "enable", "启用", "是"}


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


def _policy_path(policy: dict[str, Any], key: str) -> str:
    return _text(_policy_section(policy).get(key))


def _channel_matches(plan_platform: str, row_channel: str) -> bool:
    if not row_channel:
        return True
    platform = plan_platform.strip().lower()
    channel = row_channel.strip().lower()
    wx_platforms = {"wechat_game", "wx-mini-game", "wx", "weixin", "微信小游戏", "微小"}
    wx_channels = {"wx", "wechat", "weixin", "微信", "微小", "wechat_game", "wx-mini-game"}
    if platform in wx_platforms:
        return channel in wx_channels
    return channel == platform


def _first_text(row: dict[str, Any], keys: list[str]) -> str:
    for key in keys:
        value = _text(row.get(key))
        if value:
            return value
    return ""


def _normalize_allowed_account(row: dict[str, Any]) -> dict[str, Any]:
    advertiser_id = _first_text(row, ["advertiser_id", "account_id", "账户id", "账户ID", "账户 id"])
    return {
        "advertiser_id": advertiser_id,
        "account_name": _first_text(row, ["account_name", "账户名", "name"]),
        "product": _first_text(row, ["product", "产品"]),
        "channel": _first_text(row, ["channel", "渠道"]),
        "enable": _bool_value(row.get("enable", row.get("enabled", row.get("启用"))), True),
    }


def _json_rows(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        for key in ["allowed_target_accounts", "accounts", "rows"]:
            rows = data.get(key)
            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, dict)]
    return []


def _read_allowed_accounts(path: Path) -> list[dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix == ".json":
        return [_normalize_allowed_account(row) for row in _json_rows(json.loads(path.read_text(encoding="utf-8")))]
    delimiter = "\t" if suffix in {".tsv", ".txt"} else ","
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [_normalize_allowed_account(row) for row in csv.DictReader(handle, delimiter=delimiter)]


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


def _allowed_account_contract(plan: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    section = _policy_section(policy)
    required = _bool_value(section.get("require_allowed_target_accounts"), False)
    path_text = _policy_path(policy, "allowed_target_accounts_path")
    if not path_text:
        return {
            "checked": False,
            "required": required,
            "allowed_target_accounts_path": "",
            "allowed_target_account_count": 0,
            "missing_allowed_target_accounts": [],
            "disabled_target_accounts": [],
            "product_mismatch_target_accounts": [],
            "channel_mismatch_target_accounts": [],
            "reason": "allowed_target_accounts_path_not_configured" if required else "",
        }
    path = Path(path_text)
    if not path.exists():
        return {
            "checked": False,
            "required": required,
            "allowed_target_accounts_path": path_text,
            "allowed_target_account_count": 0,
            "missing_allowed_target_accounts": [],
            "disabled_target_accounts": [],
            "product_mismatch_target_accounts": [],
            "channel_mismatch_target_accounts": [],
            "reason": "allowed_target_accounts_path_not_found",
        }
    rows = _read_allowed_accounts(path)
    by_id = {row["advertiser_id"]: row for row in rows if row.get("advertiser_id")}
    plan_product = _text(plan.get("product"))
    plan_platform = _text(plan.get("platform"))
    missing: list[str] = []
    disabled: list[str] = []
    product_mismatch: list[str] = []
    channel_mismatch: list[str] = []
    for account in _rows(plan.get("target_accounts")):
        advertiser_id = _text(account.get("advertiser_id"))
        if not advertiser_id:
            continue
        allowed = by_id.get(advertiser_id)
        if allowed is None:
            missing.append(advertiser_id)
            continue
        if not bool(allowed.get("enable", False)):
            disabled.append(advertiser_id)
        allowed_product = _text(allowed.get("product"))
        if allowed_product and plan_product and allowed_product != plan_product:
            product_mismatch.append(advertiser_id)
        if not _channel_matches(plan_platform, _text(allowed.get("channel"))):
            channel_mismatch.append(advertiser_id)
    return {
        "checked": True,
        "required": required,
        "allowed_target_accounts_path": path_text,
        "allowed_target_account_count": len(by_id),
        "missing_allowed_target_accounts": missing,
        "disabled_target_accounts": disabled,
        "product_mismatch_target_accounts": product_mismatch,
        "channel_mismatch_target_accounts": channel_mismatch,
    }


def _field_violations(plan: dict[str, Any], policy: dict[str, Any]) -> list[str]:
    violations: list[str] = []
    required_text_fields = ["plan_id", "product", "platform", "source_advertiser_id", "reason"]
    for field in required_text_fields:
        if not _text(plan.get(field)):
            violations.append(f"{field} is required")
        elif _contains_placeholder(plan.get(field)):
            violations.append(f"{field} contains placeholder id")
    launch_mode = _text(plan.get("launch_mode"))
    if launch_mode != "create_only":
        violations.append("launch_mode must be create_only")

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
        "launch_mode": _text(plan.get("launch_mode")),
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
    allowed_account_contract = _allowed_account_contract(plan, policy)
    for advertiser_id in source_contract.get("missing_target_accounts") or []:
        violations.append(f"target account not found in SQLite: {advertiser_id}")
    for material_id in source_contract.get("missing_materials") or []:
        violations.append(f"source material not found in SQLite: {material_id}")
    if allowed_account_contract.get("required") and not allowed_account_contract.get("checked"):
        violations.append(
            "allowed_target_accounts_path is required for create_plan target account allowlist"
        )
    for advertiser_id in allowed_account_contract.get("missing_allowed_target_accounts") or []:
        violations.append(f"target account not in allowed create account list: {advertiser_id}")
    for advertiser_id in allowed_account_contract.get("disabled_target_accounts") or []:
        violations.append(f"target account is disabled in allowed create account list: {advertiser_id}")
    for advertiser_id in allowed_account_contract.get("product_mismatch_target_accounts") or []:
        violations.append(f"target account product does not match create_plan.product: {advertiser_id}")
    for advertiser_id in allowed_account_contract.get("channel_mismatch_target_accounts") or []:
        violations.append(f"target account channel does not match create_plan.platform: {advertiser_id}")
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
        "allowed_account_contract": allowed_account_contract,
        "violations": violations,
        "actions": [],
    }
