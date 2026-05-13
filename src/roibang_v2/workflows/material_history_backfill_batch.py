from __future__ import annotations

import sqlite3
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from roibang_v2.fetch.openapi_executor import Transport
from roibang_v2.fetch.workbench_account_discovery import Sleeper as WorkbenchSleeper
from roibang_v2.fetch.workbench_account_discovery import WorkbenchOpener
from roibang_v2.runs import write_run_artifact
from roibang_v2.workflows.material_history_backfill import _accounts
from roibang_v2.workflows.material_history_backfill import _date_range
from roibang_v2.workflows.material_history_backfill import _date_range_config
from roibang_v2.workflows.material_history_backfill import _detail_plan
from roibang_v2.workflows.material_history_backfill import _discovery_config
from roibang_v2.workflows.material_history_backfill import _discovery_plan
from roibang_v2.workflows.material_history_backfill import _material_fetch_config
from roibang_v2.workflows.material_history_backfill import _platforms
from roibang_v2.workflows.material_history_backfill import run_material_history_backfill_request


def _batch_config(request: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    wrapper = request.get("material_history_backfill_batch")
    if isinstance(wrapper, dict):
        material = wrapper.get("material_history_backfill")
        if not isinstance(material, dict):
            material = request.get("material_history_backfill")
        if not isinstance(material, dict):
            raise ValueError("material_history_backfill_batch requires material_history_backfill JSON object")
        return dict(wrapper), dict(material)
    material = request.get("material_history_backfill")
    if isinstance(material, dict):
        return {"batch": {}}, dict(material)
    return {"batch": {}}, dict(request)


def _batch_options(batch_cfg: dict[str, Any]) -> dict[str, Any]:
    value = batch_cfg.get("batch") if isinstance(batch_cfg.get("batch"), dict) else {}
    size = int(value.get("size") or value.get("batch_size") or 3)
    if size < 1:
        raise ValueError("material_history_backfill_batch.batch.size must be greater than 0")
    return {
        "size": size,
        "retry_failed": bool(value.get("retry_failed", False)),
        "rerun_completed": bool(value.get("rerun_completed", False)),
        "rerun_key": str(value.get("rerun_key") or "default"),
    }


def _rerun_workflow_name(rerun_key: str) -> str:
    return f"material_history_backfill_rerun:{rerun_key}"


def _sync_state_by_date(
    *,
    db_path: str | Path,
    dates: list[str],
    product: str,
    platform: str,
    workflow: str = "material_history_backfill",
) -> dict[str, str]:
    if not dates:
        return {}
    placeholders = ",".join("?" for _ in dates)
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            f"""
            SELECT sync_date, status
            FROM material_sync_state
            WHERE workflow = ?
              AND product = ?
              AND platform = ?
              AND sync_date IN ({placeholders})
            ORDER BY sync_date
            """,
            tuple([workflow, product, platform, *dates]),
        ).fetchall()
    return {str(sync_date): str(status) for sync_date, status in rows}


def _partition_dates(
    *,
    dates: list[str],
    state_by_date: dict[str, str],
    rerun_state_by_date: dict[str, str],
    retry_failed: bool,
    rerun_completed: bool,
) -> dict[str, list[str]]:
    completed: list[str] = []
    failed_skipped: list[str] = []
    candidates: list[str] = []
    retry_dates: list[str] = []
    rerun_completed_dates: list[str] = []
    for target_date in dates:
        status = state_by_date.get(target_date)
        rerun_status = rerun_state_by_date.get(target_date)
        if rerun_status == "completed":
            completed.append(target_date)
            continue
        if status == "completed":
            if rerun_completed:
                candidates.append(target_date)
                rerun_completed_dates.append(target_date)
            else:
                completed.append(target_date)
            continue
        if status == "failed":
            if retry_failed:
                candidates.append(target_date)
                retry_dates.append(target_date)
            else:
                failed_skipped.append(target_date)
            continue
        candidates.append(target_date)
    return {
        "completed": completed,
        "failed_skipped": failed_skipped,
        "candidates": candidates,
        "retry_dates": retry_dates,
        "rerun_completed_dates": rerun_completed_dates,
    }


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _single_day_request(batch_cfg: dict[str, Any], material_cfg: dict[str, Any], target_date: str) -> dict[str, Any]:
    updated_material = deepcopy(material_cfg)
    updated_material["date_range"] = {"start": target_date, "end": target_date}
    return {
        "material_history_backfill": updated_material,
        "material_history_backfill_batch": {
            key: deepcopy(value)
            for key, value in batch_cfg.items()
            if key not in {"material_history_backfill", "batch"}
        },
    }


def _record_failure_state(
    *,
    db_path: str | Path,
    target_date: str,
    product: str,
    platform: str,
    error_message: str,
    artifact_path: str,
) -> None:
    with sqlite3.connect(db_path) as conn:
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
                "failed",
                product,
                platform,
                0,
                0,
                artifact_path,
                error_message[:1000],
                _utc_now(),
            ),
        )


def _record_rerun_completion_state(
    *,
    db_path: str | Path,
    dates: list[str],
    product: str,
    platform: str,
    rerun_key: str,
    artifact_path: str,
) -> None:
    if not dates:
        return
    updated_at = _utc_now()
    workflow = _rerun_workflow_name(rerun_key)
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
                    workflow,
                    target_date,
                    "completed",
                    product,
                    platform,
                    0,
                    0,
                    artifact_path,
                    "",
                    updated_at,
                ),
            )


def build_material_history_backfill_batch_preflight(
    request: dict[str, Any],
    *,
    db_path: str | Path,
    runs_dir: str | Path,
) -> dict[str, Any]:
    batch_cfg, material_cfg = _batch_config(request)
    options = _batch_options(batch_cfg)
    date_range = _date_range_config(material_cfg)
    dates = _date_range(date_range["start"], date_range["end"])
    platforms = _platforms(material_cfg)
    platform = platforms[0] if platforms else ""
    product = str(material_cfg.get("product") or "")
    state_by_date = _sync_state_by_date(
        db_path=db_path,
        dates=dates,
        product=product,
        platform=platform,
    )
    rerun_state_by_date = {}
    if bool(options["rerun_completed"]):
        rerun_state_by_date = _sync_state_by_date(
            db_path=db_path,
            dates=dates,
            product=product,
            platform=platform,
            workflow=_rerun_workflow_name(str(options["rerun_key"])),
        )
    partitions = _partition_dates(
        dates=dates,
        state_by_date=state_by_date,
        rerun_state_by_date=rerun_state_by_date,
        retry_failed=bool(options["retry_failed"]),
        rerun_completed=bool(options["rerun_completed"]),
    )
    selected_dates = partitions["candidates"][: int(options["size"])]
    remaining_dates = partitions["candidates"][int(options["size"]) :]
    accounts = _accounts(material_cfg, db_path=db_path)
    discovery = _discovery_config(material_cfg)
    material_fetch = _material_fetch_config(material_cfg)
    discovery_plan = _discovery_plan(
        accounts=accounts,
        dates=selected_dates,
        discovery=discovery,
        platforms=platforms,
    )
    detail_plan = _detail_plan(
        accounts=accounts,
        dates=selected_dates,
        material_fetch=material_fetch,
        platforms=platforms,
    )
    discovery_request_count = int(discovery_plan["summary"]["planned_request_count"])
    detail_request_count = int(detail_plan["summary"]["planned_request_count"])
    selected_retry_dates = [target_date for target_date in selected_dates if target_date in partitions["retry_dates"]]
    selected_rerun_completed_dates = [
        target_date for target_date in selected_dates if target_date in partitions["rerun_completed_dates"]
    ]
    payload = {
        "ok": True,
        "workflow": "material_history_backfill_batch_preflight",
        "phase": "phase1",
        "execution_enabled": False,
        "external_api_calls": 0,
        "summary": {
            "product": product,
            "platforms": platforms,
            "date_count": len(dates),
            "completed_date_count": len(partitions["completed"]),
            "failed_date_count": len(partitions["failed_skipped"]) + len(partitions["retry_dates"]),
            "pending_date_count": len(partitions["candidates"]) - len(partitions["retry_dates"]),
            "selected_date_count": len(selected_dates),
            "candidate_account_count": len(accounts),
            "estimated_discovery_request_count": discovery_request_count,
            "estimated_material_detail_initial_request_count": detail_request_count,
            "estimated_total_initial_request_count": discovery_request_count + detail_request_count,
        },
        "date_range": {"start": date_range["start"], "end": date_range["end"], "dates": dates},
        "batch": {
            "size": int(options["size"]),
            "retry_failed": bool(options["retry_failed"]),
            "rerun_completed": bool(options["rerun_completed"]),
            "rerun_key": str(options["rerun_key"]),
        },
        "selected_dates": selected_dates,
        "remaining_dates": remaining_dates,
        "retry_dates": selected_retry_dates,
        "rerun_completed_dates": selected_rerun_completed_dates,
        "skipped_dates": {
            "completed": partitions["completed"],
            "failed": partitions["failed_skipped"],
        },
        "state_by_date": state_by_date,
        "rerun_state_by_date": rerun_state_by_date,
        "accounts": accounts,
        "discovery_plan": discovery_plan,
        "detail_plan": detail_plan,
        "guardrails": [
            "Preflight only; no external API calls are made.",
            "Completed material_history_backfill dates are skipped.",
            "Completed dates are rerun only when batch.rerun_completed is true.",
            "Failed dates are skipped unless batch.retry_failed is true.",
            "Selected dates are intended for small readonly material_history_backfill runs.",
        ],
    }
    artifact = write_run_artifact(runs_dir, "material_history_backfill_batch_preflight", payload)
    return {**payload, "artifact_path": str(artifact)}


def run_material_history_backfill_batch_request(
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
    batch_cfg, material_cfg = _batch_config(request)
    options = _batch_options(batch_cfg)
    preflight = build_material_history_backfill_batch_preflight(request, db_path=db_path, runs_dir=runs_dir)
    selected_dates = list(preflight["selected_dates"])
    platforms = _platforms(material_cfg)
    platform = platforms[0] if platforms else ""
    product = str(material_cfg.get("product") or "")
    executions: list[dict[str, Any]] = []
    external_api_calls = 0
    completed_dates: list[str] = []
    failed_dates: list[str] = []
    payload_stub = {
        "ok": True,
        "workflow": "material_history_backfill_batch",
        "phase": "phase1",
        "execution_enabled": False,
        "external_api_calls": 0,
        "selected_dates": selected_dates,
    }
    artifact = write_run_artifact(runs_dir, "material_history_backfill_batch", payload_stub)
    for target_date in selected_dates:
        try:
            result = run_material_history_backfill_request(
                _single_day_request(batch_cfg, material_cfg, target_date),
                db_path=db_path,
                runs_dir=runs_dir,
                workbench_opener=workbench_opener,
                workbench_sleeper=workbench_sleeper,
                openapi_transport=openapi_transport,
                http_opener=http_opener,
                http_sleeper=http_sleeper,
            )
            external_api_calls += int(result.get("external_api_calls") or 0)
            completed_dates.append(target_date)
            executions.append(
                {
                    "date": target_date,
                    "ok": True,
                    "artifact_path": str(result.get("artifact_path") or ""),
                    "summary": dict(result.get("summary") or {}),
                }
            )
        except Exception as exc:
            message = str(exc)
            failed_dates.append(target_date)
            _record_failure_state(
                db_path=db_path,
                target_date=target_date,
                product=product,
                platform=platform,
                error_message=message,
                artifact_path=str(artifact),
            )
            executions.append(
                {
                    "date": target_date,
                    "ok": False,
                    "error_message": message,
                }
            )
    ok = not failed_dates
    payload = {
        "ok": ok,
        "workflow": "material_history_backfill_batch",
        "phase": "phase1",
        "execution_enabled": False,
        "external_api_calls": external_api_calls,
        "summary": {
            "product": product,
            "platforms": platforms,
            "selected_date_count": len(selected_dates),
            "completed_date_count": len(completed_dates),
            "failed_date_count": len(failed_dates),
            "remaining_date_count": len(preflight.get("remaining_dates") or []),
        },
        "selected_dates": selected_dates,
        "completed_dates": completed_dates,
        "failed_dates": failed_dates,
        "remaining_dates": preflight.get("remaining_dates") or [],
        "preflight": preflight,
        "executions": executions,
        "guardrails": [
            "Batch execution only calls readonly material_history_backfill per selected date.",
            "Failed dates are recorded in material_sync_state with status=failed.",
            "No create, pause, delete, budget, schedule, or material push actions are allowed.",
        ],
    }
    artifact = write_run_artifact(runs_dir, "material_history_backfill_batch", payload)
    if bool(options["rerun_completed"]):
        _record_rerun_completion_state(
            db_path=db_path,
            dates=completed_dates,
            product=product,
            platform=platform,
            rerun_key=str(options["rerun_key"]),
            artifact_path=str(artifact),
        )
    return {**payload, "artifact_path": str(artifact)}
