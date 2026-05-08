from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from roibang_v2.config import load_json
from roibang_v2.fetch.report_snapshot import run_report_fetch_request
from roibang_v2.runs import write_run_artifact


def _runner_config(request: dict[str, Any]) -> dict[str, Any]:
    value = request.get("backfill_runner")
    return dict(value) if isinstance(value, dict) else dict(request)


def _selected_batches(plan: dict[str, Any], batch_ids: list[str]) -> list[dict[str, Any]]:
    batches = [batch for batch in plan.get("batches", []) if isinstance(batch, dict)]
    if not batch_ids:
        return batches
    wanted = set(batch_ids)
    selected = [batch for batch in batches if str(batch.get("batch_id") or "") in wanted]
    missing = sorted(wanted - {str(batch.get("batch_id") or "") for batch in selected})
    if missing:
        raise ValueError(f"batch not found: {', '.join(missing)}")
    return selected


def _is_execute(cfg: dict[str, Any]) -> bool:
    execution = cfg.get("execution") if isinstance(cfg.get("execution"), dict) else {}
    return str(execution.get("status") or "") == "execute" and bool(execution.get("external_api_enabled", False))


def _activate_batch_request(batch: dict[str, Any], runner_cfg: dict[str, Any]) -> dict[str, Any]:
    source = batch.get("report_fetch_request")
    if not isinstance(source, dict):
        raise ValueError(f"batch {batch.get('batch_id')} missing report_fetch_request")
    request = deepcopy(source)
    report_fetch = request.get("report_fetch") if isinstance(request.get("report_fetch"), dict) else request
    execution = report_fetch.setdefault("execution", {})
    execution["status"] = "execute"
    execution["external_api_enabled"] = True
    runner_http = runner_cfg.get("openapi_http") if isinstance(runner_cfg.get("openapi_http"), dict) else {}
    http = report_fetch.setdefault("openapi_http", {})
    http.update(runner_http)
    http["enabled"] = True
    return request


def _planned_batch_result(batch: dict[str, Any]) -> dict[str, Any]:
    request = batch.get("report_fetch_request") if isinstance(batch.get("report_fetch_request"), dict) else {}
    report_fetch = request.get("report_fetch") if isinstance(request.get("report_fetch"), dict) else request
    account_ids = report_fetch.get("account_ids") if isinstance(report_fetch.get("account_ids"), list) else []
    return {
        "batch_id": str(batch.get("batch_id") or ""),
        "status": "planned_only",
        "planned_request_count": int(batch.get("planned_request_count") or 0),
        "account_count": len(account_ids),
        "external_api_calls": 0,
    }


def run_backfill_batches_request(
    request: dict[str, Any],
    *,
    db_path: str | Path,
    runs_dir: str | Path,
    http_opener=None,
    http_sleeper=None,
) -> dict[str, Any]:
    cfg = _runner_config(request)
    plan = load_json(cfg["plan_file"])
    if str(plan.get("workflow") or "") != "report_backfill_batch_plan":
        raise ValueError("backfill runner requires report_backfill_batch_plan")
    batch_ids = [str(item) for item in cfg.get("batch_ids", [])] if isinstance(cfg.get("batch_ids"), list) else []
    batches = _selected_batches(plan, batch_ids)
    execute = _is_execute(cfg)
    runner_http = cfg.get("openapi_http") if isinstance(cfg.get("openapi_http"), dict) else {}
    if execute and not bool(runner_http.get("enabled", False)):
        raise RuntimeError("backfill runner execute requires openapi_http.enabled=true")

    results: list[dict[str, Any]] = []
    external_api_calls = 0
    failed = 0
    stop_on_error = bool(cfg.get("stop_on_error", True))
    for batch in batches:
        if not execute:
            results.append(_planned_batch_result(batch))
            continue
        batch_id = str(batch.get("batch_id") or "")
        try:
            fetch_result = run_report_fetch_request(
                _activate_batch_request(batch, cfg),
                db_path=db_path,
                runs_dir=runs_dir,
                http_opener=http_opener,
                http_sleeper=http_sleeper,
            )
            calls = int(fetch_result.get("external_api_calls") or 0)
            external_api_calls += calls
            results.append(
                {
                    "batch_id": batch_id,
                    "status": "completed",
                    "planned_request_count": int(batch.get("planned_request_count") or 0),
                    "external_api_calls": calls,
                    "artifact_path": fetch_result["artifact_path"],
                    "snapshots_written": fetch_result["summary"]["snapshots_written"],
                }
            )
        except Exception as exc:
            failed += 1
            results.append(
                {
                    "batch_id": batch_id,
                    "status": "failed",
                    "planned_request_count": int(batch.get("planned_request_count") or 0),
                    "external_api_calls": 0,
                    "error": str(exc),
                }
            )
            if stop_on_error:
                break

    payload = {
        "ok": failed == 0,
        "workflow": "backfill_batch_runner",
        "phase": "phase1",
        "execution_enabled": False,
        "external_api_calls": external_api_calls,
        "summary": {
            "selected_batch_count": len(batches),
            "executed_batch_count": sum(1 for item in results if item["status"] == "completed"),
            "planned_request_count": sum(int(batch.get("planned_request_count") or 0) for batch in batches),
            "external_api_calls": external_api_calls,
            "failed_batch_count": failed,
        },
        "batches": results,
    }
    artifact = write_run_artifact(runs_dir, "backfill_batch_runner", payload)
    return {**payload, "artifact_path": str(artifact)}
