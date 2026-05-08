from __future__ import annotations

from copy import deepcopy
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from roibang_v2.accounts.pool import import_accounts_csv, select_accounts
from roibang_v2.fetch.workbench_account_discovery import WorkbenchOpener
from roibang_v2.fetch.workbench_account_discovery import discover_spending_accounts
from roibang_v2.runs import write_run_artifact


def _workflow_config(request: dict[str, Any]) -> dict[str, Any]:
    value = request.get("workbench_account_discovery")
    return dict(value) if isinstance(value, dict) else dict(request)


def _target_date(cfg: dict[str, Any], *, today: date | None = None) -> str:
    value = cfg.get("target_date")
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, dict) and str(value.get("mode") or "") == "yesterday":
        base = today or date.today()
        return (base - timedelta(days=1)).isoformat()
    if isinstance(value, dict) and value.get("date"):
        return str(value["date"])
    raise ValueError("workbench_account_discovery requires target_date or target_date.mode=yesterday")


def _number(value: Any) -> float:
    try:
        return float(str(value or "0").replace(",", "").replace("%", ""))
    except ValueError:
        return 0.0


def _configured_accounts(cfg: dict[str, Any], *, db_path: str | Path) -> list[dict[str, Any]]:
    account_pool_csv = cfg.get("account_pool_csv")
    if account_pool_csv:
        import_accounts_csv(account_pool_csv, db_path=db_path)
    platforms = [str(item) for item in cfg.get("platforms", [])]
    accounts = select_accounts(db_path=db_path, product=str(cfg["product"]), platforms=platforms)
    account_ids = [str(item) for item in cfg.get("account_ids", [])] if isinstance(cfg.get("account_ids"), list) else []
    if account_ids:
        by_id = {account["advertiser_id"]: account for account in accounts}
        accounts = [by_id[item] for item in account_ids if item in by_id]
    return accounts


def build_workbench_account_discovery_preflight(
    request: dict[str, Any],
    *,
    db_path: str | Path,
    runs_dir: str | Path,
    today: date | None = None,
) -> dict[str, Any]:
    cfg = _workflow_config(request)
    target_date = _target_date(cfg, today=today)
    accounts = _configured_accounts(cfg, db_path=db_path)
    workbench = cfg.get("workbench") if isinstance(cfg.get("workbench"), dict) else {}
    limit = int(workbench.get("limit") or 100)
    planned_request_count = (len(accounts) + limit - 1) // limit if accounts else 0
    payload = {
        "ok": True,
        "workflow": "workbench_account_discovery_preflight",
        "phase": "phase1",
        "execution_enabled": False,
        "external_api_calls": 0,
        "summary": {
            "target_date": target_date,
            "candidate_account_count": len(accounts),
            "planned_request_count": planned_request_count,
            "min_spend": _number(cfg.get("min_spend")),
            "source": "workbench_account_list",
        },
    }
    artifact = write_run_artifact(runs_dir, "workbench_account_discovery_preflight", payload)
    return {**payload, "artifact_path": str(artifact)}


def run_workbench_account_discovery_request(
    request: dict[str, Any],
    *,
    db_path: str | Path,
    runs_dir: str | Path,
    today: date | None = None,
    opener: WorkbenchOpener | None = None,
) -> dict[str, Any]:
    cfg = _workflow_config(request)
    target_date = _target_date(cfg, today=today)
    accounts = _configured_accounts(cfg, db_path=db_path)
    workbench = deepcopy(cfg.get("workbench") if isinstance(cfg.get("workbench"), dict) else {})
    workbench["allowed_account_ids"] = [str(account["advertiser_id"]) for account in accounts]
    discovery = discover_spending_accounts(
        workbench,
        target_date=target_date,
        min_spend=_number(cfg.get("min_spend")),
        opener=opener,
    )
    payload = {
        "ok": True,
        "workflow": "workbench_account_discovery",
        "phase": "phase1",
        "execution_enabled": False,
        "external_api_calls": int(discovery.get("external_api_calls") or 0),
        "summary": discovery["summary"],
        "active_account_ids": discovery["active_account_ids"],
        "accounts": discovery["accounts"],
    }
    artifact = write_run_artifact(runs_dir, "workbench_account_discovery", payload)
    return {**payload, "artifact_path": str(artifact)}
