from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from roibang_v2.config import load_json
from roibang_v2.runs import write_run_artifact


WORKFLOW = "product_automation_job"
SUPPORTED_JOBS = {
    "material_daily_sync",
    "operation_log_sync",
    "daily_report_sync",
    "source_material_auto_push",
    "source_material_preload",
    "delivery_patrol",
}


@dataclass(frozen=True)
class ProductJobCommand:
    product_key: str
    product: str
    job: str
    request_path: str
    command: list[str]


def _text(value: Any) -> str:
    return str(value or "").strip()


def _bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _date_value(value: str, *, today: date | None = None) -> str:
    text = _text(value)
    if text and text not in {"today", "yesterday"}:
        return text
    base = today or date.today()
    if text == "yesterday":
        return date.fromordinal(base.toordinal() - 1).isoformat()
    return base.isoformat()


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def workflow_for_job(job: str) -> str:
    if job not in SUPPORTED_JOBS:
        raise ValueError(f"unsupported product automation job: {job}")
    return f"{WORKFLOW}_{job}"


def _automation(product: dict[str, Any]) -> dict[str, Any]:
    value = product.get("automation")
    return dict(value) if isinstance(value, dict) else {}


def _job_config(product: dict[str, Any], job: str) -> dict[str, Any]:
    value = _automation(product).get(job)
    return dict(value) if isinstance(value, dict) else {}


def _account_discovery(product: dict[str, Any]) -> dict[str, Any]:
    automation = _automation(product)
    value = automation.get("account_discovery")
    return dict(value) if isinstance(value, dict) else {}


def _account_keyword(product: dict[str, Any]) -> str:
    discovery = _account_discovery(product)
    return (
        _text(discovery.get("account_name_keyword"))
        or _text(product.get("account_name_keyword"))
        or _text(product.get("product"))
    )


def _account_remark(product: dict[str, Any]) -> str:
    discovery = _account_discovery(product)
    return _text(discovery.get("account_remark_equals")) or _text(product.get("account_remark_pattern"))


def _enabled_for_job(product: dict[str, Any], job: str) -> bool:
    automation = _automation(product)
    if not _bool(automation.get("enabled"), True):
        return False
    job_cfg = _job_config(product, job)
    return _bool(job_cfg.get("enabled"), False)


def load_product_configs(products_dir: str | Path, *, product_key: str = "") -> list[dict[str, Any]]:
    directory = Path(products_dir)
    if not directory.exists():
        return []
    candidates = sorted([*directory.glob("*.local.json"), *directory.glob("*.json"), *directory.glob("*.example.json")])
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for path in candidates:
        try:
            product = load_json(path)
        except (FileNotFoundError, json.JSONDecodeError, ValueError):
            continue
        key = _text(product.get("product_key") or path.stem.replace(".local", "").replace(".example", ""))
        if product_key and key != product_key:
            continue
        if key in seen:
            continue
        product["product_key"] = key
        product["_config_path"] = str(path)
        rows.append(product)
        seen.add(key)
    return rows


def _allowed_accounts(path_text: str) -> list[dict[str, str]]:
    if not _text(path_text):
        return []
    path = Path(path_text)
    if not path.exists():
        return []
    payload = load_json(path)
    rows = payload.get("allowed_target_accounts") if isinstance(payload.get("allowed_target_accounts"), list) else []
    accounts: list[dict[str, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        enabled = _bool(row.get("enable", row.get("enabled", True)), True)
        advertiser_id = _text(row.get("advertiser_id"))
        if enabled and advertiser_id:
            accounts.append(
                {
                    "advertiser_id": advertiser_id,
                    "account_name": _text(row.get("account_name")),
                    "account_remark": _text(row.get("account_remark")),
                }
            )
    return accounts


def build_product_job_request(product: dict[str, Any], job: str, *, target_date: str = "yesterday") -> dict[str, Any]:
    if job not in SUPPORTED_JOBS:
        raise ValueError(f"unsupported product automation job: {job}")
    product_name = _text(product.get("product"))
    product_key = _text(product.get("product_key"))
    platform = _text(product.get("platform") or "WECHAT_GAME")
    source_advertiser_id = _text(product.get("source_advertiser_id"))
    organization_id = _text(product.get("organization_id"))
    keyword = _account_keyword(product)
    remark = _account_remark(product)
    target = target_date if target_date in {"today", "yesterday"} else _date_value(target_date)

    if job == "material_daily_sync":
        return {
            "material_history_backfill": {
                "product": product_name,
                "platforms": [platform],
                "date_range": {"mode": target} if target in {"today", "yesterday"} else {"start": target, "end": target},
                "active_account_discovery": {
                    "enabled": True,
                    "source": "workbench_account_list",
                    "allow_keyword_accounts": True,
                    "product": product_name,
                    "platform": platform,
                    "min_spend": 0,
                    "workbench": {
                        "enabled": True,
                        "organization_id": organization_id,
                        "keyword": keyword,
                        "limit": 100,
                        "max_pages": 20,
                        "stop_when_sorted_cost_reaches_zero": True,
                        "session_file": "data/secrets/oceanengine-workbench-session.local.json",
                        "timeout_seconds": 20,
                        "max_retries": 3,
                        "retry_sleep_seconds": 5,
                        "retry_statuses": [429, 500, 502, 503, 504],
                        "response_audit_dir": f"data/runs/workbench_account_discovery/{product_key}-material-history",
                    },
                },
                "material_fetch": {
                    "source": "openapi_http_execute",
                    "openapi": {"endpoints": ["report_custom"], "report_presets": ["material_daily"], "page_size": 20},
                    "openapi_http": {
                        "enabled": False,
                        "token_store": {
                            "enabled": True,
                            "store_file": "data/secrets/oceanengine-tokens.local.json",
                            "user_id": "default",
                            "auto_refresh": True,
                            "refresh_lead_seconds": 900,
                            "credentials_file": "data/secrets/oceanengine-app.local.json",
                        },
                        "timeout_seconds": 20,
                        "max_retries": 3,
                        "retry_api_codes": [40100, 50000],
                        "max_api_retries": 3,
                        "retry_sleep_seconds": 3,
                        "min_interval_seconds": 0.2,
                        "retry_statuses": [429, 500, 502, 503, 504],
                        "response_audit_dir": f"data/runs/openapi_http/{product_key}-material-history",
                    },
                    "execution": {"status": "planned_only", "external_api_enabled": False},
                },
            }
        }

    if job == "source_material_auto_push":
        auto_push_cfg = _job_config(product, job)
        return {
            "source_material_account_auto_push": {
                "product": product_name,
                "source_advertiser_id": source_advertiser_id,
                "organization_id": organization_id,
                "timezone": "Asia/Shanghai",
                "date_range": {"mode": target} if target in {"today", "yesterday"} else {"start": target, "end": target},
                "source_account_sync": {
                    "enabled": True,
                    "page_size": 100,
                    "max_pages": 80,
                    "mark_absent_inactive": False,
                    "retry_api_codes": [40100, 51010],
                    "max_api_retries": 2,
                    "retry_sleep_seconds": 10,
                },
                "material_source": {
                    "from": "material_daily_metrics",
                    "account_name_keyword": keyword,
                    "min_stat_cost": 0,
                    "max_materials": int(auto_push_cfg.get("max_materials") or 500),
                    "max_video_ids_per_call": 50,
                },
                "material_detail_fetch": {
                    "enabled": True,
                    "page_size": 100,
                    "max_pages": 1,
                    "retry_api_codes": [40100, 51010],
                    "max_api_retries": 2,
                    "retry_sleep_seconds": 10,
                },
                "openapi_http": _readonly_http(f"{product_key}-source-material-account-auto-push"),
                "execute": _mutation_execute(f"{product_key}-source-material-account-auto-push"),
                "verify_after_execute": {"enabled": True},
            }
        }

    if job == "operation_log_sync":
        return {
            "operation_log_history_sync": {
                "product_keyword": product_name,
                "operation_log_page_size": 20,
                "date_range": {"mode": target} if target in {"today", "yesterday"} else {"start": target, "end": target},
                "window_days": 3,
                "row_sample_limit": 20,
                "openapi_http": _readonly_http(f"{product_key}-operation-log-daily"),
                "execution": {"status": "planned_only", "external_api_enabled": False},
            }
        }

    if job == "daily_report_sync":
        return {
            "daily_report_pipeline": {
                "target_date": {"mode": target} if target in {"today", "yesterday"} else {"date": target},
                "catch_up": {"enabled": False, "source_table": "metric_snapshots", "max_days": 1},
                "active_account_discovery": {
                    "enabled": True,
                    "source": "workbench_account_list",
                    "min_spend": 0,
                    "fallback_to_openapi": True,
                    "openapi": {"page_size": 100},
                    "workbench": {
                        "enabled": True,
                        "organization_id": organization_id,
                        "session_file": "data/secrets/oceanengine-workbench-session.local.json",
                        "keyword": keyword,
                        "limit": 100,
                        "max_pages": 20,
                        "stop_when_sorted_cost_reaches_zero": True,
                        "timeout_seconds": 20,
                        "max_retries": 2,
                        "retry_sleep_seconds": 1,
                        "retry_statuses": [429, 500, 502, 503, 504],
                        "response_audit_dir": f"data/runs/workbench_account_discovery/{product_key}-daily-report",
                    },
                },
                "report_fetch": {
                    "source": "openapi_http_execute",
                    "account_pool_csv": "",
                    "product": product_name,
                    "platforms": [platform],
                    "openapi": {
                        "endpoints": ["report_custom", "project_list", "promotion_list", "operation_log_search"],
                        "report_presets": ["promotion_daily"],
                        "page_size": 100,
                    },
                    "openapi_http": _readonly_http(f"{product_key}-daily-report"),
                    "output": {"snapshot_dir": f"data/snapshots/report/{product_key}-daily"},
                    "execution": {"status": "planned_only", "external_api_enabled": False},
                },
                "daily_learning": {
                    "min_cost_for_signal": 50,
                    "min_conversions_for_signal": 3,
                    "low_roi_threshold": 0.4,
                    "top_material_limit": 10,
                    "operation_log_limit": 20,
                },
            }
        }

    if job == "source_material_preload":
        preload_cfg = _job_config(product, job)
        target_scope = _text(preload_cfg.get("target_scope") or "allowed_accounts")
        target_accounts: dict[str, Any]
        if target_scope == "allowed_accounts":
            target_accounts = {"accounts": _allowed_accounts(_text(product.get("allowed_target_accounts_path")))}
        else:
            target_accounts = {
                "source": "delivery_patrol_artifact",
                "artifact_path": "data/runs/delivery_patrol/latest.json",
                "account_remark_equals": remark,
                "spend_window": "today" if target_scope == "today_spent" else "yesterday",
                "min_spend": 0,
            }
        return {
            "source_material_preload_to_accounts": {
                "product": product_name,
                "source_advertiser_id": source_advertiser_id,
                "organization_id": organization_id,
                "target_date": _date_value(target_date),
                "target_accounts": target_accounts,
                "material_source": {"material_type": "video", "limit": 0, "max_bind_materials": 0, "batch_size": 50},
                "execute": _mutation_execute(f"{product_key}-source-material-preload-to-accounts", concurrency=3),
            }
        }

    return {
        "delivery_patrol": {
            "product_keyword": product_name,
            "allowed_target_accounts_path": _text(product.get("allowed_target_accounts_path")),
            "account_scope": {"source": "workbench_account_list", "account_remark_equals": remark, "min_spend": 0},
            "active_account_discovery": {
                "enabled": True,
                "source": "workbench_account_list",
                "min_spend": 0,
                "workbench": {
                    "enabled": True,
                    "organization_id": organization_id,
                    "session_file": "data/secrets/oceanengine-workbench-session.local.json",
                    "keyword": keyword,
                    "limit": 100,
                    "max_pages": 20,
                    "stop_when_sorted_cost_reaches_zero": True,
                    "timeout_seconds": 20,
                    "max_retries": 2,
                    "retry_sleep_seconds": 1,
                    "retry_statuses": [429, 500, 502, 503, 504],
                    "response_audit_dir": f"data/runs/workbench_account_discovery/{product_key}-delivery-patrol",
                },
            },
            "page_size": 100,
            "execution": {"status": "execute", "external_api_enabled": True},
            "delivery": {"feishu": {"enabled": True, "runtime_file": "data/secrets/feishu.runtime.local.json"}},
            "suggestions": {
                "enabled": True,
                "request_path": "configs/delivery-patrol-suggestions.example.json",
                "db_path": "data/roibang_v2.sqlite3",
            },
            "openapi_http": _readonly_http(f"{product_key}-delivery-patrol"),
        }
    }


def _readonly_http(name: str) -> dict[str, Any]:
    return {
        "enabled": True,
        "token_store": {
            "enabled": True,
            "store_file": "data/secrets/oceanengine-tokens.local.json",
            "user_id": "default",
            "credentials_file": "data/secrets/oceanengine-app.local.json",
            "auto_refresh": True,
            "refresh_lead_seconds": 900,
        },
        "timeout_seconds": 20,
        "max_retries": 2,
        "retry_api_codes": [40100, 400308, 51010, 50000],
        "max_api_retries": 2,
        "retry_sleep_seconds": 1,
        "min_interval_seconds": 0.2,
        "retry_statuses": [429, 500, 502, 503, 504],
        "response_audit_dir": f"data/runs/openapi_http/{name}",
    }


def _mutation_execute(run_id: str, *, concurrency: int = 1) -> dict[str, Any]:
    return {
        "enabled": False,
        "approved": False,
        "allow_mutation": False,
        "retry_api_codes": [40100, 51010],
        "max_api_retries": 2,
        "retry_sleep_seconds": 10,
        "concurrency": concurrency,
        "create_http_transport": {
            "enabled": True,
            "allow_mutation": True,
            "run_id": run_id,
            "operator": "roibang-v2-product-automation",
            "token_store": {
                "enabled": True,
                "store_file": "data/secrets/oceanengine-tokens.local.json",
                "user_id": "default",
                "credentials_file": "data/secrets/oceanengine-app.local.json",
                "auto_refresh": True,
                "refresh_lead_seconds": 900,
            },
            "timeout_seconds": 20,
            "max_retries": 1,
            "retry_sleep_seconds": 1,
            "retry_transient_operations": ["bind_material"],
            "min_interval_seconds_by_operation": {"bind_material": 0.2},
            "retry_api_codes_by_operation": {"bind_material": [40100, 51010]},
            "base_url": "https://api.oceanengine.com",
        },
    }


def write_product_job_request(
    product: dict[str, Any],
    job: str,
    *,
    output_dir: str | Path,
    target_date: str,
) -> Path:
    key = _text(product.get("product_key"))
    request = build_product_job_request(product, job, target_date=target_date)
    path = Path(output_dir) / f"{_timestamp()}-{key}-{job}.local.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(request, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def build_product_job_command(
    *,
    job: str,
    request_path: str,
    enable_readonly: bool = False,
    execute: bool = False,
    yes: bool = False,
) -> list[str]:
    python = sys.executable or "python3"
    if job == "material_daily_sync":
        command = [
            python,
            "scripts/run_material_history_backfill.py",
            "--config",
            "configs/runtime.openapi-execute.local.example.json",
            "--request",
            request_path,
        ]
        if enable_readonly:
            command.append("--enable-readonly")
        return command
    if job == "operation_log_sync":
        command = [
            python,
            "scripts/run_control_operation_log_history_sync.py",
            "--config",
            "configs/runtime.openapi-execute.local.example.json",
            "--request",
            request_path,
        ]
        if enable_readonly:
            command.append("--enable-readonly")
        return command
    if job == "daily_report_sync":
        command = [
            python,
            "scripts/run_daily_report_pipeline.py",
            "--config",
            "configs/runtime.openapi-execute.local.example.json",
            "--request",
            request_path,
        ]
        if enable_readonly:
            command.append("--enable-readonly")
        return command
    if job == "source_material_auto_push":
        command = [
            python,
            "scripts/run_source_material_account_auto_push.py",
            "--config",
            "configs/runtime.openapi-execute.local.example.json",
            "--request",
            request_path,
            "--enable-readonly",
        ]
    elif job == "source_material_preload":
        command = [
            python,
            "scripts/run_source_material_preload_to_accounts.py",
            "--config",
            "configs/runtime.openapi-execute.local.example.json",
            "--request",
            request_path,
        ]
    elif job == "delivery_patrol":
        command = [
            python,
            "scripts/run_delivery_patrol.py",
            "--config",
            "configs/runtime.openapi-execute.local.example.json",
            "--request",
            request_path,
            "--enable-readonly",
        ]
    else:
        raise ValueError(f"unsupported product automation job: {job}")
    if job in {"source_material_auto_push", "source_material_preload"} and execute:
        command.append("--execute")
    if job in {"source_material_auto_push", "source_material_preload"} and yes:
        command.append("--yes")
    return command


def build_product_job_commands(
    *,
    job: str,
    products_dir: str | Path,
    request_dir: str | Path,
    product_key: str = "",
    target_date: str = "yesterday",
    enable_readonly: bool = False,
    execute: bool = False,
    yes: bool = False,
) -> list[ProductJobCommand]:
    products = [
        product
        for product in load_product_configs(products_dir, product_key=product_key)
        if _enabled_for_job(product, job)
    ]
    commands: list[ProductJobCommand] = []
    for product in products:
        request_path = write_product_job_request(product, job, output_dir=request_dir, target_date=target_date)
        command = build_product_job_command(
            job=job,
            request_path=str(request_path),
            enable_readonly=enable_readonly,
            execute=execute,
            yes=yes,
        )
        commands.append(
            ProductJobCommand(
                product_key=_text(product.get("product_key")),
                product=_text(product.get("product")),
                job=job,
                request_path=str(request_path),
                command=command,
            )
        )
    return commands


def run_product_automation_job(
    *,
    job: str,
    products_dir: str | Path = "configs/products",
    request_dir: str | Path = "data/requests/product-automation",
    runs_dir: str | Path = "data/runs",
    product_key: str = "",
    target_date: str = "yesterday",
    enable_readonly: bool = False,
    execute: bool = False,
    yes: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    commands = build_product_job_commands(
        job=job,
        products_dir=products_dir,
        request_dir=request_dir,
        product_key=product_key,
        target_date=target_date,
        enable_readonly=enable_readonly,
        execute=execute,
        yes=yes,
    )
    results: list[dict[str, Any]] = []
    for item in commands:
        result: dict[str, Any] = {
            "product_key": item.product_key,
            "product": item.product,
            "job": item.job,
            "request_path": item.request_path,
            "command": item.command,
        }
        if not dry_run:
            completed = subprocess.run(item.command, text=True, capture_output=True, check=False)
            parsed: dict[str, Any] = {}
            try:
                parsed = json.loads(completed.stdout)
            except json.JSONDecodeError:
                parsed = {}
            result.update(
                {
                    "return_code": completed.returncode,
                    "ok": completed.returncode == 0,
                    "stdout": completed.stdout,
                    "stderr": completed.stderr,
                    "parsed_stdout": parsed,
                }
            )
        results.append(result)
    workflow = workflow_for_job(job)
    payload = {
        "ok": all(bool(item.get("ok", True)) for item in results),
        "workflow": workflow,
        "phase": "product_automation",
        "execution_enabled": bool(execute),
        "external_api_calls": sum(int(item.get("parsed_stdout", {}).get("external_api_calls") or 0) for item in results),
        "status": "dry_run" if dry_run else "completed",
        "summary": {
            "job": job,
            "product_count": len(results),
            "target_date": target_date,
            "execute": bool(execute),
            "dry_run": bool(dry_run),
        },
        "blocking_reasons": [],
        "results": results,
    }
    artifact = write_run_artifact(runs_dir, workflow, payload)
    return {**payload, "artifact_path": str(artifact)}
