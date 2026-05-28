from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.app.services.accounts_store import load_accounts
from backend.app.services.artifacts import read_json


def load_account_name_map(configs_dir: str | Path) -> dict[str, str]:
    configs_path = Path(configs_dir)
    names: dict[str, str] = {}
    for account in load_accounts(configs_path):
        _put_account_name(names, account.get("advertiser_id"), account.get("advertiser_name"))

    for path in [
        configs_path / "control-allowed-accounts.local.json",
        configs_path / "control-allowed-accounts.example.json",
    ]:
        _collect_account_names(read_json(path), names)
    return names


def account_name_for(account_names: dict[str, str], advertiser_id: Any, fallback: str = "未配置账户名") -> str:
    account_id = str(advertiser_id or "").strip()
    if not account_id:
        return ""
    return account_names.get(account_id, fallback)


def _collect_account_names(value: Any, names: dict[str, str]) -> None:
    if isinstance(value, list):
        for item in value:
            _collect_account_names(item, names)
        return
    if not isinstance(value, dict):
        return

    advertiser_id = _first_text(value, ["advertiser_id", "account_id", "operator", "target_advertiser_id"])
    account_name = _first_text(value, ["advertiser_name", "account_name", "accountName", "name"])
    _put_account_name(names, advertiser_id, account_name)
    for child in value.values():
        _collect_account_names(child, names)


def _put_account_name(names: dict[str, str], advertiser_id: Any, account_name: Any) -> None:
    account_id = str(advertiser_id or "").strip()
    name = str(account_name or "").strip()
    if account_id and name and name != account_id:
        names.setdefault(account_id, name)


def _first_text(value: dict[str, Any], keys: list[str]) -> str:
    for key in keys:
        text = str(value.get(key) or "").strip()
        if text:
            return text
    return ""
