from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path
from typing import Any

from roibang_v2.runs import write_run_artifact


def _rows(value: Any) -> list[dict[str, Any]]:
    return [dict(item) for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _json_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [dict(item) for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ["allowed_target_accounts", "accounts", "rows"]:
            value = payload.get(key)
            if isinstance(value, list):
                return [dict(item) for item in value if isinstance(item, dict)]
    return []


def _text(value: Any) -> str:
    return str(value or "").strip()


def _enabled(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "enabled"}


def _first_text(row: dict[str, Any], keys: list[str]) -> str:
    for key in keys:
        value = _text(row.get(key))
        if value:
            return value
    return ""


def _normalize_allowed_account(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "advertiser_id": _first_text(row, ["advertiser_id", "account_id", "账户id", "账户ID", "账户 id"]),
        "account_name": _first_text(row, ["account_name", "账户名", "name"]),
        "product": _first_text(row, ["product", "产品"]),
        "channel": _first_text(row, ["channel", "渠道"]),
        "enable": _enabled(row.get("enable", row.get("enabled", row.get("启用", True)))),
    }


def _read_allowed_accounts(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".json":
        return [_normalize_allowed_account(row) for row in _json_rows(json.loads(path.read_text(encoding="utf-8")))]
    delimiter = "\t" if path.suffix.lower() in {".tsv", ".txt"} else ","
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [_normalize_allowed_account(row) for row in csv.DictReader(handle, delimiter=delimiter)]


def _allowed_account_contract(project_update: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    path_text = _text(project_update.get("allowed_target_accounts_path"))
    action_accounts = sorted({_text(action.get("advertiser_id")) for action in _rows(project_update.get("actions")) if _text(action.get("advertiser_id"))})
    if not path_text:
        return (
            {
                "checked": False,
                "allowed_target_accounts_path": "",
                "allowed_target_account_count": 0,
                "missing_allowed_target_accounts": action_accounts,
                "disabled_target_accounts": [],
                "reason": "allowed_target_accounts_path_not_configured",
            },
            [f"target account is not in allowlist: {advertiser_id}" for advertiser_id in action_accounts],
        )
    path = Path(path_text)
    if not path.exists():
        return (
            {
                "checked": False,
                "allowed_target_accounts_path": path_text,
                "allowed_target_account_count": 0,
                "missing_allowed_target_accounts": action_accounts,
                "disabled_target_accounts": [],
                "reason": "allowed_target_accounts_path_not_found",
            },
            [f"target account is not in allowlist: {advertiser_id}" for advertiser_id in action_accounts],
        )
    accounts = _read_allowed_accounts(path)
    by_id = {account["advertiser_id"]: account for account in accounts if account.get("advertiser_id")}
    missing: list[str] = []
    disabled: list[str] = []
    violations: list[str] = []
    for advertiser_id in action_accounts:
        account = by_id.get(advertiser_id)
        if account is None:
            missing.append(advertiser_id)
            violations.append(f"target account is not in allowlist: {advertiser_id}")
        elif not account.get("enable", False):
            disabled.append(advertiser_id)
            violations.append(f"target account is disabled in allowlist: {advertiser_id}")
    return (
        {
            "checked": True,
            "allowed_target_accounts_path": path_text,
            "allowed_target_account_count": len(by_id),
            "missing_allowed_target_accounts": missing,
            "disabled_target_accounts": disabled,
        },
        violations,
    )


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ? LIMIT 1",
        (table,),
    ).fetchone()
    return row is not None


def _project_exists(conn: sqlite3.Connection, *, advertiser_id: str, project_id: str) -> bool:
    checks = [
        (
            "project_hourly_metrics",
            "SELECT 1 FROM project_hourly_metrics WHERE advertiser_id = ? AND project_id = ? LIMIT 1",
        ),
        (
            "material_daily_metrics",
            "SELECT 1 FROM material_daily_metrics WHERE advertiser_id = ? AND project_id = ? LIMIT 1",
        ),
        (
            "projects",
            "SELECT 1 FROM projects WHERE advertiser_id = ? AND project_id = ? LIMIT 1",
        ),
    ]
    for table, sql in checks:
        if _table_exists(conn, table) and conn.execute(sql, (advertiser_id, project_id)).fetchone() is not None:
            return True
    return False


def _valid_hours(hours: Any) -> bool:
    if not isinstance(hours, list) or not hours:
        return False
    normalized: list[int] = []
    for hour in hours:
        if isinstance(hour, bool):
            return False
        try:
            value = int(hour)
        except (TypeError, ValueError):
            return False
        normalized.append(value)
    return all(0 <= hour <= 23 for hour in normalized) and len(set(normalized)) == len(normalized)


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _project_key(advertiser_id: str, project_id: str) -> str:
    return f"{advertiser_id}/{project_id}"


def _restore_key(action: dict[str, Any]) -> tuple[str, str, str]:
    return (_text(action.get("advertiser_id")), _text(action.get("project_id")), _text(action.get("restore_date")))


def _action_key(action: dict[str, Any]) -> str:
    return f"{_text(action.get('advertiser_id'))}/{_text(action.get('project_id'))}"


def _validate_management_action(action: dict[str, Any]) -> list[str]:
    action_type = _text(action.get("action_type"))
    advertiser_id = _text(action.get("advertiser_id"))
    project_id = _text(action.get("project_id"))
    key = _project_key(advertiser_id, project_id)
    violations: list[str] = []
    if _text(action.get("entity_type") or "project") != "project" or not advertiser_id or not project_id:
        return [f"invalid project update action: {key}"]
    if action_type == "status_update":
        if _text(action.get("opt_status")) not in {"ENABLE", "DISABLE"}:
            violations.append(f"status_update opt_status must be ENABLE or DISABLE: {key}")
    elif action_type == "budget_update":
        budget_mode = _text(action.get("budget_mode"))
        if budget_mode not in {"BUDGET_MODE_DAY", "BUDGET_MODE_INFINITE"}:
            violations.append(f"budget_update budget_mode must be BUDGET_MODE_DAY or BUDGET_MODE_INFINITE: {key}")
        if budget_mode == "BUDGET_MODE_DAY":
            budget = _number(action.get("budget"))
            if budget is None:
                violations.append(f"budget_update requires budget when budget_mode is BUDGET_MODE_DAY: {key}")
            elif budget <= 0:
                violations.append(f"budget_update budget must be greater than 0: {key}")
    elif action_type == "bid_update":
        cpa_bid = _number(action.get("cpa_bid"))
        if cpa_bid is None or cpa_bid <= 0:
            violations.append(f"bid_update cpa_bid must be greater than 0: {key}")
    elif action_type == "roi_coeff_update":
        roi_goal = _number(action.get("roi_goal"))
        if roi_goal is None or roi_goal < 0.01 or roi_goal > 5:
            violations.append(f"roi_coeff_update roi_goal must be between 0.01 and 5: {key}")
    else:
        violations.append(f"invalid project update action: {key}")
    return violations


def _planned_management_change(action: dict[str, Any]) -> dict[str, Any]:
    action_type = _text(action.get("action_type"))
    change = {
        "action_type": action_type,
        "advertiser_id": _text(action.get("advertiser_id")),
        "project_id": _text(action.get("project_id")),
    }
    if action_type == "status_update":
        change["opt_status"] = _text(action.get("opt_status"))
    elif action_type == "budget_update":
        change["budget_mode"] = _text(action.get("budget_mode"))
        if _text(action.get("budget")):
            change["budget"] = action.get("budget")
    elif action_type == "bid_update":
        change["cpa_bid"] = action.get("cpa_bid")
    elif action_type == "roi_coeff_update":
        change["roi_goal"] = action.get("roi_goal")
    return change


def build_project_update_preflight(project_update: dict[str, Any], *, db_path: str | Path) -> dict[str, Any]:
    actions = _rows(project_update.get("actions"))
    restore_actions = _rows(project_update.get("restore_actions"))
    restore_keys = {
        (
            _text(action.get("advertiser_id")),
            _text(action.get("project_id")),
            _text(action.get("restore_date")),
        )
        for action in restore_actions
        if action.get("action_type") == "schedule_restore"
    }
    allowed_contract, violations = _allowed_account_contract(project_update)
    invalid_action_count = 0
    management_action_count = 0
    missing_restore_count = 0
    missing_project_count = 0
    planned_changes: list[dict[str, Any]] = []

    db_file = Path(db_path)
    conn: sqlite3.Connection | None = None
    if db_file.exists():
        conn = sqlite3.connect(db_file)
        conn.row_factory = sqlite3.Row
    else:
        violations.append(f"db_path not found: {db_file}")

    try:
        for action in actions:
            action_type = _text(action.get("action_type"))
            advertiser_id = _text(action.get("advertiser_id"))
            project_id = _text(action.get("project_id"))
            if action_type in {"status_update", "budget_update", "bid_update", "roi_coeff_update"}:
                management_action_count += 1
                action_violations = _validate_management_action(action)
                if action_violations:
                    invalid_action_count += 1
                    violations.extend(action_violations)
                planned_changes.append(_planned_management_change(action))
                continue
            if action_type != "schedule_hollow" or _text(action.get("entity_type")) != "project" or not advertiser_id or not project_id:
                invalid_action_count += 1
                violations.append(f"invalid project update action: {_action_key(action)}")
                continue
            if not _valid_hours(action.get("hollow_hours")):
                invalid_action_count += 1
                violations.append(f"hollow_hours must be unique hours from 0 to 23: {_action_key(action)}")
            if not bool(action.get("preserve_original_schedule_required", False)):
                invalid_action_count += 1
                violations.append(f"schedule_hollow action must preserve original schedule: {_action_key(action)}")
            if not bool(action.get("restore_required", False)) or _restore_key(action) not in restore_keys:
                missing_restore_count += 1
                violations.append(f"schedule_hollow action requires a matching restore action: {_action_key(action)}")
            if conn is None or not _project_exists(conn, advertiser_id=advertiser_id, project_id=project_id):
                missing_project_count += 1
                violations.append(f"project is not present in local metrics or project table: {_action_key(action)}")
            planned_changes.append(
                {
                    "action_type": action_type,
                    "advertiser_id": advertiser_id,
                    "project_id": project_id,
                    "target_date": _text(action.get("target_date")),
                    "hollow_hours": [int(hour) for hour in action.get("hollow_hours") or [] if str(hour).strip().lstrip("-").isdigit()],
                    "restore_date": _text(action.get("restore_date")),
                }
            )
    finally:
        if conn is not None:
            conn.close()

    status = "passed" if not violations else "failed"
    project_ids = {_text(action.get("project_id")) for action in actions if _text(action.get("project_id"))}
    account_ids = {_text(action.get("advertiser_id")) for action in actions if _text(action.get("advertiser_id"))}
    return {
        "ok": not violations,
        "workflow": "project_update_preflight",
        "phase": "control_preflight",
        "status": status,
        "execution_enabled": False,
        "external_api_calls": 0,
        "project_update_path": "",
        "summary": {
            "project_update_id": _text(project_update.get("project_update_id")),
            "action_count": len(actions),
            "restore_action_count": len(restore_actions),
            "target_account_count": len(account_ids),
            "project_count": len(project_ids),
            "management_action_count": management_action_count,
            "missing_allowed_account_count": len(allowed_contract.get("missing_allowed_target_accounts") or []),
            "disabled_allowed_account_count": len(allowed_contract.get("disabled_target_accounts") or []),
            "missing_restore_count": missing_restore_count,
            "invalid_action_count": invalid_action_count,
            "missing_project_count": missing_project_count,
        },
        "checks": {
            "allowed_account_contract": allowed_contract,
            "restore_action_contract": {"required": True, "checked": True},
            "project_presence_contract": {"checked": db_file.exists(), "db_path": str(db_file)},
        },
        "violations": violations,
        "planned_changes": planned_changes,
    }


def run_project_update_preflight_request(
    request: dict[str, Any] | None,
    *,
    runs_dir: str | Path,
) -> dict[str, Any]:
    cfg = dict(request or {})
    project_update = cfg.get("project_update")
    path_text = _text(cfg.get("project_update_path"))
    if not isinstance(project_update, dict):
        if not path_text:
            raise ValueError("project update preflight requires project_update or project_update_path")
        path = Path(path_text)
        if not path.exists():
            raise ValueError(f"project_update_path not found: {path}")
        project_update = json.loads(path.read_text(encoding="utf-8"))
        path_text = str(path)
    db_path = _text(cfg.get("db_path") or "data/roibang_v2.sqlite3")
    payload = build_project_update_preflight(project_update, db_path=db_path)
    payload["project_update_path"] = path_text
    payload["artifact_path"] = str(write_run_artifact(runs_dir, "project_update_preflight", payload))
    return payload
