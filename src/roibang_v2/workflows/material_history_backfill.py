from __future__ import annotations

import json
import sqlite3
from copy import deepcopy
from datetime import date, timedelta
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from roibang_v2.accounts.pool import import_accounts_csv
from roibang_v2.accounts.pool import select_accounts
from roibang_v2.fetch.openapi_executor import Transport
from roibang_v2.fetch.openapi_executor import execute_openapi_readonly_plan
from roibang_v2.fetch.openapi_http import build_http_transport
from roibang_v2.fetch.openapi_readonly import build_openapi_readonly_plan
from roibang_v2.fetch.workbench_account_discovery import WorkbenchOpener
from roibang_v2.fetch.workbench_account_discovery import Sleeper as WorkbenchSleeper
from roibang_v2.fetch.workbench_account_discovery import discover_spending_accounts
from roibang_v2.runs import write_run_artifact


def _config(request: dict[str, Any]) -> dict[str, Any]:
    value = request.get("material_history_backfill")
    return dict(value) if isinstance(value, dict) else dict(request)


def _date_range(start_date: str, end_date: str) -> list[str]:
    start = date.fromisoformat(str(start_date))
    end = date.fromisoformat(str(end_date))
    if end < start:
        raise ValueError("date_range.end must be greater than or equal to date_range.start")
    days: list[str] = []
    current = start
    while current <= end:
        days.append(current.isoformat())
        current += timedelta(days=1)
    return days


def _date_range_config(cfg: dict[str, Any]) -> dict[str, str]:
    value = cfg.get("date_range") if isinstance(cfg.get("date_range"), dict) else {}
    if str(value.get("mode") or "").strip() == "yesterday":
        base_date_text = str(value.get("base_date") or "").strip()
        base = date.fromisoformat(base_date_text) if base_date_text else date.today()
        target = (base - timedelta(days=1)).isoformat()
        return {"start": target, "end": target}
    start = str(value.get("start") or "").strip()
    end = str(value.get("end") or "").strip()
    if not start or not end:
        raise ValueError("material_history_backfill requires date_range.start and date_range.end")
    return {"start": start, "end": end}


def _platforms(cfg: dict[str, Any]) -> list[str]:
    return [str(item) for item in cfg.get("platforms", []) if str(item)]


def _accounts(cfg: dict[str, Any], *, db_path: str | Path) -> list[dict[str, Any]]:
    if cfg.get("account_pool_csv"):
        import_accounts_csv(cfg["account_pool_csv"], db_path=db_path)
    product = str(cfg.get("product") or "").strip()
    if not product:
        raise ValueError("material_history_backfill requires product")
    accounts = select_accounts(db_path=db_path, product=product, platforms=_platforms(cfg))
    account_ids = [str(item) for item in cfg.get("account_ids", []) if str(item)]
    if account_ids:
        by_id = {account["advertiser_id"]: account for account in accounts}
        accounts = [by_id[item] for item in account_ids if item in by_id]
    limits = cfg.get("limits") if isinstance(cfg.get("limits"), dict) else {}
    if limits.get("max_accounts"):
        accounts = accounts[: int(limits["max_accounts"])]
    return accounts


def _discovery_config(cfg: dict[str, Any]) -> dict[str, Any]:
    value = cfg.get("active_account_discovery")
    return dict(value) if isinstance(value, dict) else {}


def _material_fetch_config(cfg: dict[str, Any]) -> dict[str, Any]:
    value = cfg.get("material_fetch")
    if not isinstance(value, dict):
        value = {}
    material_fetch = deepcopy(value)
    openapi = deepcopy(material_fetch.get("openapi") if isinstance(material_fetch.get("openapi"), dict) else {})
    openapi.setdefault("endpoints", ["report_custom"])
    openapi.setdefault("report_presets", ["material_daily"])
    openapi.setdefault("page_size", 20)
    material_fetch["openapi"] = openapi
    return material_fetch


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _number(value: Any) -> float:
    if isinstance(value, int | float):
        return float(value)
    try:
        return float(str(value or "0").replace(",", "").replace("%", "").strip() or "0")
    except ValueError:
        return 0.0


def _section(row: dict[str, Any], key: str) -> dict[str, Any]:
    value = row.get(key)
    return value if isinstance(value, dict) else {}


def _first_text(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _metric(metrics: dict[str, Any], row: dict[str, Any], *keys: str) -> float:
    for key in keys:
        if key in metrics:
            return _number(metrics.get(key))
        if key in row:
            return _number(row.get(key))
    return 0.0


def _request_account_id(request: dict[str, Any]) -> str:
    account = request.get("account") if isinstance(request.get("account"), dict) else {}
    query_params = request.get("query_params") if isinstance(request.get("query_params"), dict) else {}
    return _first_text(account.get("advertiser_id"), query_params.get("advertiser_id"))


def _row_payload(row: dict[str, Any], request: dict[str, Any]) -> str:
    return json.dumps(
        {
            "request": {
                "date": request.get("date"),
                "endpoint_key": request.get("endpoint_key"),
                "report_preset": request.get("report_preset"),
                "account": request.get("account") if isinstance(request.get("account"), dict) else {},
            },
            "row": row,
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def _workbench_discovery_request_count(
    *,
    account_count: int,
    date_count: int,
    discovery: dict[str, Any],
) -> int:
    workbench = discovery.get("workbench") if isinstance(discovery.get("workbench"), dict) else {}
    limit = int(workbench.get("limit") or 100)
    if limit < 1:
        raise ValueError("active_account_discovery.workbench.limit must be greater than 0")
    per_day = (account_count + limit - 1) // limit if account_count else 0
    return per_day * date_count


def _discovery_plan(
    *,
    accounts: list[dict[str, Any]],
    dates: list[str],
    discovery: dict[str, Any],
    platforms: list[str],
) -> dict[str, Any]:
    source = str(discovery.get("source") or "workbench_account_list")
    if source == "workbench_account_list":
        request_count = _workbench_discovery_request_count(
            account_count=len(accounts),
            date_count=len(dates),
            discovery=discovery,
        )
        return {
            "summary": {
                "source": source,
                "date_count": len(dates),
                "candidate_account_count": len(accounts),
                "planned_request_count": request_count,
                "external_api_calls": 0,
            },
            "endpoints": ["workbench_account_list"],
            "report_presets": ["account_spend_sorted"],
        }
    if source not in {"openapi_account_daily", "openapi"}:
        raise ValueError(f"unsupported active_account_discovery.source: {source}")
    plan = build_openapi_readonly_plan(
        accounts=accounts,
        dates=dates,
        endpoints=["report_custom"],
        report_presets=["account_daily"],
        platforms=platforms,
        page_size=100,
    )
    return {
        "summary": {
            "source": source,
            "date_count": len(dates),
            "candidate_account_count": len(accounts),
            "planned_request_count": int(plan["summary"]["planned_request_count"]),
            "external_api_calls": 0,
        },
        "endpoints": plan["endpoints"],
        "report_presets": plan["report_presets"],
    }


def _detail_plan(
    *,
    accounts: list[dict[str, Any]],
    dates: list[str],
    material_fetch: dict[str, Any],
    platforms: list[str],
) -> dict[str, Any]:
    openapi = material_fetch["openapi"]
    plan = build_openapi_readonly_plan(
        accounts=accounts,
        dates=dates,
        endpoints=[str(item) for item in openapi.get("endpoints", [])],
        report_presets=[str(item) for item in openapi.get("report_presets", [])],
        platforms=platforms,
        page_size=int(openapi.get("page_size") or 20),
    )
    return {
        "summary": plan["summary"],
        "endpoints": plan["endpoints"],
        "report_presets": plan["report_presets"],
    }


def build_material_history_backfill_preflight(
    request: dict[str, Any],
    *,
    db_path: str | Path,
    runs_dir: str | Path,
) -> dict[str, Any]:
    cfg = _config(request)
    date_range = _date_range_config(cfg)
    dates = _date_range(date_range["start"], date_range["end"])
    platforms = _platforms(cfg)
    accounts = _accounts(cfg, db_path=db_path)
    discovery = _discovery_config(cfg)
    discovery_source = str(discovery.get("source") or "workbench_account_list")
    discovery_plan = _discovery_plan(
        accounts=accounts,
        dates=dates,
        discovery=discovery,
        platforms=platforms,
    )
    material_fetch = _material_fetch_config(cfg)
    detail_plan = _detail_plan(
        accounts=accounts,
        dates=dates,
        material_fetch=material_fetch,
        platforms=platforms,
    )
    discovery_request_count = int(discovery_plan["summary"]["planned_request_count"])
    detail_request_count = int(detail_plan["summary"]["planned_request_count"])
    payload = {
        "ok": True,
        "workflow": "material_history_backfill_preflight",
        "phase": "phase1",
        "execution_enabled": False,
        "external_api_calls": 0,
        "summary": {
            "product": str(cfg.get("product") or ""),
            "platforms": platforms,
            "date_count": len(dates),
            "candidate_account_count": len(accounts),
            "discovery_source": discovery_source,
            "discovery_planned_request_count": discovery_request_count,
            "material_detail_worst_case_account_count": len(accounts),
            "material_detail_initial_request_count": detail_request_count,
            "estimated_total_initial_request_count": discovery_request_count + detail_request_count,
        },
        "date_range": {
            "start": date_range["start"],
            "end": date_range["end"],
            "dates": dates,
        },
        "accounts": accounts,
        "discovery_plan": discovery_plan,
        "detail_plan": detail_plan,
        "guardrails": [
            "Preflight only; no external API calls are made.",
            "Legacy RoiBang material data is not imported into RoiBang-v2.",
            "Material supply strategy stays disabled until complete daily material metrics exist.",
        ],
    }
    artifact = write_run_artifact(runs_dir, "material_history_backfill_preflight", payload)
    return {**payload, "artifact_path": str(artifact)}


def import_material_daily_execution(
    execution: dict[str, Any],
    *,
    db_path: str | Path,
    source: str,
) -> dict[str, int]:
    rows_seen = 0
    rows_imported = 0
    rows_skipped_zero_cost = 0
    rows_skipped_invalid = 0
    synced_at = _utc_now()
    with sqlite3.connect(db_path) as conn:
        for item in execution.get("responses") or []:
            if not isinstance(item, dict):
                continue
            request = item.get("request") if isinstance(item.get("request"), dict) else {}
            if request.get("endpoint_key") != "report_custom" or request.get("report_preset") != "material_daily":
                continue
            advertiser_id = _request_account_id(request)
            request_date = str(request.get("date") or "")
            for row in item.get("rows") or []:
                if not isinstance(row, dict):
                    continue
                rows_seen += 1
                dimensions = _section(row, "dimensions")
                metrics = _section(row, "metrics")
                metric_date = _first_text(
                    dimensions.get("stat_time_day"),
                    dimensions.get("stat_time"),
                    row.get("stat_time_day"),
                    row.get("stat_time"),
                    request_date,
                )
                material_id = _first_text(
                    dimensions.get("material_id"),
                    dimensions.get("video_material_id"),
                    row.get("material_id"),
                    row.get("video_material_id"),
                )
                if not metric_date or not advertiser_id or not material_id:
                    rows_skipped_invalid += 1
                    continue
                stat_cost = _metric(metrics, row, "stat_cost")
                if stat_cost <= 0:
                    rows_skipped_zero_cost += 1
                    continue
                project_id = _first_text(dimensions.get("cdp_project_id"), dimensions.get("project_id"), row.get("project_id"))
                project_name = _first_text(
                    dimensions.get("cdp_project_name"),
                    dimensions.get("project_name"),
                    row.get("project_name"),
                )
                promotion_id = _first_text(
                    dimensions.get("cdp_promotion_id"),
                    dimensions.get("promotion_id"),
                    row.get("promotion_id"),
                )
                promotion_name = _first_text(
                    dimensions.get("cdp_promotion_name"),
                    dimensions.get("promotion_name"),
                    row.get("promotion_name"),
                )
                material_kind = _first_text(
                    dimensions.get("material_kind"),
                    dimensions.get("material_type"),
                    row.get("material_kind"),
                    "unknown",
                )
                conn.execute(
                    """
                    INSERT INTO material_daily_metrics (
                      metric_date,
                      advertiser_id,
                      project_id,
                      project_name,
                      promotion_id,
                      promotion_name,
                      material_id,
                      material_kind,
                      stat_cost,
                      show_cnt,
                      click_cnt,
                      convert_cnt,
                      active_register,
                      roi_1day,
                      roi_7days,
                      metric_payload_json,
                      source,
                      synced_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(metric_date, advertiser_id, project_id, promotion_id, material_id)
                    DO UPDATE SET
                      project_name=excluded.project_name,
                      promotion_name=excluded.promotion_name,
                      material_kind=excluded.material_kind,
                      stat_cost=excluded.stat_cost,
                      show_cnt=excluded.show_cnt,
                      click_cnt=excluded.click_cnt,
                      convert_cnt=excluded.convert_cnt,
                      active_register=excluded.active_register,
                      roi_1day=excluded.roi_1day,
                      roi_7days=excluded.roi_7days,
                      metric_payload_json=excluded.metric_payload_json,
                      source=excluded.source,
                      synced_at=excluded.synced_at
                    """,
                    (
                        metric_date,
                        advertiser_id,
                        project_id,
                        project_name,
                        promotion_id,
                        promotion_name,
                        material_id,
                        material_kind,
                        stat_cost,
                        _metric(metrics, row, "show_cnt"),
                        _metric(metrics, row, "click_cnt"),
                        _metric(metrics, row, "convert_cnt"),
                        _metric(metrics, row, "active_register"),
                        _metric(metrics, row, "roi_1day", "attribution_billing_game_in_app_roi_1day"),
                        _metric(metrics, row, "roi_7days", "attribution_billing_game_in_app_roi_7days"),
                        _row_payload(row, request),
                        source,
                        synced_at,
                    ),
                )
                rows_imported += 1
    return {
        "rows_seen": rows_seen,
        "rows_imported": rows_imported,
        "rows_skipped_zero_cost": rows_skipped_zero_cost,
        "rows_skipped_invalid": rows_skipped_invalid,
    }


def _workbench_config(discovery: dict[str, Any], accounts: list[dict[str, Any]]) -> dict[str, Any]:
    workbench = deepcopy(discovery.get("workbench") if isinstance(discovery.get("workbench"), dict) else {})
    workbench.setdefault("enabled", bool(discovery.get("enabled", False)))
    if workbench.get("organization_id") and not workbench.get("ebpid"):
        workbench["ebpid"] = str(workbench["organization_id"])
    workbench["allowed_account_ids"] = [str(account["advertiser_id"]) for account in accounts]
    return workbench


def _discover_active_accounts_by_date(
    *,
    accounts: list[dict[str, Any]],
    dates: list[str],
    discovery: dict[str, Any],
    workbench_opener: WorkbenchOpener | None,
    workbench_sleeper: WorkbenchSleeper | None,
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    source = str(discovery.get("source") or "workbench_account_list")
    if source != "workbench_account_list":
        raise ValueError(f"material history execution only supports workbench_account_list discovery, got: {source}")
    workbench = _workbench_config(discovery, accounts)
    min_spend = float(discovery.get("min_spend") or 0)
    account_by_id = {str(account["advertiser_id"]): account for account in accounts}
    active_by_date: dict[str, list[dict[str, Any]]] = {}
    summaries: list[dict[str, Any]] = []
    readonly_calls = 0
    for target_date in dates:
        result = discover_spending_accounts(
            workbench,
            target_date=target_date,
            min_spend=min_spend,
            opener=workbench_opener,
            sleeper=workbench_sleeper,
        )
        readonly_calls += int(result.get("external_api_calls") or 0)
        active_accounts: list[dict[str, Any]] = []
        for advertiser_id in result.get("active_account_ids") or []:
            account = account_by_id.get(str(advertiser_id))
            if account is not None:
                active_accounts.append(account)
        active_by_date[target_date] = active_accounts
        summaries.append(dict(result.get("summary") or {}))
    return active_by_date, {
        "source": source,
        "readonly_request_calls": readonly_calls,
        "daily_summaries": summaries,
    }


def _detail_plan_for_active_accounts(
    *,
    active_by_date: dict[str, list[dict[str, Any]]],
    material_fetch: dict[str, Any],
    platforms: list[str],
) -> dict[str, Any]:
    openapi = material_fetch["openapi"]
    requests: list[dict[str, Any]] = []
    for target_date, accounts in active_by_date.items():
        day_plan = build_openapi_readonly_plan(
            accounts=accounts,
            dates=[target_date],
            endpoints=[str(item) for item in openapi.get("endpoints", [])],
            report_presets=[str(item) for item in openapi.get("report_presets", [])],
            platforms=platforms,
            page_size=int(openapi.get("page_size") or 20),
        )
        requests.extend(day_plan.get("requests") or [])
    return {
        "ok": True,
        "workflow": "openapi_readonly_plan",
        "phase": "phase1",
        "execution_enabled": False,
        "external_api_calls": 0,
        "summary": {"planned_request_count": len(requests)},
        "endpoints": [str(item) for item in openapi.get("endpoints", [])],
        "report_presets": [str(item) for item in openapi.get("report_presets", [])],
        "requests": requests,
    }


def _should_skip_material_execution(material_fetch: dict[str, Any]) -> bool:
    source = str(material_fetch.get("source") or "openapi_http_execute")
    if source != "openapi_http_execute":
        return False
    execution = material_fetch.get("execution") if isinstance(material_fetch.get("execution"), dict) else {}
    openapi_http = material_fetch.get("openapi_http") if isinstance(material_fetch.get("openapi_http"), dict) else {}
    status_execute = str(execution.get("status") or "") == "execute"
    external_enabled = bool(execution.get("external_api_enabled", False))
    http_enabled = bool(openapi_http.get("enabled", False))
    if not status_execute and not external_enabled and not http_enabled:
        return True
    if not (status_execute and external_enabled and http_enabled):
        raise RuntimeError("openapi_http_execute requires execution.status=execute, external_api_enabled=true, and openapi_http.enabled=true together")
    return False


def _openapi_transport(
    material_fetch: dict[str, Any],
    *,
    runs_dir: str | Path,
    openapi_transport: Transport | None,
    http_opener=None,
    http_sleeper=None,
) -> Transport:
    source = str(material_fetch.get("source") or "openapi_http_execute")
    if openapi_transport is not None:
        return openapi_transport
    if source == "openapi_mock_execute":
        raise RuntimeError("openapi_mock_execute requires an explicit openapi_transport")
    if source != "openapi_http_execute":
        raise ValueError(f"unsupported material fetch source: {source}")
    openapi_http = material_fetch.get("openapi_http") if isinstance(material_fetch.get("openapi_http"), dict) else {}
    response_dir = Path(openapi_http.get("response_audit_dir") or Path(runs_dir) / "openapi_http" / "material-history-backfill")
    return build_http_transport(openapi_http, response_dir=response_dir, opener=http_opener, sleeper=http_sleeper)


def _openapi_execution_retry_options(material_fetch: dict[str, Any]) -> dict[str, Any]:
    openapi_http = material_fetch.get("openapi_http") if isinstance(material_fetch.get("openapi_http"), dict) else {}
    return {
        "retry_api_codes": list(openapi_http.get("retry_api_codes") or []),
        "max_api_retries": int(openapi_http.get("max_api_retries", openapi_http.get("max_retries") or 0) or 0),
        "retry_sleep_seconds": float(openapi_http.get("retry_sleep_seconds") or 1),
    }


def _record_sync_state(
    *,
    db_path: str | Path,
    dates: list[str],
    product: str,
    platform: str,
    active_by_date: dict[str, list[dict[str, Any]]],
    material_row_counts_by_date: dict[str, int],
    artifact_path: str,
) -> None:
    updated_at = _utc_now()
    with sqlite3.connect(db_path) as conn:
        for target_date in dates:
            conn.execute(
                """
                INSERT INTO material_sync_state (
                  workflow,
                  sync_date,
                  status,
                  product,
                  platform,
                  account_count,
                  material_row_count,
                  artifact_path,
                  error_message,
                  updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(workflow, sync_date, product, platform)
                DO UPDATE SET
                  status=excluded.status,
                  account_count=excluded.account_count,
                  material_row_count=excluded.material_row_count,
                  artifact_path=excluded.artifact_path,
                  error_message=excluded.error_message,
                  updated_at=excluded.updated_at
                """,
                (
                    "material_history_backfill",
                    target_date,
                    "completed",
                    product,
                    platform,
                    len(active_by_date.get(target_date) or []),
                    int(material_row_counts_by_date.get(target_date) or 0),
                    artifact_path,
                    "",
                    updated_at,
                ),
            )


def _material_daily_row_counts_by_date(
    *,
    db_path: str | Path,
    dates: list[str],
) -> dict[str, int]:
    if not dates:
        return {}
    placeholders = ",".join("?" for _ in dates)
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            f"""
            SELECT metric_date, COUNT(*)
            FROM material_daily_metrics
            WHERE metric_date IN ({placeholders})
            GROUP BY metric_date
            """,
            tuple(dates),
        ).fetchall()
    counts = {str(metric_date): int(count) for metric_date, count in rows}
    return {target_date: counts.get(target_date, 0) for target_date in dates}


def run_material_history_backfill_request(
    request: dict[str, Any],
    *,
    db_path: str | Path,
    runs_dir: str | Path,
    workbench_opener: WorkbenchOpener | None = None,
    workbench_sleeper: WorkbenchSleeper | None = None,
    openapi_transport: Transport | None = None,
    http_opener=None,
    http_sleeper=None,
) -> dict[str, Any]:
    cfg = _config(request)
    material_fetch = _material_fetch_config(cfg)
    if _should_skip_material_execution(material_fetch):
        preflight = build_material_history_backfill_preflight(request, db_path=db_path, runs_dir=runs_dir)
        payload = {
            "ok": True,
            "workflow": "material_history_backfill",
            "phase": "phase1",
            "skipped": True,
            "skip_reason": "material_fetch execution is disabled; wrote preflight only.",
            "execution_enabled": False,
            "external_api_calls": 0,
            "summary": preflight["summary"],
            "preflight": preflight,
        }
        artifact = write_run_artifact(runs_dir, "material_history_backfill", payload)
        return {**payload, "artifact_path": str(artifact)}

    date_range = _date_range_config(cfg)
    dates = _date_range(date_range["start"], date_range["end"])
    platforms = _platforms(cfg)
    accounts = _accounts(cfg, db_path=db_path)
    discovery = _discovery_config(cfg)
    active_by_date, discovery_result = _discover_active_accounts_by_date(
        accounts=accounts,
        dates=dates,
        discovery=discovery,
        workbench_opener=workbench_opener,
        workbench_sleeper=workbench_sleeper,
    )
    request_plan = _detail_plan_for_active_accounts(
        active_by_date=active_by_date,
        material_fetch=material_fetch,
        platforms=platforms,
    )
    transport = _openapi_transport(
        material_fetch,
        runs_dir=runs_dir,
        openapi_transport=openapi_transport,
        http_opener=http_opener,
        http_sleeper=http_sleeper,
    )
    execution = execute_openapi_readonly_plan(
        request_plan,
        transport=transport,
        **_openapi_execution_retry_options(material_fetch),
    )
    import_result = import_material_daily_execution(
        execution,
        db_path=db_path,
        source=str(material_fetch.get("source") or "openapi_http_execute"),
    )
    material_row_counts_by_date = _material_daily_row_counts_by_date(db_path=db_path, dates=dates)
    material_rows_unique_in_db = sum(material_row_counts_by_date.values())
    material_external_calls = 0
    if str(material_fetch.get("source") or "") == "openapi_http_execute":
        material_external_calls = int(execution["summary"]["transport_calls"])
    active_account_ids = sorted(
        {
            str(account["advertiser_id"])
            for active_accounts in active_by_date.values()
            for account in active_accounts
        }
    )
    payload = {
        "ok": True,
        "workflow": "material_history_backfill",
        "phase": "phase1",
        "skipped": False,
        "execution_enabled": False,
        "external_api_calls": int(discovery_result["readonly_request_calls"]) + material_external_calls,
        "summary": {
            "product": str(cfg.get("product") or ""),
            "platforms": platforms,
            "date_count": len(dates),
            "candidate_account_count": len(accounts),
            "active_account_count": len(active_account_ids),
            "material_fetch_planned_request_count": int(request_plan["summary"]["planned_request_count"]),
            "material_fetch_transport_calls": int(execution["summary"]["transport_calls"]),
            "material_rows_seen": int(import_result["rows_seen"]),
            "material_rows_imported": int(import_result["rows_imported"]),
            "material_rows_unique_in_db": int(material_rows_unique_in_db),
            "material_rows_skipped_zero_cost": int(import_result["rows_skipped_zero_cost"]),
            "material_rows_skipped_invalid": int(import_result["rows_skipped_invalid"]),
        },
        "date_range": {"start": date_range["start"], "end": date_range["end"], "dates": dates},
        "active_account_ids": active_account_ids,
        "discovery_result": discovery_result,
        "request_plan": request_plan,
        "execution_result": execution,
        "import_result": import_result,
        "guardrails": [
            "Execution path is read-only: workbench account discovery plus OpenAPI report reads.",
            "Only accounts with stat_cost greater than min_spend are used for material detail fetch.",
            "Only material rows with stat_cost greater than 0 are stored.",
        ],
    }
    artifact = write_run_artifact(runs_dir, "material_history_backfill", payload)
    first_platform = platforms[0] if platforms else ""
    _record_sync_state(
        db_path=db_path,
        dates=dates,
        product=str(cfg.get("product") or ""),
        platform=first_platform,
        active_by_date=active_by_date,
        material_row_counts_by_date=material_row_counts_by_date,
        artifact_path=str(artifact),
    )
    return {**payload, "artifact_path": str(artifact)}
