from __future__ import annotations

import csv
import sqlite3
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from roibang_v2.runs import write_run_artifact


REQUIRED_COLUMNS = {"account_name", "advertiser_id", "product", "platform"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _parse_spend(value: str | None) -> float:
    raw = str(value or "0").strip().replace(",", "")
    if not raw:
        return 0.0
    return float(raw)


def _read_csv_rows(path: str | Path) -> list[dict[str, str]]:
    source = Path(path)
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = set(reader.fieldnames or [])
        missing = sorted(REQUIRED_COLUMNS - fieldnames)
        if missing:
            raise ValueError(f"accounts csv missing required columns: {', '.join(missing)}")
        return [dict(row) for row in reader]


def import_accounts_csv(path: str | Path, *, db_path: str | Path) -> dict[str, Any]:
    rows = _read_csv_rows(path)
    synced_at = _now_iso()
    normalized: list[dict[str, Any]] = []
    for row in rows:
        advertiser_id = str(row.get("advertiser_id") or "").strip()
        account_name = str(row.get("account_name") or "").strip()
        product = str(row.get("product") or "").strip()
        platform = str(row.get("platform") or "").strip()
        if not advertiser_id or not account_name or not product or not platform:
            continue
        normalized.append(
            {
                "advertiser_id": advertiser_id,
                "account_name": account_name,
                "product": product,
                "platform": platform,
                "historical_spend": _parse_spend(row.get("消耗") or row.get("spend") or row.get("historical_spend")),
            }
        )

    with sqlite3.connect(db_path) as conn:
        for item in normalized:
            conn.execute(
                """
                INSERT INTO account_pool (
                  advertiser_id, account_name, product, platform, historical_spend, source, synced_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(advertiser_id) DO UPDATE SET
                  account_name = excluded.account_name,
                  product = excluded.product,
                  platform = excluded.platform,
                  historical_spend = excluded.historical_spend,
                  source = excluded.source,
                  synced_at = excluded.synced_at
                """,
                (
                    item["advertiser_id"],
                    item["account_name"],
                    item["product"],
                    item["platform"],
                    item["historical_spend"],
                    str(path),
                    synced_at,
                ),
            )

    return {
        "ok": True,
        "workflow": "account_pool_import",
        "rows_seen": len(rows),
        "accounts_imported": len(normalized),
        "products": dict(sorted(Counter(item["product"] for item in normalized).items())),
        "platforms": dict(sorted(Counter(item["platform"] for item in normalized).items())),
        "external_api_calls": 0,
        "execution_enabled": False,
    }


def select_accounts(
    *,
    db_path: str | Path,
    product: str,
    platforms: list[str] | None = None,
) -> list[dict[str, Any]]:
    query = """
        SELECT advertiser_id, account_name, product, platform, historical_spend
        FROM account_pool
        WHERE product = ?
    """
    params: list[Any] = [product]
    if platforms:
        placeholders = ",".join("?" for _ in platforms)
        query += f" AND platform IN ({placeholders})"
        params.extend(platforms)
    query += " ORDER BY platform ASC, historical_spend DESC, advertiser_id ASC"
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(query, params).fetchall()
    return [
        {
            "advertiser_id": str(row[0]),
            "account_name": str(row[1]),
            "product": str(row[2]),
            "platform": str(row[3]),
            "historical_spend": float(row[4] or 0),
        }
        for row in rows
    ]


def _date_range(start_date: str, end_date: str) -> list[str]:
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    if end < start:
        raise ValueError("end_date must be greater than or equal to start_date")
    days: list[str] = []
    current = start
    while current <= end:
        days.append(current.isoformat())
        current += timedelta(days=1)
    return days


def build_backfill_plan(
    *,
    db_path: str | Path,
    product: str,
    platforms: list[str],
    start_date: str,
    end_date: str,
    runs_dir: str | Path,
) -> dict[str, Any]:
    accounts = select_accounts(db_path=db_path, product=product, platforms=platforms)
    days = _date_range(start_date, end_date)
    tasks: list[dict[str, Any]] = []
    for day in days:
        for account in accounts:
            tasks.append(
                {
                    "date": day,
                    "advertiser_id": account["advertiser_id"],
                    "account_name": account["account_name"],
                    "product": account["product"],
                    "platform": account["platform"],
                    "status": "planned_only",
                }
            )
    payload = {
        "ok": True,
        "workflow": "report_backfill_plan",
        "phase": "phase1",
        "execution_enabled": False,
        "external_api_calls": 0,
        "summary": {
            "product": product,
            "platforms": platforms,
            "account_count": len(accounts),
            "date_count": len(days),
            "planned_fetch_tasks": len(tasks),
        },
        "accounts": accounts,
        "date_range": {"start": start_date, "end": end_date, "dates": days},
        "tasks": tasks,
    }
    artifact = write_run_artifact(runs_dir, "report_backfill_plan", payload)
    return {**payload, "artifact_path": str(artifact)}


def _chunks(items: list[Any], size: int) -> list[list[Any]]:
    if size <= 0:
        raise ValueError("chunk size must be greater than 0")
    return [items[index : index + size] for index in range(0, len(items), size)]


def _requests_per_account_date(endpoints: list[str], report_presets: list[str]) -> int:
    total = 0
    for endpoint in endpoints:
        total += len(report_presets) if endpoint == "report_custom" else 1
    return total


def _batch_request(
    *,
    batch_id: str,
    product: str,
    platforms: list[str],
    accounts: list[dict[str, Any]],
    dates: list[str],
    endpoints: list[str],
    report_presets: list[str],
    page_size: int,
) -> dict[str, Any]:
    return {
        "report_fetch": {
            "mode": "backfill",
            "source": "openapi_http_execute",
            "batch_id": batch_id,
            "product": product,
            "platforms": platforms,
            "account_ids": [account["advertiser_id"] for account in accounts],
            "date_range": {"start": dates[0], "end": dates[-1]},
            "openapi": {
                "endpoints": endpoints,
                "report_presets": report_presets,
                "page_size": page_size,
            },
            "openapi_http": {
                "enabled": False,
                "token_env": "OCEANENGINE_ACCESS_TOKEN",
                "response_audit_dir": f"data/runs/openapi_http/{batch_id}",
            },
            "output": {
                "snapshot_dir": f"data/snapshots/report/backfill/{batch_id}",
            },
            "execution": {
                "status": "planned_only",
                "external_api_enabled": False,
            },
        }
    }


def build_backfill_batch_plan(
    *,
    db_path: str | Path,
    product: str,
    platforms: list[str],
    start_date: str,
    end_date: str,
    endpoints: list[str],
    report_presets: list[str],
    runs_dir: str | Path,
    max_accounts_per_batch: int = 20,
    max_dates_per_batch: int = 3,
    max_requests_per_batch: int | None = None,
    page_size: int = 100,
) -> dict[str, Any]:
    accounts = select_accounts(db_path=db_path, product=product, platforms=platforms)
    days = _date_range(start_date, end_date)
    requests_per_task = _requests_per_account_date(endpoints, report_presets)
    if requests_per_task <= 0:
        raise ValueError("at least one planned endpoint is required")
    effective_max_dates = max_dates_per_batch
    if max_requests_per_batch:
        allowed_date_count = max_requests_per_batch // max(1, max_accounts_per_batch * requests_per_task)
        effective_max_dates = max(1, min(max_dates_per_batch, allowed_date_count))

    batches: list[dict[str, Any]] = []
    batch_index = 1
    for date_group in _chunks(days, effective_max_dates):
        for account_group in _chunks(accounts, max_accounts_per_batch):
            planned_request_count = len(date_group) * len(account_group) * requests_per_task
            batch_id = f"batch_{batch_index:04d}"
            batches.append(
                {
                    "batch_id": batch_id,
                    "status": "planned_only",
                    "account_count": len(account_group),
                    "date_count": len(date_group),
                    "account_date_tasks": len(account_group) * len(date_group),
                    "planned_request_count": planned_request_count,
                    "accounts": account_group,
                    "date_range": {"start": date_group[0], "end": date_group[-1], "dates": date_group},
                    "report_fetch_request": _batch_request(
                        batch_id=batch_id,
                        product=product,
                        platforms=platforms,
                        accounts=account_group,
                        dates=date_group,
                        endpoints=endpoints,
                        report_presets=report_presets,
                        page_size=page_size,
                    ),
                }
            )
            batch_index += 1

    payload = {
        "ok": True,
        "workflow": "report_backfill_batch_plan",
        "phase": "phase1",
        "execution_enabled": False,
        "external_api_calls": 0,
        "summary": {
            "product": product,
            "platforms": platforms,
            "account_count": len(accounts),
            "date_count": len(days),
            "batch_count": len(batches),
            "planned_account_date_tasks": len(accounts) * len(days),
            "planned_request_count": len(accounts) * len(days) * requests_per_task,
            "requests_per_account_date": requests_per_task,
        },
        "limits": {
            "max_accounts_per_batch": max_accounts_per_batch,
            "max_dates_per_batch": max_dates_per_batch,
            "effective_max_dates_per_batch": effective_max_dates,
            "max_requests_per_batch": max_requests_per_batch,
            "page_size": page_size,
        },
        "endpoints": endpoints,
        "report_presets": report_presets,
        "batches": batches,
    }
    artifact = write_run_artifact(runs_dir, "report_backfill_batch_plan", payload)
    return {**payload, "artifact_path": str(artifact)}
