from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ScriptResult:
    ok: bool
    return_code: int
    command: list[str]
    stdout: str
    stderr: str
    parsed_stdout: dict[str, Any]


def _python() -> str:
    return sys.executable or "python3"


def _split_accounts(raw: str) -> list[str]:
    accounts: list[str] = []
    for part in str(raw or "").replace("\n", ",").split(","):
        value = part.strip()
        if value:
            accounts.append(value)
    return accounts


def build_delivery_patrol_command(*, readonly: bool = True) -> list[str]:
    command = [
        _python(),
        "scripts/run_delivery_patrol.py",
        "--config",
        "configs/runtime.openapi-execute.local.example.json" if readonly else "configs/runtime.example.json",
        "--request",
        "configs/delivery-patrol.daily-readonly.example.json" if readonly else "configs/delivery-patrol.example.json",
    ]
    if readonly:
        command.append("--enable-readonly")
    return command


def build_ai_template_drafts_command() -> list[str]:
    return [
        _python(),
        "scripts/run_ai_create_template_drafts.py",
        "--config",
        "configs/runtime.example.json",
        "--request",
        "configs/ai-create-template-drafts/example.json",
    ]


def build_product_config_publish_command(*, draft_path: str, replace: bool = False) -> list[str]:
    command = [
        _python(),
        "scripts/run_product_config_publish.py",
        "--draft",
        draft_path.strip(),
        "--products-dir",
        "configs/products",
        "--runs-dir",
        "data/runs",
    ]
    if replace:
        command.append("--replace")
    return command


def build_account_remark_config_command(
    *,
    update_id: str,
    remark: str,
    accounts: str,
    output_path: str,
) -> list[str]:
    command = [
        _python(),
        "scripts/run_account_remark_update_config.py",
        "--update-id",
        update_id.strip(),
        "--remark",
        remark.strip(),
        "--output",
        output_path.strip(),
    ]
    for account in _split_accounts(accounts):
        command.extend(["--account", account])
    return command


def build_account_remark_execute_command(*, account_remark_update_path: str, execute: bool = False) -> list[str]:
    command = [
        _python(),
        "scripts/run_account_remark_update.py",
        "--account-remark-update",
        account_remark_update_path.strip(),
        "--config",
        "configs/project-update-execute.local.json",
    ]
    if execute:
        command.extend(["--execute", "--yes"])
    return command


def build_create_plan_command(
    *,
    mode: str,
    accounts: str,
    owner: str,
    target_date: str = "",
    product_key: str = "",
    template_catalog: str = "",
    cpa_bid: str = "",
    roi_coefficient: str = "",
) -> list[str]:
    account_ids = _split_accounts(accounts)
    if not account_ids:
        raise ValueError("生成创建计划需要至少填写一个账户 ID。")
    command = [
        _python(),
        "scripts/run_create_mode.py",
        "--config",
        "configs/runtime.example.json",
        "--mode",
        mode.strip(),
        "--owner",
        owner.strip() or "郭靖",
        "--policy",
        "policies/create-policy.example.json",
    ]
    if product_key.strip():
        command.extend(["--product-key", product_key.strip()])
    if template_catalog.strip():
        command.extend(["--template-catalog", template_catalog.strip()])
    if target_date.strip():
        command.extend(["--target-date", target_date.strip()])
    if cpa_bid.strip():
        command.extend(["--cpa-bid", cpa_bid.strip()])
    if roi_coefficient.strip():
        command.extend(["--roi-coefficient", roi_coefficient.strip()])
    for account in account_ids:
        command.extend(["--account", account])
    return command


def build_create_live_terminal_command(
    *,
    plan_path: str,
    check_config_only: bool = True,
    open_progress_window: bool = False,
) -> list[str]:
    command = [
        _python(),
        "scripts/run_create_live_execute_terminal.py",
        "--plan",
        plan_path.strip(),
        "--config",
        "configs/runtime.create-live.local.json",
        "--policy",
        "policies/create-live-execute.local.json",
    ]
    if check_config_only:
        command.append("--check-config-only")
    if open_progress_window and not check_config_only:
        command.append("--open-progress-window")
    return command


def build_create_live_config_check_command(*, plan_path: str) -> list[str]:
    return [
        _python(),
        "scripts/run_create_live_execute_once.py",
        "--plan",
        plan_path.strip(),
        "--config",
        "configs/runtime.create-live.local.json",
        "--policy",
        "policies/create-live-execute.local.json",
        "--check-config-only",
    ]


def build_project_update_execute_command(*, project_update_path: str, execute: bool = False) -> list[str]:
    command = [
        _python(),
        "scripts/run_project_update_execute.py",
        "--project-update",
        project_update_path.strip(),
        "--config",
        "configs/project-update-execute.local.json",
    ]
    if execute:
        command.extend(["--execute", "--yes"])
    return command


def build_project_filter_command(
    *,
    project_update_id: str,
    advertiser_id: str = "",
    advertiser_ids: str = "",
    action_type: str,
    name_contains: str,
    spend_window: str,
    metric_field: str,
    metric_op: str,
    metric_value: str,
    output_path: str,
    opt_status: str = "",
    budget: str = "",
    cpa_bid: str = "",
    roi_goal: str = "",
) -> list[str]:
    command = [
        _python(),
        "scripts/run_project_realtime_filter_config.py",
        "--config",
        "configs/project-update-execute.local.json",
        "--project-update-id",
        project_update_id.strip(),
        "--action-type",
        action_type.strip(),
        "--spend-window",
        spend_window.strip(),
        "--metric-filter",
        f"{metric_field.strip()}:{metric_op.strip()}:{metric_value.strip()}",
        "--output",
        output_path.strip(),
    ]
    for account in _split_accounts(advertiser_ids or advertiser_id):
        command.extend(["--advertiser-id", account])
    if name_contains.strip():
        command.extend(["--name-contains", name_contains.strip()])
    if opt_status.strip():
        command.extend(["--opt-status", opt_status.strip()])
    if budget.strip():
        command.extend(["--budget", budget.strip()])
    if cpa_bid.strip():
        command.extend(["--cpa-bid", cpa_bid.strip()])
    if roi_goal.strip():
        command.extend(["--roi-goal", roi_goal.strip()])
    return command


def run_fixed_script(command: list[str], *, cwd: str | Path, timeout_seconds: int = 900) -> ScriptResult:
    completed = subprocess.run(
        command,
        cwd=str(cwd),
        text=True,
        capture_output=True,
        timeout=timeout_seconds,
        check=False,
    )
    parsed: dict[str, Any] = {}
    try:
        value = json.loads(completed.stdout)
        if isinstance(value, dict):
            parsed = value
    except json.JSONDecodeError:
        parsed = {}
    return ScriptResult(
        ok=completed.returncode == 0,
        return_code=int(completed.returncode),
        command=command,
        stdout=completed.stdout,
        stderr=completed.stderr,
        parsed_stdout=parsed,
    )
