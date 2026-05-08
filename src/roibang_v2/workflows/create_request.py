from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from roibang_v2.runs import write_run_artifact


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _request_config(request: dict[str, Any]) -> dict[str, Any]:
    value = request.get("create_request")
    return dict(value) if isinstance(value, dict) else dict(request)


def _required_text(row: dict[str, Any], key: str) -> str:
    value = str(row.get(key) or "").strip()
    if not value:
        raise ValueError(f"create request requires {key}")
    return value


def _int_value(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _target_accounts(request: dict[str, Any]) -> list[dict[str, Any]]:
    rows = request.get("target_accounts")
    if not isinstance(rows, list) or not rows:
        raise ValueError("create request requires target_accounts")
    accounts: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        advertiser_id = _required_text(row, "advertiser_id")
        accounts.append(
            {
                **row,
                "advertiser_id": advertiser_id,
                "project_count": max(_int_value(row.get("project_count"), 1), 0),
                "units_per_project": max(_int_value(row.get("units_per_project"), 1), 0),
            }
        )
    if not accounts:
        raise ValueError("create request requires at least one target account")
    return accounts


def _summary(request: dict[str, Any]) -> dict[str, Any]:
    accounts = _target_accounts(request)
    project_count = sum(int(row["project_count"]) for row in accounts)
    unit_count = sum(int(row["project_count"]) * int(row["units_per_project"]) for row in accounts)
    return {
        "request_id": _required_text(request, "request_id"),
        "target_date": _required_text(request, "target_date"),
        "target_account_count": len(accounts),
        "planned_project_count": project_count,
        "planned_unit_count": unit_count,
    }


def _validate_request(request: dict[str, Any]) -> None:
    for key in (
        "request_id",
        "target_date",
        "product",
        "platform",
        "project_type",
        "source_advertiser_id",
        "pool_key",
    ):
        _required_text(request, key)
    constraints = request.get("constraints") if isinstance(request.get("constraints"), dict) else {}
    if str(constraints.get("phase") or request.get("phase") or "phase1") != "phase1":
        raise ValueError("create request phase must be phase1")
    if bool(constraints.get("execution_enabled", request.get("execution_enabled", False))):
        raise ValueError("create request execution_enabled must be false")
    if bool(constraints.get("allow_real_create", False)):
        raise ValueError("create request allow_real_create must be false in phase1")
    _target_accounts(request)


def _store_request(*, db_path: str | Path, request: dict[str, Any]) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO create_requests (
              request_id, phase, execution_enabled, request_json, created_at
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(request_id) DO UPDATE SET
              phase = excluded.phase,
              execution_enabled = excluded.execution_enabled,
              request_json = excluded.request_json,
              created_at = excluded.created_at
            """,
            (
                request["request_id"],
                "phase1",
                0,
                json.dumps(request, ensure_ascii=False, sort_keys=True),
                _now_iso(),
            ),
        )


def run_create_request(
    request: dict[str, Any],
    *,
    db_path: str | Path,
    runs_dir: str | Path,
) -> dict[str, Any]:
    cfg = _request_config(request)
    _validate_request(cfg)
    _store_request(db_path=db_path, request=cfg)
    payload = {
        "ok": True,
        "workflow": "create_request",
        "phase": "phase1",
        "execution_enabled": False,
        "external_api_calls": 0,
        "summary": _summary(cfg),
        "request": cfg,
        "actions": [],
        "live_api_payloads": [],
    }
    artifact = write_run_artifact(runs_dir, "create_request", payload)
    return {**payload, "artifact_path": str(artifact)}
