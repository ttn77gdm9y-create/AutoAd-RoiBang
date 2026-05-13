from __future__ import annotations

import sqlite3
import re
from pathlib import Path
from typing import Any, Callable

from roibang_v2.runs import write_run_artifact

Transport = Callable[[dict[str, Any]], dict[str, Any]]
ACTIVATE_UNIT_ENDPOINT = "/open_api/v3.0/promotion/status/update/"
BATCH_SIZE = 10
ADVERTISER_ID_PATTERN = re.compile(r"^(\d{10,})-")


def _cfg(request: dict[str, Any]) -> dict[str, Any]:
    value = request.get("create_live_activate_once")
    return dict(value) if isinstance(value, dict) else dict(request)


def _provider_id_value(value: str) -> int | str:
    return int(value) if str(value).isdigit() else str(value)


def _advertiser_id_from_row(*, advertiser_id: str, local_key: str, parent_local_key: str) -> str:
    if str(advertiser_id).strip():
        return str(advertiser_id).strip()
    for value in (local_key, parent_local_key):
        match = ADVERTISER_ID_PATTERN.match(str(value or ""))
        if match:
            return match.group(1)
    return ""


def _promotion_rows(*, db_path: str | Path, plan_id: str) -> list[dict[str, str]]:
    if not str(plan_id or "").strip():
        return []
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT advertiser_id, local_key, provider_id, parent_local_key
            FROM create_provider_id_ledger
            WHERE plan_id = ?
              AND entity_type = 'promotion'
              AND status = 'active'
              AND provider_id NOT LIKE 'mock_%'
              AND source_workflow != 'create_mock_execute'
            ORDER BY advertiser_id, provider_id
            """,
            (str(plan_id),),
        ).fetchall()
    normalized_rows: list[dict[str, str]] = []
    for advertiser_id, local_key, provider_id, parent_local_key in rows:
        normalized_advertiser_id = _advertiser_id_from_row(
            advertiser_id=str(advertiser_id),
            local_key=str(local_key),
            parent_local_key=str(parent_local_key),
        )
        if not normalized_advertiser_id or not str(provider_id):
            continue
        normalized_rows.append(
            {
                "advertiser_id": normalized_advertiser_id,
                "local_key": str(local_key),
                "provider_id": str(provider_id),
            }
        )
    return normalized_rows


def _activation_batches(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    batches: list[dict[str, Any]] = []
    current_advertiser_id = ""
    current: list[dict[str, str]] = []

    def flush() -> None:
        nonlocal current, current_advertiser_id
        if not current:
            return
        batches.append(
            {
                "advertiser_id": current_advertiser_id,
                "promotion_ids": [row["provider_id"] for row in current],
                "local_keys": [row["local_key"] for row in current],
            }
        )
        current = []
        current_advertiser_id = ""

    for row in rows:
        advertiser_id = row["advertiser_id"]
        if not current or current_advertiser_id != advertiser_id or len(current) >= BATCH_SIZE:
            flush()
            current_advertiser_id = advertiser_id
        current.append(row)
    flush()
    return batches


def _activation_payload(batch: dict[str, Any]) -> dict[str, Any]:
    return {
        "advertiser_id": _provider_id_value(str(batch.get("advertiser_id") or "")),
        "data": [
            {"promotion_id": _provider_id_value(str(promotion_id)), "opt_status": "ENABLE"}
            for promotion_id in batch.get("promotion_ids", [])
        ],
    }


def _runtime_blocking_reasons(runtime: dict[str, Any], transport: Transport | None) -> list[str]:
    reasons: list[str] = []
    if not bool(runtime.get("execution_enabled", False)):
        reasons.append("runtime.execution_enabled is false")
    if not bool(runtime.get("external_api_enabled", False)):
        reasons.append("runtime.external_api_enabled is false")
    if transport is None and not reasons:
        reasons.append("activate_unit transport is not constructed")
    return reasons


def _summary(
    *,
    batches: list[dict[str, Any]],
    activated_unit_count: int = 0,
    failed_reasons: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    failed = failed_reasons or []
    planned_unit_count = sum(len(batch.get("promotion_ids", [])) for batch in batches)
    return {
        "planned_unit_count": planned_unit_count,
        "planned_batch_count": len(batches),
        "activated_unit_count": activated_unit_count,
        "failed_unit_count": sum(int(row.get("failed_unit_count") or 0) for row in failed),
        "manual_review_required": bool(failed),
        "failure_reasons": failed,
    }


def _blocked_result(*, plan_id: str, blocking_reasons: list[str], batches: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "ok": False,
        "workflow": "create_live_activate_once",
        "phase": "phase2_preparation",
        "execution_enabled": False,
        "external_api_calls": 0,
        "status": "blocked",
        "plan_id": plan_id,
        "blocking_reasons": blocking_reasons,
        "summary": _summary(batches=batches),
        "activation_batches": batches,
        "actions": [],
    }


def build_create_live_activate_once(
    *,
    plan_id: str,
    runtime: dict[str, Any],
    db_path: str | Path,
    execute: bool,
    transport: Transport | None = None,
) -> dict[str, Any]:
    rows = _promotion_rows(db_path=db_path, plan_id=plan_id)
    batches = _activation_batches(rows)
    if not execute:
        return {
            "ok": True,
            "workflow": "create_live_activate_once",
            "phase": "phase2_preparation",
            "execution_enabled": False,
            "external_api_calls": 0,
            "status": "dry_run_completed",
            "plan_id": plan_id,
            "blocking_reasons": [],
            "summary": _summary(batches=batches),
            "activation_batches": batches,
            "actions": [],
        }

    blocking_reasons = _runtime_blocking_reasons(runtime, transport)
    if blocking_reasons:
        return _blocked_result(plan_id=plan_id, blocking_reasons=blocking_reasons, batches=batches)

    external_api_calls = 0
    activated_unit_count = 0
    failure_reasons: list[dict[str, Any]] = []
    for batch in batches:
        payload = _activation_payload(batch)
        response = transport(
            {
                "operation": "activate_unit",
                "endpoint": ACTIVATE_UNIT_ENDPOINT,
                "payload": payload,
                "transport_mode": "create_http",
            }
        )
        external_api_calls += 1
        code = int(response.get("code") or 0)
        data = response.get("data") if isinstance(response.get("data"), dict) else {}
        errors = [row for row in data.get("errors", []) if isinstance(row, dict)] if isinstance(data, dict) else []
        if code != 0:
            failure_reasons.append(
                {
                    "advertiser_id": str(batch.get("advertiser_id") or ""),
                    "message": str(response.get("message") or response.get("msg") or "开启失败"),
                    "code": code,
                    "failed_unit_count": len(batch.get("promotion_ids", [])),
                }
            )
            continue
        if errors:
            failure_reasons.extend(
                {
                    "advertiser_id": str(batch.get("advertiser_id") or ""),
                    "promotion_id": str(error.get("promotion_id") or ""),
                    "message": str(error.get("error_message") or "开启失败"),
                    "code": code,
                    "failed_unit_count": 1,
                }
                for error in errors
            )
            activated_unit_count += max(len(batch.get("promotion_ids", [])) - len(errors), 0)
            continue
        activated_ids = data.get("promotion_ids") if isinstance(data.get("promotion_ids"), list) else []
        activated_unit_count += len(activated_ids) if activated_ids else len(batch.get("promotion_ids", []))

    summary = _summary(
        batches=batches,
        activated_unit_count=activated_unit_count,
        failed_reasons=failure_reasons,
    )
    return {
        "ok": not bool(failure_reasons),
        "workflow": "create_live_activate_once",
        "phase": "phase2_preparation",
        "execution_enabled": external_api_calls > 0,
        "external_api_calls": external_api_calls,
        "status": "activate_completed" if not failure_reasons else "activate_partial_failed",
        "plan_id": plan_id,
        "blocking_reasons": [],
        "summary": summary,
        "activation_batches": batches,
        "actions": [],
    }


def run_create_live_activate_once_request(
    request: dict[str, Any],
    *,
    runs_dir: str | Path,
    db_path: str | Path,
    transport: Transport | None = None,
) -> dict[str, Any]:
    cfg = _cfg(request)
    plan_id = str(cfg.get("plan_id") or "").strip()
    if not plan_id:
        raise ValueError("create live activate once requires plan_id")
    runtime = cfg.get("runtime") if isinstance(cfg.get("runtime"), dict) else {}
    payload = build_create_live_activate_once(
        plan_id=plan_id,
        runtime=runtime,
        db_path=db_path,
        execute=bool(cfg.get("execute", False)),
        transport=transport,
    )
    artifact_path = write_run_artifact(runs_dir, "create_live_activate_once", payload)
    return {**payload, "artifact_path": str(artifact_path)}
